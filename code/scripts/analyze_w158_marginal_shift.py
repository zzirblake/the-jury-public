"""W158 marginal-shift analysis.

Local-compute inspection on the Stage B W158 v1 output. No API calls.

Outputs intermediate JSON at out/stage_b/W158_n1000_probvec_20260516_v1/marginal_shift_analysis.json
that the analysis markdown is built from.
"""

import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path("out/stage_b/W158_n1000_probvec_20260516_v1")
PEW = Path("data/pew/W158_microdata.csv")

# Extended axes pulled from trait_vectors (beyond the four validation axes).
EXTENDED_AXES = [
    "religion",
    "religiosity",
    "political_ideology",
    "media_diet_primary",
    "media_diet_slant",
    "household_composition",
    "life_stage_recent",
    "is_outlier",
]

# Validation axes (match those in validation_results.json).
VALIDATION_AXES = ["age", "race", "education", "party"]


def weighted_dist(df, value_col, weight_col, options):
    """Weighted distribution over `options` keys."""
    total_w = df[weight_col].sum()
    if total_w == 0:
        return {opt: 0.0 for opt in options}
    out = {}
    for opt in options:
        mask = df[value_col] == opt
        out[opt] = float(df.loc[mask, weight_col].sum() / total_w)
    return out


def expected_dist(probvecs, weights, options):
    """Weighted average of per-juror probability vectors."""
    w = np.asarray(weights, dtype=float)
    if w.sum() == 0:
        return {opt: 0.0 for opt in options}
    norm_w = w / w.sum()
    out = {opt: 0.0 for opt in options}
    for vec, ww in zip(probvecs, norm_w):
        for opt in options:
            out[opt] += float(vec.get(opt, 0.0)) * ww
    return out


