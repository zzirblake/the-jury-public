"""Generate 3 alternative SVG figures for the §Regression-coefficient-comparison
section so Blake can pick one (or two) to embed.

Each design tells the same story differently:
  6a: pooled scatter — "direction is right, magnitude is off" in a single panel
  6b: two-panel direction-vs-magnitude — splits the finding into its two parts
  6c: per-question scorecard — heatmap-style table of metrics vs locked thresholds

All read from out/stage_b/W158_n1000_probvec_20260516_v1/regression_comparison.json.
SVG output so Figma can import and restyle.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
FIG_DIR = REPO_ROOT.parent / "docs" / "figures"
SRC = REPO_ROOT / "out" / "stage_b" / "W158_n1000_probvec_20260516_v1" / "regression_comparison.json"

Q_LABELS = {
    "Q1_climate_personal_impact": "Q1 climate impact",
    "Q2_climate_human_cause": "Q2 climate cause",
    "Q3_climate_policy_economy": "Q3 climate policy",
    "Q4_scientist_confidence": "Q4 sci confidence",
    "Q5_scientists_policy_role": "Q5 sci policy role",
    "Q6_covid_restrictions_retro": "Q6 COVID restr",
    "Q7_covid_school_closures": "Q7 school closures",
    "Q8_covid_updated_vaccine": "Q8 vaccine",
    "Q9_astrology_belief": "Q9 astrology",
    "Q10_astrology_consult_freq": "Q10 horoscope freq",
    "Q11_police_confidence": "Q11 police",
}

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
    "font.size": 10,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.titleweight": "bold",
    "axes.titlesize": 12,
    "axes.labelsize": 10,
    "figure.dpi": 100,
    "savefig.bbox": "tight",
    "savefig.facecolor": "white",
})


def load_per_coef_rows():
    """Flatten the JSON into per-coefficient rows across all (question, option) pairs."""
    data = json.loads(SRC.read_text())
    rows = []
    for qopt_key, three_levels in data["per_option"].items():
        qid, opt = qopt_key.split("::", 1)
        comp = three_levels.get("primary", {})
        if not comp.get("valid"):
            continue
        for cp in comp.get("per_coef", []):
            if cp["coef"] == "intercept":
                continue
            rows.append({
                "qid": qid, "option": opt, "coef_name": cp["coef"],
                "pew": cp["pew"], "synth": cp["synth"],
                "sign_agree": cp["sign_agree"],
                "ci_overlap": cp["ci_overlap"],
                "meaningful": cp["meaningful"],
            })
    return pd.DataFrame(rows), data


# ============================================================
# 6a — Pooled scatter, single panel
# "Direction is right; magnitude is off"
# ============================================================
def fig6a_pooled_scatter():
    df, data = load_per_coef_rows()
    # Pool across all 11 questions, only meaningful coefficients
    meaningful = df[df.meaningful].copy()
    nearzero = df[~df.meaningful].copy()

    fig, ax = plt.subplots(figsize=(8.5, 8))

    # Per-question color palette
    qids = sorted(df.qid.unique())
    cmap = plt.get_cmap("tab20")
    colors = {q: cmap(i / max(len(qids) - 1, 1)) for i, q in enumerate(qids)}

    # Near-zero (faded background)
    ax.scatter(nearzero.pew, nearzero.synth, s=8, facecolors="none",
               edgecolors="#bbbbbb", linewidths=0.4, alpha=0.4, zorder=1)

    # Meaningful: color by question, mark sign-disagreement as red ring
    for qid in qids:
        sub = meaningful[meaningful.qid == qid]
        agree = sub[sub.sign_agree]
        disagree = sub[~sub.sign_agree]
        ax.scatter(agree.pew, agree.synth, s=42, c=[colors[qid]],
                   edgecolors="white", linewidths=0.5, alpha=0.85,
                   label=Q_LABELS[qid], zorder=3)
        ax.scatter(disagree.pew, disagree.synth, s=55, c=[colors[qid]],
                   edgecolors="#C44E52", linewidths=1.6, alpha=0.95, zorder=4)

    # Diagonal y=x reference (perfect agreement)
    lim_lo = min(df.pew.min(), df.synth.min()) - 0.2
    lim_hi = max(df.pew.max(), df.synth.max()) + 0.2
    ax.plot([lim_lo, lim_hi], [lim_lo, lim_hi], color="#666666",
            linewidth=1.0, linestyle="--", label="y = x (perfect agreement)", zorder=2)
    ax.axhline(0, color="#dddddd", linewidth=0.5, zorder=0)
    ax.axvline(0, color="#dddddd", linewidth=0.5, zorder=0)

    ax.set_xlabel("Pew coefficient (log-odds)", fontsize=12)
    ax.set_ylabel("Synth panel coefficient (log-odds)", fontsize=12)
    op = data.get("overall_primary", {})
    mv = op.get("metric_values", {})
    title = (
        f"Pew vs synth: where each demographic group lands on each survey option\n"
        f"Points cluster along y=x (direction agreement); spread off-diagonal is magnitude divergence.  "
        f"Median per-Q correlation = {mv.get('median_per_question_pearson_r', 0):.2f}, "
        f"sign agreement = {mv.get('macro_sign_agreement_rate', 0):.0%}"
    )
    ax.set_title(title, fontsize=10.5, loc="left", pad=14)
    ax.legend(loc="upper left", framealpha=0.92, fontsize=8.5, ncol=2)
    ax.grid(alpha=0.15)
    ax.set_xlim(lim_lo, lim_hi)
    ax.set_ylim(lim_lo, lim_hi)
    ax.set_aspect("equal")

    plt.savefig(FIG_DIR / "fig6a_pooled_scatter.svg", format="svg")
    plt.savefig(FIG_DIR / "fig6a_pooled_scatter.png", format="png", dpi=150)
    plt.close()
    print(f"wrote {FIG_DIR / 'fig6a_pooled_scatter.svg'} + .png")


# ============================================================
# 6b — Two-panel "direction story" + "magnitude story"
# Per question: sign agreement % (direction) + median std-delta (magnitude)
# ============================================================
def fig6b_two_panel_direction_vs_magnitude():
    data = json.loads(SRC.read_text())
    qids = list(Q_LABELS.keys())
    sign_rates = []
    std_deltas = []
    for q in qids:
        agg = data["per_question_primary"].get(q, {})
        sign_rates.append(agg.get("median_sign_agreement_rate") or 0)
        std_deltas.append(agg.get("median_standardized_delta") or 0)

    fig, (ax_l, ax_r) = plt.subplots(1, 2, figsize=(14, 5.5))

    # Left: sign agreement (direction)
    x_pos = np.arange(len(qids))
    labels = [Q_LABELS[q] for q in qids]
    # Color by threshold band: success >85%, partial 70-85%, failure <70%
    sign_colors = [
        "#55A868" if r > 0.85 else "#DD8452" if r > 0.70 else "#C44E52"
        for r in sign_rates
    ]
    ax_l.barh(x_pos, [r * 100 for r in sign_rates], color=sign_colors, alpha=0.9)
    for i, r in enumerate(sign_rates):
        ax_l.text(r * 100 + 1, i, f"{r:.0%}", va="center", fontsize=9.5)
    ax_l.set_yticks(x_pos)
    ax_l.set_yticklabels(labels, fontsize=10)
    ax_l.invert_yaxis()
    ax_l.axvline(85, color="#55A868", linestyle="--", linewidth=0.8, alpha=0.6)
    ax_l.axvline(70, color="#C44E52", linestyle="--", linewidth=0.8, alpha=0.6)
    ax_l.set_xlim(0, 110)
    ax_l.set_xlabel("Sign agreement (%) — does synth point the same direction as Pew?", fontsize=10)
    ax_l.set_title("DIRECTION: which way each demographic group leans\n(green = success, orange = partial, red = failure)",
                   fontsize=11, loc="left", pad=10)
    ax_l.grid(axis="x", alpha=0.2)

    # Right: standardized delta (magnitude)
    std_colors = [
        "#55A868" if d < 1.0 else "#DD8452" if d < 2.0 else "#C44E52"
        for d in std_deltas
    ]
    ax_r.barh(x_pos, std_deltas, color=std_colors, alpha=0.9)
    for i, d in enumerate(std_deltas):
        ax_r.text(d + 0.05, i, f"{d:.2f}σ", va="center", fontsize=9.5)
    ax_r.set_yticks(x_pos)
    ax_r.set_yticklabels([])  # avoid duplicating labels
    ax_r.invert_yaxis()
    ax_r.axvline(1.0, color="#55A868", linestyle="--", linewidth=0.8, alpha=0.6)
    ax_r.axvline(2.0, color="#C44E52", linestyle="--", linewidth=0.8, alpha=0.6)
    ax_r.set_xlim(0, max(std_deltas) * 1.15)
    ax_r.set_xlabel("Standardized delta — how many standard errors apart Pew & synth are", fontsize=10)
    ax_r.set_title("MAGNITUDE: how strong each demographic effect is\n(lower = closer; failure threshold = 2σ)",
                   fontsize=11, loc="left", pad=10)
    ax_r.grid(axis="x", alpha=0.2)

    fig.suptitle(
        "The synth panel agrees with Pew on which direction each demographic group leans, "
        "but mis-calibrates how strong those leans are.",
        fontsize=12, y=1.02
    )
    plt.tight_layout()
    plt.savefig(FIG_DIR / "fig6b_direction_vs_magnitude.svg", format="svg")
    plt.savefig(FIG_DIR / "fig6b_direction_vs_magnitude.png", format="png", dpi=150)
    plt.close()
    print(f"wrote {FIG_DIR / 'fig6b_direction_vs_magnitude.svg'} + .png")


# ============================================================
# 6c — Per-question scorecard (heatmap-style)
# 11 rows × 4 metric columns, color-coded against locked thresholds
# ============================================================
def fig6c_scorecard():
    data = json.loads(SRC.read_text())
    qids = list(Q_LABELS.keys())

    # Compute per-question values
    rows = []
    for q in qids:
        agg = data["per_question_primary"].get(q, {})
        rows.append({
            "qid": q,
            "label": Q_LABELS[q],
            "pearson_r": agg.get("median_pearson_r") or 0,
            "sign_pct": (agg.get("median_sign_agreement_rate") or 0) * 100,
            "ci_overlap_pct": (agg.get("median_ci_overlap_rate") or 0) * 100,
            "std_delta": agg.get("median_standardized_delta") or 0,
        })
    df = pd.DataFrame(rows)

    # Color bands per metric (success / partial / failure)
    def band_pearson(v):
        return "#55A868" if v > 0.70 else "#DD8452" if v > 0.40 else "#C44E52"
    def band_sign(v):
        return "#55A868" if v > 85 else "#DD8452" if v > 70 else "#C44E52"
    def band_ci(v):
        return "#55A868" if v > 80 else "#DD8452" if v > 60 else "#C44E52"
    def band_std(v):  # lower is better
        return "#55A868" if v < 1.0 else "#DD8452" if v < 2.0 else "#C44E52"

    fig, ax = plt.subplots(figsize=(12, 6.5))
    n = len(df)
    metrics = [
        ("Pearson correlation\n(higher = better)", "pearson_r", band_pearson, lambda v: f"{v:.2f}"),
        ("Sign agreement %\n(higher = better)", "sign_pct", band_sign, lambda v: f"{v:.0f}%"),
        ("CI overlap %\n(higher = better)", "ci_overlap_pct", band_ci, lambda v: f"{v:.0f}%"),
        ("Standardized delta\n(lower = better)", "std_delta", band_std, lambda v: f"{v:.2f}σ"),
    ]

    # Draw cells
    for i, (mlabel, col, band_fn, fmt) in enumerate(metrics):
        for j in range(n):
            v = df.iloc[j][col]
            color = band_fn(v)
            rect = mpatches.Rectangle((i, n - j - 1), 1, 1, facecolor=color,
                                       edgecolor="white", linewidth=2, alpha=0.85)
            ax.add_patch(rect)
            ax.text(i + 0.5, n - j - 1 + 0.5, fmt(v),
                    ha="center", va="center", fontsize=11, fontweight="bold",
                    color="white")
        # Column header
        ax.text(i + 0.5, n + 0.3, mlabel, ha="center", va="bottom", fontsize=10, fontweight="bold")

    # Row labels (question names)
    for j in range(n):
        ax.text(-0.15, n - j - 1 + 0.5, df.iloc[j]["label"], ha="right", va="center", fontsize=10)

    ax.set_xlim(-2.5, len(metrics) + 0.2)
    ax.set_ylim(-1.2, n + 1.2)
    ax.axis("off")

    op = data.get("overall_primary", {})
    band_text = op.get("band", "n/a")
    fig.suptitle(
        f"Per-question regression-coefficient comparison vs Pew (primary, probvec).  "
        f"Overall outcome: {band_text.upper()}.\n"
        f"Green = pre-registered success band.  Orange = partial.  Red = failure.",
        fontsize=11, y=0.98
    )
    # Legend
    legend_elems = [
        mpatches.Patch(color="#55A868", label="Success band (pre-registered)"),
        mpatches.Patch(color="#DD8452", label="Partial band"),
        mpatches.Patch(color="#C44E52", label="Failure band"),
    ]
    ax.legend(handles=legend_elems, loc="lower center", framealpha=0.9, fontsize=9.5,
              bbox_to_anchor=(0.5, -0.08), ncol=3)

    plt.savefig(FIG_DIR / "fig6c_scorecard.svg", format="svg")
    plt.savefig(FIG_DIR / "fig6c_scorecard.png", format="png", dpi=150)
    plt.close()
    print(f"wrote {FIG_DIR / 'fig6c_scorecard.svg'} + .png")


def main():
    fig6a_pooled_scatter()
    fig6b_two_panel_direction_vs_magnitude()
    fig6c_scorecard()
    print(f"\nAll 3 alternative figures (SVG + PNG) in {FIG_DIR}")
    print("  6a: pooled scatter (single panel, all coefs, color by question)")
    print("  6b: two-panel direction-vs-magnitude (per-question bars)")
    print("  6c: per-question scorecard (heatmap-style, 4 metrics)")


if __name__ == "__main__":
    main()
