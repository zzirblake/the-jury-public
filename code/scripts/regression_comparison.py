"""Regression coefficient comparison: synth panel vs Pew W158.

PRE-REGISTERED ANALYSIS — specifications, thresholds, and outcome language
locked in `docs/regression-coefficient-plan.md` v4.1 before this script runs.

Goal: address Bisbee 2024's strongest critique by fitting the same regression
on Pew weighted respondents and on the synth panel, then comparing coefficients
with bootstrap CIs.

Approach (v4.1):
- One-vs-rest weighted fractional logit per response option (39 regressions
  per dataset; 78 primary fits + bootstrap)
- 8-covariate primary (age + race + education + party + gender + region +
  ideology + religion); 4-covariate sensitivity
- Primary uses synth probvec as fractional y (Papke-Wooldridge QMLE);
  secondary uses sampled responses
- L2 alpha=0.01 on synth, unpenalized on Pew + symmetric sanity check
- Thresholds locked in THRESHOLD_BANDS; outcome language in OUTCOME_TEMPLATES_*

Reviewer history: 4 rounds (Sonnet → v2; Opus → v3; Blake → v4; Blake cleanup
→ v4.1); 26 findings, all addressed. Plan locked. Git commit is the
pre-registration.

Outputs:
    out/stage_b/W158_n1000_probvec_20260516_v1/regression_comparison.json
    docs/figures/fig6_regression_coefficient_comparison.png
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
import scipy.optimize

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "out" / "stage_b" / "W158_n1000_probvec_20260516_v1"
FIG_DIR = REPO_ROOT.parent / "docs" / "figures"

# ============================================================
# LOCKED SPECIFICATIONS (do not change post-hoc)
# ============================================================

COVARIATES_PRIMARY = [
    "age", "race", "education", "party",
    "gender", "region", "ideology", "religion",
]
COVARIATES_SENSITIVITY = ["age", "race", "education", "party"]

REFERENCE_LEVELS = {
    "age": "18-29",
    "race": "White-NH",
    "education": "BA+",
    "party": "I",
    "gender": "Male",
    "region": "NE",
    "ideology": "moderate",
    "religion": "Unaffiliated",
}

EXPECTED_BUCKETS = {
    "age": ["18-29", "30-44", "45-64", "65+"],
    "race": ["White-NH", "Hispanic", "Black", "Asian/Other"],
    "education": ["<HS", "HS", "SomeCollege/AA", "BA+"],
    "party": ["D", "R", "I"],
    "gender": ["Male", "Female"],
    "region": ["NE", "MW", "S", "W"],
    "ideology": ["very_liberal", "liberal", "moderate", "conservative", "very_conservative"],
    "religion": ["Protestant", "Catholic", "Unaffiliated", "Other"],
}

RELIGION_4WAY_MAP = {
    "protestant_evangelical": "Protestant",
    "protestant_mainline": "Protestant",
    "protestant_historically_black": "Protestant",
    "catholic": "Catholic",
    "jewish": "Other",
    "muslim": "Other",
    "hindu": "Other",
    "buddhist": "Other",
    "sikh": "Other",
    "latter_day_saints_lds": "Other",
    "orthodox_christian": "Other",
    "other_christian_orthodox": "Other",  # Eastern Orthodox + other non-Catholic Christian
    "other_christian": "Other",
    "other_world_religion": "Other",
    "other_faith_or_spiritual": "Other",
    "nothing_in_particular": "Unaffiliated",
    "agnostic": "Unaffiliated",
    "atheist": "Unaffiliated",
    "spiritual_not_affiliated": "Unaffiliated",  # spiritual-but-not-religious → Pew Unaffiliated
}

# Pew education has 3 buckets (collapses <HS + HS); synth has 4. For regression
# we collapse the synth side to match Pew's coarser 3-way scheme on education.
EDUCATION_SYNTH_TO_PEW = {
    "<HS": "HS",  # synth's <HS folded into Pew's HS-or-less
    "HS": "HS",
    "SomeCollege/AA": "SomeCollege/AA",
    "BA+": "BA+",
}
EXPECTED_BUCKETS["education_3way"] = ["HS", "SomeCollege/AA", "BA+"]

QUESTION_OPTIONS: dict[str, list[str]] = {
    "Q1_climate_personal_impact": ["A great deal", "Some", "Not too much", "Not at all"],
    "Q2_climate_human_cause": ["A great deal", "Some", "Not too much", "Not at all"],
    "Q3_climate_policy_economy": [
        "Help the U.S. economy", "Hurt the U.S. economy", "Make no difference for the U.S. economy",
    ],
    "Q4_scientist_confidence": [
        "A great deal of confidence", "A fair amount of confidence",
        "Not too much confidence", "No confidence at all",
    ],
    "Q5_scientists_policy_role": [
        "Usually better at making good policy decisions about scientific issues than other people",
        "Usually worse at making good policy decisions about scientific issues than other people",
        "Neither better nor worse at making good policy decisions about scientific issues than other people",
    ],
    "Q6_covid_restrictions_retro": [
        "More restrictions", "Fewer restrictions", "The restrictions were about right",
    ],
    "Q7_covid_school_closures": [
        "Too long", "Not long enough", "About the right amount of time",
        "K-12 public schools in my area were never closed", "Not sure",
    ],
    "Q8_covid_updated_vaccine": [
        "Probably get an updated vaccine",
        "Probably not get an updated vaccine",
        "Have already received an updated vaccine",
    ],
    "Q9_astrology_belief": ["Yes, believe in"],
    "Q10_astrology_consult_freq": [
        "Daily", "At least weekly", "Once or twice a month", "Once or twice a year", "Never",
    ],
    "Q11_police_confidence": [
        "A great deal of confidence", "A fair amount of confidence",
        "Not too much confidence", "No confidence at all",
    ],
}

BOOTSTRAP_ITERATIONS = 1000
CI_CONFIDENCE = 0.90
L2_PENALTY_ALPHA = 0.01
RNG_SEED = 20260519

MEANINGFUL_COEF_THRESHOLD = 0.10

THRESHOLD_BANDS = {
    "sign_agreement": {"success_above": 0.85, "failure_below": 0.70},
    "median_per_question_pearson_r": {"success_above": 0.70, "failure_below": 0.40},
    "ci_overlap_rate": {"success_above": 0.80, "failure_below": 0.60},
    "standardized_delta_median": {"success_below": 1.0, "failure_above": 2.0},
}

OUTCOME_TEMPLATES_PRIMARY = {
    "success": (
        "On the W158 8-covariate one-vs-rest comparison, synth panel "
        "expected-probability coefficients reproduce Pew observed-response "
        "coefficients. Coefficient divergence is not observed on the "
        "expected-probability surface at this scope."
    ),
    "partial": (
        "Mixed result. Synth panel expected-probability coefficients reproduce "
        "some but not all of Pew's coefficient structure. Details in per-question "
        "breakdown."
    ),
    "failure": (
        "Coefficient divergence observed on the expected-probability surface: "
        "synth panel expected-probability coefficients diverge from Pew "
        "observed-response coefficients on multiple metrics."
    ),
}
OUTCOME_TEMPLATES_SECONDARY = {
    "success": (
        "On the secondary realized-response analysis, synth sampled-response "
        "coefficients reproduce Pew observed-response coefficients. Bisbee's "
        "regression-coefficient critique does not replicate on the W158 synth "
        "panel at this scope."
    ),
    "partial": (
        "Mixed result on the secondary realized-response analysis. The Bisbee "
        "critique partially replicates."
    ),
    "failure": (
        "Bisbee's regression-coefficient critique replicates on the W158 synth "
        "panel on the secondary realized-response analysis: sampled-response "
        "coefficients diverge from Pew on multiple metrics."
    ),
}
OUTCOME_TEMPLATES = OUTCOME_TEMPLATES_PRIMARY


# ============================================================
# DATA LOADING
# ============================================================

def load_pew_long_extended() -> pd.DataFrame:
    """Load Pew W158 long-format CSV with 8 demographic columns."""
    path = REPO_ROOT / "data" / "pew" / "W158_microdata.csv"
    df = pd.read_csv(path)
    required = {"respondent_id", "question_id", "response", "weight",
                "age", "race", "education", "party",
                "gender", "region", "ideology", "religion"}
    missing = required - set(df.columns)
    if missing:
        raise RuntimeError(f"Pew microdata missing columns: {missing}. "
                           f"Re-run scripts/convert_pew.py with the v4.1 8-axis spec.")
    print(f"loaded Pew long: {len(df):,} rows, {df.respondent_id.nunique():,} respondents")
    return df


def load_synth_long_extended() -> pd.DataFrame:
    """Load synth panel responses joined to 8-covariate trait set + probvecs."""
    sr = pd.read_parquet(OUT_DIR / "synth_responses.parquet")
    tv = pd.read_parquet(OUT_DIR / "trait_vectors.parquet")
    # sr already has: juror_id, question_id, response, weight, age, race, education, party,
    #                 probabilities_json
    # tv has the richer trait set including SEX, region_bucket, political_ideology, religion
    tv = tv.copy()
    tv["gender"] = tv["SEX"].map({1: "Male", 2: "Female"})
    tv["region"] = tv["region_bucket"]
    tv["ideology"] = tv["political_ideology"]
    # Apply locked 16-way → 4-way religion mapping; loud-fail on unmapped values
    unmapped = set(tv["religion"].dropna()) - set(RELIGION_4WAY_MAP)
    if unmapped:
        raise RuntimeError(f"Synth religion values not in RELIGION_4WAY_MAP: {unmapped}")
    tv["religion_4way"] = tv["religion"].map(RELIGION_4WAY_MAP)
    # Collapse synth education (4-way) to Pew's 3-way scheme
    sr = sr.copy()
    sr["education"] = sr["education"].map(EDUCATION_SYNTH_TO_PEW)
    # Join the extra covariates onto synth_responses by pums_idx (=juror_id)
    join_cols = ["pums_idx", "gender", "region", "ideology", "religion_4way"]
    out = sr.merge(tv[join_cols], left_on="juror_id", right_on="pums_idx", how="left")
    out = out.rename(columns={"religion_4way": "religion"})
    if "pums_idx" in out.columns:
        out = out.drop(columns=["pums_idx"])
    print(f"loaded synth long: {len(out):,} rows, {out.juror_id.nunique():,} jurors")
    return out


def collapse_pew_education(pew: pd.DataFrame) -> pd.DataFrame:
    """Pew F_EDUCCAT only has 3 levels (HS-or-less / Some College / College+);
    its `education` column has values 'HS', 'SomeCollege/AA', 'BA+'. Synth has
    4 levels. We collapse synth's <HS+HS in load_synth_long_extended; here we
    don't need to do anything to Pew (already 3-way)."""
    return pew


