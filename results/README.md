# Aggregate Results

These files are aggregate validation outputs only.

- `validation_results.json` — per-question validation metrics, coverage, and thresholds.
- `expected_distribution_diagnostics.json` — expected probability-vector distributions versus Pew toplines.
- `marginal_shift_analysis.json` — per-question topline expected/sampled/Pew per option, per-validation-cell expected-vs-Pew with sampling-noise decomposition, extended-axis breakdowns for the four worst questions, and worst-cell juror inspection. Output of `code/scripts/analyze_w158_marginal_shift.py`.
- `w158_crossmodel_canary_comparison.json` — aggregate comparison for the Sonnet/Opus × canonical/reversed option-order canary.
- `regression_comparison.json` — per-(question, option) coefficient comparison Pew vs synth. Primary (Pew binary observed vs synth fractional probvec), secondary (vs synth post-hoc sampled responses), sensitivity (4-covariate model). One-vs-rest weighted fractional logit with bootstrap 90% CIs. Macro-averaged metrics by question, applied to pre-registered thresholds. See `../docs/regression-coefficient-plan.md` v4.1 for full pre-registration.

No raw Pew records, raw PUMS records, row-level synthetic juror trait vectors, generated narratives, or per-juror response rows are included here.

Source data is excluded for license-compliance reasons. Free registration at [IPUMS](https://usa.ipums.org/) and [Pew Research Center](https://www.pewresearch.org/american-trends-panel-datasets/) provides equivalent access for readers who want to reproduce the pipeline.
