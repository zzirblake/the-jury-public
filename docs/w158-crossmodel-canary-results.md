---
type: canary-results
project: the-jury
artifact: W158 cross-model + option-order canary
created: 2026-05-17
output_dirs:
  - build/out/stage_b/canary_W158_n200_probvec_sonnet_fwd_20260517_crossmodel/
  - build/out/stage_b/canary_W158_n200_probvec_sonnet_rev_20260517_crossmodel/
  - build/out/stage_b/canary_W158_n200_probvec_opus_fwd_20260517_crossmodel/
  - build/out/stage_b/canary_W158_n200_probvec_opus_rev_20260517_crossmodel/
  - build/out/stage_b/w158_crossmodel_canary_comparison.json
script: build/scripts/compare_crossmodel_canary.py
companion: [w158-marginal-shift-analysis.md, stage-b-w158-results.md, literature-bisbee-methods-review.md, sanitized-chronology.md]
---

# W158 Cross-Model + Option-Order Canary

Paired 2x2 factorial canary at n=200 on a 4-question slice of W158 (Q5 control, Q8 directional, Q9 minority, Q11 fragmentation), permuting polling model (Sonnet 4.6 vs Opus 4.5) x option order (Pew canonical vs reversed). Same expanded corpus reused across all 4 arms so any movement is attributable to model/order, not panel composition.

## TL;DR

1. **Opus 4.5 leaves the main W158 errors largely intact.** At Pew-canonical option order, Opus matches Sonnet within ~3pp on every question on the bias-direction options. The structural failure surface appears Claude-family-level; the same Pew-canonical pattern appears on Opus 4.5. Switching to Opus costs 5-7x more per call. *(Caveat: there is a real model x order interaction, especially on Q5 reversed where Sonnet and Opus diverge by 14pp on "Better" — see Cross-model summary section.)*
2. **Option-order effect is large and question-dependent.** Reversal *destroys* Q5's near-perfect baseline calibration (1.8pp → 12.3pp on Sonnet). Reversal *substantially improves* Q9 astrology (~5pp recovery on both models) and Q11 police (~6pp recovery on both models). Q8 vaccine bias direction is stable but redistributes between the other two options.
3. **The morning's Q11 "LLM over-polarizes police confidence" diagnosis is mostly wrong.** Half-to-most of the Q11 "Fair amount" fragmentation was option-order, not LLM-prior bias. "Fair amount" recovers from 40-43% → 47% on both models under reversal. This is a clean retraction of a prior call.
4. **Q8 vaccine bias is structural and survives both perturbations.** "Probably not" sits at 43-46% on every arm against a Pew 60% rate. The LLM-family prior on vaccine refusal underestimation is the kind of failure that needs ground-truth calibration, not protocol change.
5. **Q9 astrology partially recovers but ~7pp gap is structural.** Best arm (Opus-rev) closes 6.3pp of the 12.7pp Yes-rate suppression, still 6.4pp short of Pew. Bisbee-class minority suppression has a recoverable component (option-order) and a structural component (LLM family prior).
6. **Methodology implication:** option-order randomization per juror should be standard for synthetic respondent panels. One-line change in the polling primitive; effectively free. **Reporting cross-model results should always condition on option order**, because models can differ materially on how they respond to presentation perturbations even when canonical-order outputs look similar.

## Run details

| Arm | Model | Option order | Wall clock | Status |
|---|---|---|---|---|
| 1 | claude-sonnet-4-6 | Pew canonical | 14:14 → 15:14 (60 min) | exit 0 |
| 2 | claude-sonnet-4-6 | reversed | 15:14 → 16:14 (60 min) | exit 0 |
| 3 | claude-opus-4-5 | Pew canonical | 16:14 → 17:20 (66 min) | exit 0 |
| 4 | claude-opus-4-5 | reversed | 17:20 → 18:26 (66 min) | exit 0 |

