# Reference Code

This directory contains reference implementation code copied from the working pipeline for inspection and adaptation.

It is not a turnkey reproduction by itself. To run it, provide:

- an IPUMS ACS/PUMS extract obtained under your own account and terms;
- Pew microdata obtained from Pew Research Center under your own account and terms;
- reconstructed prior JSON files following `../docs/prior-provenance-schema.md`;
- a local LLM provider API key kept outside version control;
- local configuration based on `config.example.yaml`.

The public package intentionally omits raw data, row-level synthetic outputs, logs, and real sourced prior files.

