"""Re-poll an existing expanded corpus with a different polling mode / model / option order.

Use when iterating on polling-protocol changes (direct vs probvec, prompt
variants, model choice, option-order perturbation, etc.) and you want a clean
A/B against the previous poll without re-sampling jurors or re-expanding
narratives. Reuses the same expanded corpus + the same Pew questions + Pew
microdata; just swaps in a fresh polling pass and re-runs the validation harness.

Output goes to a sibling directory of the input corpus directory, named to
encode polling-mode + model + option-order + run-label so A/B/C/D arms stay
organized.

Usage:
    python scripts/repoll_corpus.py \\
        --in-dir   out/stage_b/W158_n1000_probvec_20260516_v1 \\
        --polling-mode probvec \\
        --polling-model claude-sonnet-4-6 \\
        --reverse-options \\
        --n-sample 200 \\
        --question-ids Q5_scientists_policy_role,Q8_covid_updated_vaccine \\
        --run-label crossmodel_sonnet_rev \\
        --pew-questions data/pew/W158_questions.json \\
        --pew-microdata data/pew/W158_microdata.csv
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

import pandas as pd
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src import buckets, env_loader, expected_dist, poll_runner, validation  # noqa: E402

env_loader.load_anthropic_key()


def _attach_validation_axes(jurors: pd.DataFrame) -> pd.DataFrame:
    out = jurors.copy()
    out["age"] = buckets.bucket_age_validation(out["AGE"])
    out["race"] = buckets.bucket_race_validation(out["race_bucket"])
    out["education"] = out["education_bucket"]
    out["party"] = out["political_party"]
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in-dir", required=True, help="dir containing expanded_corpus.parquet to re-poll")
    parser.add_argument("--polling-mode", choices=["direct", "probvec"], default="probvec")
    parser.add_argument("--polling-model", default=None,
                        help="override model for polling calls (default: cfg.expansion.default_model)")
    parser.add_argument("--option-order",
                        choices=["canonical", "reverse", "randomize"],
                        default="canonical",
                        help="how options are presented to the LLM per (juror, question). "
                             "'canonical' = Pew source order; 'reverse' = reversed once per question "
                             "(diagnostic only — see 2026-05-17 cross-model canary); "
                             "'randomize' = per-(juror, question) deterministic shuffle, recommended "
                             "for production runs. Validation harness sees unchanged option semantics "
                             "so cell metrics stay comparable across modes.")
    parser.add_argument("--reverse-options", action="store_true",
                        help="DEPRECATED: shorthand for --option-order reverse. "
                             "Retained for the 2026-05-17 cross-model canary scripts; new code "
                             "should use --option-order.")
    parser.add_argument("--n-sample", type=int, default=None,
                        help="subsample N jurors from the corpus deterministically with run_seed. "
                             "Required for canary runs against a large Stage B corpus.")
    parser.add_argument("--question-ids", default=None,
                        help="comma-separated subset of question ids to poll (e.g. Q5_a,Q8_b). "
                             "Default: poll all questions in the pew-questions file.")
    parser.add_argument("--run-label", required=True, help="label suffix for output dir")
    parser.add_argument("--pew-questions", required=True)
    parser.add_argument("--pew-microdata", required=True)
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--skip-preflight", action="store_true",
                        help="skip API preflight (use only when preflight already passed this session)")
    args = parser.parse_args()

    in_dir = REPO_ROOT / args.in_dir
    expanded_path = in_dir / "expanded_corpus.parquet"
    if not expanded_path.exists():
        print(f"FATAL: expanded_corpus.parquet not found at {expanded_path}", file=sys.stderr)
        sys.exit(2)
    jurors = pd.read_parquet(expanded_path)
    print(f"loaded expanded corpus: {len(jurors)} jurors from {in_dir.name}")

    cfg = yaml.safe_load((REPO_ROOT / args.config).read_text())

    # Subsample if requested.
    if args.n_sample is not None and args.n_sample < len(jurors):
        jurors = jurors.sample(n=args.n_sample, random_state=cfg["run"]["seed"]).reset_index(drop=True)
        print(f"subsampled to n={len(jurors)} jurors (seed={cfg['run']['seed']})")

    n = len(jurors)
    polling_model = args.polling_model or cfg["expansion"]["default_model"]
    # Reconcile legacy --reverse-options shorthand with the new flag.
    if args.reverse_options and args.option_order == "canonical":
        option_order = "reverse"
    elif args.reverse_options and args.option_order != "reverse":
        print(f"FATAL: --reverse-options and --option-order={args.option_order} disagree", file=sys.stderr)
        sys.exit(2)
    else:
        option_order = args.option_order
    order_tag = {"canonical": "fwd", "reverse": "rev", "randomize": "rand"}[option_order]
    # Short model tag for dir naming
    model_tag = "sonnet" if "sonnet" in polling_model else ("opus" if "opus" in polling_model else polling_model)

    prefix = "canary_" if n < 500 else ""
    poll_id = cfg["validation"]["pew_source"].get("poll_id", "unknown")
    today = date.today().isoformat().replace("-", "")
    out_label = (f"{prefix}{poll_id}_n{n}_{args.polling_mode}_"
                 f"{model_tag}_{order_tag}_{today}_{args.run_label}")
    out_dir = REPO_ROOT / "out" / "stage_b" / out_label
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"output -> {out_dir}")

    # Pull field date from spec
    spec_path = REPO_ROOT / "data" / "pew" / f"{cfg['validation']['pew_source']['poll_id']}_spec.json"
    spec = json.loads(spec_path.read_text())
    field_date_iso = spec.get("field_window") or "the survey field date"
    print(f"  polling_mode: {args.polling_mode}, model: {polling_model}, "
          f"option_order: {option_order}, field date: {field_date_iso}")

    # === API preflight ===
    if not args.skip_preflight:
        print("running API preflight...")
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        import preflight as preflight_mod  # noqa: E402
        rc = preflight_mod.preflight(REPO_ROOT / args.config)
        if rc != 0:
            sys.exit(rc)
    else:
        print("(skipping preflight per --skip-preflight)")

    # === Load questions + apply subsetting + option reversal ===
    questions = json.loads(Path(args.pew_questions).read_text())
    if args.question_ids:
        wanted = {qid.strip() for qid in args.question_ids.split(",") if qid.strip()}
        questions = [q for q in questions if q["id"] in wanted]
        missing = wanted - {q["id"] for q in questions}
        if missing:
            print(f"FATAL: question ids not found in pew-questions file: {sorted(missing)}", file=sys.stderr)
            sys.exit(2)
        print(f"restricted to {len(questions)} questions: {[q['id'] for q in questions]}")
    # Note: option-order presentation is now handled per-(juror, question) inside
    # `poll_runner.run_poll` via the `option_order` parameter, not by pre-mutating
    # the questions list. The questions JSON below records the canonical option
    # order; the per-call presentation order is persisted in synth_responses
    # under `options_as_presented`.
    (out_dir / "questions_as_polled.json").write_text(json.dumps(questions, indent=2))

    # === Re-poll ===
    jurors_with_axes = _attach_validation_axes(jurors)
    synth_responses = poll_runner.run_poll(
        jurors_with_axes, questions,
        field_date_iso=field_date_iso,
        model=polling_model,
        allow_failures=(n < 500),  # canary opts into fail-open
        polling_mode=args.polling_mode,
        run_seed=cfg["run"]["seed"],
        option_order=option_order,
    )

    # Merge validation axes onto responses
    axes_only = jurors_with_axes[["pums_idx", "age", "race", "education", "party"]]
    synth_long = synth_responses.merge(
        axes_only, left_on="juror_id", right_on="pums_idx", how="left",
    )
    assert "weight" in synth_long.columns
    synth_long.to_parquet(out_dir / "synth_responses.parquet")
    print(f"saved synth_responses -> {out_dir / 'synth_responses.parquet'}")

    # === Validation ===
    source = pd.read_csv(args.pew_microdata)
    cells_config = {
        "top_level": {
            axis: {"buckets": spec["buckets"], "min_synth_n": spec["min_synth_n"], "min_source_n": spec["min_source_n"]}
            for axis, spec in cfg["validation"]["validation_cells"]["top_level"].items()
        },
        "interaction": {pair: spec for pair, spec in cfg["validation"]["validation_cells"]["interaction"].items()},
    }
    all_results = []
    for q in questions:
        q_synth = synth_long[synth_long["question_id"] == q["id"]]
        q_source = source[source["question_id"] == q["id"]]
        if q_source.empty:
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
            "top_level_cells": {ax: [asdict(c) for c in cells] for ax, cells in result.top_level_cells.items()},
            "interaction_cells": {ax: [asdict(c) for c in cells] for ax, cells in result.interaction_cells.items()},
        })
        print(f"  {q['id']}: cov_pass={coverage.overall_passes} thr_pass={thresholds.overall_passes}")
    with (out_dir / "validation_results.json").open("w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\nvalidation_results.json -> {out_dir}")

    if args.polling_mode == "probvec":
        exp_path = out_dir / "expected_distribution_diagnostics.json"
        expected_dist.save_expected_diagnostics(
            exp_path, synth_long, questions, source,
            source_weight_col=cfg["validation"]["pew_source"].get("weight_col", "WEIGHT"),
        )
        print(f"expected_distribution_diagnostics.json -> {exp_path}")
    print("done.")


if __name__ == "__main__":
    main()