def validate_buckets(df: pd.DataFrame, source_name: str, covariates: list[str]) -> None:
    """Fail loud if any covariate has values outside EXPECTED_BUCKETS."""
    edu_key = "education_3way" if "education" in covariates else "education"
    for cov in covariates:
        if cov not in df.columns:
            raise RuntimeError(f"{source_name}: covariate '{cov}' missing")
        # Use 3-way education for both
        expected_key = "education_3way" if cov == "education" else cov
        expected = set(EXPECTED_BUCKETS[expected_key])
        observed = set(df[cov].dropna().unique())
        unexpected = observed - expected
        if unexpected:
            raise RuntimeError(
                f"{source_name}: covariate '{cov}' has unexpected values {unexpected}. "
                f"Expected ⊆ {expected}. Check axis mapping in W158_spec.json or "
                f"RELIGION_4WAY_MAP."
            )


# ============================================================
# DESIGN MATRIX CONSTRUCTION
# ============================================================

def build_design_matrix(
    df: pd.DataFrame, covariates: list[str],
) -> tuple[np.ndarray, list[str], pd.Series]:
    """Build (n, p) design matrix with intercept + dummies for each covariate
    (drop reference level). Returns (X, coef_names, keep_mask).
    keep_mask is True for rows with no missing covariates."""
    keep_mask = pd.Series(True, index=df.index)
    for cov in covariates:
        keep_mask &= df[cov].notna()
    sub = df[keep_mask]
    cols = [np.ones(len(sub))]
    names = ["intercept"]
    for cov in covariates:
        expected_key = "education_3way" if cov == "education" else cov
        ref = REFERENCE_LEVELS[cov]
        levels = [lvl for lvl in EXPECTED_BUCKETS[expected_key] if lvl != ref]
        for lvl in levels:
            cols.append((sub[cov] == lvl).astype(float).values)
            names.append(f"{cov}={lvl}")
    X = np.column_stack(cols)
    return X, names, keep_mask


