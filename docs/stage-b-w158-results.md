---
type: results-summary
project: the-jury
artifact: Stage B W158 v1
run_completed: 2026-05-17
status: complete; marginal-shift analysis + cross-model + option-order canary both landed 2026-05-17 (see `w158-marginal-shift-analysis.md` and `w158-crossmodel-canary-results.md`). Project repositioned toward methods writeup; W163/W161 stay parked.
output_dir: build/out/stage_b/W158_n1000_probvec_20260516_v1/
companion_docs: [w158-marginal-shift-analysis.md, w158-crossmodel-canary-results.md, literature-bisbee-methods-review.md, sanitized-chronology.md, corpus-construction-plan.md]
---

# Stage B W158 v1 — Results Summary

First Stage B credibility-artifact run against Pew ATP Wave 158 (fielded October 21-27, 2024; topics: climate change, COVID-19 retrospective, trust in scientists, spiritual practices including astrology). n=1,000 synthetic jurors, 11 questions, probability-vector polling. Companion to the chronological build log at `sanitized-chronology.md` and the methodology at `corpus-construction-plan.md`.

## TL;DR

- Run completed cleanly (exit code 0) after 18h 8m wall clock.
- 11,000 / 11,000 responses captured. The 410 transient API failures that occurred during a mid-run credit-exhaustion window were all recovered by the failed-row repoll guard. Final missing responses: 0.
- **Coverage rule passed on all 11 questions** at n=1,000.
- **Thresholds failed on all 11 questions**, but the failure mode is not the within-cell variance compression the construction plan was built to defend against.
- **Probability-vector polling substantially mitigated Bisbee-style within-cell variance compression on 10 of 11 W158 questions.** Q9 astrology belief remains the hard failure case.
- Residual failure mode is **systematic marginal directional bias on specific topics** (notably vaccine acceptance, school-closure assessment, astrological belief). This differs from the broad stereotype-center collapse Bisbee identifies.

The artifact does not pass validation overall. It is methodologically valuable because the failure mode shifted from the construction plan's central worry (Bisbee within-cell compression) to a different and more tractable problem class (topic-specific topline shifts).

## Run details

- **Output directory:** `build/out/stage_b/W158_n1000_probvec_20260516_v1/`
- **Files:**
  - `trait_vectors.parquet` — 1,000 jurors x 107 columns (PUMS + bucket axes + sampled traits + variance flags)
  - `expanded_corpus.parquet` — same 1,000 jurors with `narrative` and `expansion_model` columns
  - `synth_responses.parquet` — 11,000 long-format rows (1,000 x 11) with response, reasoning, probabilities_json, prob_sum_before_norm, prob_max, prob_entropy, weight, plus validation axes
  - `validation_results.json` — per-cell Wasserstein + entropy ratio + minority recovery with 1000-iteration bootstrap 90% CIs; coverage rule and threshold reports per question
  - `expected_distribution_diagnostics.json` — per-question latent-calibration distribution vs Pew + per-juror probability-vector stats
- **Polling mode:** probability-vector (`--polling-mode probvec`). LLM returns probability over offered options; the synthetic response is sampled deterministically post-hoc using `sha256(juror_id|question_id|run_seed)` as RNG seed.
- **Wall clock:** May 16 6:52 PM through May 17 1:00 PM (≈18h 8m total). Expansion phase ~5h, polling phase ~13h (slowed by a credit-out window mid-run).
- **Estimated API cost:** ~$50-80 for the Stage B run alone (Anthropic console authoritative; cannot read directly from here).

## Reliability

| Check | Result |
|---|---|
| Final missing responses | **0 / 11,000** |
| Transient failures encountered during run | 410 (all `api_error` during a credit-exhaustion window) |
| Failed-row repoll recoveries | **410 / 410** |
| Per-question failure rate gate (>5% trips) | not triggered (all 0% post-repoll) |
| Overall failure rate gate (>5% trips) | not triggered (0% post-repoll) |

The 4 production guards added before fire (per-question failure gate, failed-row repoll, expected-distribution diagnostics, probvec primitive) all behaved as designed. The credit-out incident was the realistic test of the repoll mechanism; it passed.

## Coverage rule — PASS on all 11 questions

The construction plan specifies the coverage rule as a precondition for validation results to count: at least 80% of top-level cells AND at least 50% of interaction cells must clear the minimum-n thresholds (otherwise the run is reported "underpowered, not measured" rather than passing or failing the thresholds).

| Question | Top-level cells measured | Interaction cells measured | Coverage |
|---|---|---|---|
| Q1 climate impact | 87% | 79% | ✓ |
| Q2 climate human cause | 87% | 79% | ✓ |
| Q3 climate policy economy | 87% | 75% | ✓ |
| Q4 scientist confidence | 87% | 71% | ✓ |
| Q5 scientists policy role | 87% | 79% | ✓ |
| Q6 COVID restrictions | 87% | 79% | ✓ |
| Q7 school closures | 87% | 79% | ✓ |
| Q8 vaccine | 87% | 79% | ✓ |
| Q9 astrology belief | 87% | 79% | ✓ |
| Q10 astrology freq | 87% | 79% | ✓ |
| Q11 police confidence | 93% | 79% | ✓ |

n=1000 is where the coverage rule actually has signal. At n=100 (Stage A and the canaries) every question failed coverage by design.

## Thresholds — fail on all 11, but the breakdown is the result

The three threshold components and the % of measured cells per question that pass each component's CI lower bound:

| Component | Threshold | Pass rate across 11 questions |
|---|---|---|
| Entropy ratio CI lower ≥0.70 | "within-cell variance preserved" | **85-97% of cells for 10 of 11 questions**; Q9 astrology is the outlier at 17% |
| Minority recovery CI lower ≥0.45 | "minority positions recovered" | **79-100% of cells across all 11 questions** |
| Marginal error sigma ≤2σ | "synth and Pew distributions match on each option" | **0-11% of cells across all 11 questions** |

