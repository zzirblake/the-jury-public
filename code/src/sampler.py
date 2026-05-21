"""Stage A/B PUMS sampler: PPS selection + IPF raking + capped analysis weights.

Implements D2 + D3 of corpus-construction-plan.md:
  1. Probability-proportional-to-size selection from ACS PUMS using PWGTP
  2. Iterative proportional fitting (raking) on race x age x education x region
     marginals
  3. Calibrated analysis weights bounded to [0.33x, 3x]; if a juror's required
     weight breaches the cap, re-select on the relevant stratum (do not clip)

Public API:
    select_jurors(pums, n, seed) -> DataFrame of selected raw records
    rake_weights(jurors, acs_targets, axes, cap) -> DataFrame with `weight`
    sample(pums, n, acs_targets, seed, cap) -> orchestrated end-to-end
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import buckets


@dataclass
class WeightCap:
    min: float = 0.33
    max: float = 3.0


def pps_select(pums: pd.DataFrame, n: int, seed: int) -> pd.DataFrame:
    """PPS selection of n records from PUMS, weighted by IPUMS PERWT.

    Sampling without replacement; PERWT is the basis for inclusion probability.
    Returns the selected raw PUMS rows with original index preserved as `pums_idx`.
    """
    if "PERWT" not in pums.columns:
        raise ValueError("PUMS extract must include PERWT (IPUMS person weight)")
    if n > len(pums):
        raise ValueError(f"requested n={n} exceeds PUMS rows={len(pums)}")
    rng = np.random.default_rng(seed)
    probs = pums["PERWT"].to_numpy(dtype=float)
    probs = probs / probs.sum()
    idx = rng.choice(len(pums), size=n, replace=False, p=probs)
    out = pums.iloc[idx].copy()
    out["pums_idx"] = pums.index[idx]
    out = out.reset_index(drop=True)
    return out


def compute_marginals_from_pums(
    pums: pd.DataFrame, axes: list[str] | None = None
) -> dict[str, dict[str, float]]:
    """Compute PERWT-weighted marginal distributions from the PUMS extract.

    This is the authoritative source of ACS marginals because PERWT itself is
    the Census person weight calibrated to ACS controls. Using PUMS marginals
    avoids vintage drift between hardcoded targets and the loaded extract.
    """
    if axes is None:
        axes = ["age_bucket", "race_bucket", "education_bucket", "region_bucket"]
    bucketed = attach_buckets(pums)
    out = {}
    for axis in axes:
        wsum = bucketed.groupby(axis, observed=True)["PERWT"].sum()
        wsum = wsum / wsum.sum()
        out[axis] = wsum.to_dict()
    return out


def attach_buckets(jurors: pd.DataFrame) -> pd.DataFrame:
    """Add raking-axis bucket columns + life_stage_recent to a juror frame.

    `life_stage_recent` is derived directly from PUMS event variables
    (FERTYR / DIVINYR / MARRINYR / MIGRATE1 / MARST) per the D5 mechanism #5
    upgrade — pulled out of the v0.1 second-pass conditional sampler so it
    carries real Census joint covariance.
    """
    jurors = jurors.copy()
    jurors["age_bucket"] = buckets.bucket_age(jurors["AGE"])
    jurors["race_bucket"] = buckets.bucket_race(jurors["RACE"], jurors["HISPAN"])
    jurors["education_bucket"] = buckets.bucket_education(jurors["EDUC"])
    jurors["region_bucket"] = buckets.bucket_region(jurors["REGION"])
    jurors["life_stage_recent"] = buckets.derive_life_stage_recent(jurors)
    return jurors


def rake_weights(
    jurors: pd.DataFrame,
    acs_targets: dict[str, dict[str, float]],
    axes: list[str],
    cap: WeightCap,
    max_iter: int = 50,
    tol: float = 0.01,
) -> pd.DataFrame:
    """Iterative proportional fitting on the named axes against ACS marginals.

    Args:
        jurors: frame already through attach_buckets()
        acs_targets: {axis: {bucket: target_proportion}} per raking axis
        axes: list of bucket-column names to rake on (e.g., ["age_bucket", ...])
        cap: WeightCap instance bounding final calibrated weights
        max_iter: hard ceiling on IPF iterations
        tol: convergence tolerance — max axis-marginal absolute error

    Returns:
        jurors frame with `weight` column (calibrated, capped, sum-to-n).

    Raises:
        WeightCapBreach if any juror's required weight is outside the cap
        after IPF converges. Caller catches and re-selects on the stratum.
    """
    n = len(jurors)
    w = np.full(n, n / n, dtype=float)  # start at uniform 1.0 each

    for iteration in range(max_iter):
        max_err = 0.0
        for axis in axes:
            buckets_in = jurors[axis].astype(str).to_numpy()
            current = pd.Series(w).groupby(buckets_in).sum()
            current = current / current.sum()
            target = pd.Series(acs_targets[axis])
            for b, p_target in target.items():
                p_current = current.get(b, 0.0)
                if p_current == 0.0:
                    continue  # cell empty; cannot rake into it
                ratio = p_target / p_current
                mask = buckets_in == b
                w[mask] *= ratio
                err = abs(p_current - p_target)
                if err > max_err:
                    max_err = err
        if max_err < tol:
            break

    # Normalize so weights sum to n (effective sample size = n by construction).
    w = w * (n / w.sum())

    if (w < cap.min).any() or (w > cap.max).any():
        breach = jurors.copy()
        breach["weight"] = w
        breach = breach[(w < cap.min) | (w > cap.max)]
        raise WeightCapBreach(
            f"{len(breach)} juror(s) breach weight cap [{cap.min}, {cap.max}]; "
            f"re-select on the affected strata before re-raking",
            breaching=breach,
        )

    out = jurors.copy()
    out["weight"] = w
    return out


class WeightCapBreach(Exception):
    """Raised when raking produces weights outside the configured cap."""

    def __init__(self, message: str, breaching: pd.DataFrame):
        super().__init__(message)
        self.breaching = breaching


def sample(
    pums: pd.DataFrame,
    n: int,
    acs_targets: dict[str, dict[str, float]],
    seed: int,
    cap: WeightCap | None = None,
    axes: list[str] | None = None,
    max_reselect: int = 3,
) -> pd.DataFrame:
    """End-to-end: PPS-select, attach buckets, rake; re-select on cap breach.

    Each re-selection draws fresh n from PUMS with seed bumped by 1 (so the
    re-roll is reproducible from the original seed). After max_reselect
    attempts, the final WeightCapBreach propagates.
    """
    if cap is None:
        cap = WeightCap()
    if axes is None:
        axes = ["age_bucket", "race_bucket", "education_bucket", "region_bucket"]

    attempt = 0
    cur_seed = seed
    while True:
        raw = pps_select(pums, n, cur_seed)
        bucketed = attach_buckets(raw)
        try:
            return rake_weights(bucketed, acs_targets, axes, cap)
        except WeightCapBreach:
            attempt += 1
            if attempt >= max_reselect:
                raise
            cur_seed += 1
