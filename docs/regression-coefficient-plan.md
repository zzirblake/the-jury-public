---
type: analysis-plan
project: the-jury
created: 2026-05-19
updated: 2026-05-19 (v4.1)
status: v4.1, LOCKED, READY FOR EXECUTION
goal: close Bisbee 2024's strongest critique (regression-coefficient divergence) on W158
output: code/scripts/regression_comparison.py + JSON + figure + new article §"Regression coefficient comparison"
cost: $0 API; 6-8 hours (Pew converter extension + 8-covariate one-vs-rest fractional logit + bootstrap + figure)
review_history: 4 rounds of review (two code-review-agent passes, two author passes); 26 findings total, all addressed in v4.1
---

# Regression Coefficient Comparison: Analysis Plan

## 1. Goal and scope

Bisbee et al. (2024) document that synthetic respondent panels can reproduce acceptable aggregate means while subgroup regression coefficients diverge or sign-flip from the real data. This is the single critique the current artifact acknowledges in §Limitations but does not answer. This analysis answers it for W158.

**Concrete deliverable.** For each of the 11 W158 questions, fit the same regression on (a) Pew W158 weighted respondents and (b) the synthetic panel, then compare coefficients with bootstrap CIs. Output a per-question coefficient comparison table plus a single summary figure.

**Bounds on the claim.** This is one Pew wave, one synthetic panel, one set of covariates. The comparison can confirm or refute whether the topline-level diagnostics extend to the regression layer; it cannot prove generalizable coefficient fidelity across other surveys or other panels.

## 2. Data substrate (verified 2026-05-19)

**Pew W158 microdata source state (pre-extension):** the current `build/data/pew/W158_microdata.csv` (100,150 long-format rows, 9,593 respondents × 11 questions, refused/DK dropped) carries only `age`, `race`, `education`, `party` as demographics. The original SPSS bundle has the richer set we need.

**Pew W158 microdata target state (v4 extension, required before running):** re-converted CSV with 8 demographic columns by extending `data/pew/W158_spec.json` and `scripts/convert_pew.py` to keep `F_GENDER`, `F_CREGION`, `F_IDEO`, `F_RELIGCAT1` alongside the existing 4 axes. Verified all 4 columns exist in the SPSS bundle. Verified F_RELIGCAT1 value labels = `{1: Protestant, 2: Catholic, 3: Unaffiliated, 4: Other, 99: Refused}` (n=57 Refused respondents to be dropped from religion-using regressions per Pew convention).

- Q4 is form-split (~4,800 respondents); other questions have ~9,500.

**Synthetic panel** (`out/stage_b/W158_n1000_probvec_20260516_v1/`):
- `synth_responses.parquet`: 11,000 rows (1,000 jurors × 11 questions), 0 missing
- `trait_vectors.parquet`: 1,000 jurors × 107 columns including all richer traits
- Synth-side covariates available beyond the 4 Pew has: religion, religiosity, ideology, media diet (primary + slant), household composition, life-stage transitions, gender (SEX), region, income (PUMS HHINCOME).

**Implication for covariate selection.** The comparison must use only the 4 covariates BOTH datasets carry: **age, race, education, party**. This is a real constraint and a real limitation; documented as such in the article.

## 3. Decision: covariate set (revised v4 — 8 covariates primary)

**Primary test: 8-covariate shared set.** Confirmed 2026-05-19 that all four additional covariates are available in the Pew W158 SPSS bundle (`F_GENDER`, `F_CREGION`, `F_IDEO`, `F_RELIGCAT1`) and all four are already in the synth panel's trait vectors. Extending the Pew converter to keep these is a ~1-hour task (already factored into the cost estimate).

| Covariate | Pew SPSS column | Synth column | Buckets |
|---|---|---|---|
| age | F_AGECAT | age_bucket | 18-29 / 30-44 / 45-64 / 65+ |
| race | F_RACETHNMOD | race_bucket | White-NH / Hispanic / Black / Asian-Other |
| education | F_EDUCCAT | education_bucket | <HS / HS / SomeCollege/AA / BA+ |
| party | F_PARTYSUM_FINAL | political_party | D / R / I |
| gender | F_GENDER | SEX | Male / Female |
| region | F_CREGION | region_bucket | NE / MW / S / W |
| ideology | F_IDEO | political_ideology | very_liberal / liberal / moderate / conservative / very_conservative |
| religion | F_RELIGCAT1 (4-way condensed) | religion (mapped to 4-way) | Protestant / Catholic / Unaffiliated / Other |

Reference levels (same on both sides; locked in code constants):
age=18-29, race=White-NH, education=BA+, party=I, gender=Male, region=NE, ideology=moderate, religion=Unaffiliated.

Total dummy coefficients per regression: 3 age + 3 race + 3 education + 2 party + 1 gender + 3 region + 4 ideology + 3 religion = **22 coefficients per regression**.

**Sensitivity test: 4-covariate model** (age, race, education, party only). Documents how much of the apparent agreement is driven by the richer covariates closing the OVB hole that v3's all-4-covariate plan would have left open. If primary and sensitivity results diverge sharply, that itself is a Bisbee-relevant finding (the synth panel reproduces broad demographic structure but breaks down when richer covariates resolve subgroup heterogeneity).