**Overall median entropy ratio across 383 measured cells: 1.035.** Mean 1.026. The synthetic within-cell distributions are as spread as the real Pew within-cell distributions — sometimes more.

### Per-question entropy ratio (median across measured cells)

| Question | Median entropy ratio | % cells with CI lower ≥0.70 |
|---|---|---|
| Q1 climate impact | 0.995 | 94% |
| Q2 climate human cause | 1.037 | 94% |
| Q3 climate policy economy | 0.965 | 85% |
| Q4 scientist confidence | 1.086 | 97% |
| Q5 scientists policy role | 1.029 | 91% |
| Q6 COVID restrictions | 0.988 | 91% |
| Q7 school closures | 1.050 | 94% |
| Q8 vaccine | 1.134 | 94% |
| **Q9 astrology belief** | **0.721** | **17%** |
| Q10 astrology freq | 1.137 | 89% |
| Q11 police confidence | 1.071 | 92% |

Q9 is the one question where Bisbee-style within-cell variance compression persists. The LLM still suppresses attribution of astrological belief in 83% of measured cells even with probability-vector polling and full trait conditioning. This is a topic-specific holdout.

## Marginal error — the actual bottleneck

The thresholds fail because synth distributions are systematically shifted relative to Pew on most questions. Max-abs-error-percentage-point per question (across all options):

| Question | Max abs error (pp) | Reading |
|---|---|---|
| Q5 scientists policy role | **1.8** | matches Pew within 1.8pp |
| Q2 climate human cause | 3.2 | strong |
| Q6 COVID restrictions | 4.2 | strong |
| Q3 climate policy economy | 6.2 | good |
| Q1 climate impact | 7.5 | good |
| Q4 scientist confidence | 8.8 | acceptable |
| Q10 astrology freq | 8.9 | acceptable |
| Q11 police confidence | 10.9 | residual gap |
| Q7 school closures | 12.4 | residual gap |
| Q9 astrology belief | 12.7 | residual gap (compounding the entropy issue) |
| Q8 vaccine | **16.1** | worst (mostly "already received" overshoot) |

7 of 11 questions within 10pp on every option. Q5 matches Pew at canonical option order, but the later cross-model + option-order canary shows that this calibration was order-dependent rather than a stable control. Q8/Q9/Q7/Q11 carry the residual gaps.

## Interpretation

**Bisbee-style variance compression is substantially mitigated, with Q9 astrology as the hard failure case.** The probability-vector polling protocol — eliciting option probabilities per (juror, question) rather than forcing a single committed pick — restored within-cell variance on 10 of 11 W158 questions. The within-cell entropy ratios are at or above 1.0 across most of the surface; the bootstrap CIs on those ratios are tight enough that the threshold (point estimate ≥0.80, CI lower ≥0.70) passes for 85-97% of cells per question on the non-astrology questions.

The mechanism is now grounded in the post-Bisbee distributional-alignment literature, not just in prompt intuition. Meister, Guestrin, and Hashimoto (NAACL 2025) identify a "knowledge-to-simulation gap": LLMs can describe opinion distributions more accurately than they sample from those distributions. W158 v3 is an applied version of that move: ask for the option-probability vector, validate it, then sample externally. The v1/v2 direct-choice canaries reproduced the known variance-collapse pattern; v3 changed the response primitive.

**The residual failure mode is marginal directional bias, not entropy compression.** The synthetic and source distributions have the same shape within each cell, but their modes differ by 6-16pp on most questions. This is structurally different from the Bisbee critique. Bisbee 2024 documents LLMs picking the stereotyped center of each demographic cell with high marginal accuracy while compressing within-cell variance. This run shows the opposite shape: within-cell variance is preserved, but the modal answer is shifted.

Plausible causes of the marginal shift include:
- LLM training-distribution divergence from October 2024 Pew respondents on specific topics (vaccine acceptance, school-closure attitudes, astrological belief)
- A polling-prompt-level bias that systematically tilts toward certain endpoint options regardless of trait conditioning
- A persona-expansion-level bias that produces narratives correlated with particular topical stances

These are distinguishable from each other by inspection of the per-cell shift pattern. That inspection is the next step and requires no further API spend.

**The artifact fails overall validation.** Thresholds fail on all 11 questions, driven by the marginal-error component. The package therefore presents W158 as a diagnostic artifact.

**The artifact is methodologically valuable** because:
1. The coverage rule passed at n=1,000, validating the construction-plan framing that "n=1,000 is the smallest publishable sample" for which the validation cells have real statistical signal.
2. The observed failure mode (marginal directional bias) is a different problem class than the one the construction plan was built to defend against (Bisbee within-cell variance compression). Probability-vector polling addressed the originally feared failure mode. Marginal directional bias needs separate diagnostics.

## Cost + wall clock

| Item | Value |
|---|---|
| Start | 2026-05-16 18:52 |
| End | 2026-05-17 13:00 |
| Wall clock | ≈18h 8m |
| API cost (Stage B alone, estimate) | ~$50-80 |

Anthropic console is authoritative for true totals.

## Follow-up work

The W158 marginal-shift analysis and cross-model + option-order canary have now landed in companion documents. Remaining methods work is narrower:

1. Regression-coefficient comparison against Pew, matching Bisbee's strongest inferential critique.
2. Time-reproducibility slice under the locked probability-vector protocol.
3. Nonsense/placebo question class for settings where ground truth is unavailable.
4. Full expected-probability diagnostics for every validation cell.

W163 and W161 remain parked. The public package centers the W158 diagnostic artifact.
