"""Expected-distribution diagnostics for probvec polling output.

Computes the weighted expected distribution across all jurors' probability
vectors per question (the model's latent calibration on each option). This
is distinct from the SAMPLED distribution that the validation harness scores
against Pew; at finite n the sampled outcome carries hash-sampling noise
that the expected distribution does not.

For Stage B, the methodologist will want both:
  - SAMPLED metrics (what the published poll-replication produced)
  - EXPECTED metrics (what the model's underlying calibration produced)

The breakthrough claim of probvec polling is that the model's *latent*
distribution calibrates to the source survey. Storing both makes that
claim inspectable.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass

import pandas as pd


@dataclass
class ExpectedDist:
    question_id: str
    n_synth: int
    n_failed: int
    total_weight: float
    distribution: dict[str, float]      # option -> weighted-expected probability
    entropy_nats: float                  # Shannon entropy of the expected distribution
    mean_juror_max_p: float | None       # avg of per-juror max-prob (low = spread juror vectors)
    median_juror_entropy: float | None   # median juror-level prob_entropy
    pct_jurors_concentrated: float | None  # % jurors with max_p > 0.85


def compute_expected_per_question(
    synth_responses: pd.DataFrame, questions: list[dict]
) -> list[ExpectedDist]:
    """For each question, weighted-aggregate juror probability vectors into
    the expected population distribution. Requires probvec mode output
    (rows with `probabilities_json` column populated)."""
    out = []
    for q in questions:
        qid = q["id"]
        options = q["options"]
        qdf = synth_responses[synth_responses["question_id"] == qid]
        if qdf.empty:
            continue
        valid = qdf[qdf["probabilities_json"].notna()]
        n_failed = len(qdf) - len(valid)
        if valid.empty:
            out.append(ExpectedDist(
                question_id=qid, n_synth=len(qdf), n_failed=n_failed,
                total_weight=0.0, distribution={o: 0.0 for o in options},
                entropy_nats=0.0, mean_juror_max_p=None,
                median_juror_entropy=None, pct_jurors_concentrated=None,
            ))
            continue
        # Aggregate
        accum = {o: 0.0 for o in options}
        total_w = 0.0
        for _, r in valid.iterrows():
            probs = json.loads(r["probabilities_json"])
            w = r["weight"]
            for opt in options:
                accum[opt] += probs.get(opt, 0.0) * w
            total_w += w
        if total_w > 0:
            dist = {o: accum[o] / total_w for o in options}
        else:
            dist = {o: 0.0 for o in options}
        # Entropy of the expected distribution
        entropy = -sum(p * math.log(p) for p in dist.values() if p > 0)
        # Per-juror diagnostics
        max_p = valid["prob_max"].dropna()
        ent = valid["prob_entropy"].dropna()
        out.append(ExpectedDist(
            question_id=qid, n_synth=len(qdf), n_failed=n_failed,
            total_weight=total_w, distribution=dist, entropy_nats=entropy,
            mean_juror_max_p=float(max_p.mean()) if not max_p.empty else None,
            median_juror_entropy=float(ent.median()) if not ent.empty else None,
            pct_jurors_concentrated=float((max_p > 0.85).mean()) if not max_p.empty else None,
        ))
    return out


def compute_topline_accuracy_vs_source(
    expected: list[ExpectedDist], source_responses: pd.DataFrame,
    questions: list[dict], source_weight_col: str = "WEIGHT",
) -> list[dict]:
    """For each question, compare expected synth distribution to weighted Pew
    distribution. Reports max absolute percentage-point error per option."""
    out = []
    for q, exp in zip(questions, expected):
        qid = q["id"]
        src = source_responses[source_responses["question_id"] == qid]
        if src.empty:
            continue
        src_dist = (src.groupby("response")[source_weight_col].sum()
                    / src[source_weight_col].sum()).to_dict()
        per_option = []
        max_abs_err = 0.0
        for opt in q["options"]:
            synth_p = exp.distribution.get(opt, 0.0)
            src_p = src_dist.get(opt, 0.0)
            err = synth_p - src_p
            per_option.append({"option": opt, "synth_expected": round(synth_p, 4),
                               "source": round(src_p, 4), "delta_pp": round(err * 100, 2)})
            max_abs_err = max(max_abs_err, abs(err) * 100)
        out.append({
            "question_id": qid,
            "n_synth_valid": exp.n_synth - exp.n_failed,
            "n_source": len(src),
            "max_abs_error_pp": round(max_abs_err, 2),
            "synth_entropy_nats": round(exp.entropy_nats, 4),
            "per_juror_calibration": {
                "mean_max_p": round(exp.mean_juror_max_p, 4) if exp.mean_juror_max_p is not None else None,
                "median_entropy": round(exp.median_juror_entropy, 4) if exp.median_juror_entropy is not None else None,
                "pct_concentrated_gt_0.85": round(exp.pct_jurors_concentrated, 4) if exp.pct_jurors_concentrated is not None else None,
            },
            "per_option_comparison": per_option,
        })
    return out


def save_expected_diagnostics(
    out_path, synth_responses, questions, source_responses, source_weight_col,
) -> None:
    """Write expected_distribution_diagnostics.json to the given path."""
    expected = compute_expected_per_question(synth_responses, questions)
    topline = compute_topline_accuracy_vs_source(
        expected, source_responses, questions, source_weight_col,
    )
    payload = {
        "schema_version": "1.0",
        "interpretation": (
            "Expected distribution = weighted sum of per-juror probability vectors "
            "(the model's latent calibration). Distinct from the SAMPLED distribution "
            "that validation_results.json scores. At finite n, sampled outcomes carry "
            "hash-sampling noise that expected does not. The breakthrough claim of "
            "probvec polling is that the model's latent distribution calibrates to "
            "the source survey — this artifact makes that claim inspectable."
        ),
        "per_question": topline,
    }
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2, default=str)