Per-call latency held steady at ~4.5-4.9s across both models (Opus only modestly slower than Sonnet on probvec calls). Corpus subset = 200 jurors drawn deterministically from the Stage B W158 v1 n=1000 expanded corpus with `random_state=20260515`. Same jurors across all 4 arms.

Total: 4 x 800 = 3,200 polling calls.

## Headline: max-abs expected-distribution error vs Pew

| Question | baseline n=1000 | sonnet_fwd | sonnet_rev | opus_fwd | opus_rev |
|---|---:|---:|---:|---:|---:|
| Q5 scientists policy | 1.8pp | 2.1pp | **12.3pp** | 4.1pp | 8.3pp |
| Q8 vaccine | 16.1pp | 15.1pp | 15.2pp | 14.3pp | 17.0pp |
| Q9 astrology | 12.7pp | 11.7pp | 7.0pp | 9.5pp | **6.4pp** |
| Q11 police | 10.9pp | 11.8pp | 5.6pp | 9.4pp | **5.2pp** |

n=200 sub-sample faithfully reproduces n=1000: sonnet_fwd is within 1pp of baseline on every option of every question. The canary design holds — any movement across the other 3 arms is attributable to model or order, not sample size.

## Q5 scientists policy — option order destroys the calibration

Pew distribution: 43.1% Better / 10.3% Worse / 46.6% Neither.

| Arm | Order | Better | Worse | Neither |
|---|---|---:|---:|---:|
| Pew | — | 43.1 | 10.3 | 46.6 |
| sonnet_fwd | [Better, Worse, Neither] | 43.8 | 11.7 | 44.5 |
| sonnet_rev | [Neither, Worse, Better] | **53.8** | 11.9 | **34.3** |
| opus_fwd | [Better, Worse, Neither] | 40.2 | 14.4 | 45.3 |
| opus_rev | [Neither, Worse, Better] | 39.7 | **18.6** | 41.6 |

**Sonnet recency effect:** "Better" jumps from 43.8% (when presented first) to 53.8% (when presented last). "Neither" drops from 44.5% (last) to 34.3% (first). The Q5 baseline that looked like near-perfect calibration on the morning analysis was order-dependent. Q5 is a poor control because the Pew-aligned topline happens to align with Sonnet's recency-favored option.

Opus is steadier on "Better" (40.2 → 39.7) but inflates "Worse" under reversal (14.4 → 18.6). Different option-order signature.

## Q8 vaccine — bias direction stable across all perturbations

Pew distribution: 24.6% Probably get / 60.1% Probably not / 15.2% Already received.

| Arm | Probably get | Probably not | Already received |
|---|---:|---:|---:|
| Pew | 24.6 | **60.1** | 15.2 |
| sonnet_fwd | 24.9 | **45.0** | 30.1 |
| sonnet_rev | 33.0 | **44.9** | 22.1 |
| opus_fwd | 29.8 | **45.8** | 24.3 |
| opus_rev | 33.8 | **43.1** | 23.1 |

**"Probably not" sits at 43-46% on every arm against Pew's 60%.** Cross-model: no material movement. Option-order: no material movement. **The ~15-17pp underestimate of vaccine refusal is a structural LLM-family prior.** Reversal does redistribute mass between "Already received" and "Probably get" (the "Already received" overshoot is partly recovered under reversal on both models), but the missing refusal mass stays missing.

This is the canonical "LLM prior bias on temporal topline" finding from the morning analysis, now confirmed against three controls. Plausible cause stands: training data over-represents engaged-liberal-vaxxed-respondent-discourse vs the actual Oct-2024 uptake distribution.

## Q9 astrology — partial recovery, structural residual

Pew distribution: 27.3% Yes / 72.7% No.

| Arm | Yes, believe in | No, don't believe | Gap vs Pew |
|---|---:|---:|---:|
| Pew | 27.3 | 72.7 | — |
| baseline n=1000 | 14.6 | 85.4 | 12.7pp |
| sonnet_fwd | 15.7 | 84.3 | 11.7pp |
| sonnet_rev | 20.3 | 79.7 | 7.0pp |
| opus_fwd | 17.8 | 82.2 | 9.5pp |
| **opus_rev** | **20.9** | **79.1** | **6.4pp** |

