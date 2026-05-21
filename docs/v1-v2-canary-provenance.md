---
type: provenance-record
project: the-jury
created: 2026-05-19
artifact: n=100 V1 / V2 polling canary, Pew W158, 2026-05-16
companion: results/v1_v2_canary_raw_output_2026-05-16.txt
status: chain-of-custody record for the V1 and V2 entropy values cited in the canonical article and the academic paper
---

# V1 / V2 Canary Data Provenance

## Why this document exists

The canonical article and the academic paper both report a V1 → V2 → V3 polling-protocol arc with median per-question entropy ratios of 0.56 → 0.64 → 0.93 (or equivalently, pooled-across-cell medians of 0.53 → 0.56 → 0.91). The V3 figure is recomputable from the on-disk `canary_W158_n100_probvec_20260516_v3/` artifact. The V1 and V2 figures are not recomputable from the V1 and V2 on-disk directories, because those directories were overwritten before the project went under git tracking on 2026-05-17.

This document is the chain of custody for the V1 and V2 values. Three corroborating sources back them:

1. **Raw tool output** captured at run time. Both V1 and V2 protocol-comparison outputs are preserved verbatim in `results/v1_v2_canary_raw_output_2026-05-16.txt`. These are the authoritative source.
2. **Contemporaneous lab-notebook transcription** of those same values, dated 2026-05-16, reproduced below.
3. **Forensic addendum** dated 2026-05-19 that diagnosed the disk-overwrite incident with a sha256 identity check and a mechanistic argument, also reproduced below.

The figure script `code/scripts/generate_writeup_figures.py` hardcodes the per-question values from source (1) in a `LAB_NOTEBOOK_ENTROPY` constant. Figure 1 is rendered from that constant.

## Lab-notebook V1 narrative (2026-05-16)

> Pipeline runs cleanly through preflight, sampler, persona expansion, polling, and validation. All 11 questions get measured cells. 176 / 473 total cells measured (37%); coverage rule fails on every question by design at n=100 (top-level coverage 40%; interaction coverage 36%; thresholds are 80% / 50%).
>
> However, the validation harness caught a systematic bias in the polling layer that was not present at the Stage A persona-narrative level. Across the 11 questions, synthetic distributions showed:
>
> - **Center-mass concentration:** Q4 scientist confidence, synth 84% "Fair amount" vs Pew 51% (+33pp); 1% "A great deal" vs 26%; 0% "No confidence at all" vs 4%.
> - **Extreme-option refusal:** Q1 climate "Not at all" 0% vs 15%; Q2 climate cause "Not at all" 0% vs 8%; Q5 scientists "Worse at policy" 0% vs 10%; Q11 police "No confidence" 0% vs 7%.
> - **Most striking, Q9 astrology:** synth 1% "Yes, believe in" vs Pew 27%. The LLM essentially refused to attribute astrological belief to any juror.
>
> Median entropy ratios across measured cells ranged from 0.11 (Q9) to 0.77 (Q6), with most questions below the 0.80 point-estimate threshold.
>
> This is exactly the Bisbee 2024 failure mode the validation harness was built to catch. The canary did its job.

## Lab-notebook V2 narrative (2026-05-16)

> Result: small movement, mixed direction. Median entropy ratio baseline 0.53 → v2 0.56. Per-question deltas:
>
> - Big wins: Q4 scientist confidence 0.35 → 0.56, Q11 police 0.56 → 0.77, Q9 astrology 0.11 → 0.28, Q5 0.52 → 0.64.
> - Anti-center overshoot regressions: Q3 climate-policy-economy 0.58 → 0.42 ("Make no difference" purged from 6.5% to 0%); Q6 COVID 0.77 → 0.71 ("Fewer restrictions" overshot to 64% vs Pew 38%); Q10 astrology freq 0.51 → 0.42 ("Never" climbed to 85%).
> - Q9 astrology still well below decision-rule target: 5.4% Yes (target 15-35%; Pew 27%).
>
> Diagnosis: the anti-center language was too aggressive on questions where center is genuinely modal. The structured trait block clearly added differentiation signal. The probvec polling primitive remained the right next step.

## Per-question entropy table

This is the table from the lab notebook that anchors Figure 1. Values are derived from the raw tool outputs in `results/v1_v2_canary_raw_output_2026-05-16.txt`.