**Religion mapping (verified against SPSS labels 2026-05-19).** Pew F_RELIGCAT1 has 4 categories: `{Protestant, Catholic, Unaffiliated, Other}` (plus Refused=99, dropped). Synth's `religion` column has 16 categories. Locked mapping:
- `protestant_evangelical + protestant_mainline + protestant_historically_black` → "Protestant"
- `catholic` → "Catholic"
- `nothing_in_particular + agnostic + atheist` → "Unaffiliated"
- `jewish + muslim + hindu + buddhist + latter_day_saints_lds + orthodox_christian + other_christian + other_world_religion + other_faith_or_spiritual` → "Other"

Mapping locked in code constant `RELIGION_4WAY_MAP`. Failure of any synth value to map → loud error, exclude juror, document.

**Religion-mapping known limitation (load-bearing for Q9 astrology).** Pew F_RELIGCAT1's "Other" bucket lumps LDS, Orthodox, Jewish, Muslim, Buddhist, Hindu, and "Other Christian" together. These groups have heterogeneous astrology-belief base rates (Hindu and Buddhist accepting; LDS and Orthodox skeptical). Both Pew and synth lose the same heterogeneity at the F_RELIGCAT1 level — comparison validity holds, but the religion coefficient for Q9 underestimates the true heterogeneity of astrology belief across non-Christian-non-secular respondents. A finer F_RELIG-based regression (11 categories) is future work; it would create sparse-cell problems at synth n=1,000 for several categories (Hindu, Buddhist, etc.).

**Ideology validation.** Pew F_IDEO is a 5-point scale that matches synth's `political_ideology` 5 buckets exactly. Direct passthrough. Loud-fail if either dataset has values outside the 5-bucket set.

## 4. Decision: regression specifications (revised v4 — one-vs-rest fractional logit)

**Primary model: one-vs-rest weighted fractional logit per response option.**

Earlier drafts proposed ordered logit + multinomial logit + binary logit across 11 questions, which creates a lot of avoidable surface area (proportional-odds assumptions, multinomial convergence, mixed coefficient scales, custom optimizer risk per model type). Cleaner primary test: fit `P(option_k selected)` as a separate weighted binary/fractional logit for every response option k across all 11 questions, with the same 8-covariate specification on both Pew and synth.

**This produces:**
- One common coefficient scale across all questions × all options (log-odds)
- No ordinal assumption to test (avoids Brant tests + proportional-odds validation)
- No multinomial convergence issues
- Pearson r is meaningful across all coefficients globally (same units throughout)
- Each option's coefficients independently testable

**Per-side likelihood family:**
- **Pew side:** binary observed responses → standard binary logit with `sample_weight=pew_weight`
- **Synth side:** for option k, the synth dependent variable is `juror_probvec[k]` ∈ [0, 1] — a fractional outcome, not a binary event. Use fractional logit (Papke & Wooldridge 1996): quasi-binomial likelihood with logit link, point estimates identical to binary logit's MLE on the same logit-link family. Implementation: scipy.optimize.minimize on the quasi-binomial log-likelihood `sum(w * [y * log(p) + (1-y) * log(1-p)])` where `y` is now in [0,1] not {0,1}. This is mathematically Bernoulli's log-likelihood evaluated at fractional y; for fractional y this is the QMLE that Papke & Wooldridge proved is consistent under correctly specified mean.
- **Both sides produce comparable log-odds coefficients on the same scale.** This is the entire point of the v4 redesign.

**Total response options across 11 questions:**

| Q | Options | Regressions |
|---|---|---:|
| Q1 climate impact | A great deal / Some / Not too much / Not at all | 4 |
| Q2 climate cause | A great deal / Some / Not too much / Not at all | 4 |
| Q3 climate policy | Help / Hurt / Make no difference | 3 |
| Q4 sci confidence | Great deal / Fair amount / Not too much / No confidence | 4 |
| Q5 sci policy role | Better / Worse / Neither | 3 |
| Q6 COVID restrictions | More / Fewer / About right | 3 |
| Q7 school closures | Too long / Not long enough / About right / Never closed / Not sure | 5 |
| Q8 vaccine | Probably get / Probably not / Already received | 3 |
| Q9 astrology belief | Yes / No | 1 (binary; second option redundant) |
| Q10 horoscope frequency | Daily / Weekly / Monthly / Yearly / Never | 5 |
| Q11 police confidence | Great deal / Fair amount / Not too much / No confidence | 4 |
| **Total options** | | **39 per dataset** |

39 regressions per dataset × 2 datasets = **78 model fits per main result, plus bootstrap (1000 iterations × 78 = 78,000 fits)**. Each fit is small (22 dummy covariates, n=9,593 Pew / n=1,000 synth). Compute-feasible in ~15-30 min total via L-BFGS-B.

**Coefficient count:** 22 coefs × 39 regressions = **858 per-coefficient comparisons** (substantial sample size for aggregate metrics — addresses multiple-testing concerns by relying on rates rather than per-coef significance).

**Secondary (robustness check):** fit the same one-vs-rest specification on the synth panel's deterministic post-hoc sampled responses (instead of the probvecs). If the primary (probvec) and secondary (sampled) results converge, the probvec → sample step is faithful. If they diverge, the divergence is itself informative about the hash-sampler's contribution.

## 5. Decision: estimation

### 5a. Library + estimator (v4 — collapsed to a single function)

**v3 had three custom scipy implementations** (one per model family: binary / multinomial / ordered). **v4 collapses these to one function** because the v4 model family is one-vs-rest fractional logit only — no ordered logit, no multinomial logit.

