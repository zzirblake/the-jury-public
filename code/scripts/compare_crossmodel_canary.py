"""Compare the 4 arms of the W158 cross-model + option-order canary.

Loads `expected_distribution_diagnostics.json` from each of the 4 arms plus the
baseline v1 Stage B run, and produces a per-question per-option table showing
how expected-distribution toplines move across:

  - baseline v1 (Sonnet, Pew order, n=1000 — already in hand)
  - arm 1 (Sonnet, Pew order, n=200 — sub-sample sanity check)
  - arm 2 (Sonnet, reversed order, n=200)
  - arm 3 (Opus,   Pew order, n=200)
  - arm 4 (Opus,   reversed order, n=200)

Discriminating reads:
  - arm1 ≈ baseline → n=200 sub-sample faithfully reproduces the n=1000 latent
  - arm2 - arm1 → option-order effect on Sonnet
  - arm3 - arm1 → model effect (Opus vs Sonnet) at Pew option order
  - arm4 - arm3 → option-order effect on Opus
  - (arm3 - arm1) ≈ (arm4 - arm2) → option-order and model effects are independent

Output: writes `out/stage_b/w158_crossmodel_canary_comparison.json` + prints
a per-question summary.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

ARMS = [
    ("baseline", "out/stage_b/W158_n1000_probvec_20260516_v1"),
    ("sonnet_fwd_n200", "out/stage_b/canary_W158_n200_probvec_sonnet_fwd_20260517_crossmodel"),
    ("sonnet_rev_n200", "out/stage_b/canary_W158_n200_probvec_sonnet_rev_20260517_crossmodel"),
    ("opus_fwd_n200", "out/stage_b/canary_W158_n200_probvec_opus_fwd_20260517_crossmodel"),
    ("opus_rev_n200", "out/stage_b/canary_W158_n200_probvec_opus_rev_20260517_crossmodel"),
]

CANARY_QUESTIONS = [
    "Q5_scientists_policy_role",
    "Q8_covid_updated_vaccine",
    "Q9_astrology_belief",
    "Q11_police_confidence",
]


def load_arm_topline(arm_dir: Path) -> dict[str, dict[str, dict[str, float]]]:
    """Return {qid: {option: {synth_expected, source, delta_pp}}} from expected_distribution_diagnostics.json."""
    diag_path = arm_dir / "expected_distribution_diagnostics.json"
    if not diag_path.exists():
        return {}
    diag = json.loads(diag_path.read_text())
    out = {}
    for q in diag["per_question"]:
        qid = q["question_id"]
        if qid not in CANARY_QUESTIONS:
            continue
        out[qid] = {
            entry["option"]: {
                "synth_expected": entry["synth_expected"],
                "source": entry["source"],
                "delta_pp": entry["delta_pp"],
            }
            for entry in q["per_option_comparison"]
        }
    return out


def main():
    arm_data: dict[str, dict] = {}
    missing = []
    for name, rel in ARMS:
        arm_dir = REPO_ROOT / rel
        if not arm_dir.exists():
            missing.append(name)
            continue
        arm_data[name] = load_arm_topline(arm_dir)
    if missing:
        print(f"WARNING: arms not yet present (run may still be in flight): {missing}")
        if "baseline" not in arm_data or not any(k for k in arm_data if k != "baseline"):
            print("baseline + at least one canary arm required; exiting.")
            sys.exit(2)

    # ============================================================
    # Per-question per-option cross-arm table + 2x2 factorial contrasts
    # ============================================================
    # Factorial contrasts per option:
    #   model_delta_fwd  = opus_fwd - sonnet_fwd    (model effect at canonical order)
    #   model_delta_rev  = opus_rev - sonnet_rev    (model effect at reversed order)
    #   order_delta_son  = sonnet_rev - sonnet_fwd  (order effect on Sonnet)
    #   order_delta_opus = opus_rev - opus_fwd      (order effect on Opus)
    #   interaction      = model_delta_rev - model_delta_fwd
    #                    = order_delta_opus - order_delta_son
    #                    (model x order interaction; nonzero means the two
    #                     perturbations are not independent)
    summary = {"per_question": {}, "headline_per_question": {}}
    for qid in CANARY_QUESTIONS:
        options = list(arm_data.get("baseline", {}).get(qid, {}).keys())
        if not options:
            for arm in arm_data:
                if qid in arm_data[arm]:
                    options = list(arm_data[arm][qid].keys())
                    break
        if not options:
            continue
        rows = []
        pew_dist = {}
        for opt in options:
            row = {"option": opt}
            for arm in arm_data:
                if qid in arm_data[arm] and opt in arm_data[arm][qid]:
                    row[arm] = round(arm_data[arm][qid][opt]["synth_expected"] * 100, 2)
                    row[f"{arm}_delta_pp"] = round(arm_data[arm][qid][opt]["delta_pp"], 2)
                    pew_dist[opt] = arm_data[arm][qid][opt]["source"]
                else:
                    row[arm] = None
                    row[f"{arm}_delta_pp"] = None
            # Factorial contrasts (pp). Only computed when all 4 canary arms have this option.
            sf, sr = row.get("sonnet_fwd_n200"), row.get("sonnet_rev_n200")
            of, orv = row.get("opus_fwd_n200"), row.get("opus_rev_n200")
            if None not in (sf, sr, of, orv):
                model_delta_fwd = round(of - sf, 2)
                model_delta_rev = round(orv - sr, 2)
                order_delta_son = round(sr - sf, 2)
                order_delta_opus = round(orv - of, 2)
                interaction = round(model_delta_rev - model_delta_fwd, 2)
                row.update({
                    "model_delta_fwd_pp": model_delta_fwd,
                    "model_delta_rev_pp": model_delta_rev,
                    "order_delta_sonnet_pp": order_delta_son,
                    "order_delta_opus_pp": order_delta_opus,
                    "interaction_pp": interaction,
                })
            rows.append(row)
        summary["per_question"][qid] = {
            "pew_pct": {o: round(pew_dist.get(o, 0) * 100, 2) for o in options},
            "options": options,
            "per_option_pct": rows,
        }
        # Headline: max abs delta per arm
        headline = {}
        for arm in arm_data:
            if qid not in arm_data[arm]:
                headline[arm] = None
                continue
            max_abs = max(abs(arm_data[arm][qid][o]["delta_pp"]) for o in options)
            headline[arm] = round(max_abs, 2)
        # Question-level factorial summary: max-abs contrast across options
        contrast_max = {}
        contrast_fields = ["model_delta_fwd_pp", "model_delta_rev_pp",
                           "order_delta_sonnet_pp", "order_delta_opus_pp", "interaction_pp"]
        for fld in contrast_fields:
            vals = [abs(r[fld]) for r in rows if fld in r and r[fld] is not None]
            contrast_max[fld] = round(max(vals), 2) if vals else None
        summary["headline_per_question"][qid] = {
            "max_abs_error_per_arm": headline,
            "max_abs_contrast_pp": contrast_max,
        }

    # ============================================================
    # Save + print
    # ============================================================
    out_path = REPO_ROOT / "out" / "stage_b" / "w158_crossmodel_canary_comparison.json"
    out_path.write_text(json.dumps(summary, indent=2))
    print(f"wrote {out_path}\n")

    # Per-question max-abs-error-per-arm headline
    print(f"{'Question':40s} | " + " | ".join(f"{a:>17s}" for a, _ in ARMS))
    print("-" * 130)
    for qid in CANARY_QUESTIONS:
        if qid not in summary["headline_per_question"]:
            continue
        h = summary["headline_per_question"][qid]["max_abs_error_per_arm"]
        row = f"{qid:40s} | " + " | ".join(
            f"{h.get(a):>15}pp" if h.get(a) is not None else f"{'pending':>17s}"
            for a, _ in ARMS
        )
        print(row)

    # Factorial contrast headline (max-abs across options per question)
    contrast_cols = ["model_delta_fwd_pp", "model_delta_rev_pp",
                     "order_delta_sonnet_pp", "order_delta_opus_pp", "interaction_pp"]
    print()
    print("FACTORIAL CONTRASTS (max abs across options, pp)")
    print(f"{'Question':40s} | " + " | ".join(f"{c.replace('_pp',''):>20s}" for c in contrast_cols))
    print("-" * 150)
    for qid in CANARY_QUESTIONS:
        if qid not in summary["headline_per_question"]:
            continue
        c = summary["headline_per_question"][qid]["max_abs_contrast_pp"]
        row = f"{qid:40s} | " + " | ".join(
            f"{c.get(col):>18}pp" if c.get(col) is not None else f"{'-':>20s}"
            for col in contrast_cols
        )
        print(row)
    print()

    # Per-option deltas for the four worst questions
    for qid in CANARY_QUESTIONS:
        if qid not in summary["per_question"]:
            continue
        pq = summary["per_question"][qid]
        print(f"\n=== {qid} ===")
        print(f"  Pew %: " + ", ".join(f"{o[:30]}={p:.1f}" for o, p in pq["pew_pct"].items()))
        print()
        print(f"  {'Option':45s} " + " ".join(f"{a:>10s}" for a, _ in ARMS))
        for row in pq["per_option_pct"]:
            cells = []
            for a, _ in ARMS:
                v = row.get(a)
                cells.append(f"{v:>9.1f}%" if v is not None else "    --   ")
            print(f"  {row['option'][:45]:45s} " + " ".join(cells))


if __name__ == "__main__":
    main()