Best arm (opus_rev) closes 6.3pp of the 12.7pp baseline gap — still 6.4pp short of Pew. **Both effects are real and roughly additive:** option-order alone recovers ~5pp; cross-model alone recovers ~3pp; combined recovers ~6pp. The Bisbee-class minority suppression has a recoverable component (option-order) and a structural component (LLM family prior). The morning analysis' attribution to "missing latent trait + Meister-Guestrin-Hashimoto knowledge-to-simulation gap" stands but should now be split: option-order is a third contributor.

## Q11 police — fragmentation was mostly option-order, not LLM polarization

Pew distribution: 20.6% Great deal / 52.1% Fair amount / 20.6% Not too much / 6.7% No confidence.

| Arm | Great deal | **Fair amount** | Not too much | No confidence | Max-abs |
|---|---:|---:|---:|---:|---:|
| Pew | 20.6 | **52.1** | 20.6 | 6.7 | — |
| sonnet_fwd | 22.0 | 40.4 | 27.0 | 10.7 | 11.8 |
| sonnet_rev | 26.2 | **46.9** | 20.4 | 6.6 | 5.6 |
| opus_fwd | 21.1 | 42.8 | 27.1 | 8.9 | 9.4 |
| opus_rev | 21.1 | **46.9** | 24.0 | 8.0 | 5.2 |

**"Fair amount" recovers from 40-43% → 47% on both models under reversal.** Cross-model effect is small (Sonnet-fwd 40.4 vs Opus-fwd 42.8). The dominant signal is option-order.

**The morning's marginal-shift analysis attributed Q11 to "LLM over-polarization of older respondents away from the moderate option." That diagnosis is mostly wrong.** The bulk of the Q11 "Fair amount" loss was an option-order artifact, not an LLM-prior failure. The remaining ~5pp gap is real residual error, but it is well within the kind of bias band that proper survey-methodology option-rotation would average over.

This is the clearest result-changing finding of the canary. The corresponding Q11 entry in `w158-marginal-shift-analysis.md` is superseded by this result (see the supersession banner at the top of that document).

## Cross-model summary

**At Pew-canonical option order, the cross-model effect is small (within ~3pp on every question):**

| Question | sonnet_fwd | opus_fwd | Δ (Opus - Sonnet) max_abs_pp |
|---|---:|---:|---:|
| Q5 | 2.1pp | 4.1pp | +2pp worse |
| Q8 | 15.1pp | 14.3pp | -0.8pp better |
| Q9 | 11.7pp | 9.5pp | -2.2pp better |
| Q11 | 11.8pp | 9.4pp | -2.4pp better |

**But a real model x order interaction exists**, and it is large on Q5 specifically. Comparing per-option distributions at reversed order:

| Question | option | sonnet_rev | opus_rev | Δ (Opus - Sonnet) pp |
|---|---|---:|---:|---:|
| Q5 | Better | 53.8% | 39.7% | **-14.1** |
| Q5 | Worse | 11.9% | 18.6% | **+6.7** |
| Q5 | Neither | 34.3% | 41.6% | **+7.3** |
| Q8 | Probably get | 33.0% | 33.8% | +0.8 |
| Q8 | Probably not | 44.9% | 43.1% | -1.8 |
| Q8 | Already received | 22.1% | 23.1% | +1.0 |
| Q9 | Yes | 20.3% | 20.9% | +0.6 |
| Q11 | Great deal | 26.2% | 21.1% | **-5.1** |
| Q11 | Fair amount | 46.9% | 46.9% | 0.0 |
| Q11 | Not too much | 20.4% | 24.0% | +3.6 |

**Read the interaction by question:**