**Single function: `weighted_fractional_logit(X, y, w, alpha=0)`.** Handles both Pew (y ∈ {0, 1} binary observed) and synth (y ∈ [0, 1] probvec value) cases — the quasi-binomial log-likelihood is identical in form; only the y values differ. Coefficients are log-odds in both cases. Implementation sketch:

```python
def weighted_fractional_logit(X, y, w, alpha=0):
    # Weighted quasi-binomial NLL with logit link.
    # Pew: y binary (0/1).  Synth: y fractional in [0, 1].
    # Coef interpretation identical: log-odds per covariate unit.
    def neg_ll(beta):
        eta = X @ beta
        p = np.clip(1 / (1 + np.exp(-eta)), 1e-12, 1 - 1e-12)
        ll = w @ (y * np.log(p) + (1 - y) * np.log(1 - p))
        return -ll + 0.5 * alpha * (beta @ beta)
    result = scipy.optimize.minimize(
        neg_ll, x0=np.zeros(X.shape[1]), method='L-BFGS-B', jac=False
    )
    # Numerical Hessian → SE
    hess = nd.Hessian(neg_ll)(result.x)
    cov = np.linalg.inv(hess)
    return {
        'coef': result.x,
        'se': np.sqrt(np.diag(cov)),
        'converged': result.success,
        'hess_cond': np.linalg.cond(hess),
    }
```

~50 lines including the SE computation. Single fit ~10ms on n=10K with 22 covariates. Total bootstrap compute: 78,000 fits × 10ms ≈ 13 minutes.

**Theoretical justification for fractional logit on synth probvecs:** Papke & Wooldridge (1996) prove that the binary logit log-likelihood evaluated at fractional y (instead of binary y) is a consistent QMLE for `E[y | X]` under correctly specified mean. The coefficient interpretation is identical to binary logit. This is the right primitive for "what is the LLM's expected probability of selecting option k for jurors with these covariates."

**Assertion checks per fit:**
- `result.success` is True
- `hess_cond < 1e10`
- No coef SE > 1e3
- Failures: `excluded_reason` set in JSON, regression dropped from comparison

**Weighting:** weights enter the log-likelihood directly via `w`. Continuous survey/raked weights handled correctly (which is the bug v1/v2 hybrid approaches all stumbled on).

**Penalization:** L2 alpha=0.01 on synth fit; Pew unpenalized (alpha=0). Spread-compression sanity check (§6) runs Pew also at alpha=0.01 to verify the asymmetric penalty doesn't bias the Pearson r.

