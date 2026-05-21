"""Variance instrumentation: outlier slate + persona-expansion temperatures.

Implements D5 mechanisms 3 and 4 of corpus-construction-plan.md:
  - 7% of jurors per stage flagged as outliers, allocated across coarse
    party x age cells (16 cells), each carrying a *concrete non-modal opinion
    prior* drawn from the actual GSS/Pew non-modal distribution for the cell
  - persona-expansion temperatures distributed 30/50/20 across T=0.3/0.7/1.0

The outlier mechanism does NOT add a vague "atypical" flag. Each outlier
juror is paired with a specific opinion that is held but is non-modal for
their coarse cell, and the persona-expansion prompt is conditioned on that
specific committed opinion. The non-modal opinion bank loads from
data/crosstabs/non_modal_priors.json with the schema:

    {
      "source": "GSS 2022 multi-issue battery",
      "issues": ["abortion_legal_all_cases", "guns_universal_bg_check", ...],
      "non_modal_distributions": {
        "white_evangelical|D|18-34": {
          "abortion_legal_all_cases": {"position": "supports", "cell_density": 0.18},
          ...
        },
        ...
      }
    }
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import buckets


OUTLIER_RATE = 0.07
# Temperatures bounded by Anthropic API [0.0, 1.0]. The 30/50/20 split preserves
# the low / mid / high spread intent: tight stereotype-anchored / varied / atypical.
TEMPERATURE_DISTRIBUTION = {
    0.3: 0.30,
    0.7: 0.50,
    1.0: 0.20,
}


def assign_coarse_outlier_cells(jurors: pd.DataFrame) -> pd.DataFrame:
    """Add coarse_party_age_cell column for outlier allocation."""
    out = jurors.copy()
    out["coarse_age"] = buckets.bucket_age_outlier(out["AGE"])
    party = out["political_party"].astype(str)
    party_coarse = party.where(party.isin(["D", "R", "I"]), "I")
    out["coarse_party"] = party_coarse
    out["coarse_party_age_cell"] = (
        out["coarse_party"].astype(str) + "|" + out["coarse_age"].astype(str)
    )
    return out


def allocate_outlier_slate(
    jurors: pd.DataFrame, outlier_rate: float, seed: int
) -> pd.DataFrame:
    """Flag outlier_rate * n jurors across coarse_party_age_cells.

    Allocation is proportional to ACS coarse-cell weight (each cell's juror
    count). Distribution is rng-controlled but seeded for reproducibility.
    Adds boolean `is_outlier` column.
    """
    n = len(jurors)
    target_outliers = int(round(n * outlier_rate))
    rng = np.random.default_rng(seed)
    out = jurors.copy()
    out["is_outlier"] = False

    cell_counts = out.groupby("coarse_party_age_cell", observed=True).size()
    # Proportional allocation per cell, with a floor of 1 outlier per cell that
    # has at least 3 jurors (so each non-trivial cell gets representation).
    per_cell_target = (cell_counts * outlier_rate).round().astype(int)
    per_cell_target = per_cell_target.where(
        ~((cell_counts >= 3) & (per_cell_target == 0)), 1
    )
    # Adjust to hit total target_outliers (balance via largest-residue method).
    delta = target_outliers - per_cell_target.sum()
    if delta != 0:
        residues = (cell_counts * outlier_rate) - per_cell_target
        order = residues.sort_values(ascending=(delta < 0)).index
        for cell in order:
            if delta == 0:
                break
            if delta > 0:
                if per_cell_target[cell] < cell_counts[cell]:
                    per_cell_target[cell] += 1
                    delta -= 1
            else:
                if per_cell_target[cell] > 0:
                    per_cell_target[cell] -= 1
                    delta += 1

    for cell, k in per_cell_target.items():
        if k == 0:
            continue
        cell_idx = out.index[out["coarse_party_age_cell"] == cell].to_numpy()
        if len(cell_idx) == 0:
            continue
        chosen = rng.choice(cell_idx, size=min(k, len(cell_idx)), replace=False)
        out.loc[chosen, "is_outlier"] = True

    return out


class StubPriorRefused(RuntimeError):
    """Raised when a STUB-sourced non-modal priors file is loaded without allow_stubs."""


class MissingProvenance(RuntimeError):
    """Raised when a non-STUB non-modal priors file is missing required provenance."""


# Same required fields as conditional priors, plus issue-level provenance.
# See docs/prior-provenance-schema.md (Section: non_modal_priors.json extended provenance).
REQUIRED_NON_MODAL_PROVENANCE_FIELDS = [
    "source_url",
    "field_year",
    "publication_date",
    "retrieved_at",
    "retrieved_by",
    "population",
    "sample_size_total",
    "weighting_note",
    "table_id",
    "license_or_citation",
    "known_limitations",
    "issues_covered",   # extended field — list of per-issue provenance blocks
]


class NonModalOpinionBank:
    """Loads concrete non-modal opinion priors per (race x religion x party x age) cell.

    Refuses STUB-sourced files unless allow_stubs=True. Non-STUB files must
    carry the extended provenance block per docs/prior-provenance-schema.md
    (Section: non_modal_priors.json extended provenance), with per-issue
    sub-blocks documenting the GSS variable, pooled years, question wording,
    and non-modal threshold for every issue covered.
    """

    def __init__(self, path: Path, allow_stubs: bool = False):
        with Path(path).open() as f:
            self.data = json.load(f)
        source = str(self.data.get("source", "")).strip().upper()
        if source == "STUB":
            if not allow_stubs:
                raise StubPriorRefused(
                    f"{path} declares source=STUB. Production runs (Stage B) must "
                    f"use real GSS/Pew-sourced non-modal opinion priors. To run "
                    f"anyway for pipeline debug, pass --allow-stubs."
                )
        else:
            provenance = self.data.get("provenance")
            if not isinstance(provenance, dict):
                raise MissingProvenance(
                    f"{path} declares source={self.data.get('source')!r} but is "
                    f"missing the `provenance` block entirely. "
                    f"See docs/prior-provenance-schema.md (non_modal_priors section)."
                )
            missing = [
                k for k in REQUIRED_NON_MODAL_PROVENANCE_FIELDS if k not in provenance
            ]
            if missing:
                raise MissingProvenance(
                    f"{path}: provenance missing required fields: {missing}. "
                    f"See docs/prior-provenance-schema.md."
                )
        self.distributions = self.data["non_modal_distributions"]

    def assign_opinion(
        self, juror_cell_key: str, rng: np.random.Generator
    ) -> dict | None:
        """Pick one issue + non-modal position for an outlier juror.

        Returns {issue, position, cell_density} or None if no entry exists for
        this cell key (caller may fall back to a coarser key).
        """
        if juror_cell_key not in self.distributions:
            return None
        issues = self.distributions[juror_cell_key]
        if not issues:
            return None
        chosen_issue = rng.choice(list(issues.keys()))
        return {"issue": chosen_issue, **issues[chosen_issue]}


def attach_non_modal_opinions(
    jurors: pd.DataFrame, bank: NonModalOpinionBank, seed: int
) -> pd.DataFrame:
    """For every is_outlier juror, attach a concrete non-modal opinion."""
    rng = np.random.default_rng(seed)
    out = jurors.copy()
    out["non_modal_issue"] = None
    out["non_modal_position"] = None
    out["non_modal_density"] = None
    for idx in out.index[out["is_outlier"]]:
        race = out.at[idx, "race_bucket"]
        relig = out.at[idx, "religion"]
        party = out.at[idx, "coarse_party"]
        age_c = out.at[idx, "coarse_age"]
        # Try most-specific key first; back off through coarser combinations.
        keys = [
            f"{race}|{relig}|{party}|{age_c}",
            f"{race}|{relig}|{party}",
            f"{race}|{party}",
            f"{party}",
        ]
        opinion = None
        for k in keys:
            opinion = bank.assign_opinion(k, rng)
            if opinion is not None:
                break
        if opinion is None:
            continue
        out.at[idx, "non_modal_issue"] = opinion["issue"]
        out.at[idx, "non_modal_position"] = opinion["position"]
        out.at[idx, "non_modal_density"] = opinion["cell_density"]
    return out


def assign_temperatures(jurors: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Sample expansion temperature per juror from the 30/50/20 distribution."""
    rng = np.random.default_rng(seed)
    n = len(jurors)
    temps = list(TEMPERATURE_DISTRIBUTION.keys())
    probs = list(TEMPERATURE_DISTRIBUTION.values())
    out = jurors.copy()
    out["expansion_temperature"] = rng.choice(temps, size=n, p=probs)
    return out


def instrument(
    jurors: pd.DataFrame,
    non_modal_bank: NonModalOpinionBank,
    seed: int,
    outlier_rate: float = OUTLIER_RATE,
) -> pd.DataFrame:
    """End-to-end variance instrumentation. Caller passes seed for reproducibility."""
    out = assign_coarse_outlier_cells(jurors)
    out = allocate_outlier_slate(out, outlier_rate, seed)
    out = attach_non_modal_opinions(out, non_modal_bank, seed + 1)
    out = assign_temperatures(out, seed + 2)
    return out