- **Q5:** Sonnet shows a strong recency boost on the last-presented option ("Better" jumps 43.8% → 53.8% under reversal). Opus is much more stable to order ("Better" 40.2% → 39.7%). The Q5 model x order interaction is the largest in the canary at ~14pp.
- **Q8 and Q9:** model effect at canonical order (~5pp on Q8; ~2pp on Q9) shrinks toward zero at reversed order. Both models converge on the same biased distribution when options are reversed.
- **Q11:** model effect at canonical order is small (~2pp on Fair amount) but emerges at reversed order, with Sonnet over-attributing "Great deal" by 5pp relative to Opus.

**Safer reading.** The earlier "cross-model effect is small" framing is correct at canonical Pew order on the questions that matter most for the bias story (Q8 structural, Q9 minority). That claim should not be generalized across option-order perturbations. Sonnet and Opus respond differently to option presentation order. The defensible reading is:

> Opus 4.5 leaves the main W158 errors largely intact. At Pew-canonical order, the cross-model deltas are within ~3pp on every question; both Claude-family models share the same priors on vaccine refusal underestimation, astrology yes-rate suppression, and police "Fair amount" under-attribution. The cross-model picture is more complicated under option-order perturbation — Sonnet shows a stronger recency boost than Opus on Q5 (14pp), confirming that primacy/recency interacts with model-family architecture as well as with question shape.

The product-decision implication is unchanged: swapping to Opus 4.5 leaves W158 marginal shifts in place and costs 5-7x per call. The methodology-claim implication is sharper: when reporting cross-model results, always condition on option order, because models can differ materially on how they respond to presentation perturbations even when their canonical-order outputs look similar.

## Factorial contrasts (max-abs across options, per question)

The comparison JSON (`build/out/stage_b/w158_crossmodel_canary_comparison.json`) now carries five explicit per-option contrasts (`model_delta_fwd_pp`, `model_delta_rev_pp`, `order_delta_sonnet_pp`, `order_delta_opus_pp`, `interaction_pp`) so the 2x2 factorial is not hidden behind per-arm max-abs error. Per-question summary (max-abs across options):

| Question | model_delta_fwd | model_delta_rev | order_Δ_sonnet | order_Δ_opus | interaction |
|---|---:|---:|---:|---:|---:|
| Q5 scientists policy | 3.5pp | **14.1pp** | 10.2pp | 4.2pp | **10.6pp** |
| Q8 vaccine | 5.8pp | 1.8pp | 8.2pp | 4.0pp | 6.8pp |
| Q9 astrology | 2.2pp | 0.6pp | 4.6pp | 3.1pp | 1.6pp |
| Q11 police | 2.4pp | 5.1pp | 6.6pp | 4.1pp | 4.2pp |

Two observations the max-abs-per-arm table couldn't surface:

1. **Sonnet is more order-sensitive than Opus on every question in the slice** (`order_Δ_sonnet > order_Δ_opus` on all four). Sonnet's recency-favoring behavior is stronger on every question.
2. **The model effect can shrink or grow under reversal.** Q8's model effect collapses from 5.8pp at canonical order to 1.8pp at reversed (the two models converge under perturbation). Q5 + Q11's model effect *grows* under reversal. The interaction column captures this — it's the cleanest single number for "is the perturbation interpretation simple."

## Option-order summary

For each question, the reversed - forward delta (controlling for model at Sonnet):

| Question | sonnet_fwd | sonnet_rev | Δ (rev - fwd) | Direction |
|---|---:|---:|---:|---|
| Q5 | 2.1pp | 12.3pp | **+10.2pp** | reversal destroys calibration |
| Q8 | 15.1pp | 15.2pp | +0.1pp | no change on bias-direction option |
| Q9 | 11.7pp | 7.0pp | **-4.7pp** | reversal improves |
| Q11 | 11.8pp | 5.6pp | **-6.2pp** | reversal substantially improves |

