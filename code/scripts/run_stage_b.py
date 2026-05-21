"""Stage B orchestrator: n=1000 public credibility artifact.

Same pipeline as Stage A plus the actual Pew replication poll + the
validation harness with bootstrap CIs and the coverage rule. Writes a
publishable artifact bundle to out/stage_b/run_NN/.

Usage:
    python scripts/run_stage_b.py --config config.yaml --pew-questions data/pew/questions.json

Required external artifacts:
  - a locally procured IPUMS PUMS extract
  - rebuilt conditional prior JSON files following the provenance schema
  - rebuilt non-modal prior JSON file following the provenance schema
  - locally procured Pew microdata converted to the expected long format
  - selected questions in {id, text, options} format
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

import pandas as pd
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src import (
    buckets,
    conditional_sampler,
    env_loader,
    expansion,
    expected_dist,
    poll_runner,
    sampler,
    validation,
    variance,
)

env_loader.load_anthropic_key()


def _load_dictionary_excerpt(repo_root: Path) -> str:
    csv_path = repo_root.parent / "docs" / "identity-inception.csv"
    return csv_path.read_text() if csv_path.exists() else ""


def _attach_validation_axes(jurors: pd.DataFrame) -> pd.DataFrame:
    """Add coarse validation-axis columns matching cells_config."""
    out = jurors.copy()
    out["age"] = buckets.bucket_age_validation(out["AGE"])
    out["race"] = buckets.bucket_race_validation(out["race_bucket"])
    out["education"] = out["education_bucket"]
    out["party"] = out["political_party"]
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--pew-questions", required=True,
                        help="JSON file: list of {id, text, options} for the replication")
    parser.add_argument("--pew-microdata", required=True,
                        help="CSV: Pew source microdata with axes age/race/education/party + response columns per question_id")
    parser.add_argument("--skip-expansion", action="store_true")
    parser.add_argument("--allow-stubs", action="store_true",
                        help="explicitly permit STUB-sourced priors (DEFAULT: refused). "
                             "Stage B should NEVER ship with stubs; this flag exists only "
                             "for development against partial real-prior coverage.")
    parser.add_argument("--n", type=int, default=1000,
                        help="juror panel size. Default 1000 (full Stage B). Use smaller "
                             "values for canary runs (e.g. --n 25). The output directory "
                             "encodes the n value so canary runs do not collide with real Stage B.")
    parser.add_argument("--polling-mode", choices=["direct", "probvec"], default="direct",
                        help="direct=LLM picks one option (legacy); probvec=LLM returns option "
                             "probabilities, we sample deterministically. probvec is the "
                             "next-generation polling primitive per Argyle 2023 / Park 2024.")
    parser.add_argument("--option-order", choices=["canonical", "reverse", "randomize"],
                        default="canonical",
                        help="order in which answer options are presented to the LLM. "
                             "Use randomize for future production runs; canonical preserves "
                             "the original W158 Stage B protocol.")
    parser.add_argument("--run-label", default=None,
                        help="optional label appended to output dir name. Use to distinguish "
                             "iterations of the same wave/n/date combo (e.g., --run-label v3).")
    args = parser.parse_args()

    cfg_path = REPO_ROOT / args.config
    with cfg_path.open() as f:
        cfg = yaml.safe_load(f)
    cfg["run"]["stage"] = "B"
    cfg["run"]["n"] = args.n
    # Output dir name encodes wave + n + polling_mode + date + (optional label)
    # so a methodologist can identify the run from the path alone, and no two
    # runs collide on file paths. Canary runs (n<500) get a `canary_` prefix
    # so they're never mistaken for the publishable artifact.
    from datetime import date
    poll_id = cfg["validation"]["pew_source"].get("poll_id", "unknown")
    today = date.today().isoformat().replace("-", "")
    prefix = "canary_" if args.n < 500 else ""
    suffix = f"_{args.run_label}" if args.run_label else ""
    dir_label = f"{prefix}{poll_id}_n{cfg['run']['n']}_{args.polling_mode}_{today}{suffix}"
    out_dir = REPO_ROOT / "out" / "stage_b" / dir_label
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Stage B output -> {out_dir}")
    print(f"  polling mode: {args.polling_mode}")

    # === Load PUMS, sample, second-pass, instrument variance ===
    pums = pd.read_parquet(REPO_ROOT / cfg["ipums"]["pums_extract_path"])
    print(f"loaded PUMS: {len(pums):,} records; sampling n={cfg['run']['n']}")
    targets = sampler.compute_marginals_from_pums(pums)
    jurors = sampler.sample(
        pums=pums, n=cfg["run"]["n"],
        acs_targets=targets,
        seed=cfg["run"]["seed"],
        cap=sampler.WeightCap(min=cfg["raking"]["weight_cap"]["min"],
                              max=cfg["raking"]["weight_cap"]["max"]),
    )
    bank = conditional_sampler.ConditionalPriorBank(
        REPO_ROOT / "data" / "crosstabs", allow_stubs=args.allow_stubs,
    )
    jurors = conditional_sampler.second_pass_sample(jurors, bank, seed=cfg["run"]["seed"] + 100)
    nm_bank = variance.NonModalOpinionBank(
        REPO_ROOT / "data" / "crosstabs" / "non_modal_priors.json",
        allow_stubs=args.allow_stubs,
    )
    jurors = variance.instrument(jurors, nm_bank, seed=cfg["run"]["seed"] + 200,
                                  outlier_rate=cfg["variance"]["outlier_rate"])
    jurors = _attach_validation_axes(jurors)
    jurors.to_parquet(out_dir / "trait_vectors.parquet")
    print(f"saved trait vectors -> {out_dir / 'trait_vectors.parquet'}")

    if args.skip_expansion:
        print("--skip-expansion set; halting before LLM calls")
        return

    # === API preflight before paid expansion + polling ===
    print("\nrunning API preflight...")
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import preflight as preflight_mod  # noqa: E402
    rc = preflight_mod.preflight(REPO_ROOT / args.config)
    if rc != 0:
        print(f"FATAL: preflight failed (rc={rc}); aborting Stage B", file=sys.stderr)
        sys.exit(rc)

    # === Persona expansion ===
    print("expanding personas")
    exp_cfg = expansion.ExpansionConfig(
        default_model=cfg["expansion"]["default_model"],
        outlier_model=cfg["expansion"]["outlier_model"],
        max_tokens_out=cfg["expansion"]["max_tokens_out"],
    )
    dictionary_excerpt = _load_dictionary_excerpt(REPO_ROOT)
    jurors = expansion.expand_corpus(jurors, exp_cfg, dictionary_excerpt)
    jurors.to_parquet(out_dir / "expanded_corpus.parquet")

    # === Run the Pew replication ===
    questions = json.loads(Path(args.pew_questions).read_text())
    print(f"running poll: {len(questions)} questions x {len(jurors)} jurors")
    # Pass the source-poll field date so the LLM answers from that vantage point
    # (don't contaminate retrospective questions with 2026 hindsight).
    # Spec carries `field_window` from W158_spec.json provenance; fall back to wave date.
    spec_path = REPO_ROOT / "data" / "pew" / f"{cfg['validation']['pew_source']['poll_id']}_spec.json"
    if spec_path.exists():
        spec = json.loads(spec_path.read_text())
        field_date_iso = spec.get("field_window") or spec.get("_field_window") or "the survey field date"
    else:
        field_date_iso = cfg["validation"]["pew_source"].get("field_window", "the survey field date")
    print(f"  field date passed to polling: {field_date_iso}")
    # Canary runs (small n) opt into fail-open polling so we can see partial
    # results during prompt iteration; production runs fail closed at 5% rate
    # so 1000 x 11 = 11000 calls don't silently lose 500+ rows.
    is_canary = args.n < 500
    synth_responses = poll_runner.run_poll(
        jurors, questions,
        field_date_iso=field_date_iso,
        model=cfg["expansion"]["default_model"],
        allow_failures=is_canary,
        polling_mode=args.polling_mode,
        option_order=args.option_order,
        run_seed=cfg["run"]["seed"],
    )
    # Attach validation axes by joining on juror_id. Do NOT bring `weight` over
    # from the jurors frame: poll_runner already attached the calibrated raked
    # weight per response row, and a duplicate-named column would suffix to
    # weight_x/weight_y and silently break weighted validation downstream.
    axes_only = jurors[["pums_idx", "age", "race", "education", "party"]]
    synth_long = synth_responses.merge(
        axes_only, left_on="juror_id", right_on="pums_idx", how="left",
    )
    assert "weight" in synth_long.columns, (
        "post-merge `weight` column missing — poll_runner contract broken"
    )
    synth_long.to_parquet(out_dir / "synth_responses.parquet")

    # === Load Pew source microdata ===
    source = pd.read_csv(args.pew_microdata)
    # Source must already have age/race/education/party columns matching synthetic;
    # the README documents the bucket-mapping the user must apply on Pew side.

    # === Validate ===
    cells_config = {
        "top_level": {
            axis: {"buckets": spec["buckets"],
                   "min_synth_n": spec["min_synth_n"],
                   "min_source_n": spec["min_source_n"]}
            for axis, spec in cfg["validation"]["validation_cells"]["top_level"].items()
        },
        "interaction": {
            pair: spec for pair, spec
            in cfg["validation"]["validation_cells"]["interaction"].items()
        },
    }
    print("computing validation metrics with bootstrap CIs")
    all_results = []
    for q in questions:
        q_synth = synth_long[synth_long["question_id"] == q["id"]]
        q_source = source[source["question_id"] == q["id"]]
        if q_source.empty:
            print(f"  WARNING: no source microdata for {q['id']}; skipping")
            continue
        result = validation.compute_metrics(
            q_synth, q_source, cells_config, q["id"],
            bootstrap_iter=cfg["validation"]["bootstrap"]["iterations"],
            confidence=cfg["validation"]["bootstrap"]["confidence"],
            seed=cfg["run"]["seed"] + 1000,
            weight_col_synth="weight",
            weight_col_source=cfg["validation"]["pew_source"].get("weight_col", "WEIGHT"),
        )
        coverage = validation.apply_coverage_rule(result, cfg["validation"]["coverage_rule"])
        thresholds = validation.apply_thresholds(result, cfg["validation"]["thresholds"])
        all_results.append({
            "question_id": q["id"],
            "coverage": asdict(coverage),
            "thresholds": asdict(thresholds),
            "top_level_cells": {
                ax: [asdict(c) for c in cells]
                for ax, cells in result.top_level_cells.items()
            },
            "interaction_cells": {
                ax: [asdict(c) for c in cells]
                for ax, cells in result.interaction_cells.items()
            },
        })
        print(f"  {q['id']}: coverage_pass={coverage.overall_passes} "
              f"thresholds_pass={thresholds.overall_passes}")

    with (out_dir / "validation_results.json").open("w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\nValidation report -> {out_dir / 'validation_results.json'}")

    # Expected-distribution diagnostics (probvec only). Captures the model's
    # latent calibration distinct from the sampled outcome. Methodologist
    # surface for the "probvec calibrates the latent distribution" claim.
    if args.polling_mode == "probvec":
        exp_path = out_dir / "expected_distribution_diagnostics.json"
        expected_dist.save_expected_diagnostics(
            exp_path, synth_long, questions, source,
            source_weight_col=cfg["validation"]["pew_source"].get("weight_col", "WEIGHT"),
        )
        print(f"Expected-distribution diagnostics -> {exp_path}")
    print(f"Stage B complete. -> {out_dir}")


if __name__ == "__main__":
    main()