def main():
    questions = json.loads(Path("data/pew/W158_questions.json").read_text())
    qmap = {q["id"]: q for q in questions}
    qids = [q["id"] for q in questions]

    sr = pd.read_parquet(OUT / "synth_responses.parquet")
    tv = pd.read_parquet(OUT / "trait_vectors.parquet")
    pew = pd.read_csv(PEW)

    # Merge extended trait axes into synth_responses.
    keep = ["pums_idx"] + EXTENDED_AXES
    sr = sr.merge(
        tv[keep].drop_duplicates("pums_idx"), on="pums_idx", how="left"
    )
    # Parse probvecs once.
    sr["probvec"] = sr["probabilities_json"].map(json.loads)

    results = {"per_question": {}, "extended_axis_breakdown": {}}

    # =============== Per-question analysis ===============
    for qid in qids:
        q = qmap[qid]
        options = q["options"]
        sr_q = sr[sr.question_id == qid].copy()
        pew_q = pew[pew.question_id == qid].copy()

        # (1) Topline expected vs sampled vs Pew, per option.
        pew_dist = weighted_dist(pew_q, "response", "weight", options)
        sampled_dist = weighted_dist(sr_q, "response", "weight", options)
        exp_dist = expected_dist(sr_q["probvec"].tolist(), sr_q["weight"].tolist(), options)

        per_option = []
        for opt in options:
            per_option.append(
                {
                    "option": opt,
                    "pew": pew_dist[opt],
                    "synth_expected": exp_dist[opt],
                    "synth_sampled": sampled_dist[opt],
                    "expected_minus_pew_pp": (exp_dist[opt] - pew_dist[opt]) * 100,
                    "sampled_minus_pew_pp": (sampled_dist[opt] - pew_dist[opt]) * 100,
                    "sampling_noise_pp": (sampled_dist[opt] - exp_dist[opt]) * 100,
                }
            )

        # (2) Per validation-cell expected-vs-Pew (the gap currently only at topline).
        cell_breakdown = {}
        for axis in VALIDATION_AXES:
            axis_cells = []
            for cell_val in sorted(sr_q[axis].dropna().unique()):
                sr_cell = sr_q[sr_q[axis] == cell_val]
                pew_cell = pew_q[pew_q[axis] == cell_val]
                if len(pew_cell) < 30 or len(sr_cell) < 8:
                    continue
                p = weighted_dist(pew_cell, "response", "weight", options)
                e = expected_dist(sr_cell["probvec"].tolist(), sr_cell["weight"].tolist(), options)
                s = weighted_dist(sr_cell, "response", "weight", options)
                max_abs_exp = max(abs(e[o] - p[o]) for o in options) * 100
                max_abs_smp = max(abs(s[o] - p[o]) for o in options) * 100
                axis_cells.append(
                    {
                        "cell": f"{axis}={cell_val}",
                        "n_synth": int(len(sr_cell)),
                        "n_pew": int(len(pew_cell)),
                        "max_abs_expected_pp": round(max_abs_exp, 2),
                        "max_abs_sampled_pp": round(max_abs_smp, 2),
                        "sampling_noise_share": round((max_abs_smp - max_abs_exp), 2),
                    }
                )
            cell_breakdown[axis] = axis_cells

        # (3) Worst-error cell (across all single-axis cells) on expected distribution.
        all_cells = [
            (axis, c) for axis, cells in cell_breakdown.items() for c in cells
        ]
        worst_cells = sorted(all_cells, key=lambda x: -x[1]["max_abs_expected_pp"])[:5]
        results["per_question"][qid] = {
            "options": options,
            "topline_per_option": per_option,
            "topline_max_abs_expected_pp": max(abs(po["expected_minus_pew_pp"]) for po in per_option),
            "topline_max_abs_sampled_pp": max(abs(po["sampled_minus_pew_pp"]) for po in per_option),
            "topline_sampling_noise_max_pp": max(abs(po["sampling_noise_pp"]) for po in per_option),
            "validation_cell_breakdown": cell_breakdown,
            "worst_expected_cells_top5": [
                {"axis": a, **c} for a, c in worst_cells
            ],
        }

    # =============== (3) Extended-axis cluster scan across worst questions ===============
    # For each of the worst questions (Q7,Q8,Q9,Q11) compute max-abs-expected-pp per extended axis cell.
    worst_qs = ["Q7_covid_school_closures", "Q8_covid_updated_vaccine",
                "Q9_astrology_belief", "Q11_police_confidence"]

    for qid in worst_qs:
        q = qmap[qid]
        options = q["options"]
        sr_q = sr[sr.question_id == qid].copy()
        pew_q = pew[pew.question_id == qid].copy()
        pew_topline = weighted_dist(pew_q, "response", "weight", options)
        axis_block = {}
        for axis in EXTENDED_AXES:
            if axis not in sr_q.columns:
                continue
            cells = []
            for cell_val in sorted(sr_q[axis].dropna().astype(str).unique()):
                sr_cell = sr_q[sr_q[axis].astype(str) == cell_val]
                if len(sr_cell) < 15:
                    continue
                e = expected_dist(sr_cell["probvec"].tolist(), sr_cell["weight"].tolist(), options)
                # Compare to TOPLINE Pew (Pew does not carry these extended axes).
                max_abs = max(abs(e[o] - pew_topline[o]) for o in options) * 100
                # Also signed direction per option.
                deltas = {o: round((e[o] - pew_topline[o]) * 100, 2) for o in options}
                cells.append(
                    {
                        "cell": f"{axis}={cell_val}",
                        "n_synth": int(len(sr_cell)),
                        "max_abs_pp_vs_pew_topline": round(max_abs, 2),
                        "deltas_pp": deltas,
                    }
                )
            cells_sorted = sorted(cells, key=lambda c: -c["max_abs_pp_vs_pew_topline"])
            axis_block[axis] = cells_sorted[:10]
        results["extended_axis_breakdown"][qid] = axis_block

    # =============== (4) Sample probvecs + reasonings from high-error cells ===============
    inspection = {}
    for qid in worst_qs:
        q = qmap[qid]
        options = q["options"]
        sr_q = sr[sr.question_id == qid].copy()
        pew_q = pew[pew.question_id == qid].copy()
        # Find a high-error validation cell.
        cells = results["per_question"][qid]["worst_expected_cells_top5"]
        sample = []
        for c in cells[:2]:
            axis, val = c["cell"].split("=", 1)
            sr_cell = sr_q[sr_q[axis] == val]
            pew_cell = pew_q[pew_q[axis] == val]
            pew_dist = weighted_dist(pew_cell, "response", "weight", options)
            exp_dist_c = expected_dist(sr_cell["probvec"].tolist(), sr_cell["weight"].tolist(), options)
            # Pick 3 jurors closest to median weight.
            jurors = sr_cell.copy()
            jurors_sample = jurors.sample(min(3, len(jurors)), random_state=0)
            juror_list = []
            for _, j in jurors_sample.iterrows():
                juror_list.append(
                    {
                        "juror_id": int(j.juror_id),
                        "age": j.age,
                        "race": j.race,
                        "education": j.education,
                        "party": j.party,
                        "religion": j.get("religion", ""),
                        "religiosity": j.get("religiosity", ""),
                        "ideology": j.get("political_ideology", ""),
                        "media_slant": j.get("media_diet_slant", ""),
                        "is_outlier": bool(j.get("is_outlier", False)),
                        "response_sampled": j.response,
                        "probvec": j.probvec,
                        "reasoning": j.reasoning[:600],
                    }
                )
            sample.append(
                {
                    "axis_value": c["cell"],
                    "n_synth": c["n_synth"],
                    "max_abs_pp": c["max_abs_expected_pp"],
                    "pew_dist": pew_dist,
                    "synth_expected_dist": exp_dist_c,
                    "juror_examples": juror_list,
                }
            )
        inspection[qid] = sample
    results["inspection_worst_cells"] = inspection

    # =============== Save intermediate ===============
    out_path = OUT / "marginal_shift_analysis.json"
    out_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"wrote {out_path}")

    # Quick console summary.
    print("\n--- per-question topline gap (expected vs Pew) ---")
    for qid in qids:
        r = results["per_question"][qid]
        print(f"  {qid:35s} max_exp={r['topline_max_abs_expected_pp']:5.2f}pp  "
              f"max_smp={r['topline_max_abs_sampled_pp']:5.2f}pp  "
              f"noise={r['topline_sampling_noise_max_pp']:5.2f}pp")


if __name__ == "__main__":
    main()
