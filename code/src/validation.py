"""Validation harness: per-cell Wasserstein, entropy ratio, minority recovery,
all with bootstrap CIs and weight-aware metrics; plus the coverage rule on
the validation surface.

Implements D6 of corpus-construction-plan.md. Validation cells are coarse
(age, education, race, party, age x party, race x education) — distinct
from the construction frame. Cells where either synthetic or source n falls
below the configured minimum are flagged "underpowered, not measured" and
do not enter the threshold counts.

D3 contract: every published metric is computed against the calibrated
analysis weights (synthetic side: raked PERWT-derived `weight`; source side:
Pew survey weights). Unweighted metrics would invalidate the defensibility
of the entire raking step.

Public API:
    compute_metrics(synth, source, cells_config, ...) -> ValidationResult
    apply_coverage_rule(result, coverage_config) -> CoverageReport
    apply_thresholds(result, thresholds_config) -> ThresholdReport
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product

import numpy as np
import pandas as pd
from scipy.stats import wasserstein_distance


WEIGHT_COL = "weight"


@dataclass
class CellMetric:
    cell_key: str
    n_synth: int
    n_source: int
    measured: bool
    wasserstein: float | None = None
    entropy_ratio: float | None = None
    minority_recovery: float | None = None
    wasserstein_ci: tuple[float, float] | None = None
    entropy_ratio_ci: tuple[float, float] | None = None
    minority_recovery_ci: tuple[float, float] | None = None
    marginal_error_sigma: float | None = None
    underpowered_reason: str | None = None


@dataclass
class ValidationResult:
    question_id: str
    top_level_cells: dict[str, list[CellMetric]] = field(default_factory=dict)
    interaction_cells: dict[str, list[CellMetric]] = field(default_factory=dict)


@dataclass
class CoverageReport:
    top_level_pct_measured: float
    interaction_pct_measured: float
    top_level_passes: bool
    interaction_passes: bool
    overall_passes: bool


@dataclass
class ThresholdReport:
    marginal_pass_pct: float
    entropy_ci_pass_pct: float
    minority_ci_pass_pct: float
    marginal_passes: bool
    entropy_passes: bool
    minority_passes: bool
    overall_passes: bool


# ---------------------------------------------------------------------------
# Weighted distribution + metric primitives
# ---------------------------------------------------------------------------


def _weighted_distribution(
    responses: pd.Series, weights: pd.Series
) -> pd.Series:
    """Empirical weighted distribution over response categories.

    Weights are required (D3 contract). Pass a Series of 1.0s if a side genuinely
    has no weights, but this should be rare and intentional.
    """
    if responses.empty:
        return pd.Series(dtype=float)
    df = pd.DataFrame({"r": responses.values, "w": weights.values})
    df = df.dropna(subset=["r"])
    if df.empty:
        return pd.Series(dtype=float)
    sums = df.groupby("r")["w"].sum()
    total = sums.sum()
    return (sums / total).sort_index() if total > 0 else pd.Series(dtype=float)


def _aligned_arrays(
    synth_dist: pd.Series, source_dist: pd.Series
) -> tuple[np.ndarray, np.ndarray, list]:
    cats = sorted(set(synth_dist.index) | set(source_dist.index))
    return (
        synth_dist.reindex(cats, fill_value=0.0).to_numpy(),
        source_dist.reindex(cats, fill_value=0.0).to_numpy(),
        cats,
    )


def _entropy(probs: np.ndarray) -> float:
    p = probs[probs > 0]
    return float(-np.sum(p * np.log(p)))


def _wasserstein_metric_weighted(
    s_r: pd.Series, s_w: pd.Series, src_r: pd.Series, src_w: pd.Series
) -> float:
    s_dist = _weighted_distribution(s_r, s_w)
    src_dist = _weighted_distribution(src_r, src_w)
    s_arr, src_arr, cats = _aligned_arrays(s_dist, src_dist)
    positions = np.arange(len(cats), dtype=float)
    if s_arr.sum() == 0 or src_arr.sum() == 0:
        return float("nan")
    return float(wasserstein_distance(positions, positions, s_arr, src_arr))


def _entropy_ratio_metric_weighted(
    s_r: pd.Series, s_w: pd.Series, src_r: pd.Series, src_w: pd.Series
) -> float:
    s_dist = _weighted_distribution(s_r, s_w)
    src_dist = _weighted_distribution(src_r, src_w)
    s_arr, src_arr, _ = _aligned_arrays(s_dist, src_dist)
    h_synth = _entropy(s_arr)
    h_source = _entropy(src_arr)
    if h_source == 0:
        return 1.0 if h_synth == 0 else 0.0
    return float(h_synth / h_source)


def _minority_recovery_metric_weighted(
    s_r: pd.Series, s_w: pd.Series, src_r: pd.Series, src_w: pd.Series
) -> float:
    """Ratio of synth density to expected source density in the 0-15th and
    85-100th percentile bands of the source response distribution."""
    src_dist = _weighted_distribution(src_r, src_w)
    if len(src_dist) < 3:
        return 1.0
    src_sorted = src_dist.sort_values()
    cum = src_sorted.cumsum()
    low_cats = src_sorted.index[cum <= 0.15].tolist()
    high_cats = src_sorted.index[cum >= 0.85].tolist()
    minority_cats = set(low_cats) | set(high_cats)
    if not minority_cats:
        return 1.0
    expected = src_dist.reindex(minority_cats).fillna(0).sum()
    s_dist = _weighted_distribution(s_r, s_w)
    actual = s_dist.reindex(minority_cats).fillna(0).sum()
    return float(actual / expected) if expected > 0 else 1.0


def _marginal_error_sigma_weighted(
    s_r: pd.Series, s_w: pd.Series, src_r: pd.Series, src_w: pd.Series, n_source_eff: int
) -> float:
    s_dist = _weighted_distribution(s_r, s_w)
    src_dist = _weighted_distribution(src_r, src_w)
    s_arr, src_arr, _ = _aligned_arrays(s_dist, src_dist)
    abs_err = np.abs(s_arr - src_arr)
    se = np.sqrt(np.maximum(src_arr * (1 - src_arr) / max(n_source_eff, 1), 1e-12))
    return float(np.max(abs_err / se))


# ---------------------------------------------------------------------------
# Bootstrap (weighted)
# ---------------------------------------------------------------------------


def _bootstrap_metric_weighted(
    s_r: pd.Series, s_w: pd.Series, src_r: pd.Series, src_w: pd.Series,
    metric_fn, n_iter: int, rng: np.random.Generator, confidence: float,
) -> tuple[float, tuple[float, float]]:
    point = metric_fn(s_r, s_w, src_r, src_w)
    n_synth = len(s_r)
    n_source = len(src_r)
    samples = np.empty(n_iter, dtype=float)
    s_r_arr = s_r.to_numpy()
    s_w_arr = s_w.to_numpy()
    src_r_arr = src_r.to_numpy()
    src_w_arr = src_w.to_numpy()
    for i in range(n_iter):
        si = rng.integers(0, n_synth, n_synth)
        srci = rng.integers(0, n_source, n_source)
        samples[i] = metric_fn(
            pd.Series(s_r_arr[si]), pd.Series(s_w_arr[si]),
            pd.Series(src_r_arr[srci]), pd.Series(src_w_arr[srci]),
        )
    alpha = (1 - confidence) / 2
    lo = float(np.quantile(samples[~np.isnan(samples)], alpha))
    hi = float(np.quantile(samples[~np.isnan(samples)], 1 - alpha))
    return point, (lo, hi)


# ---------------------------------------------------------------------------
# Cell evaluation
# ---------------------------------------------------------------------------


def evaluate_cell(
    cell_key: str,
    s_r: pd.Series, s_w: pd.Series,
    src_r: pd.Series, src_w: pd.Series,
    min_synth_n: int, min_source_n: int,
    bootstrap_iter: int, confidence: float,
    rng: np.random.Generator,
) -> CellMetric:
    n_s = len(s_r)
    n_src = len(src_r)
    if n_s < min_synth_n or n_src < min_source_n:
        reason = []
        if n_s < min_synth_n:
            reason.append(f"synth_n={n_s}<{min_synth_n}")
        if n_src < min_source_n:
            reason.append(f"source_n={n_src}<{min_source_n}")
        return CellMetric(
            cell_key=cell_key, n_synth=n_s, n_source=n_src, measured=False,
            underpowered_reason=", ".join(reason),
        )

    w_pt, w_ci = _bootstrap_metric_weighted(
        s_r, s_w, src_r, src_w,
        _wasserstein_metric_weighted, bootstrap_iter, rng, confidence,
    )
    e_pt, e_ci = _bootstrap_metric_weighted(
        s_r, s_w, src_r, src_w,
        _entropy_ratio_metric_weighted, bootstrap_iter, rng, confidence,
    )
    m_pt, m_ci = _bootstrap_metric_weighted(
        s_r, s_w, src_r, src_w,
        _minority_recovery_metric_weighted, bootstrap_iter, rng, confidence,
    )
    sigma = _marginal_error_sigma_weighted(s_r, s_w, src_r, src_w, n_src)

    return CellMetric(
        cell_key=cell_key, n_synth=n_s, n_source=n_src, measured=True,
        wasserstein=w_pt, entropy_ratio=e_pt, minority_recovery=m_pt,
        wasserstein_ci=w_ci, entropy_ratio_ci=e_ci, minority_recovery_ci=m_ci,
        marginal_error_sigma=sigma,
    )


# ---------------------------------------------------------------------------
# Top-level entry
# ---------------------------------------------------------------------------


def _select_cell(df: pd.DataFrame, conditions: dict[str, str]) -> pd.DataFrame:
    mask = pd.Series(True, index=df.index)
    for col, val in conditions.items():
        mask &= df[col] == val
    return df[mask]


class UnweightedRefused(RuntimeError):
    """Raised when a required weight column is missing and allow_unweighted is False.

    Stage B must never silently validate unweighted responses — the entire raking
    discipline (D3 of the construction plan) hinges on weighted metrics. This
    guard prevents a misnamed Pew weight column or a post-merge column-suffix
    bug from looking like a valid weighted run.
    """


def compute_metrics(
    synth_responses: pd.DataFrame,
    source_responses: pd.DataFrame,
    cells_config: dict,
    question_id: str,
    bootstrap_iter: int = 1000,
    confidence: float = 0.90,
    seed: int = 1,
    weight_col_synth: str = WEIGHT_COL,
    weight_col_source: str = WEIGHT_COL,
    allow_unweighted: bool = False,
) -> ValidationResult:
    """Run validation for one question.

    Required columns:
      synth_responses: response, weight_col_synth, plus all axes referenced in cells_config
      source_responses: response, weight_col_source, plus all axes referenced in cells_config

    cells_config:
      {"top_level": {axis_name: {buckets, min_synth_n, min_source_n}},
       "interaction": {pair_name: {axes: [ax1, ax2],
                                   buckets1: [...], buckets2: [...],
                                   min_synth_n, min_source_n}}}

    Interaction cells are enumerated from the FULL CARTESIAN PRODUCT of the
    configured buckets, NOT from observed combinations in the synthetic panel,
    so cells absent from synth still enter the denominator as underpowered.

    Raises UnweightedRefused if either side is missing its declared weight
    column and allow_unweighted is False. Stage B should always run with
    allow_unweighted=False. Test/smoke paths may pass True deliberately.
    """
    rng = np.random.default_rng(seed)
    result = ValidationResult(question_id=question_id)

    missing = []
    if weight_col_synth not in synth_responses.columns:
        missing.append(f"synth weight column '{weight_col_synth}'")
    if weight_col_source not in source_responses.columns:
        missing.append(f"source weight column '{weight_col_source}'")
    if missing:
        if not allow_unweighted:
            raise UnweightedRefused(
                f"required weight column(s) missing: {', '.join(missing)}. "
                f"Validation metrics are weight-aware by contract (D3). "
                f"Pass allow_unweighted=True only for explicit debug/test runs."
            )
        if weight_col_synth not in synth_responses.columns:
            synth_responses = synth_responses.assign(**{weight_col_synth: 1.0})
        if weight_col_source not in source_responses.columns:
            source_responses = source_responses.assign(**{weight_col_source: 1.0})

    # === Top-level cells ===
    for axis, spec in cells_config["top_level"].items():
        cells = []
        for bucket in spec["buckets"]:
            s_sub = _select_cell(synth_responses, {axis: bucket})
            src_sub = _select_cell(source_responses, {axis: bucket})
            cells.append(
                evaluate_cell(
                    f"{axis}={bucket}",
                    s_sub["response"], s_sub[weight_col_synth],
                    src_sub["response"], src_sub[weight_col_source],
                    spec["min_synth_n"], spec["min_source_n"],
                    bootstrap_iter, confidence, rng,
                )
            )
        result.top_level_cells[axis] = cells

    # === Interaction cells: enumerate FULL cartesian product ===
    for pair_name, spec in cells_config["interaction"].items():
        ax1, ax2 = spec["axes"]
        buckets1 = spec.get("buckets1") or cells_config["top_level"][ax1]["buckets"]
        buckets2 = spec.get("buckets2") or cells_config["top_level"][ax2]["buckets"]
        cells = []
        for v1, v2 in product(buckets1, buckets2):
            s_sub = _select_cell(synth_responses, {ax1: v1, ax2: v2})
            src_sub = _select_cell(source_responses, {ax1: v1, ax2: v2})
            cells.append(
                evaluate_cell(
                    f"{ax1}={v1}|{ax2}={v2}",
                    s_sub["response"], s_sub[weight_col_synth],
                    src_sub["response"], src_sub[weight_col_source],
                    spec["min_synth_n"], spec["min_source_n"],
                    bootstrap_iter, confidence, rng,
                )
            )
        result.interaction_cells[pair_name] = cells

    return result


def apply_coverage_rule(
    result: ValidationResult, coverage_config: dict
) -> CoverageReport:
    top_cells = [c for cells in result.top_level_cells.values() for c in cells]
    int_cells = [c for cells in result.interaction_cells.values() for c in cells]

    top_pct = sum(c.measured for c in top_cells) / max(len(top_cells), 1)
    int_pct = sum(c.measured for c in int_cells) / max(len(int_cells), 1)
    top_pass = top_pct >= coverage_config["top_level_min_pct"]
    int_pass = int_pct >= coverage_config["interaction_min_pct"]
    return CoverageReport(
        top_level_pct_measured=top_pct,
        interaction_pct_measured=int_pct,
        top_level_passes=top_pass,
        interaction_passes=int_pass,
        overall_passes=top_pass and int_pass,
    )


def apply_thresholds(
    result: ValidationResult, thresholds_config: dict
) -> ThresholdReport:
    measured = [
        c for cells in (
            list(result.top_level_cells.values()) + list(result.interaction_cells.values())
        )
        for c in cells if c.measured
    ]
    if not measured:
        return ThresholdReport(
            marginal_pass_pct=0, entropy_ci_pass_pct=0, minority_ci_pass_pct=0,
            marginal_passes=False, entropy_passes=False, minority_passes=False,
            overall_passes=False,
        )

    marginal_passes_per_cell = [
        c.marginal_error_sigma is not None
        and c.marginal_error_sigma <= thresholds_config["marginal_error_sigma"]
        for c in measured
    ]
    entropy_passes_per_cell = [
        c.entropy_ratio_ci is not None
        and c.entropy_ratio_ci[0] >= thresholds_config["entropy_ratio_ci_lower"]
        and c.entropy_ratio is not None
        and c.entropy_ratio >= thresholds_config["entropy_ratio_point"]
        for c in measured
    ]
    minority_passes_per_cell = [
        c.minority_recovery_ci is not None
        and c.minority_recovery_ci[0] >= thresholds_config["minority_recovery_ci_lower"]
        and c.minority_recovery is not None
        and c.minority_recovery >= thresholds_config["minority_recovery_point"]
        for c in measured
    ]

    n = len(measured)
    marg_pct = sum(marginal_passes_per_cell) / n
    ent_pct = sum(entropy_passes_per_cell) / n
    min_pct = sum(minority_passes_per_cell) / n

    marg_ok = marg_pct >= (1 - thresholds_config["marginal_fail_pct"])
    ent_ok = ent_pct >= 0.70
    min_ok = min_pct >= 0.70

    return ThresholdReport(
        marginal_pass_pct=marg_pct, entropy_ci_pass_pct=ent_pct,
        minority_ci_pass_pct=min_pct,
        marginal_passes=marg_ok, entropy_passes=ent_ok, minority_passes=min_ok,
        overall_passes=marg_ok and ent_ok and min_ok,
    )