| Question | V1 | V2 | V3 | Δ V3-V2 |
|---|---:|---:|---:|---:|
| Q1 climate impact | 0.62 | 0.67 | 0.95 | +0.28 |
| Q2 climate cause | 0.65 | 0.69 | 0.93 | +0.24 |
| Q3 climate policy economy | 0.58 | 0.42 | 0.91 | +0.49 |
| Q4 scientist confidence | 0.35 | 0.56 | 0.98 | +0.42 |
| Q5 scientists policy | 0.52 | 0.64 | 0.90 | +0.27 |
| Q6 COVID restrictions | 0.77 | 0.71 | 0.91 | +0.19 |
| Q7 school closures | 0.42 | 0.38 | 0.97 | +0.59 |
| Q8 vaccine | 0.75 | 0.66 | 1.09 | +0.43 |
| Q9 astrology | 0.11 | 0.28 | 0.48 | +0.20 |
| Q10 astrology freq | 0.51 | 0.42 | 0.84 | +0.42 |
| Q11 police | 0.56 | 0.77 | 1.00 | +0.23 |

Two summary statistics arise from this table:

- **Median of per-question medians:** V1 = 0.56, V2 = 0.64, V3 = 0.93. This is what Figure 1 in the paper visualizes (the slopegraph shows per-question trajectories; the labeled median is the middle question's value at each iteration).
- **Median across all measured cells, pooled across questions:** V1 = 0.53, V2 = 0.56, V3 = 0.91. This is what the lab-notebook and `docs/corpus-construction-plan.md` polling-protocol section cite. The pooled value differs from the per-question median because the pooled cell distribution is dominated by the larger-frame questions (Q1, Q2, Q4, Q11), while the per-question median treats each question equally regardless of how many cells it carries.

Both statistics compute from the same underlying response data with different aggregation orders. Both are statistically defensible.

## Forensic addendum (2026-05-19)

> **Discovery.** While pulling exact per-question entropy values from disk for a follow-up figure, found that `out/stage_b/canary_W158_n100_20260516/` and `out/stage_b/canary_W158_n100_direct_20260516_v2/` are byte-identical (sha256 verified across every file). The V2 directory has identical-second file timestamps (all 2026-05-16 13:38:48) suggesting a single copy operation; the V1 directory has staggered timestamps (07:54-09:24) consistent with a pipeline run unfolding.
>
> **Forensic test.** Compared on-disk V1 response distributions against the lab-notebook narrative descriptions of the V1 baseline:
>
> | Question | Lab-notebook V1 narrative | Disk-V1 actual |
> |---|---|---|
> | Q9 astrology "No, don't believe" rate | 99% | 94% |
> | Q4 sci confidence "Fair amount" rate | 84% | 68% |
> | Q4 median entropy ratio | 0.35 | 0.59 |
> | Q9 median entropy ratio | 0.11 | 0.26 |
>
> On-disk values are systematically less compressed than the lab-notebook V1 narrative, which is what would be expected if disk-V1 contains V2-era (anti-center patched) data rather than raw V1 direct-choice data. The disk-V1 directory contents are within ~0.05 of the lab notebook's V2 column for Q4, Q5, Q9, and Q11.
>
> **Conclusion.** The original V1 raw direct-choice canary response data is no longer on disk. The disk-V1 directory was overwritten with V2-era data at some point in the pre-git canary workflow; the disk-V2 directory is a copy of that. Both directories now contain V2-era data, mislabeled.
>
> **Scope of compromise.** Only the n=100 canary trio (V1, V2 directories). Verified clean:
>
> - Stage B n=1,000 (`W158_n1000_probvec_20260516_v1/`): staggered timestamps consistent with the 18h run; no duplicates.
> - 4-arm cross-model canary at n=200: all 4 arms have distinct sha256 hashes, different file sizes, sequential run timestamps.
> - V3 probvec canary at n=100: independent directory, clean.
>
> **What stays authoritative.**
>
> - The lab notebook's per-question V1 / V2 / V3 entropy table is the canonical record for the n=100 canary arc. Values are observed measurements at run time, even though the underlying response parquets are no longer recoverable for V1 / V2.
> - The raw tool outputs at `results/v1_v2_canary_raw_output_2026-05-16.txt` are the source the lab notebook transcribed from.
> - All Stage B n=1,000 derived analyses (marginal-shift, validation thresholds, expected-distribution diagnostics) are clean.
> - All cross-model canary derived analyses are clean.
> - The polling-protocol section of `docs/corpus-construction-plan.md` (citing pooled-cell medians 0.53, 0.56, 0.91) matches the lab notebook and is authoritative.
>
> **Going-forward guardrail.** The repository went under git tracking on 2026-05-17 (initial commit `dbba646`). Any future overwrite of a tracked file will appear in `git status` and is reversible from history. The pre-git workflow had no such guardrail; this episode is the load-bearing cost of starting version control after the working data was already in motion.

## Reproducibility statement for the V1 / V2 values

A reader who wishes to verify the V1 and V2 values in Figure 1 of the paper or the canonical article should consult `results/v1_v2_canary_raw_output_2026-05-16.txt`. The V3 values are independently recomputable from `code/scripts/generate_writeup_figures.py` against the on-disk V3 directory (which is not affected by the overwrite incident).