# ============================================================
# WEIGHTED FRACTIONAL LOGIT (the single estimator per v4)
# ============================================================

def _neg_log_lik(beta: np.ndarray, X: np.ndarray, y: np.ndarray, w: np.ndarray, alpha: float) -> float:
    eta = X @ beta
    # Numerically stable log(1 + exp(-eta)) and log(1 + exp(eta))
    log_p = -np.logaddexp(0.0, -eta)        # log(p)
    log_1mp = -np.logaddexp(0.0, eta)       # log(1-p)
    ll = w @ (y * log_p + (1 - y) * log_1mp)
    return -ll + 0.5 * alpha * (beta @ beta)


def _neg_log_lik_grad(beta: np.ndarray, X: np.ndarray, y: np.ndarray, w: np.ndarray, alpha: float) -> np.ndarray:
    eta = X @ beta
    p = 1.0 / (1.0 + np.exp(-eta))
    grad = -X.T @ (w * (y - p)) + alpha * beta
    return grad


def weighted_fractional_logit(
    X: np.ndarray, y: np.ndarray, w: np.ndarray, alpha: float = 0.0,
) -> dict:
    """Fit weighted quasi-binomial logit via L-BFGS-B with analytic gradient.

    Pew: y is binary 0/1 (standard binary logit MLE).
    Synth primary: y is fractional in [0, 1] (Papke-Wooldridge 1996 QMLE).
    Synth secondary: y is binary 0/1 from post-hoc sampled response.

    Coefficient interpretation is identical: log-odds per covariate unit.

    Returns: {coef, converged, n, alpha}
    """
    beta0 = np.zeros(X.shape[1])
    result = scipy.optimize.minimize(
        _neg_log_lik, beta0, args=(X, y, w, alpha),
        jac=_neg_log_lik_grad,
        method="L-BFGS-B",
        options={"maxiter": 200, "ftol": 1e-9, "gtol": 1e-7},
    )
    return {
        "coef": result.x,
        "converged": bool(result.success),
        "n": len(y),
        "alpha": alpha,
        "neg_ll": float(result.fun),
    }


