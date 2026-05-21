# Sanitized Build Chronology

This is a public-facing chronological account of the research activities. It omits raw lab notes, local paths, API keys, detailed cost logs, row-level synthetic juror outputs, and working-session transcripts.

## 1. Methodology plan

The project began as a synthetic-respondent panel experiment: sample a U.S.-adult panel from ACS/PUMS, enrich it with sourced conditional priors, expand each trait vector into a narrative respondent, poll the panel against a real Pew wave, and validate against Pew microdata.

The key methodological risk was the Bisbee et al. (2024) failure mode: synthetic respondents can match marginal averages while compressing within-cell variance and erasing minority positions.

## 2. Real ACS/PUMS integration

The sampler was wired to an IPUMS USA ACS 2024 1-year adult extract. Selection used probability-proportional-to-size sampling, then iterative proportional fitting on race, age, education, and Census region. Calibrated analysis weights were capped to prevent any one synthetic juror from dominating validation cells.

## 3. Prior sourcing

Seven conditional prior files and one non-modal opinion bank were sourced from public Pew, GSS, Census, and media-bias classification materials. The runtime was updated to reject missing provenance, malformed fallback chains, invalid probability sums, and STUB priors in production mode.

The public package includes the schema and examples, not the real prior files.

## 4. Stage A architecture QA

An internal n=200 run tested the expansion process. Two API-configuration bugs surfaced and were fixed: an invalid temperature value and an outlier model setting that did not accept temperature. Preflight checks were added to the expansion script.

## 5. W158 selection and conversion

Pew ATP Wave 158 was selected because it mixes climate, COVID retrospective, trust-in-scientists, spiritual-practice, vaccine, school-closure, and police-confidence items. The question set produced a varied validation surface across that range.

## 6. Polling protocol iteration

The first direct-choice canary reproduced center-mass concentration and endpoint suppression. A second prompt-only patch helped some questions but overcorrected on questions where the middle option was genuinely modal. **The third protocol asked the model for a probability vector over options, then sampled externally with a deterministic hash. This substantially improved within-cell entropy.**

(Per-question medians for the three n=100 canaries are tabulated in the figure caption for `figures/jury-fig-1-trial.png`. Values are sourced from the chronological build log; the V3 figure is independently recomputable from the on-disk `canary_W158_n100_probvec_20260516_v3/` artifact, while the V1 and V2 figures are not recomputable from disk because the original V1 directory was overwritten by V2-era data before the project went under git tracking on 2026-05-17. The V1 and V2 values are preserved in three corroborating sources: raw tool output at `results/v1_v2_canary_raw_output_2026-05-16.txt`, the lab-notebook transcription reproduced in `docs/v1-v2-canary-provenance.md`, and a forensic addendum in that same document with a sha256 identity check confirming the disk-V1 contents are V2-era. Aggregate pooled-cell medians 0.53 / 0.56 / 0.91 (and the equivalent per-question medians 0.56 / 0.64 / 0.93 used in Figure 1) are anchored to those sources.)

## 7. Stage B W158

The final Stage B run used 1,000 synthetic jurors and 11 W158 questions. Coverage passed on all questions. Entropy and minority-recovery metrics largely passed, but marginal-error thresholds failed on every question. This changed the project interpretation: the pipeline did not broadly collapse within-cell variance, but it retained topic-specific marginal directional bias.

## 8. Marginal-shift analysis

The largest residual errors clustered by question type. Vaccine uptake showed a directional swap. Astrology showed minority suppression. School closures and police confidence showed fragmentation around Pew-modal moderate options.

## 9. Cross-model and option-order canary

A four-arm canary tested Sonnet vs Opus and canonical vs reversed option order. Opus did not rescue the W158 failure surface. Option order mattered substantially, especially on Q5, Q9, and Q11. Future runs should randomize option order per respondent.

## 10. Current public conclusion

The project is best presented as a methods artifact. Probability-vector polling mitigates one important synthetic-respondent failure mode, but the remaining topic-specific marginal bias is still large enough that synthetic panels should augment real surveys.

