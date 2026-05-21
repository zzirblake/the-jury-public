# Data Not Included

This package intentionally excludes raw data, restricted data, row-level derived data, and private operational files.

## Excluded source data

- IPUMS USA ACS 2024 1-year PUMS extract.
- Converted IPUMS parquet files.
- Pew ATP Wave 158 raw files, including CSV, SAV, codebook, questionnaire, and methodology files.
- Pew ATP Wave 161 / Wave 163 raw ZIPs.
- Raw GSS, Census, AllSides, or other source files.

Readers must procure these sources directly from their original publishers and follow those publishers' terms.

## Excluded derived row-level data

- `trait_vectors.parquet`
- `expanded_corpus.parquet`
- `synth_responses.parquet`
- Stage A / Stage B canary parquets
- QA review packs containing generated juror narratives
- logs containing API run details

These files either contain row-level PUMS-derived records, generated synthetic narratives, per-juror probability vectors, reasoning traces, or local operational state.

## Excluded secrets and local state

- `.env`
- API keys
- virtual environments
- caches
- local absolute paths
- Claude/Codex routing files and internal state docs

## Included instead

This package includes aggregate validation outputs, figures, methods documentation, and illustrative example priors. The real sourced prior distributions are not redistributed here; the schema and sourcing discipline are documented so readers can rebuild them.

