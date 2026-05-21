"""End-to-end smoke test against a synthetic PUMS-shaped frame.

Generates a fake PUMS extract that respects the ACS marginal targets,
runs the full pipeline (selection -> raking -> second-pass -> variance)
with stub conditional priors and a stub non-modal opinion bank, and
confirms the expected outputs land. Does NOT call the Anthropic API.

Run after `pip install -r requirements.txt`:
    python scripts/smoke_test.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src import conditional_sampler, sampler, variance


def make_synthetic_pums(n: int = 50_000, seed: int = 42) -> pd.DataFrame:
    """Build a fake IPUMS-shaped PUMS frame for offline testing.

    Generates IPUMS-USA harmonized columns (AGE, SEX, RACE, HISPAN, EDUC,
    REGION, PERWT, plus event flags). Code distributions roughly match the
    real ACS 2024 PUMS observed values.
    """
    rng = np.random.default_rng(seed)

    # rough US adult marginals — used only to make a plausible-looking synthetic
    age_buckets = rng.choice(
        ["18-24", "25-34", "35-44", "45-54", "55-64", "65+"],
        size=n, p=[0.118, 0.174, 0.174, 0.154, 0.157, 0.223],
    )
    age_low_map = {"18-24": 18, "25-34": 25, "35-44": 35, "45-54": 45, "55-64": 55, "65+": 65}
    age_high_map = {"18-24": 24, "25-34": 34, "35-44": 44, "45-54": 54, "55-64": 64, "65+": 90}
    age = np.array([rng.integers(age_low_map[b], age_high_map[b] + 1) for b in age_buckets])

    # IPUMS RACE codes 1-9; HISPAN 0/1/2/3/4 (0=non-hispanic)
    race = rng.choice([1, 2, 3, 4, 5, 6, 7, 8, 9],
                      size=n, p=[0.683, 0.086, 0.012, 0.016, 0.003, 0.046, 0.054, 0.094, 0.006])
    hispan = rng.choice([0, 1, 2, 3, 4], size=n, p=[0.856, 0.083, 0.013, 0.007, 0.041])

    # IPUMS EDUC code: 0-11 sparse range
    educ = rng.choice([0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 11],
                      size=n, p=[0.018, 0.004, 0.016, 0.009, 0.011, 0.017, 0.363, 0.130, 0.086, 0.209, 0.137])

    # IPUMS REGION 2-digit codes
    region = rng.choice([11, 12, 21, 22, 31, 32, 33, 41, 42],
                        size=n, p=[0.048, 0.130, 0.142, 0.065, 0.203, 0.060, 0.117, 0.077, 0.158])

    pums = pd.DataFrame({
        "AGE": age,
        "SEX": rng.integers(1, 3, n),
        "RACE": race,
        "HISPAN": hispan,
        "EDUC": educ,
        "REGION": region,
        "MARST": rng.choice([1, 2, 3, 4, 5, 6], size=n, p=[0.508, 0.025, 0.014, 0.110, 0.062, 0.281]),
        "MARRINYR": rng.choice([1, 2], size=n, p=[0.984, 0.016]),
        "DIVINYR": rng.choice([0, 1, 2], size=n, p=[0.281, 0.713, 0.006]),
        "FERTYR": rng.choice([0, 1, 2], size=n, p=[0.760, 0.227, 0.013]),
        "MIGRATE1": rng.choice([1, 2, 3, 4], size=n, p=[0.890, 0.083, 0.021, 0.006]),
        "PERWT": rng.integers(20, 200, n).astype(float),
    })
    return pums


def make_stub_priors(crosstabs_dir: Path):
    """Write minimal-coverage stub conditional priors so the second-pass sampler runs."""
    crosstabs_dir.mkdir(parents=True, exist_ok=True)

    stubs = {
        "political_party": {
            "trait": "political_party",
            "source": "STUB",
            "conditioning_axes": ["race", "education"],
            "fallback_chain": [["race", "education"], ["race"], []],
            "distributions": {
                "__unconditional__": {"D": 0.31, "R": 0.29, "I": 0.40},
            },
        },
        "political_ideology": {
            "trait": "political_ideology",
            "source": "STUB",
            "conditioning_axes": ["education"],
            "fallback_chain": [["education"], []],
            "distributions": {
                "__unconditional__": {"liberal": 0.27, "moderate": 0.36, "conservative": 0.37},
            },
        },
        "religion": {
            "trait": "religion",
            "source": "STUB",
            "conditioning_axes": ["race", "region"],
            "fallback_chain": [["race", "region"], ["race"], []],
            "distributions": {
                "__unconditional__": {
                    "protestant_evangelical": 0.23, "catholic": 0.20,
                    "nothing_in_particular": 0.17, "atheist": 0.04, "agnostic": 0.06,
                    "jewish": 0.02, "muslim": 0.013, "other": 0.267,
                },
            },
        },
        "religiosity": {
            "trait": "religiosity",
            "source": "STUB",
            "conditioning_axes": ["religion"],
            "fallback_chain": [["religion"], []],
            "distributions": {
                "__unconditional__": {"weekly+": 0.22, "monthly": 0.20, "rarely": 0.41, "never": 0.17},
            },
        },
        "media_diet_primary": {
            "trait": "media_diet_primary",
            "source": "STUB",
            "conditioning_axes": ["age", "political_party"],
            "fallback_chain": [["age", "political_party"], []],
            "distributions": {
                "__unconditional__": {"local_tv": 0.15, "cable_news": 0.20, "online": 0.30, "social_media": 0.20, "none": 0.15},
            },
        },
        "media_diet_slant": {
            "trait": "media_diet_slant",
            "source": "STUB",
            "conditioning_axes": ["political_party"],
            "fallback_chain": [["political_party"], []],
            "distributions": {
                "__unconditional__": {"left": 0.30, "center": 0.30, "right": 0.40},
            },
        },
        "household_composition": {
            "trait": "household_composition",
            "source": "STUB",
            "conditioning_axes": ["age"],
            "fallback_chain": [["age"], []],
            "distributions": {
                "__unconditional__": {"single": 0.30, "couple_no_kids": 0.30, "couple_with_kids": 0.30, "other": 0.10},
            },
        },
        # life_stage_recent removed: now derived directly from PUMS event flags
        # (FERTYR/DIVINYR/MARRINYR/MIGRATE1/MARST) in src/buckets.py:derive_life_stage_recent.
        # No conditional prior needed for this trait.
    }
    for trait, payload in stubs.items():
        (crosstabs_dir / f"{trait}.json").write_text(json.dumps(payload, indent=2))

    # Non-modal opinion stub
    non_modal = {
        "source": "STUB",
        "issues": ["abortion_legal_all_cases", "guns_universal_bg_check", "climate_action_aggressive"],
        "non_modal_distributions": {
            "R": {
                "abortion_legal_all_cases": {"position": "supports", "cell_density": 0.18},
                "climate_action_aggressive": {"position": "supports", "cell_density": 0.12},
            },
            "D": {
                "guns_universal_bg_check": {"position": "opposes", "cell_density": 0.10},
            },
            "I": {
                "abortion_legal_all_cases": {"position": "opposes", "cell_density": 0.20},
            },
        },
    }
    (crosstabs_dir / "non_modal_priors.json").write_text(json.dumps(non_modal, indent=2))


def main():
    print("=== smoke test: end-to-end pipeline (no API calls) ===\n")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        crosstabs_dir = tmp_root / "crosstabs"
        make_stub_priors(crosstabs_dir)

        print("[1/4] generating synthetic PUMS...")
        pums = make_synthetic_pums(n=50_000)
        print(f"      generated {len(pums):,} fake PUMS records")

        print("[2/4] PPS selection + raking n=200 (PUMS-derived marginals)...")
        targets = sampler.compute_marginals_from_pums(pums)
        jurors = sampler.sample(
            pums=pums, n=200,
            acs_targets=targets,
            seed=20260515,
        )
        print(f"      n={len(jurors)}, weight range "
              f"[{jurors['weight'].min():.3f}, {jurors['weight'].max():.3f}], "
              f"sum-to-{jurors['weight'].sum():.1f}")
        for axis in ["age_bucket", "race_bucket", "education_bucket", "region_bucket"]:
            wsum = jurors.groupby(axis, observed=True)["weight"].sum()
            wsum = wsum / wsum.sum()
            target = pd.Series(targets[axis])
            max_err = (wsum.reindex(target.index).fillna(0) - target).abs().max()
            print(f"      {axis}: max marginal error = {max_err:.4f}")

        print("[3/4] second-pass conditional sampler (allow_stubs=True for debug)...")
        bank = conditional_sampler.ConditionalPriorBank(crosstabs_dir, allow_stubs=True)
        jurors = conditional_sampler.second_pass_sample(
            jurors, bank, seed=20260515 + 100
        )
        for trait in conditional_sampler.V01_TRAITS:
            counts = jurors[trait].value_counts(normalize=True).head(3)
            top3 = ", ".join(f"{k}={v:.2f}" for k, v in counts.items())
            print(f"      {trait}: top3 = {top3}")

        print("[4/4] variance instrumentation (outliers + temperatures)...")
        nm_bank = variance.NonModalOpinionBank(crosstabs_dir / "non_modal_priors.json", allow_stubs=True)
        jurors = variance.instrument(
            jurors, nm_bank, seed=20260515 + 200, outlier_rate=0.07
        )
        n_outlier = jurors["is_outlier"].sum()
        n_with_op = jurors["non_modal_issue"].notna().sum()
        temp_dist = jurors["expansion_temperature"].value_counts(normalize=True).sort_index()
        print(f"      outliers: {n_outlier} flagged, {n_with_op} with concrete non-modal opinions")
        print(f"      temperatures: {dict(temp_dist.round(2))}")

    print("\n=== smoke test PASSED: pipeline runs end-to-end ===")
    print("Real PUMS extract + real conditional priors + LLM_API_KEY required for "
          "Stage A run; see build/README.md.")


if __name__ == "__main__":
    main()
