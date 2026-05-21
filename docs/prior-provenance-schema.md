---
type: schema-spec
project: the-jury
created: 2026-05-16
applies_to: build/data/crosstabs/*.json
status: canonical for v0.1 conditional-prior sourcing
---

# Conditional-Prior Provenance Schema

Every JSON file in `build/data/crosstabs/` must carry full provenance metadata in a top-level `provenance` block. This is the schema a methodologist or peer-review panel inspects to decide whether a Stage B replication artifact built on these priors is defensible.

The schema is enforced at runtime by `src.conditional_sampler.ConditionalPriorBank.load()`: any file missing required `provenance` fields raises `MissingProvenance` and refuses to load (analogous to the `StubPriorRefused` guard). Stage B will never run on under-documented priors.

---

## Required fields

### Top-level keys

```json
{
  "trait": "political_party",
  "source": "Pew Research Political Typology 2024",
  "provenance": { ... },
  "conditioning_axes": ["race", "education", "age", "region"],
  "fallback_chain": [...],
  "distributions": { ... }
}
```

| Key | Required | Notes |
|---|---|---|
| `trait` | yes | Must match one of the v0.1 traits listed below |
| `source` | yes | Human-readable source name. **`source == "STUB"` is blocked unless `--allow-stubs` flag set.** |
| `provenance` | yes | Block defined below |
| `conditioning_axes` | yes | Axes the finest cells condition on, in fallback-chain priority order |
| `fallback_chain` | yes | List of axis subsets (most-specific to least-specific), terminating in `[]` for the unconditional marginal |
| `distributions` | yes | Per-cell `{label: probability}` mappings |

### Required `provenance` fields

```json
"provenance": {
  "source_url": "https://www.pewresearch.org/political-typology-2024/",
  "field_year": 2024,
  "field_window": "2024-04-08 to 2024-04-14",
  "publication_date": "2024-09-30",
  "retrieved_at": "2026-05-17",
  "retrieved_by": "Blake Corman (manual transcription) | scripts/source_political_party.py | etc.",
  "population": "US adults 18+",
  "sample_size_total": 12693,
  "weighting_note": "Source crosstabs are weighted to ATP panel weights v2024.3 calibrated to ACS demographics. Our derived distributions preserve weighted proportions.",
  "table_id": "Topline T-4, p.62",
  "question_wording": "In politics today, do you consider yourself a Republican, Democrat, or independent?",
  "response_options_source": ["Republican", "Democrat", "Independent", "Something else", "No answer"],
  "response_options_used": ["R", "D", "I"],
  "fallback_behavior": "When the finest conditioning cell is sparse in source (n < 30), back off through fallback_chain. The unconditional marginal is the terminal fallback.",
  "hand_normalization": [
    "Pew 'Lean Republican' folded into R; 'Lean Democrat' into D; pure independents stay I.",
    "Pew 'Something else' and 'No answer' (combined ~3.5%) redistributed proportionally to R/D/I.",
    "race=hispanic_latino follows Census convention (Hispanic supersedes race code) consistent with our bucket_race()."
  ],
  "minimum_cell_n_in_source": 30,
  "license_or_citation": "Pew Research Center, 'Political Typology 2024' (2024). Public-use crosstabs.",
  "known_limitations": [
    "Some race x region x age x education cells in Pew topline are suppressed for n < 30; fallback_chain handles these.",
    "Pew 'Other Asian' not separated from 'Asian, NOS'; matches our asian_american collapse."
  ]
}
```

| Key | Required | Notes |
|---|---|---|
| `source_url` | yes | Stable URL or DOI |
| `field_year` | yes | Year the survey was *fielded* (distinct from publication year) |
| `field_window` | optional | Specific field dates if available; useful for political polls where 2 weeks matters |
| `publication_date` | yes | When the source data was released |
| `retrieved_at` | yes | Date pulled (ISO 8601) |
| `retrieved_by` | yes | Human name or script path. Script paths must be committed and reproducible. |
| `population` | yes | Universe (US adults 18+ / US registered voters / etc.) |
| `sample_size_total` | yes | Source survey n |
| `weighting_note` | yes | Whether source crosstabs are weighted, by what weights, and whether our distributions preserve that weighting. **A non-empty value is required even if "unweighted, see note"** — silence on weighting is the methodologist's first attack. |
| `table_id` | yes | Specific table reference within the source (page number, table number, query ID) |
| `question_wording` | yes | Verbatim question text. Direct quote. |
| `response_options_source` | yes | Verbatim source response options |
| `response_options_used` | yes | The subset/relabeling used in our distributions |
| `fallback_behavior` | yes | Plain-English explanation of fallback_chain semantics |
| `hand_normalization` | yes | List of every transformation applied to raw source data. **Empty list `[]` is acceptable if no normalization was done**, but the field must be present and explicit. |
| `minimum_cell_n_in_source` | yes | The minimum source n we accepted per cell. Cells below this should appear in `hand_normalization` if they were folded into coarser cells, or be absent from `distributions` (forcing fallback). |
| `license_or_citation` | yes | Attribution string for the methodology footnote |
| `known_limitations` | yes | Anything a methodologist might catch. Empty list acceptable but field required. |

---

## v0.1 trait files (8 required total: 7 conditional + 1 non-modal)

The canonical runtime list of conditional traits is `V01_TRAITS` in `src/conditional_sampler.py`; this table must match it. `non_modal_priors.json` is a separate artifact loaded by `src/variance.py:NonModalOpinionBank`, not by the conditional-prior bank.

**7 conditional priors:**

| File | Source class | Notes |
|---|---|---|
| `political_party.json` | Pew Political Typology | Conditional on race x education x age x region |
| `political_ideology.json` | GSS or Pew Political Typology | Conditional on party x age x education |
| `religion.json` | Pew Religious Landscape Study 2023 | Conditional on race x age x region |
| `religiosity.json` | Pew Religious Landscape Study 2023 | Conditional on religion |
| `media_diet_primary.json` | Pew News Consumption Study | Conditional on party x age x education |
| `media_diet_slant.json` | Pew News Consumption Study or AllSides | Conditional on party |
| `household_composition.json` | ACS supplement | Conditional on age x marital status |

**1 non-modal opinion bank (extended schema, see next section):**

| File | Source class | Notes |
|---|---|---|
| `non_modal_priors.json` | GSS multi-issue batteries (2018-2022 pooled) | Outlier-injection bank. Loaded by `NonModalOpinionBank`, not `ConditionalPriorBank`. |

**`life_stage_recent` is NOT in this inventory.** It was originally specified as a conditional-prior file (and an orphan `life_stage_recent.json` stub existed in earlier states of the build) but is now derived directly from PUMS event flags via `src/buckets.py:derive_life_stage_recent`. The corresponding crosstab JSON has been removed; do not source one. `caregiver_status` is similarly NOT in this inventory; deferred to v0.2 until a published US-population conditional crosstab is identified.

### `non_modal_priors.json` extended provenance

Outlier priors require additional documentation because each non-modal opinion is a per-cell-per-issue claim:

```json
"provenance": {
  ...all standard fields...,
  "issues_covered": [
    {
      "issue": "abortion_legal_all_cases",
      "gss_variable": "ABANY",
      "source_years_pooled": [2018, 2020, 2022],
      "question_wording": "Please tell me whether or not you think it should be possible for a pregnant woman to obtain a legal abortion if the woman wants it for any reason.",
      "response_options_source": ["Yes", "No", "Don't know", "No answer"],
      "non_modal_threshold": 0.30,
      "notes": "Non-modal density per cell is the proportion of that cell holding the LESS-COMMON-for-cell position. For cells where >70% hold one position, the other is the 'non-modal' opinion."
    },
    ...
  ]
}
```

---

## Validation flow

When `ConditionalPriorBank.load(trait)` runs:

1. Read JSON from `data/crosstabs/<trait>.json`.
2. If `source == "STUB"` and `allow_stubs=False`: raise `StubPriorRefused`. STUB priors still receive structural validation (steps 5-8, except step 8 which only applies to non-STUB priors).
3. If `source != "STUB"`: validate provenance metadata.
   a. If `provenance` block is missing entirely: raise `MissingProvenance`.
   b. If any field in `REQUIRED_PROVENANCE_FIELDS` is absent: raise `MissingProvenance` listing the missing fields.
   c. If any field in `REQUIRED_NON_EMPTY_TEXT_FIELDS` (source_url, population, weighting_note, table_id, question_wording, fallback_behavior, license_or_citation) is present but empty/whitespace-only: raise `MissingProvenance`. Silence on any of these is the methodologist's first attack.
4. (No-op — preserved for numbering symmetry.)
5. Verify `conditioning_axes` is a non-empty list (`MalformedPrior` otherwise).
6. Verify `fallback_chain` is a non-empty list whose final entry is `[]` (the unconditional marginal terminator). Without an unconditional fallback, sparse-cell jurors raise `KeyError` at sample time. (`MalformedPrior` otherwise.)
7. Verify `distributions` is a non-empty dict, every cell's distribution is a non-empty dict, and every distribution's probabilities sum to within ±0.001 of 1.0. (`MalformedPrior` otherwise; failing cells reported with their actual sums.)
8. For non-STUB priors with `provenance.response_options_used` declared: verify every distribution's keys are a subset of the declared options. Catches the case where a hand-normalization step missed a category. (`MalformedPrior` otherwise; undeclared keys reported.)
9. Cache and return.

Failures at steps 2, 3, 5, 6, 7, or 8 raise specific exceptions and halt the run before any expensive expansion. The eight regression tests in `scripts/test_validation.py` lock these behaviors in.

Loader code: `src/conditional_sampler.py:load` plus helpers `_validate_prior_provenance` and `_validate_prior_structure`.

---

## Methodology-footnote rendering

Stage B's published artifact carries a methodology footnote per cohort poll. The footnote draws from these provenance blocks programmatically. Each provenance field maps to a footnote line; missing fields are absent from the footnote and from the artifact's defensibility.

Example footnote excerpt rendered from this schema:

> *Political party distributions per juror were sampled from Pew Research Center's Political Typology 2024 (fielded 2024-04-08 to 2024-04-14, n=12,693 US adults 18+, weighted to ATP panel weights v2024.3 calibrated to ACS), conditional on race x education x age x region. Source response categories (Republican / Democrat / Independent / Something else / No answer) were normalized to {R, D, I} per Pew's leaning conventions; ~3.5% non-classified responses were redistributed proportionally. Cells below n=30 in source were resolved via fallback chain. Full per-cell distributions and source-table references at [appendix].*

A methodologist reading this footnote should be able to reconstruct what we did and decide whether to trust it. The provenance blocks above are what make this footnote possible and credible.

---

## Sourcing-pass discipline

Per the Option B plan (real-prior sourcing):

1. Replace one stub at a time. Validate fallback chain by running Stage A no-API immediately after; inspect the new trait's distribution against the old stub's distribution; flag any cell that swings >15 percentage points (probably indicates a hand-normalization error, not real signal).
2. Source `non_modal_priors.json` last. The outlier mechanism works in qualitative testing on stubs; better distributions sharpen but do not change the architecture.
3. Each sourcing pass commits a single file plus its provenance. PR-equivalent discipline: one source change per commit so a methodologist can bisect if needed.
4. After all 8 files are real-sourced, run Stage A no-API end-to-end to inspect the joint trait-vector distribution. If the joint looks reasonable, fire a small canary slice (n=30, ~$0.50) of LLM expansion to verify narratives still produce coherent personas under real conditional structure. Then run full Stage A; then Stage B.