**Weighting interpretive note for the article.** Pew `weight` is a calibrated survey weight (probability of selection inverted, post-stratified to population marginals via Pew's full methodology). Synth `weight` is our raked analysis weight (calibrated to ACS marginals on 4 axes via IPF, capped [0.33x, 3x]). These are not the same procedure but both target "the weighted sample mirrors the US adult population on the calibration axes." Document explicitly; do not claim equivalence.

### 5b. Bootstrap procedure (v4 — primary one-stage on probvecs, secondary two-stage on sampled responses)

**Primary analysis (synth probvec outcome): one-stage bootstrap on both sides.**

Because the v4 primary uses synth probvecs directly as the fractional dependent variable (not post-hoc sampled responses), the within-juror sampling variance is no longer relevant — the probvec IS the data, not a sample from the data. Both bootstraps are one-stage:

- **Pew:** resample respondents with replacement; refit; 1000 iterations; 90% percentile CI.
- **Synth primary:** resample jurors with replacement; refit on the resampled probvec-as-y frame; 1000 iterations; 90% percentile CI.

**Secondary analysis (synth sampled-response outcome): two-stage bootstrap on synth.**

For the robustness check, the synth y is the deterministic post-hoc sampled response (binary 0/1). Here the within-juror sampling variance IS relevant. Bootstrap:

1. Resample jurors with replacement
2. For each resampled juror, re-draw their response from their stored probvec
3. Refit
4. 1000 iterations; 90% percentile CI

This is the two-stage bootstrap from v2 — it stays in v4 but is restricted to the secondary/robustness analysis. The primary analysis (probvec direct) does not need it.

**Probvecs are in `synth_responses.parquet` as the `probabilities_json` column** — already persisted, ready to use for both primary (as continuous y) and secondary (as redraw distribution).

**Reader-expectation note (kept from v3):** for the secondary two-stage bootstrap, CIs will be wider on questions where the LLM emits higher-entropy probvecs. This is the inverse of casual expectation (LLM-confident questions get tighter CIs in the secondary). Wide synth CIs on a given question should be read as model-expressed uncertainty being honestly propagated, not as model failure.

### 5c. Penalization (revised in review round 1)

The original plan said "L2 penalty on both sides." Review correctly flagged: penalizing Pew biases comparison metrics toward apparent agreement (both penalized toward zero looks like smaller divergence).

**Corrected:**
- L2 penalty (alpha=0.01) on **synth only**. Synth at n=1,000 has sparse cells that need regularization.
- Pew fit is unpenalized (alpha=0). Pew at n=9,593 has no sparse-cell problem.
- Document the asymmetry in the article; this is the methodologically defensible move.

### 5d. Reference levels (locked above, restated)

Same reference levels on both sides, locked in code as constants:
- age=18-29, race=White-NH, education=BA+, party=I

This is non-trivial. Different reference levels would produce different coefficients that look like disagreement when they're just different parameterizations. New step `validate_response_strings()` will fail loud if either dataset has a level not in `EXPECTED_BUCKETS`.

### 5e. Convergence handling (revised in review round 1)

Original plan: "exclude question on convergence failure." Review correctly flagged: this is underspecified. Convergence can fail in non-explicit ways.

**Corrected gate:**
- After each fit, check `model.mle_retvals['converged']` is True (statsmodels) or `model.n_iter_ < model.max_iter` (sklearn).
- Check Hessian condition number < 1e10. Higher → numerical instability, exclude.
- Check no coefficient SE exceeds 1e3 (typical separation-failure signature).
- Failures excluded from comparison with explicit JSON-level `excluded_reason` field.

## 6. Decision: comparison metrics (v4 — simplified for one-vs-rest, with zero-coef rule + standardized delta)

All v4 coefficients are on the same log-odds scale (one-vs-rest fractional logit, identical link function on both sides). The mixed-scale problem from v3 is gone. Comparison metrics become more direct:

**Per-coefficient measures:**

1. **Sign agreement.** Does the synth coefficient sign match Pew?
2. **Magnitude difference.** `synth_coef - pew_coef`, in log-odds units.
3. **Standardized delta** (new in v4): `|synth_coef - pew_coef| / pooled_bootstrap_sd`. Normalizes by the bootstrap uncertainty so a 0.1 log-odds difference is treated differently when SE=0.05 vs SE=0.5.
4. **90% CI overlap.** Do Pew CI and synth CI overlap?

**Zero-coefficient handling (new in v4):**
Sign flips around zero are noise, not meaningful failures. Pre-registered exclusion rule:
- A coefficient is "meaningful" iff `|pew_coef| >= 0.10` AND the Pew 90% CI does not cross zero.
- Coefficients where Pew is near-zero with CI crossing zero are reported separately as "near-zero coefficients" with their own summary metrics (different threshold structure), not mixed into the primary sign-agreement / CI-overlap calculation.

**Aggregation strategy (revised v4.1).** One-vs-rest coefficients across response options within a question are coupled (the same juror appears in K regressions, one per option); multi-option questions (Q7 with 5 options, Q10 with 5) contribute many more coefficients than binary Q9. A naive pooled Pearson r across all 858 coefficients would over-weight Q7/Q10 and under-weight Q9. Two-level macro-averaging primary; pooled secondary.

**Primary aggregation (macro, recommended):**
- Compute Pearson r at the **(question, option)** level — one r per (question, option) pair across the 22 covariate coefs that pair carries. 39 r values total.
- Compute median per-question r — for each of 11 questions, median of its constituent (question, option) rs.
- Headline summary stat: **median of per-question rs (11 values)**. Treats Q9 (1 option) equally to Q7 (5 options).
- Same macro logic for sign-agreement, CI-overlap, standardized delta: rates computed per (question, option), then median per question, then median across questions.

**Secondary aggregation (pooled, reported for completeness):**
- Pearson r pooled across all 858 (meaningful) coefficient comparisons.
- Sign-agreement rate, CI-overlap rate, standardized-delta median pooled across all meaningful coefs.
- Reported in JSON; not the primary outcome.

**Per-question summary table** (in JSON): for each of 11 questions, list its constituent (question, option) Pearson rs + the per-question median + the (question, option)-level sign-agreement / CI-overlap / standardized-delta values.

One-sentence outcome template (v4.1 revised): "On the W158 8-covariate one-vs-rest comparison, median per-question Pearson r = Y (across 11 questions); macro sign-agreement rate on meaningful coefficients = X%; macro CI overlap rate = Z%; median standardized delta = D."

**Multicollinearity check (kept from v3):**
- Compute VIF for each covariate dummy on both datasets
- Report in JSON output per coefficient
- Flag any coefficient with VIF > 5 as unreliable for individual interpretation (aggregate metrics remain valid)

**Spread-compression sanity check (kept from v3):**
- Asymmetric L2 (synth penalized, Pew not) compresses synth coef spread toward zero. This biases Pearson r downward.
- **Mitigation:** also fit Pew at alpha=0.01 (same penalty as synth) as a sanity check. Compare the per-question Pearson r under asymmetric vs symmetric L2. Report both in JSON. If they agree (within 0.05), asymmetric is canonical. If they diverge materially, the article reports both with explanation.

**Removed from v3 (no longer needed):**
- Proportional-odds Brant test (no ordered logit in v4)
- Multinomial-vs-binary scale conversion (no multinomial logit in v4)

## 7. Decision: output artifacts

1. **JSON:** `out/stage_b/W158_n1000_probvec_20260516_v1/regression_comparison.json`
   - Per-question per-coef: Pew coef + 90% CI, synth coef + 90% CI, sign agreement, CI overlap, magnitude diff
   - Per-question summary stats (correlation, sign-agreement rate, CI-overlap rate)
   - Overall summary stats

2. **Figure 6:** `docs/figures/fig6_regression_coefficient_comparison.png` (v4 — single scatter, faceted by question)
   - With v4's unified log-odds scale across all 39 regressions, the original "single scatter" design that v3 ruled out is now actually correct: all points are on the same scale.
   - **Design: scatter of Pew coef (x) vs synth coef (y), faceted by question (3x4 grid of panels, 11 panels + 1 legend cell).** Each panel: ~22 points (one per coefficient in that question's 22-covariate dummy matrix, aggregated across response options — or, more diagnostically, ~22 × K_options points colored by option). Diagonal y=x reference per panel. Per-panel Pearson r in panel title.
   - Color coding within panel: meaningful coefs as filled circles; near-zero coefs as hollow circles (so the eye can ignore them when assessing fit).
   - Flags: coefficients where signs disagree get red outline; coefficients where 90% CIs don't overlap get bold outline.
   - Figure title: overall median per-question r + sign-agreement rate + CI-overlap rate.
   - **Supplementary: per-question forest plot** as a follow-on artifact if any individual question carries unusual rhetorical weight in the writeup. Decide after fitting.

## 8. Decision: pre-registration commitment (v4 — numeric thresholds locked)

To preserve epistemic integrity:

- This plan is locked BEFORE any regression is fit on the synth panel.
- The covariate set, model specifications, reference levels, weighting approach, bootstrap procedure, comparison metrics, **and numeric pass/fail thresholds** are all decided here.
- Outcomes are reported as findings. Failures are not bug-hunted away.
- The plan and the resulting code are committed to git BEFORE the analysis runs. The git history is the pre-registration.

### Locked numeric thresholds (v4)

On **meaningful coefficients only** (Pew |coef| ≥ 0.10 AND Pew 90% CI does not cross zero):

| Metric | Failure | Partial | Success |
|---|---|---|---|
| Sign agreement | < 70% | 70-85% | > 85% |
| Median per-question Pearson r | < 0.40 | 0.40-0.70 | > 0.70 |
| CI overlap rate | < 60% | 60-80% | > 80% |
| Standardized delta (median) | > 2 | 1-2 | < 1 |

**Overall pass/fail criterion (pre-registered):**
- **Success:** all four metrics in "success" band.
- **Partial:** at least one in "success" AND none in "failure". OR if exactly one is in "failure" with the other three in "success" (single-metric outlier).
- **Failure:** two or more metrics in "failure" band.

**Outcome-language commitment (pre-registered, written into the script as JSON output).**

The PRIMARY analysis tests synth probvecs (the LLM's emitted probability surface) against Pew observed responses. The SECONDARY analysis tests synth post-hoc sampled responses (closer to what Bisbee actually tested) against Pew observed responses. Outcome language is calibrated to which analysis is being reported: "Bisbee's critique" applies to realized responses, not expected probabilities.

**Primary (probvec) outcome language:**
- Success: "On the W158 8-covariate one-vs-rest comparison, synth panel expected-probability coefficients reproduce Pew observed-response coefficients. Coefficient divergence is not observed on the expected-probability surface at this scope."
- Partial: "Mixed result. Synth panel expected-probability coefficients reproduce some but not all of Pew's coefficient structure. Details in per-question breakdown."
- Failure: "Coefficient divergence observed on the expected-probability surface: synth panel expected-probability coefficients diverge from Pew observed-response coefficients on multiple metrics."

**Secondary (sampled-response) outcome language — the Bisbee-equivalent reading:**
- Success: "On the secondary realized-response analysis, synth sampled-response coefficients reproduce Pew observed-response coefficients. Bisbee's regression-coefficient critique does not replicate on the W158 synth panel at this scope."
- Partial: "Mixed result on the secondary realized-response analysis. The Bisbee critique partially replicates."
- Failure: "Bisbee's regression-coefficient critique replicates on the W158 synth panel on the secondary realized-response analysis: sampled-response coefficients diverge from Pew on multiple metrics."

**Article-level reading:** report both primary and secondary outcomes. The PRIMARY tests whether the LLM's calibration of subgroup associations matches Pew; the SECONDARY tests whether the post-hoc-sampled panel responses reproduce Pew. Bisbee tested the latter. Divergence between the two is itself informative (would mean the LLM "knows" the right associations but the sampler distorts them; consistent with the cross-model canary finding that bias lives in probvec calibration not the hash sampler).

**Exceptions to lock-down (must be documented in writeup if invoked):**
- If a regression fails to converge on a specific question (e.g., perfect separation on synth despite L2 penalty), document the failure and exclude that regression from the comparison. Do not change the specification to force convergence.
- If a covariate has zero observations on one side of a specific question, document and proceed with the smaller cell. Do not re-bucket.
- If the 4-covariate sensitivity model produces a materially different headline outcome from the 8-covariate primary (different overall pass/fail band), report both with explicit attribution to which covariates moved the result.

## 9. Risks and mitigations (v4.1 — cleaned of v2/v3 debris)

| Risk | Mitigation |
|---|---|
| Sparse cells on synth (n=1,000), especially Asian/Other × <HS × Republican etc. | L2 penalty (alpha=0.01) on synth only; bootstrap CIs reflect uncertainty appropriately |
| Sample-size asymmetry (Pew 9,593 vs synth 1,000) | Pew CIs tighter by construction; CI-overlap metric reflects this; document, do not equalize |
| Perfect separation in logit fits | L2 penalty + Hessian-condition-number gate (<1e10) + no SE > 1e3; failures excluded with explicit JSON `excluded_reason` and dropped from aggregate metrics |
| Multiple testing across 858 coefficients | Report aggregate metrics (macro median r, sign-agreement rate, CI-overlap rate, standardized delta median) rather than per-coef significance tests; meaningful-coef filter (Pew \|coef\| ≥ 0.10) further restricts the comparison surface |
| Pew vs synth weighting are different procedures | Document explicitly in the article; do not claim equivalence |
| Reference-level confusion | All 8 reference levels locked in code constants; `validate_response_strings()` compares Pew and synth response-text sets per question before fitting; loud-fail on mismatch |
| Weight argument misuse (recurring in libraries) | scipy custom `weighted_fractional_logit()` puts weights into the log-likelihood directly; assertion check verifies fitted `nobs == unweighted_N` not sum of weights |
| Synth-secondary bootstrap missing probvec uncertainty | Two-stage bootstrap for synth-secondary only (resample jurors + redraw responses from probvecs); synth-primary one-stage on probvec is correct because probvec IS the data, not a sample from it |
| L2 penalizing Pew would bias comparison toward agreement | L2 only on synth; Pew unpenalized; symmetric-L2 sanity check produces a second comparison reading to detect spread-compression bias |
| Coefficient one-vs-rest coupling across response options | Macro-average aggregation: (question, option) → per-question median → median across questions; pooled metric reported as secondary |
| Multicollinearity in 8-covariate dummies | VIF reported per coefficient in JSON; flag VIF > 5 as unreliable for individual interpretation; aggregate metrics remain valid |
| Religion 4-way condensation loses heterogeneity for Q9 astrology | Documented in §3 religion-mapping limitation; both Pew and synth lose the same heterogeneity so comparison validity holds; finer F_RELIG mapping is future work |
| Outcome language overclaim risk | Primary outcome language (probvec) softened to "expected-probability surface"; Bisbee-equivalent language reserved for the sampled-response secondary |
| Convergence failures going undetected | `result.success` + Hessian condition number < 1e10 + max coef SE < 1e3 gate per fit |

## 10. Time + cost estimate (v4.1, honest)

- Pew converter extension (`scripts/convert_pew.py` + `data/pew/W158_spec.json`): ~1 hour
- Re-run converter to regenerate `W158_microdata.csv` with 8 demographic columns: ~5 min
- Implement `weighted_fractional_logit()` + bootstrap loop + main orchestrator: ~2-3 hours
- Bootstrap pass (1000 iterations × 78 model fits primary + 78 secondary + 78 spread-compression sanity): ~20-40 min compute
- Comparison metrics + JSON output: ~1 hour
- Figure generation (single faceted-by-question scatter): ~45 min
- **Total: 6-8 hours actual; $0 API spend**

## 11. What stays out of scope (v4.1)

- Income covariate. Pew has F_INC_TIER2 but synth's PUMS-derived HHINCOME would need a separate bucketing step to align. Out of scope for this pass; the 8-covariate set is the locked primary.
- Finer religion resolution beyond F_RELIGCAT1 4-way. Pew F_RELIG has 11 categories but several (Hindu, Buddhist) would have sparse synth cells at n=1,000. Future work.
- Cross-wave regression comparison (W163, W161 not fired).
- Time-reproducibility of regression coefficients (would require a +30-day re-poll).
- Non-Claude model comparison (Bisbee tested GPT-3.5; we tested Sonnet 4.6 + Opus 4.5).
- Causal inference. Coefficients are descriptive associations, not causal effects.

---

## Reviewer log

### v1 → v2: code-review-agent pass #1 (2026-05-19)

A fresh code-review-agent ran a methodological-correctness pass. Findings:

| # | Severity | Issue | Resolution |
|---|---|---|---|
| 1 | P1 | `freq_weights` in statsmodels is for integer counts, not continuous survey/raked weights. Original plan would silently inflate effective N. | §5a rewritten: sklearn for binary + multinomial; var_weights approximation + caveat + sanity check for ordered; `model.nobs == unweighted_N` assertion. |
| 2 | P1 | One-stage bootstrap on synth ignores within-juror probvec sampling variance — understates synth CIs. | §5b: two-stage bootstrap for synth (resample jurors + redraw from probvecs); Pew stays one-stage (responses are observations). |
| 3 | P2 | Pearson r across all coefs mixes log-odds / proportional-odds / log relative-risk — different scales. | §6 revised: per-question Pearson r; report median of per-question rs as summary. Cutpoints excluded from coef comparison. |
| 4 | P2 | Q5 reference string is the full Pew survey wording; silent failure if synth response strings don't match exactly. | New `validate_response_strings()` step compares response sets on both datasets per question; fail loud on mismatch. |
| 5 | P2 | L2 penalty on both sides biases comparison toward agreement (both shrunk toward zero). | §5c: L2 only on synth; Pew unpenalized; documented asymmetry. |
| 6 | P2 | Proportional-odds assumption not tested; violation on one side and not the other invalidates ordered-logit comparison. | §6: Brant test or score test added to output for each ordered-logit question on both datasets; flag mismatches. |
| 7 | P3 | Convergence-failure handling underspecified — exclusion alone isn't enough; partial-convergence and degenerate Hessian go undetected. | §5e: gate on `mle_retvals['converged']` + Hessian condition number < 1e10 + no SE > 1e3. |
| 8 | P3 | VIF not in output; multicollinearity in race × education × party will destabilize individual coefs. | §6: VIF reported per coefficient in JSON; flag VIF > 5 as unreliable for individual interpretation. |

All 8 findings addressed in v2.

### v2 → v3: code-review-agent pass #2 (2026-05-19)

A second code-review-agent ran a second-round pass on v2, asked to verify the first round's fixes were correctly addressed and identify anything missed. Findings:

| # | Severity | Issue | Resolution |
|---|---|---|---|
| 1 | P1 | sklearn / statsmodels hybrid v2 still introduces library-mixing problems: sklearn always penalizes by default, removing penalty requires hacks, parameterization differs across libraries. Three penalization regimes across 22 models being compared on one scatter. | §5a rewritten v3: scipy.optimize.minimize-based custom weighted log-likelihood for all three model types. ~120 lines total, one library, one convention. |
| 2 | P1 | 4-covariate constraint rigs comparison toward agreement on exactly the questions where synth fails. Both Pew and synth share OVB on ideology/religion/media diet (the canary-confirmed loci of synth bias). Comparison could read "high agreement" while quietly demonstrating Bisbee's mechanism. | **ESCALATED TO AUTHOR** as §13 Q1. Recommendation: extend Pew converter to include religion + ideology + gender + region; rerun comparison on the richer covariate set. Adds ~1 hour to overall work. |
| 3 | P1 | Pre-registration is not binding because the disconfirmation threshold (§13 Q2 in v2) was left open for post-hoc decision. Lakatos hatch. | **ESCALATED TO AUTHOR** as §13 Q2. Proposed numeric thresholds (sign agreement < 70% / 70-85% / > 85%; per-question median Pearson r < 0.40 / 0.40-0.70 / > 0.70; CI overlap < 60% / 60-80% / > 80%) for lock-down in v3. |
| 4 | P2 | Two-stage bootstrap will produce wider synth CIs on high-entropy questions — inverse of casual reader expectation. | §5b: explicit reader-expectation note added. |
| 5 | P2 | Single scatter across all 22 models' coefs mixes incomparable scales (log-odds / log relative-risk / proportional-odds). | §7: figure design revised to 3-panel faceted scatter (one panel per model type) + supplementary per-question forest plot. |
| 6 | P2 | Asymmetric L2 (synth penalized, Pew not) biases Pearson r downward via spread compression on synth side. | §6: spread-compression sanity check added — fit Pew also at alpha=0.01 as control; report both asymmetric and symmetric r; flag if they diverge materially. |
| 7 | P3 | Article-level reading risks contradicting the structural-bias narrative if high regression-coef agreement reads as "Bisbee answered favorably" next to existing structural-failure sections. | Outcome-language commitment specifies an integrating reading: coef agreement on the covariate slice is consistent with structural marginal-error failure because the latter is in latent probvec calibration that demographic covariates don't fully resolve. |
| — | Risk summary | Round 2's biggest-risk paragraph: **4-covariate constraint + open disconfirmation threshold = result reads favorably regardless of validity.** Both issues escalated to author (§13 Q1 + Q2). | — |

7 findings; 5 addressed in v3, 2 escalated to author.

- **Drafted by:** primary agent, 2026-05-19
- **Code-review-agent pass #1:** complete, 8 findings (2 P1, 4 P2, 2 P3), all integrated → v2
- **Code-review-agent pass #2:** complete, 7 findings (3 P1, 3 P2, 1 P3), 5 integrated → v3; 2 escalated to author
- **Author review:** complete (v3 → v4)
- **Author cleanup pass:** complete (v4 → v4.1); 5 findings, all integrated
- **Status:** v4.1 LOCKED, READY FOR EXECUTION

### v4 → v4.1: author cleanup pass (2026-05-19 evening)

Five v4 inconsistencies were flagged for cleanup before execution. All addressed:

| # | Severity | Issue | Resolution in v4.1 |
|---|---|---|---|
| 1 | P1 | §2 still stated "only 4 covariates available," contradicting v4's 8-covariate primary. Other sections still described the plan as 4-covariate with richer covariates as "future work." | §2 rewritten: source state (pre-extension, 4-cov) explicitly distinguished from target state (post-extension, 8-cov verified in SPSS). §11 scoped to "income + finer religion still future work" only. |
| 2 | P1 | Outcome language overclaimed: primary uses probvec, but "Bisbee critique does not replicate" applies only to realized responses. Bisbee tested sampled responses, not expected probabilities. | §8 + script constants split into `OUTCOME_TEMPLATES_PRIMARY` (probvec → "expected-probability surface" language) and `OUTCOME_TEMPLATES_SECONDARY` (sampled-response → Bisbee-equivalent language). Article reports both surfaces; primary tests calibration; secondary is the Bisbee-equivalent reading. |
| 3 | P2 | Global Pearson r aggregation was naive: one-vs-rest coefs across response options within a question are coupled; high-option questions over-contribute. | §6 rewritten: macro-average primary aggregation (per-question median r → median of per-question medians); pooled r reported as secondary. Same macro logic for sign-agreement, CI-overlap, standardized delta. |
| 4 | P2 | §9 risks + §10 time estimate still carried v2/v3 debris ("statsmodels/sklearn," "proportional-odds tests," "22 models," "5-7 hours," "4-covariate dummies"). | §9 rewritten with v4.1 architecture (scipy custom, 39 regressions, 8 covariates, macro-average aggregation, religion-mapping limitation explicit). §10 retimed to 6-8 hours including Pew converter extension. |
| 5 | P2 | Religion mapping was locked at "Other religion" without SPSS label verification. F_RELIGCAT1 actually uses "Other" (not "Other religion") and condenses very coarsely (LDS/Orthodox/Jewish/Muslim/Buddhist/Hindu all in one bucket — load-bearing for Q9 astrology). | Verified SPSS labels via pyreadstat (Pew F_RELIGCAT1 = {Protestant, Catholic, Unaffiliated, Other, Refused}; 57 Refused respondents to drop). Script constants corrected (`EXPECTED_BUCKETS['religion']` and `RELIGION_4WAY_MAP`). §3 expanded with "religion-mapping known limitation" note flagging Q9-specific astrology heterogeneity loss. |

5 findings; all integrated. No new escalations.

### Cumulative reviewer-finding tally

- v1 → v2 (code-review-agent pass #1): 8 findings, all integrated
- v2 → v3 (code-review-agent pass #2): 7 findings, 5 integrated + 2 escalated to author
- v3 → v4 (author review): 6 findings, all integrated
- v4 → v4.1 (author cleanup): 5 findings, all integrated
- **Total: 26 reviewer findings across 4 rounds; all addressed in v4.1.**

**Status: v4.1 LOCKED. Pre-registration binding via git commit. Ready for execution.**

### v3 → v4: author review (2026-05-19)

Third reviewer pass; the substantive direction change. Findings:

| # | Severity | Issue | Resolution |
|---|---|---|---|
| 1 | P1 | v3 still locked the 4-covariate slice as primary despite the round-2 escalation; recommendation was option B but plan body wasn't updated. Too weak as the only test; could read favorably while hiding OVB structure in ideology/religion/media-diet. | §3 rewritten v4: 8-covariate primary (age, race, education, party + gender, region, ideology, religion-4-way). All four additions confirmed in Pew W158 SPSS bundle. 4-covariate kept as sensitivity check. |
| 2 | P1 | v3 model family (ordered + multinomial + binary) creates avoidable surface area: prop-odds assumptions, multinomial convergence, mixed scales, custom optimizer risk per family. | §4 collapsed v4: one-vs-rest weighted fractional logit per response option. Single log-odds scale across all 39 regressions. Eliminates ordinal assumption, multinomial complexity, mixed-scale Pearson r issue. §5a collapsed to a single `weighted_fractional_logit()` function (~50 lines vs v3's ~120). |
| 3 | P1 | v3 primary used post-hoc sampled responses on the synth side, throwing away signal. The actual finding the article makes is that bias is in the probvec calibration; compare probvec directly. | §4 + §5b v4: PRIMARY uses synth probvec as fractional y (Papke & Wooldridge 1996 QMLE for E[y|X]); SECONDARY uses sampled responses as robustness check. Primary bootstrap one-stage on probvecs; secondary two-stage on sampled responses (kept from v3). |
| 4 | P2 | v3 thresholds didn't handle near-zero coefficient sign flips, which are noise not failures. | §6 + §8 v4: zero-coef exclusion rule pre-registered (Pew \|coef\| < 0.10 with CI crossing zero → near-zero set, reported separately). Sign agreement / Pearson r / CI overlap computed on meaningful coefs only. |
| 5 | P2 | v3 lacked a magnitude-normalized comparison metric. | §6 v4: standardized delta added (`\|synth - pew\| / pooled_bootstrap_sd`); pre-registered thresholds median < 1 / 1-2 / > 2. |
| 6 | P2 | v3 figure design was 3-panel faceted scatter (one per model family); collapsed v4 model family makes this unnecessary. | §7 v4: single scatter faceted by question (3x4 grid, 11 panels), all panels on same log-odds scale. Meaningful vs near-zero coefs distinguished visually. Sign/CI failure flags inline. |

6 findings; all integrated into v4. No new escalations.

### Final architecture summary (v4)

- **Pew converter:** extended to keep F_GENDER, F_CREGION, F_IDEO, F_RELIGCAT1 (4-way condensed religion) alongside the existing 4 axes. ~1 hour task before the regression script runs.
- **Primary regression:** one-vs-rest weighted fractional logit on synth probvecs (Papke-Wooldridge QMLE); standard binary logit on Pew observed. Same 8-covariate spec on both. 39 regressions per dataset × 2 sides = 78 model fits primary; bootstrap 1000 iterations = 78,000 total fits. Estimated ~15-30 min compute.
- **Secondary regression (robustness):** same one-vs-rest spec on synth post-hoc sampled responses; two-stage bootstrap. Verifies primary holds under the sampled-response framing the article uses elsewhere.
- **Sensitivity model:** same spec on the 4-covariate set only; quantifies how much of any apparent agreement on the 8-covariate primary is driven by the added 4 covariates.
- **Thresholds locked:** sign agreement, median per-question Pearson r, CI overlap rate, standardized delta — all with success/partial/failure bands pre-registered in §8. Outcome language pre-committed in §8.
- **Figure:** single scatter faceted by question, all coefs on same log-odds scale.

### Cumulative reviewer-finding tally

- v1 → v2 (code-review-agent pass #1): 8 findings, all integrated
- v2 → v3 (code-review-agent pass #2): 7 findings, 5 integrated + 2 escalated to author
- v3 → v4 (author review): 6 findings, all integrated (the 2 escalations resolved + 4 substantive direction changes)
- **Total: 21 reviewer findings across 3 rounds; all addressed in v4.**

**Status: v4 LOCKED. Ready for execution. Pre-registration is binding by virtue of this commit (and the locked scaffold script).**