# ============================================================
# ONE-VS-REST PER-OPTION FITTING
# ============================================================

def fit_one_vs_rest(
    df: pd.DataFrame, question_id: str, response_option: str,
    covariates: list[str], weight_col: str = "weight",
    alpha: float = 0.0,
    y_mode: Literal["binary_observed", "fractional_probvec", "binary_sampled"] = "binary_observed",
) -> dict:
    """Fit one-vs-rest fractional logit for (question, option) on one dataset."""
    sub = df[df["question_id"] == question_id]
    if y_mode == "binary_observed" or y_mode == "binary_sampled":
        y_full = (sub["response"] == response_option).astype(float).values
    elif y_mode == "fractional_probvec":
        # Parse probvecs once; extract this option's probability per juror
        y_full = sub["probabilities_json"].apply(
            lambda s: json.loads(s).get(response_option, 0.0)
        ).values.astype(float)
    else:
        raise ValueError(f"unknown y_mode: {y_mode}")

    X, coef_names, keep_mask = build_design_matrix(sub, covariates)
    y = y_full[keep_mask.values]
    w = sub[weight_col].values[keep_mask.values]
    if len(y) == 0:
        return {"coef": None, "converged": False, "n": 0,
                "excluded_reason": "no observations after NaN-cov drop",
                "coef_names": coef_names}
    fit = weighted_fractional_logit(X, y, w, alpha=alpha)
    fit["coef_names"] = coef_names
    return fit


# ============================================================
# BOOTSTRAP
# ============================================================

