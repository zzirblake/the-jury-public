# The Jury Methods Package

This package contains the public-safe methods artifact for **The Jury**, a synthetic-respondent panel experiment that tested whether a calibrated LLM panel could reproduce Pew American Trends Panel Wave 158 response distributions.

The headline result is narrow: probability-vector polling substantially mitigated one Bisbee et al. (2024) failure mode, within-cell variance compression, on 10 of 11 questions. The panel still failed overall validation because topic-specific marginal error remained, most clearly on vaccine uptake and astrology belief.

Canonical article: https://corman.io/writing/the-jury/
Academic paper: deposit to SSRN and arXiv in progress.

## TL;DR

I built a 1,000-juror synthetic respondent panel from ACS/PUMS records plus Pew/GSS/Census priors and benchmarked it against Pew ATP Wave 158. Probability-vector polling substantially reduced the Bisbee-style within-cell variance collapse that appeared under direct-choice polling, but the artifact still failed overall validation through topic-specific marginal error. The package is a methods artifact: useful for inspecting the pipeline and failure modes. It does not claim that synthetic respondents replace real surveys.

## What is included

This methods package is the companion artifact to the canonical article and the academic paper; the writeup itself is not duplicated inside the repo. Citable contents:

- `figures/` — seven article figures (`jury-fig-1-trial.png` through `jury-fig-6-trial.png`, plus `fig-7-grid-scatter.png`; SVG versions of figures 1-5 are included).
- `results/` — aggregate-only validation artifacts:
  - `validation_results.json`
  - `expected_distribution_diagnostics.json`
  - `marginal_shift_analysis.json`
  - `w158_crossmodel_canary_comparison.json`
  - `regression_comparison.json` — per-(question, option) coefficient comparison Pew vs synth (primary, secondary, sensitivity)
- `docs/` — methodology notes, literature positioning, provenance schema, Stage B results, and a sanitized chronology.
- `code/` — reference pipeline code for inspection and adaptation.
- `examples/` — tiny illustrative prior/config examples only. These are not real priors.
- `LICENSE.md`, `LICENSE-CODE`, `LICENSE-DOCS`, `CITATION.cff` — package licensing and citation metadata.

## Excluded material

Raw IPUMS, Pew, GSS, Census, AllSides, Anthropic response logs, and row-level synthetic juror outputs are intentionally excluded. See `DATA_NOT_INCLUDED.md`.

## Reproduction path

To reproduce the study, a reader must independently obtain the source data under their own access terms:

1. Download an IPUMS USA ACS 2024 1-year PUMS extract with the variables described in the methodology docs.
2. Download Pew ATP Wave 158 public-use data from Pew Research Center.
3. Reconstruct conditional prior files from the cited public Pew/GSS/Census/AllSides sources using the schema in `docs/prior-provenance-schema.md`.
4. Supply an LLM provider API key locally. Do not commit it.
5. Create local data folders under `code/` (`data/raw`, `data/crosstabs`, `data/pew`) and place the locally procured/rebuilt files there.
6. Install dependencies from `code/requirements.txt`.
7. Adapt `code/config.example.yaml` to local paths.
8. Run the pipeline code in `code/`, or port the logic into a clean environment.

The package is designed to show the method, validation surface, and aggregate findings while respecting source-data licenses and privacy boundaries.

Representative command after local data has been supplied:

```bash
cd code
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
mkdir -p data/raw data/crosstabs data/pew

python scripts/run_stage_b.py \
  --config config.yaml \
  --pew-questions /path/to/local/W158_questions.json \
  --pew-microdata /path/to/local/W158_microdata.csv \
  --n 1000 \
  --polling-mode probvec \
  --option-order randomize \
  --run-label reproduction
```

The original W158 run used Pew-canonical option order. The package recommends `--option-order randomize` for subsequent runs because the cross-model canary showed meaningful option-order effects.

## Main claims

This work shows:

- Direct-choice synthetic polling reproduced a known failure class: center-mass concentration and minority-option suppression.
- Probability-vector polling recovered within-cell entropy for most W158 questions.
- The remaining error was not broad variance collapse. It was topic-specific marginal bias.
- Opus 4.5 left the main W158 errors largely intact. Option order mattered enough that future runs should randomize option presentation per respondent.

Replacement remains unproven. The package shows where one pipeline succeeds, where it fails, and how to measure the difference.

## Known limits

- One Pew wave: W158 only.
- One model family: Claude Sonnet 4.6 / Opus 4.5.
- Regression-coefficient comparison runs on the 8-covariate intersection (age, race, education, party, gender, region, ideology, 4-way condensed religion). Income and finer religion mappings remain out of scope.
- No time-reproducibility rerun under the locked probability-vector protocol.
- No nonsense/placebo question class.
- Raw data and row-level synthetic outputs are excluded for license, privacy, and operational-safety reasons.

## License

Code in `code/` is released under the MIT License. Documentation, figures, and aggregate results are released under CC BY 4.0 unless otherwise noted. Source datasets from IPUMS, Pew, GSS, Census, and AllSides are not included and remain governed by their original terms.

## Suggested reading order

The canonical article (https://corman.io/writing/the-jury/) is the primary writeup; the academic paper preprint covers the same material in academic format. Within this methods package:

1. `docs/stage-b-w158-results.md` — headline replication results
2. `docs/w158-crossmodel-canary-results.md` — 2×2 cross-model × option-order canary
3. `docs/w158-marginal-shift-analysis.md` — per-question failure-mode diagnostic
4. `docs/literature-bisbee-methods-review.md` — positioning against Bisbee 2024 and the post-Bisbee literature
5. `docs/v1-v2-canary-provenance.md` — chain-of-custody for the V1/V2 entropy values in Figure 1
6. `docs/sanitized-chronology.md` — chronological build log
7. `docs/prior-provenance-schema.md` — schema contract for conditional-prior JSON files
8. `docs/regression-coefficient-plan.md` — locked analysis plan for the regression-coefficient comparison
