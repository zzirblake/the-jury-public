"""v0.1 second-pass conditional sampler for non-PUMS traits.

Implements D4 of corpus-construction-plan.md (narrowed scope). For each
PUMS-resolved juror, samples values for:
    political_party, political_ideology, religion, religiosity,
    media_diet_primary, media_diet_slant, household_composition,
    life_stage_recent

from full conditional distributions (NOT modal values) given the juror's
demographic vector. Conditional priors load from JSON files in
data/crosstabs/, sourced from Pew typology / Religious Landscape Study /
News Consumption Study / ACS event-rate data. Format:

    {
      "trait": "political_party",
      "source": "Pew Political Typology 2024",
      "conditioning_axes": ["race", "education", "age", "region"],
      "fallback_chain": [
        ["race", "education", "age"],
        ["race", "education"],
        ["race"],
        []
      ],
      "distributions": {
        "white_non_hispanic|BA+|45-54|S": {"D": 0.31, "R": 0.46, "I": 0.23},
        ...
      }
    }

`fallback_chain` lets the sampler back off to coarser conditioning when the
finest cell is missing (sparse Pew crosstab cells). The terminal `[]` falls
back to the unconditional marginal.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

V01_TRAITS = [
    "political_party",
    "political_ideology",
    "religion",
    "religiosity",
    "media_diet_primary",
    "media_diet_slant",
    "household_composition",
    # life_stage_recent removed from second-pass: now derived directly from
    # PUMS event variables (FERTYR / DIVINYR / MARRINYR / MIGRATE1 / MARST)
    # in buckets.derive_life_stage_recent. See D5 mechanism #5 in the plan.
]


class StubPriorRefused(RuntimeError):
    """Raised when a STUB-sourced prior file is loaded without --allow-stubs."""


class MissingProvenance(RuntimeError):
    """Raised when a non-STUB prior is missing required provenance fields.

    Stage B's defensibility depends on every prior carrying full source/field-
    year/population/wording/weighting/normalization provenance. The schema is
    documented in `docs/prior-provenance-schema.md`. This guard refuses to
    load any real-source prior that does not carry the required block, so
    Stage B can never run on under-documented data.
    """


class MalformedPrior(RuntimeError):
    """Raised when a prior file's structure or distributions are malformed.

    Distinct from MissingProvenance (which catches missing metadata): this
    catches semantically broken priors that would produce nonsense draws
    (axes empty, fallback chain doesn't terminate, distributions don't sum
    to 1, response options don't match distribution keys, etc.).
    """


# Required fields per docs/prior-provenance-schema.md. Adding a field here
# tightens the contract for every future sourcing pass.
REQUIRED_PROVENANCE_FIELDS = [
    "source_url",
    "field_year",
    "publication_date",
    "retrieved_at",
    "retrieved_by",
    "population",
    "sample_size_total",
    "weighting_note",
    "table_id",
    "question_wording",
    "response_options_source",
    "response_options_used",
    "fallback_behavior",
    "hand_normalization",
    "minimum_cell_n_in_source",
    "license_or_citation",
    "known_limitations",
]

# Required text fields that must be NON-EMPTY (not just present). Silence on
# any of these is the methodologist's first attack.
REQUIRED_NON_EMPTY_TEXT_FIELDS = [
    "source_url",
    "population",
    "weighting_note",
    "table_id",
    "question_wording",
    "fallback_behavior",
    "license_or_citation",
]

# Probability-sum tolerance for distribution validation.
_PROB_SUM_TOL = 0.001


class ConditionalPriorBank:
    """Loads and queries conditional-prior JSON files for non-PUMS traits.

    By default, refuses to load any prior whose `source` field equals
    "STUB" (case-insensitive). Pass allow_stubs=True only for pipeline-debug
    runs (Stage A internal dry run).

    Non-STUB priors are additionally validated against the provenance schema
    in `docs/prior-provenance-schema.md`. Any non-STUB file missing required
    provenance fields raises MissingProvenance and refuses to load.
    """

    def __init__(self, crosstabs_dir: Path, allow_stubs: bool = False):
        self.crosstabs_dir = Path(crosstabs_dir)
        self.allow_stubs = allow_stubs
        self.priors: dict[str, dict] = {}

    def load(self, trait: str) -> dict:
        if trait in self.priors:
            return self.priors[trait]
        path = self.crosstabs_dir / f"{trait}.json"
        if not path.exists():
            raise FileNotFoundError(
                f"missing conditional prior for {trait}: expected {path}. "
                f"see build/README.md for sourcing instructions."
            )
        with path.open() as f:
            payload = json.load(f)
        source = str(payload.get("source", "")).strip().upper()
        if source == "STUB":
            if not self.allow_stubs:
                raise StubPriorRefused(
                    f"{path} declares source=STUB. Production runs (Stage B) must "
                    f"use real-source priors. To run anyway for pipeline debug, "
                    f"pass --allow-stubs (or allow_stubs=True)."
                )
            # STUBs still get structure validation so we don't ship broken stubs to debug
            _validate_prior_structure(path, payload, strict_provenance=False)
        else:
            # Non-STUB priors must carry full provenance AND structurally validate.
            _validate_prior_provenance(path, payload)
            _validate_prior_structure(path, payload, strict_provenance=True)
        self.priors[trait] = payload
        return payload

    def distribution_for(
        self, trait: str, conditioning_values: dict[str, str]
    ) -> dict[str, float]:
        """Resolve the conditional distribution for one juror on one trait,
        backing off through the trait's fallback_chain until a cell hits."""
        prior = self.load(trait)
        for fallback_axes in prior["fallback_chain"]:
            if not fallback_axes:
                key = "__unconditional__"
            else:
                key = "|".join(str(conditioning_values[a]) for a in fallback_axes)
            if key in prior["distributions"]:
                return prior["distributions"][key]
        raise KeyError(
            f"trait {trait}: no conditional cell or unconditional fallback hit "
            f"for axes {list(conditioning_values.keys())}"
        )


def _validate_prior_provenance(path: Path, payload: dict) -> None:
    """Required-fields + non-empty-text-fields check. Raises MissingProvenance."""
    provenance = payload.get("provenance")
    if not isinstance(provenance, dict):
        raise MissingProvenance(
            f"{path} declares source={payload.get('source')!r} but is "
            f"missing the `provenance` block entirely. "
            f"See docs/prior-provenance-schema.md for the required schema."
        )
    missing = [k for k in REQUIRED_PROVENANCE_FIELDS if k not in provenance]
    if missing:
        raise MissingProvenance(
            f"{path}: provenance block missing required fields: {missing}. "
            f"See docs/prior-provenance-schema.md."
        )
    # Non-empty enforcement for the critical text fields.
    empty = [
        k for k in REQUIRED_NON_EMPTY_TEXT_FIELDS
        if not str(provenance.get(k, "")).strip()
    ]
    if empty:
        raise MissingProvenance(
            f"{path}: provenance fields present but empty: {empty}. "
            f"Each is required for the methodology footnote. "
            f"Silence on any of these is the methodologist's first attack."
        )


def _validate_prior_structure(
    path: Path, payload: dict, strict_provenance: bool
) -> None:
    """Structural validation independent of provenance metadata.

    Catches:
      - conditioning_axes empty or non-list
      - fallback_chain missing or doesn't terminate in [] (unconditional)
      - distributions empty or any cell missing
      - any distribution's probabilities not summing to ~1.0
      - response_options_used (when present in provenance) mismatching distribution keys

    Raises MalformedPrior with the specific issue.
    """
    axes = payload.get("conditioning_axes")
    if not isinstance(axes, list) or not axes:
        raise MalformedPrior(
            f"{path}: conditioning_axes must be a non-empty list; got {axes!r}"
        )

    chain = payload.get("fallback_chain")
    if not isinstance(chain, list) or not chain:
        raise MalformedPrior(
            f"{path}: fallback_chain must be a non-empty list; got {chain!r}"
        )
    if chain[-1] != []:
        raise MalformedPrior(
            f"{path}: fallback_chain must terminate in [] (unconditional marginal); "
            f"final entry is {chain[-1]!r}. Without an unconditional fallback, "
            f"sparse-cell jurors will raise KeyError at sample time."
        )

    distributions = payload.get("distributions")
    if not isinstance(distributions, dict) or not distributions:
        raise MalformedPrior(
            f"{path}: distributions must be a non-empty dict"
        )

    bad_sums = []
    for cell_key, dist in distributions.items():
        if not isinstance(dist, dict) or not dist:
            raise MalformedPrior(
                f"{path}: distribution for cell {cell_key!r} is empty or not a dict"
            )
        total = sum(dist.values())
        if abs(total - 1.0) > _PROB_SUM_TOL:
            bad_sums.append(f"{cell_key} -> sum={total:.4f}")
    if bad_sums:
        raise MalformedPrior(
            f"{path}: probability distributions do not sum to 1.0 (tolerance {_PROB_SUM_TOL}): "
            f"{bad_sums[:5]}{'...' if len(bad_sums) > 5 else ''}"
        )

    # Response-options consistency check: every distribution's keys must be a
    # subset of the declared response_options_used.
    if strict_provenance:
        declared_options = payload.get("provenance", {}).get("response_options_used")
        if isinstance(declared_options, list) and declared_options:
            declared_set = set(declared_options)
            for cell_key, dist in distributions.items():
                undeclared = set(dist.keys()) - declared_set
                if undeclared:
                    raise MalformedPrior(
                        f"{path}: distribution for cell {cell_key!r} contains "
                        f"keys not in response_options_used: {sorted(undeclared)}. "
                        f"Declared options: {declared_options}."
                    )


def sample_trait(
    distribution: dict[str, float], rng: np.random.Generator
) -> str:
    """Draw one value from a {label: probability} distribution."""
    labels = list(distribution.keys())
    probs = np.array([distribution[lbl] for lbl in labels], dtype=float)
    probs = probs / probs.sum()
    return labels[rng.choice(len(labels), p=probs)]


def second_pass_sample(
    jurors: pd.DataFrame,
    bank: ConditionalPriorBank,
    seed: int,
    traits: list[str] | None = None,
) -> pd.DataFrame:
    """Apply v0.1 second-pass sampler to a bucketed juror frame.

    Each trait is drawn from its full conditional distribution (NOT modal),
    so a "white evangelical 52yo Tennessee HS-only $45K woman" comes out
    Republican ~75%, Democrat ~10%, Independent ~15% as the source crosstab
    indicates. The Bisbee-defense rationale is in D5#2.

    Reads conditioning context per trait from the trait's own
    `conditioning_axes` list (not hardcoded), so changing a crosstab's
    conditioning vintage does not require code changes.
    """
    if traits is None:
        traits = V01_TRAITS
    rng = np.random.default_rng(seed)
    out = jurors.copy()
    for trait in traits:
        prior = bank.load(trait)
        conditioning_axes = prior["conditioning_axes"]
        values = []
        for _, row in out.iterrows():
            cond = {ax: row[f"{ax}_bucket"] for ax in conditioning_axes if f"{ax}_bucket" in out.columns}
            # Some axes (race, education) have direct bucket columns; party/religion may
            # need lookups against earlier-sampled traits if the prior conditions on them.
            for ax in conditioning_axes:
                if ax not in cond and ax in out.columns:
                    cond[ax] = row[ax]
            dist = bank.distribution_for(trait, cond)
            values.append(sample_trait(dist, rng))
        out[trait] = values
    return out