def bootstrap_one_stage(
    df: pd.DataFrame, question_id: str, response_option: str,
    covariates: list[str], weight_col: str, alpha: float, y_mode: str,
    n_iterations: int = BOOTSTRAP_ITERATIONS, rng_seed: int = RNG_SEED,
) -> dict:
    """One-stage bootstrap: resample rows with replacement; refit.

    Returns: {point_coef, ci_low, ci_high, coef_names} where ci_low/high are
    arrays of per-coefficient percentile bounds."""
    point = fit_one_vs_rest(df, question_id, response_option, covariates,
                            weight_col, alpha, y_mode)
    if not point["converged"] or point.get("coef") is None:
        return {**point, "ci_low": None, "ci_high": None}

    sub = df[df["question_id"] == question_id].reset_index(drop=True)
    n = len(sub)
    rng = np.random.RandomState(rng_seed)
    boot_coefs = []
    for it in range(n_iterations):
        idx = rng.randint(0, n, size=n)
        resample = sub.iloc[idx]
        fit = fit_one_vs_rest(resample, question_id, response_option, covariates,
                              weight_col, alpha, y_mode)
        if fit["converged"] and fit.get("coef") is not None:
            boot_coefs.append(fit["coef"])
    if len(boot_coefs) < 0.5 * n_iterations:
        return {**point, "ci_low": None, "ci_high": None,
                "excluded_reason": f"bootstrap convergence < 50% ({len(boot_coefs)}/{n_iterations})"}
    boot = np.array(boot_coefs)
    lo_q = (1 - CI_CONFIDENCE) / 2
    hi_q = 1 - lo_q
    ci_low = np.percentile(boot, lo_q * 100, axis=0)
    ci_high = np.percentile(boot, hi_q * 100, axis=0)
    boot_se = boot.std(axis=0)
    return {**point, "ci_low": ci_low.tolist(), "ci_high": ci_high.tolist(),
            "boot_se": boot_se.tolist(), "n_bootstrap_converged": len(boot_coefs)}


def bootstrap_two_stage_synth(
    synth_df: pd.DataFrame, question_id: str, response_option: str,
    covariates: list[str], alpha: float,
    n_iterations: int = BOOTSTRAP_ITERATIONS, rng_seed: int = RNG_SEED,
) -> dict:
    """Two-stage bootstrap for synth-secondary (sampled responses): resample
    jurors + redraw each juror's response from their stored probvec."""
    point = fit_one_vs_rest(synth_df, question_id, response_option, covariates,
                            "weight", alpha, "binary_sampled")
    if not point["converged"] or point.get("coef") is None:
        return {**point, "ci_low": None, "ci_high": None}

    sub = synth_df[synth_df["question_id"] == question_id].reset_index(drop=True)
    n = len(sub)
    # Pre-parse probvecs once
    probvecs = sub["probabilities_json"].apply(json.loads).tolist()
    options = list(probvecs[0].keys())
    probmat = np.array([[pv.get(opt, 0.0) for opt in options] for pv in probvecs])

    rng = np.random.RandomState(rng_seed)
    boot_coefs = []
    for it in range(n_iterations):
        idx = rng.randint(0, n, size=n)
        # Stage 1: resampled juror indices
        # Stage 2: for each resampled juror, redraw response from their probvec
        resampled_probs = probmat[idx]  # (n, K)
        # Sample one option per row via cumulative sum + uniform
        cumprobs = resampled_probs.cumsum(axis=1)
        cumprobs = cumprobs / cumprobs[:, -1:]  # normalize for fp tolerance
        u = rng.uniform(size=n)
        # Find first index where cumprob >= u
        sampled_opt_idx = (cumprobs >= u[:, None]).argmax(axis=1)
        sampled_options = np.array(options)[sampled_opt_idx]
        # Resample frame + replace response column with redrawn values
        resample = sub.iloc[idx].copy()
        resample["response"] = sampled_options
        fit = fit_one_vs_rest(resample, question_id, response_option, covariates,
                              "weight", alpha, "binary_sampled")
        if fit["converged"] and fit.get("coef") is not None:
            boot_coefs.append(fit["coef"])
    if len(boot_coefs) < 0.5 * n_iterations:
        return {**point, "ci_low": None, "ci_high": None,
                "excluded_reason": f"bootstrap convergence < 50% ({len(boot_coefs)}/{n_iterations})"}
    boot = np.array(boot_coefs)
    lo_q = (1 - CI_CONFIDENCE) / 2
    hi_q = 1 - lo_q
    ci_low = np.percentile(boot, lo_q * 100, axis=0)
    ci_high = np.percentile(boot, hi_q * 100, axis=0)
    boot_se = boot.std(axis=0)
    return {**point, "ci_low": ci_low.tolist(), "ci_high": ci_high.tolist(),
            "boot_se": boot_se.tolist(), "n_bootstrap_converged": len(boot_coefs)}


# ============================================================
# COMPARISON METRICS
# ============================================================