Same pattern on Opus arms (Q5: 4.1 → 8.3; Q9: 9.5 → 6.4; Q11: 9.4 → 5.2). **Option order is a systematic confound that moves topline error in opposite directions on different questions.** The model has a slight recency bias on the option list as presented; the magnitude of that bias depends on how the Pew-canonical order happens to interact with the model's underlying topic-priors.

## Implications

### For the W158 marginal-shift diagnosis

| Q8 vaccine | LLM-family prior bias on temporal vaccine refusal rates | **CONFIRMED**, survived both perturbations |
| Q9 astrology Bisbee-class | Minority suppression with knowledge-to-simulation gap | **MOSTLY CONFIRMED**, ~5pp option-order recoverable, ~7pp structural |
| Q11 police fragmentation | LLM over-polarization of older respondents | **MOSTLY WRONG**, dominant cause was option-order |
| Q5 near-perfect calibration | "Q5 matches Pew at canonical order" | **Order-dependent**, reversing option order produces 12pp error |

### For methodology going forward

1. **Option-order randomization should be standard.** Either randomize per juror (the proper survey-methodology approach; matches human-survey practice for the same reason — primacy/recency bias) or report averaged-over-orders results. One-line change in the polling primitive (shuffle `q["options"]` per juror with a deterministic seed); effectively free.
2. **n=200 sub-sample is faithful.** Future canaries can confidently sub-sample from a Stage B corpus rather than re-firing the full pipeline.
3. **Cross-model checks should be done at smaller n=100-200 slices when used as canaries.** Full-scale model swap is not warranted for this failure surface; the family-level prior dominates.
4. **The bias separation is now cleaner:** (a) structural LLM-family priors (Q8) need post-hoc calibration; (b) recoverable protocol artifacts (Q11) need only methodology fixes; (c) hybrid cases (Q9) need both.

### For Bisbee-methods gap checklist

| Check | Status |
|---|---|
| Cross-model perturbation | **DONE** (Opus 4.5 added) |
| Option-order sensitivity | **DONE** (reversed-order arm added on both models) |
| Cell-level expected-vs-Pew | **DONE** in morning marginal-shift analysis |
| Regression coefficient comparison | still pending |
| Time reproducibility | still pending |
| Nonsense/placebo question | still pending |
| Prompt specification curve (full) | partial — v1/v2/v3 protocol arc + this 2x2 canary now provide 7 datapoints across the prompt/protocol space |

### Next experiments (if any)

The remaining open items are now smaller-scoped:

1. **Option-order-randomization protocol change.** Implement deterministic per-juror option shuffling in `src/poll_runner.py` (~10 lines). Re-poll the W158 corpus on all 11 questions with the randomized protocol. Produces a methodologically improved baseline at lower compute cost than another full Stage B run.
2. **Q8 vaccine post-hoc calibration sketch.** The "Probably not" underestimate is the cleanest case for isotonic-regression-against-Pew-topline correction. Useful demonstration of the structural-vs-recoverable bias split, even if it's not a generalizable solution.
3. **Q7 school closures (NOT in this canary).** Worth a single-question follow-up to see if its 12pp gap behaves like Q11 (mostly option-order) or like Q8 (mostly structural prior).
4. **Deferred next-step candidates: time-reproducibility rerun, W163/W161 cross-wave replication, nonsense/placebo question class.** Not load-bearing for the current finding; appropriate follow-ons for a broader product or paper.

## Companion documents

- [`stage-b-w158-results.md`](stage-b-w158-results.md) — Stage B W158 v1 headline results
- [`w158-marginal-shift-analysis.md`](w158-marginal-shift-analysis.md) — per-question, per-cell marginal-shift diagnostic with sampling-noise decomposition
- [`literature-bisbee-methods-review.md`](literature-bisbee-methods-review.md) — Bisbee 2024 + post-Bisbee positioning + Bisbee-methods gap checklist
- [`sanitized-chronology.md`](sanitized-chronology.md) — chronological build log sanitized for public release