def compute_meaningful_mask(pew_result: dict) -> np.ndarray:
    """A coef is meaningful iff |pew_coef| >= threshold AND Pew 90% CI does
    not cross zero. Intercept is always excluded from comparison."""
    coef = np.array(pew_result["coef"])
    ci_low = np.array(pew_result["ci_low"])
    ci_high = np.array(pew_result["ci_high"])
    names = pew_result["coef_names"]
    mag_ok = np.abs(coef) >= MEANINGFUL_COEF_THRESHOLD
    ci_excludes_zero = (ci_low > 0) | (ci_high < 0)
    not_intercept = np.array([n != "intercept" for n in names])
    return mag_ok & ci_excludes_zero & not_intercept


def compare_per_question_option(pew_result: dict, synth_result: dict) -> dict:
    """Compare coefs from one (question, option) across Pew vs synth.
    Returns sign_agreement_rate, ci_overlap_rate, pearson_r, standardized_delta_median,
    and per-coef diagnostics. All metrics on meaningful coefs only."""
    if pew_result.get("coef") is None or synth_result.get("coef") is None:
        return {"valid": False, "reason": "non-converged input"}
    if pew_result.get("ci_low") is None or synth_result.get("ci_low") is None:
        return {"valid": False, "reason": "no bootstrap CIs"}

    pew_coef = np.array(pew_result["coef"])
    synth_coef = np.array(synth_result["coef"])
    pew_lo = np.array(pew_result["ci_low"])
    pew_hi = np.array(pew_result["ci_high"])
    synth_lo = np.array(synth_result["ci_low"])
    synth_hi = np.array(synth_result["ci_high"])
    names = pew_result["coef_names"]
    meaningful = compute_meaningful_mask(pew_result)

    sign_agree = (np.sign(pew_coef) == np.sign(synth_coef))
    ci_overlap = (synth_hi >= pew_lo) & (pew_hi >= synth_lo)
    mag_diff = synth_coef - pew_coef

    # Standardized delta: |synth - pew| / pooled_bootstrap_sd
    pew_se = np.array(pew_result.get("boot_se", np.full_like(pew_coef, np.nan)))
    synth_se = np.array(synth_result.get("boot_se", np.full_like(synth_coef, np.nan)))
    pooled_se = np.sqrt(pew_se ** 2 + synth_se ** 2)
    std_delta = np.where(pooled_se > 0, np.abs(mag_diff) / pooled_se, np.nan)

    # Per-coef diagnostics (always include all coefs)
    per_coef = []
    for i, name in enumerate(names):
        per_coef.append({
            "coef": name,
            "pew": float(pew_coef[i]),
            "pew_ci": [float(pew_lo[i]), float(pew_hi[i])],
            "synth": float(synth_coef[i]),
            "synth_ci": [float(synth_lo[i]), float(synth_hi[i])],
            "sign_agree": bool(sign_agree[i]),
            "ci_overlap": bool(ci_overlap[i]),
            "magnitude_diff": float(mag_diff[i]),
            "standardized_delta": float(std_delta[i]) if not np.isnan(std_delta[i]) else None,
            "meaningful": bool(meaningful[i]),
        })

    # Aggregate metrics over meaningful coefs only
    n_meaningful = int(meaningful.sum())
    if n_meaningful == 0:
        return {
            "valid": True,
            "n_coefs_total": len(names) - 1,  # excl intercept
            "n_meaningful": 0,
            "per_coef": per_coef,
            "sign_agreement_rate": None,
            "ci_overlap_rate": None,
            "pearson_r": None,
            "standardized_delta_median": None,
        }
    sign_rate = float(sign_agree[meaningful].mean())
    ci_rate = float(ci_overlap[meaningful].mean())
    std_median = float(np.nanmedian(std_delta[meaningful]))
    if meaningful.sum() >= 2:
        pew_m = pew_coef[meaningful]
        synth_m = synth_coef[meaningful]
        if pew_m.std() > 0 and synth_m.std() > 0:
            r = float(np.corrcoef(pew_m, synth_m)[0, 1])
        else:
            r = None
    else:
        r = None

    return {
        "valid": True,
        "n_coefs_total": len(names) - 1,
        "n_meaningful": n_meaningful,
        "per_coef": per_coef,
        "sign_agreement_rate": sign_rate,
        "ci_overlap_rate": ci_rate,
        "pearson_r": r,
        "standardized_delta_median": std_median,
    }


def aggregate_per_question(option_comparisons: list[dict]) -> dict:
    """Aggregate (question, option) comparisons to a per-question level via
    median across options."""
    valid = [c for c in option_comparisons if c.get("valid") and c.get("n_meaningful", 0) > 0]
    if not valid:
        return {"valid": False, "n_options_valid": 0}
    sign_rates = [c["sign_agreement_rate"] for c in valid if c["sign_agreement_rate"] is not None]
    ci_rates = [c["ci_overlap_rate"] for c in valid if c["ci_overlap_rate"] is not None]
    rs = [c["pearson_r"] for c in valid if c["pearson_r"] is not None]
    std_medians = [c["standardized_delta_median"] for c in valid if c["standardized_delta_median"] is not None]
    return {
        "valid": True,
        "n_options_valid": len(valid),
        "median_sign_agreement_rate": float(np.median(sign_rates)) if sign_rates else None,
        "median_ci_overlap_rate": float(np.median(ci_rates)) if ci_rates else None,
        "median_pearson_r": float(np.median(rs)) if rs else None,
        "median_standardized_delta": float(np.median(std_medians)) if std_medians else None,
    }


def compute_overall_outcome(per_question_aggregates: dict, templates: dict) -> dict:
    """Apply locked THRESHOLD_BANDS to macro-averaged metrics; emit outcome band."""
    valid_qs = {q: a for q, a in per_question_aggregates.items() if a.get("valid")}
    if not valid_qs:
        return {"band": "no_valid_questions", "language": "Insufficient valid questions to evaluate."}

    macro_sign = float(np.median([a["median_sign_agreement_rate"] for a in valid_qs.values()
                                  if a["median_sign_agreement_rate"] is not None]))
    macro_ci = float(np.median([a["median_ci_overlap_rate"] for a in valid_qs.values()
                                if a["median_ci_overlap_rate"] is not None]))
    median_r = float(np.median([a["median_pearson_r"] for a in valid_qs.values()
                                if a["median_pearson_r"] is not None]))
    median_std = float(np.median([a["median_standardized_delta"] for a in valid_qs.values()
                                  if a["median_standardized_delta"] is not None]))

    def band(metric: str, value: float) -> str:
        b = THRESHOLD_BANDS[metric]
        if "success_above" in b:
            if value > b["success_above"]:
                return "success"
            if value < b["failure_below"]:
                return "failure"
            return "partial"
        else:  # "success_below" form
            if value < b["success_below"]:
                return "success"
            if value > b["failure_above"]:
                return "failure"
            return "partial"

    bands = {
        "sign_agreement": band("sign_agreement", macro_sign),
        "median_per_question_pearson_r": band("median_per_question_pearson_r", median_r),
        "ci_overlap_rate": band("ci_overlap_rate", macro_ci),
        "standardized_delta_median": band("standardized_delta_median", median_std),
    }
    n_success = sum(1 for b in bands.values() if b == "success")
    n_failure = sum(1 for b in bands.values() if b == "failure")
    if n_success == 4:
        overall = "success"
    elif n_failure >= 2:
        overall = "failure"
    elif n_success >= 1 and n_failure == 0:
        overall = "partial"
    elif n_failure == 1 and n_success >= 3:
        overall = "partial"
    else:
        overall = "partial"

    return {
        "band": overall,
        "language": templates[overall],
        "metric_values": {
            "macro_sign_agreement_rate": macro_sign,
            "macro_ci_overlap_rate": macro_ci,
            "median_per_question_pearson_r": median_r,
            "median_standardized_delta": median_std,
        },
        "metric_bands": bands,
    }


# ============================================================
# ORCHESTRATOR
# ============================================================

def main():
    print("=" * 60)
    print("Regression coefficient comparison — v4.1 LOCKED")
    print("=" * 60)
    print()
    pew = load_pew_long_extended()
    synth = load_synth_long_extended()
    print()
    print("Validating buckets...")
    validate_buckets(pew, "Pew", COVARIATES_PRIMARY)
    validate_buckets(synth, "Synth", COVARIATES_PRIMARY)
    print("  buckets validated.")
    print()

    # Per (question, option), fit Pew + synth-primary + synth-secondary + Pew-symmetric-L2 sanity
    results = {"per_option": {}, "per_question_primary": {},
               "per_question_secondary": {}, "per_question_sensitivity": {}}

    n_pairs = sum(len(opts) for opts in QUESTION_OPTIONS.values())
    pair_i = 0
    for qid, options in QUESTION_OPTIONS.items():
        print(f"\n=== {qid} ({len(options)} option{'s' if len(options) != 1 else ''}) ===")
        option_primary = []
        option_secondary = []
        option_sensitivity = []
        for opt in options:
            pair_i += 1
            print(f"  [{pair_i}/{n_pairs}] {opt[:50]}")
            # PRIMARY: Pew binary observed vs synth fractional probvec
            pew_fit = bootstrap_one_stage(
                pew, qid, opt, COVARIATES_PRIMARY, "weight",
                alpha=0.0, y_mode="binary_observed",
                rng_seed=RNG_SEED + pair_i,
            )
            synth_prim_fit = bootstrap_one_stage(
                synth, qid, opt, COVARIATES_PRIMARY, "weight",
                alpha=L2_PENALTY_ALPHA, y_mode="fractional_probvec",
                rng_seed=RNG_SEED + pair_i + 100000,
            )
            comp_prim = compare_per_question_option(pew_fit, synth_prim_fit)
            option_primary.append(comp_prim)
            print(f"    primary:  n_meaningful={comp_prim.get('n_meaningful', 0)} "
                  f"r={comp_prim.get('pearson_r')} sign={comp_prim.get('sign_agreement_rate')} "
                  f"CI={comp_prim.get('ci_overlap_rate')}")

            # SECONDARY: Pew binary vs synth sampled binary (two-stage bootstrap on synth)
            synth_sec_fit = bootstrap_two_stage_synth(
                synth, qid, opt, COVARIATES_PRIMARY,
                alpha=L2_PENALTY_ALPHA,
                rng_seed=RNG_SEED + pair_i + 200000,
            )
            comp_sec = compare_per_question_option(pew_fit, synth_sec_fit)
            option_secondary.append(comp_sec)
            print(f"    secondary:  n_meaningful={comp_sec.get('n_meaningful', 0)} "
                  f"r={comp_sec.get('pearson_r')}")

            # SENSITIVITY: 4-covariate primary
            pew_sens = bootstrap_one_stage(
                pew, qid, opt, COVARIATES_SENSITIVITY, "weight",
                alpha=0.0, y_mode="binary_observed",
                rng_seed=RNG_SEED + pair_i + 300000,
            )
            synth_sens = bootstrap_one_stage(
                synth, qid, opt, COVARIATES_SENSITIVITY, "weight",
                alpha=L2_PENALTY_ALPHA, y_mode="fractional_probvec",
                rng_seed=RNG_SEED + pair_i + 400000,
            )
            comp_sens = compare_per_question_option(pew_sens, synth_sens)
            option_sensitivity.append(comp_sens)

            results["per_option"][f"{qid}::{opt}"] = {
                "primary": comp_prim, "secondary": comp_sec, "sensitivity": comp_sens,
            }

        results["per_question_primary"][qid] = aggregate_per_question(option_primary)
        results["per_question_secondary"][qid] = aggregate_per_question(option_secondary)
        results["per_question_sensitivity"][qid] = aggregate_per_question(option_sensitivity)

    # Overall outcomes
    print("\n" + "=" * 60)
    print("Computing overall outcomes...")
    results["overall_primary"] = compute_overall_outcome(
        results["per_question_primary"], OUTCOME_TEMPLATES_PRIMARY)
    results["overall_secondary"] = compute_overall_outcome(
        results["per_question_secondary"], OUTCOME_TEMPLATES_SECONDARY)
    results["overall_sensitivity"] = compute_overall_outcome(
        results["per_question_sensitivity"], OUTCOME_TEMPLATES_PRIMARY)

    # Write JSON
    out_path = OUT_DIR / "regression_comparison.json"
    out_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nwrote {out_path}")

    print("\n=== OVERALL PRIMARY OUTCOME ===")
    print(f"Band: {results['overall_primary']['band']}")
    print(f"Metrics: {results['overall_primary'].get('metric_values', {})}")
    print(f"\n{results['overall_primary']['language']}")
    print("\n=== OVERALL SECONDARY OUTCOME ===")
    print(f"Band: {results['overall_secondary']['band']}")
    print(f"Metrics: {results['overall_secondary'].get('metric_values', {})}")
    print(f"\n{results['overall_secondary']['language']}")
    print("\n=== OVERALL SENSITIVITY (4-cov) OUTCOME ===")
    print(f"Band: {results['overall_sensitivity']['band']}")
    print(f"Metrics: {results['overall_sensitivity'].get('metric_values', {})}")


if __name__ == "__main__":
    main()
