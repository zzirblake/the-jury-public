"""Generate the 5 figures for the public methods writeup.

Outputs PNG files into ../docs/figures/. Each figure is deterministic and
re-runs from the existing JSON artifacts in out/stage_b/.

Figure list (per docs/writeup-outline.md):
  Fig 1: Within-cell entropy ratio by question across v1/v2/v3 polling protocols
  Fig 2: Stage B threshold breakdown — coverage passes, marginal fails
  Fig 3: Expected-distribution max error vs Pew by question (n=1000)
  Fig 4: Q9 astrology — one-juror reasoning-vs-probability gap
  Fig 5: Cross-model + option-order canary — max-abs error per arm
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # no display needed
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import pandas as pd  # used by fig6_regression_coefficient_comparison

REPO_ROOT = Path(__file__).resolve().parents[1]
FIG_DIR = REPO_ROOT.parent / "docs" / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

# Short question labels for chart readability
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
    "Q10_astrology_consult_freq": "Q10 astrology freq",
    "Q11_police_confidence": "Q11 police",
}
Q_ORDER = list(Q_LABELS.keys())

# Style — light, clean, blog-readable
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
    "font.size": 10,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.titleweight": "bold",
    "axes.titlesize": 12,
    "axes.labelsize": 10,
    "figure.dpi": 150,
    "savefig.dpi": 150,
    "savefig.bbox": "tight",
    "savefig.facecolor": "white",
})


def median_entropy_by_question(vr_path: Path) -> dict[str, float]:
    """For each question, median entropy_ratio across all MEASURED cells (top_level + interaction)."""
    vr = json.loads(vr_path.read_text())
    out = {}
    for q in vr:
        cells = []
        for axis, axis_cells in q.get("top_level_cells", {}).items():
            for c in axis_cells:
                if c.get("measured") and c.get("entropy_ratio") is not None:
                    cells.append(c["entropy_ratio"])
        for axis, axis_cells in q.get("interaction_cells", {}).items():
            for c in axis_cells:
                if c.get("measured") and c.get("entropy_ratio") is not None:
                    cells.append(c["entropy_ratio"])
        out[q["question_id"]] = statistics.median(cells) if cells else None
    return out


# ============================================================
# Fig 1: Entropy recovery v1 -> v2 -> v3
#
# Data source: chronological lab notebook table (canonical).
#
# Forensic note (2026-05-19): the on-disk dirs for v1 and v2 are byte-identical
# and the disk-v1 response distributions (Q4 68% "fair amount", Q9 94% "No")
# are systematically less compressed than the lab notebook's v1 narrative
# descriptions (Q4 84%, Q9 99%). On-disk v1 dir actually carries v2-era data
# from a pre-git copy-overwrite incident. The lab notebook table is the only
# authoritative record of true v1/v2 per-question entropy.
#
# Hard-coded here from docs/lab-notebook.md, "Full v3 canary" section, table
# "Per-question entropy median" with columns [baseline | v2 | v3].
# ============================================================

# Per-question median within-cell entropy ratio across measured cells,
# n=100 canary, sourced from lab notebook (the only complete record).
LAB_NOTEBOOK_ENTROPY = {
    "Q1_climate_personal_impact":   {"v1": 0.62, "v2": 0.67, "v3": 0.95},
    "Q2_climate_human_cause":       {"v1": 0.65, "v2": 0.69, "v3": 0.93},
    "Q3_climate_policy_economy":    {"v1": 0.58, "v2": 0.42, "v3": 0.91},
    "Q4_scientist_confidence":      {"v1": 0.35, "v2": 0.56, "v3": 0.98},
    "Q5_scientists_policy_role":    {"v1": 0.52, "v2": 0.64, "v3": 0.90},
    "Q6_covid_restrictions_retro":  {"v1": 0.77, "v2": 0.71, "v3": 0.91},
    "Q7_covid_school_closures":     {"v1": 0.42, "v2": 0.38, "v3": 0.97},
    "Q8_covid_updated_vaccine":     {"v1": 0.75, "v2": 0.66, "v3": 1.09},
    "Q9_astrology_belief":          {"v1": 0.11, "v2": 0.28, "v3": 0.48},
    "Q10_astrology_consult_freq":   {"v1": 0.51, "v2": 0.42, "v3": 0.84},
    "Q11_police_confidence":        {"v1": 0.56, "v2": 0.77, "v3": 1.00},
}


def fig1_entropy_recovery():
    v1_vals = [LAB_NOTEBOOK_ENTROPY[q]["v1"] for q in Q_ORDER]
    v2_vals = [LAB_NOTEBOOK_ENTROPY[q]["v2"] for q in Q_ORDER]
    v3_vals = [LAB_NOTEBOOK_ENTROPY[q]["v3"] for q in Q_ORDER]

    fig, ax = plt.subplots(figsize=(12, 5.4))
    x = list(range(len(Q_ORDER)))
    width = 0.27
    ax.bar([i - width for i in x], v1_vals, width,
           label="v1 direct-choice polling", color="#C44E52")
    ax.bar(x, v2_vals, width,
           label="v2 anti-center prompt patch", color="#DD8452")
    ax.bar([i + width for i in x], v3_vals, width,
           label="v3 probability-vector polling", color="#55A868")
    ax.axhline(0.80, color="#666666", linestyle="--", linewidth=1, label="threshold (0.80)")
    ax.axhline(1.00, color="#999999", linestyle=":", linewidth=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels([Q_LABELS[q] for q in Q_ORDER], rotation=35, ha="right")
    ax.set_ylabel("Median within-cell entropy ratio (synth / Pew)")
    ax.set_title("Within-cell entropy ratio by question across three polling protocols\n"
                 "Pew W158 canary, n=100 per protocol. "
                 "Probability-vector polling lifts 10 of 11 questions above the 0.80 threshold; "
                 "Q9 astrology remains compressed.")
    ax.legend(loc="upper left", framealpha=0.95, ncol=2)
    ax.set_ylim(0, 1.25)
    ax.grid(axis="y", alpha=0.3)
    ax.text(0.5, -0.30,
            "Values from chronological build log (docs/lab-notebook.md, n=100 canary per-question entropy table). "
            "Aggregate medians: v1 0.53, v2 0.56, v3 0.91.",
            transform=ax.transAxes, ha="center", fontsize=8.5,
            color="#666666", style="italic")
    plt.savefig(FIG_DIR / "fig1_entropy_recovery.png")
    plt.close()
    print(f"wrote {FIG_DIR / 'fig1_entropy_recovery.png'}")


# ============================================================
# Fig 2: Stage B threshold breakdown
# ============================================================
def fig2_threshold_breakdown():
    vr = json.loads((REPO_ROOT / "out/stage_b/W158_n1000_probvec_20260516_v1/validation_results.json").read_text())
    # Per-question pass percentages of the three threshold components
    qids, ent, mnr, mar = [], [], [], []
    for q in vr:
        t = q["thresholds"]
        qids.append(q["question_id"])
        ent.append(t["entropy_ci_pass_pct"] * 100)
        mnr.append(t["minority_ci_pass_pct"] * 100)
        mar.append(t["marginal_pass_pct"] * 100)

    fig, ax = plt.subplots(figsize=(11, 5.5))
    x = list(range(len(qids)))
    width = 0.27
    ax.bar([i - width for i in x], ent, width, label="entropy ratio CI lower ≥ 0.70", color="#4C72B0")
    ax.bar(x, mnr, width, label="minority recovery CI lower ≥ 0.45", color="#55A868")
    ax.bar([i + width for i in x], mar, width, label="marginal error sigma ≤ 2σ", color="#C44E52")
    ax.set_xticks(x)
    ax.set_xticklabels([Q_LABELS[q] for q in qids], rotation=35, ha="right")
    ax.set_ylabel("% of measured cells passing component threshold")
    ax.set_ylim(0, 105)
    ax.set_title("Stage B W158 threshold pass-rate by component (n=1,000)\n"
                 "Coverage rule passed all 11 questions; entropy + minority pass 10/11; marginal fails 11/11")
    ax.legend(loc="upper right", framealpha=0.95)
    ax.grid(axis="y", alpha=0.3)
    # Annotate the marginal-sigma failure pattern
    ax.text(0.5, 102, "marginal-sigma is the bottleneck", ha="center",
            fontsize=9, style="italic", color="#C44E52")
    plt.savefig(FIG_DIR / "fig2_threshold_breakdown.png")
    plt.close()
    print(f"wrote {FIG_DIR / 'fig2_threshold_breakdown.png'}")


# ============================================================
# Fig 3: Expected topline error by question (sorted)
# ============================================================
def fig3_expected_topline_error():
    diag = json.loads((REPO_ROOT / "out/stage_b/W158_n1000_probvec_20260516_v1/expected_distribution_diagnostics.json").read_text())
    pairs = []
    for q in diag["per_question"]:
        max_abs = max(abs(p["delta_pp"]) for p in q["per_option_comparison"])
        pairs.append((q["question_id"], max_abs))
    pairs.sort(key=lambda x: x[1])  # ascending; bottom of chart = best
    qids = [p[0] for p in pairs]
    vals = [p[1] for p in pairs]

    # Color code by severity
    def color_for(v):
        if v < 5: return "#55A868"      # green: strong
        if v < 10: return "#DD8452"     # orange: acceptable
        return "#C44E52"                # red: residual gap
    colors = [color_for(v) for v in vals]

    fig, ax = plt.subplots(figsize=(10, 5.5))
    bars = ax.barh([Q_LABELS[q] for q in qids], vals, color=colors)
    ax.set_xlabel("Max absolute expected-distribution error vs Pew (pp)")
    ax.set_title("Expected-distribution max error by question (n=1,000, probability-vector polling)\n"
                 "Q5 matches canonical option order; Q8/Q9/Q7/Q11 carry the residual gap")
    ax.axvline(5, color="#999999", linestyle=":", linewidth=0.8)
    ax.axvline(10, color="#999999", linestyle=":", linewidth=0.8)
    for bar, val in zip(bars, vals):
        ax.text(val + 0.3, bar.get_y() + bar.get_height() / 2, f"{val:.1f}pp",
                va="center", fontsize=9)
    ax.set_xlim(0, max(vals) * 1.18)
    # Legend
    legend_handles = [
        mpatches.Patch(color="#55A868", label="< 5pp (strong)"),
        mpatches.Patch(color="#DD8452", label="5-10pp (acceptable)"),
        mpatches.Patch(color="#C44E52", label="> 10pp (residual gap)"),
    ]
    ax.legend(handles=legend_handles, loc="lower right", framealpha=0.95)
    ax.grid(axis="x", alpha=0.3)
    plt.savefig(FIG_DIR / "fig3_expected_topline_error.png")
    plt.close()
    print(f"wrote {FIG_DIR / 'fig3_expected_topline_error.png'}")


# ============================================================
# Fig 5: 4-arm canary — max-abs error per arm per question
# ============================================================
def fig5_crossmodel_canary():
    cmp_data = json.loads((REPO_ROOT / "out/stage_b/w158_crossmodel_canary_comparison.json").read_text())
    qids = list(cmp_data["headline_per_question"].keys())
    arms = ["baseline", "sonnet_fwd_n200", "sonnet_rev_n200", "opus_fwd_n200", "opus_rev_n200"]
    arm_labels = ["Sonnet baseline\n(n=1000)", "Sonnet-fwd\n(n=200)",
                  "Sonnet-rev\n(n=200)", "Opus-fwd\n(n=200)", "Opus-rev\n(n=200)"]
    arm_colors = ["#999999", "#4C72B0", "#8172B2", "#937860", "#DA8BC3"]

    fig, ax = plt.subplots(figsize=(11, 5.5))
    x = list(range(len(qids)))
    width = 0.16
    for ai, (arm, label, color) in enumerate(zip(arms, arm_labels, arm_colors)):
        vals = []
        for q in qids:
            h = cmp_data["headline_per_question"][q]["max_abs_error_per_arm"]
            vals.append(h.get(arm, 0))
        offsets = [i + (ai - 2) * width for i in x]
        ax.bar(offsets, vals, width, label=label, color=color)
    ax.set_xticks(x)
    ax.set_xticklabels([Q_LABELS[q] for q in qids])
    ax.set_ylabel("Max-abs expected-distribution error vs Pew (pp)")
    ax.set_title("Cross-model + option-order canary: max error per arm (n=200 × 4 questions)\n"
                 "Q5 reversal destroys calibration; Q9 + Q11 substantially improve under reversal; "
                 "Q8 invariant\n"
                 "Opus 4.5 does not rescue the failure surface")
    ax.legend(loc="upper left", framealpha=0.95, fontsize=8.5, ncol=5)
    ax.set_ylim(0, max(20, max(
        cmp_data["headline_per_question"][q]["max_abs_error_per_arm"][a] or 0
        for q in qids for a in arms
    )) * 1.18)
    ax.grid(axis="y", alpha=0.3)
    plt.savefig(FIG_DIR / "fig5_crossmodel_canary.png")
    plt.close()
    print(f"wrote {FIG_DIR / 'fig5_crossmodel_canary.png'}")


# ============================================================
# Fig 4: Q9 astrology — one juror's reasoning-vs-probability gap
# ============================================================
def fig4_q9_reasoning_gap():
    msa = json.loads((REPO_ROOT / "out/stage_b/W158_n1000_probvec_20260516_v1/marginal_shift_analysis.json").read_text())
    q9 = msa["inspection_worst_cells"]["Q9_astrology_belief"]
    # Pick juror 2179219 from the race=Black cell. The cell-level structural
    # gap there is -17pp (Pew 37.6% Yes; synth expected 20.5% Yes), and this
    # juror's probvec lands at 20% Yes — exactly the structural shortfall.
    # The prose articulates the demographic prior ("a young woman in a
    # demographic where astrology has cultural popularity") then under-applies
    # it, which is the knowledge-to-simulation gap the figure illustrates.
    # Per Blake (2026-05-18): empirical clarity over prose elegance.
    target_id = 2179219
    target_cell = "race=Black"
    juror = None
    cell_pew = None
    cell_synth_expected = None
    for sample in q9:
        if sample["axis_value"] != target_cell:
            continue
        for j in sample["juror_examples"]:
            if j["juror_id"] == target_id:
                juror = j
                cell_pew = sample["pew_dist"]
                cell_synth_expected = sample["synth_expected_dist"]
                break
        if juror:
            break
    if juror is None:
        # Fallback: any juror from the race=Black cell
        for sample in q9:
            if sample["axis_value"] == target_cell:
                juror = sample["juror_examples"][0]
                cell_pew = sample["pew_dist"]
                cell_synth_expected = sample["synth_expected_dist"]
                break

    # Trim reasoning quote to a clean sentence boundary
    raw_reasoning = juror["reasoning"]
    # Find the last sentence-ending punctuation in the first ~360 chars
    cutoff = 360
    if len(raw_reasoning) > cutoff:
        truncated = raw_reasoning[:cutoff]
        last_period = max(truncated.rfind(". "), truncated.rfind("; "), truncated.rfind(", "))
        if last_period > 200:
            truncated = truncated[:last_period].rstrip(".;, ")
        reasoning_quote = '"' + truncated + ' ..."'
    else:
        reasoning_quote = '"' + raw_reasoning + '"'

    fig = plt.figure(figsize=(13, 6.5))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.0, 1.35], wspace=0.25)

    # Left: probvec bar chart for this juror, with Pew cell distribution overlay
    ax1 = fig.add_subplot(gs[0, 0])
    options = list(juror["probvec"].keys())
    probs = [juror["probvec"][o] * 100 for o in options]
    pew_vals = [cell_pew.get(o, 0) * 100 for o in options]
    x = list(range(len(options)))
    width = 0.36
    bars_llm = ax1.bar([i - width / 2 for i in x], probs, width,
                       label=f"LLM probvec\n(juror {juror['juror_id']})", color="#4C72B0")
    bars_pew = ax1.bar([i + width / 2 for i in x], pew_vals, width,
                       label="Pew actual\n(race=Black cell)", color="#55A868")
    ax1.set_xticks(x)
    ax1.set_xticklabels([o for o in options], fontsize=11)
    ax1.set_ylabel("Probability / proportion (%)", fontsize=11)
    ax1.set_title(f"Juror {juror['juror_id']}: emitted probvec vs Pew cell distribution",
                  fontsize=12, loc="left")
    ax1.legend(loc="upper center", framealpha=0.95, fontsize=10, ncol=2)
    ax1.set_ylim(0, 105)
    ax1.grid(axis="y", alpha=0.3)
    for bar, val in zip(list(bars_llm) + list(bars_pew), probs + pew_vals):
        ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1.8,
                 f"{val:.0f}%", ha="center", fontsize=11, fontweight="bold")

    # Right: reasoning quote + diagnosis
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.axis("off")
    ax2.set_title("The knowledge-to-simulation gap, on one juror",
                  fontsize=13, loc="left", pad=14)

    profile = (f"Profile: {juror['age']} / {juror['race']} / {juror['party']} / "
               f"{juror['ideology']} / {juror['religion']} / "
               f"{juror['religiosity']} attendance / {juror['media_slant']} media diet")

    yes_prob_pct = juror["probvec"].get("Yes, believe in", 0) * 100
    pew_yes_pct = cell_pew.get("Yes, believe in", 0) * 100
    synth_exp_yes_pct = (cell_synth_expected or {}).get("Yes, believe in", 0) * 100
    diagnosis_lines = [
        f"This juror's probvec assigns {yes_prob_pct:.0f}% to 'Yes' against a Pew",
        f"race=Black cell rate of {pew_yes_pct:.1f}%. The panel-level expected rate",
        f"on this cell is {synth_exp_yes_pct:.1f}% in the Stage B canonical run,",
        "a -17pp gap. The cross-model + option-order canary narrows the",
        "cell-level gap to -10pp at best (Opus-rev) but does not close it",
        "(n=23 race=Black jurors per arm).",
        "",
        "The reasoning excerpt acknowledges the demographic prior",
        "(\"a demographic where astrology has cultural popularity\") and then",
        "treats it as a small concession to a skepticism-first conclusion.",
        "",
        "Meister, Guestrin, and Hashimoto (2025) call this the",
        "knowledge-to-simulation gap: LLMs describe the right distribution",
        "more accurately than they sample from it. The probability-vector",
        "primitive elicits the description; the residual gap is how well the",
        "model converts that description into a calibrated probability vector.",
    ]

    ax2.text(0, 0.96, profile, fontsize=10, style="italic", color="#555555",
             transform=ax2.transAxes, verticalalignment="top",
             wrap=True)
    ax2.text(0, 0.84, "Juror reasoning (verbatim excerpt):",
             fontsize=11, fontweight="bold",
             transform=ax2.transAxes, verticalalignment="top")
    ax2.text(0, 0.79, reasoning_quote, fontsize=10.5, color="#222222",
             transform=ax2.transAxes, verticalalignment="top",
             family="serif", wrap=True,
             bbox=dict(boxstyle="round,pad=0.6", facecolor="#F4F4F0",
                       edgecolor="#CCCCCC", linewidth=0.6))
    ax2.text(0, 0.43, "Diagnosis:", fontsize=11, fontweight="bold",
             transform=ax2.transAxes, verticalalignment="top")
    for i, line in enumerate(diagnosis_lines):
        ax2.text(0, 0.38 - i * 0.038, line, fontsize=10.5, color="#222222",
                 transform=ax2.transAxes, verticalalignment="top")

    plt.savefig(FIG_DIR / "fig4_q9_reasoning_gap.png")
    plt.close()
    print(f"wrote {FIG_DIR / 'fig4_q9_reasoning_gap.png'}")


# ============================================================
# Fig 6: Regression coefficient comparison (Pew vs synth)
#
# Reads out/stage_b/W158_n1000_probvec_20260516_v1/regression_comparison.json
# produced by scripts/regression_comparison.py. Single scatter faceted by
# question (3x4 grid, 11 panels). x = Pew coef, y = synth coef. Diagonal y=x
# reference per panel. Meaningful coefs filled; near-zero coefs hollow.
# Sign disagreement = red outline; CI non-overlap = bold outline.
# ============================================================
def fig6_regression_coefficient_comparison():
    src = REPO_ROOT / "out/stage_b/W158_n1000_probvec_20260516_v1/regression_comparison.json"
    if not src.exists():
        print(f"  skipping fig6: {src} not present yet (run regression_comparison.py first)")
        return
    data = json.loads(src.read_text())

    # Collect all per-coef points across (question, option) pairs from PRIMARY
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
                "qid": qid,
                "option": opt,
                "coef_name": cp["coef"],
                "pew": cp["pew"],
                "synth": cp["synth"],
                "sign_agree": cp["sign_agree"],
                "ci_overlap": cp["ci_overlap"],
                "meaningful": cp["meaningful"],
            })

    if not rows:
        print("  skipping fig6: no valid comparison rows")
        return

    df = pd.DataFrame(rows)
    qids = sorted(df.qid.unique())
    n_panels = len(qids)
    n_cols = 4
    n_rows = (n_panels + n_cols - 1) // n_cols  # 3 rows of 4 cols + spare

    fig, axes = plt.subplots(n_rows, n_cols, figsize=(15, 11), sharex=True, sharey=True)
    axes_flat = axes.flatten()

    # Per-question Pearson r from per_question_primary
    per_q_r = {q: data["per_question_primary"].get(q, {}).get("median_pearson_r")
               for q in qids}

    for i, qid in enumerate(qids):
        ax = axes_flat[i]
        sub = df[df.qid == qid]
        # Meaningful coefs: filled circle; near-zero: hollow
        meaningful = sub[sub.meaningful]
        nearzero = sub[~sub.meaningful]
        # Sign disagreement / CI non-overlap: red outline / bold outline
        for _, r in meaningful.iterrows():
            ec = "#C44E52" if not r.sign_agree else ("#222222" if r.ci_overlap else "#222222")
            lw = 2.0 if not r.ci_overlap else 0.5
            face = "#55A868" if r.sign_agree and r.ci_overlap else (
                   "#DD8452" if r.sign_agree and not r.ci_overlap else "#C44E52")
            ax.scatter(r.pew, r.synth, s=45, c=face, edgecolors=ec, linewidths=lw, alpha=0.85, zorder=3)
        for _, r in nearzero.iterrows():
            ax.scatter(r.pew, r.synth, s=25, facecolors="none", edgecolors="#888888",
                       linewidths=0.6, alpha=0.6, zorder=2)
        # Diagonal y=x reference per panel
        lim_lo = min(sub.pew.min(), sub.synth.min(), -2)
        lim_hi = max(sub.pew.max(), sub.synth.max(), 2)
        ax.plot([lim_lo, lim_hi], [lim_lo, lim_hi], color="#999999", linewidth=0.8, linestyle="--", zorder=1)
        ax.axhline(0, color="#cccccc", linewidth=0.4)
        ax.axvline(0, color="#cccccc", linewidth=0.4)
        # Title with question label + Pearson r
        r_val = per_q_r.get(qid)
        r_label = f"r={r_val:.2f}" if r_val is not None else "r=n/a"
        n_m = int(sub.meaningful.sum())
        ax.set_title(f"{Q_LABELS.get(qid, qid)}\n{r_label}  (n_meaningful={n_m})",
                     fontsize=9.5, pad=4)
        ax.grid(axis="both", alpha=0.2)
    for j in range(n_panels, len(axes_flat)):
        axes_flat[j].set_visible(False)

    fig.supxlabel("Pew coefficient (log-odds)", fontsize=11, y=0.02)
    fig.supylabel("Synth coefficient (log-odds)", fontsize=11, x=0.02)

    # Headline metrics from overall_primary
    op = data.get("overall_primary", {})
    mv = op.get("metric_values", {})
    headline = (
        f"Regression-coefficient comparison: Pew W158 vs synth panel  |  "
        f"primary (probvec): median per-Q r = {mv.get('median_per_question_pearson_r', 'n/a'):.2f}, "
        f"macro sign-agreement = {mv.get('macro_sign_agreement_rate', 0):.0%}, "
        f"macro CI overlap = {mv.get('macro_ci_overlap_rate', 0):.0%}  |  outcome: {op.get('band', 'n/a')}"
    ) if mv else "Regression-coefficient comparison: Pew W158 vs synth panel"
    fig.suptitle(headline, fontsize=11.5, y=0.995, wrap=True)

    # Legend (single, in spare panel position if available; else outside)
    legend_elems = [
        mpatches.Patch(facecolor="#55A868", edgecolor="#222222", label="Meaningful: sign + CI agree"),
        mpatches.Patch(facecolor="#DD8452", edgecolor="#222222", label="Meaningful: sign agrees, CI non-overlap"),
        mpatches.Patch(facecolor="#C44E52", edgecolor="#C44E52", label="Meaningful: sign disagreement"),
        mpatches.Patch(facecolor="none", edgecolor="#888888", label="Near-zero (excluded from metrics)"),
    ]
    if n_panels < len(axes_flat):
        legend_ax = axes_flat[-1]
        legend_ax.set_visible(True)
        legend_ax.axis("off")
        legend_ax.legend(handles=legend_elems, loc="center", framealpha=0.9, fontsize=10)
    else:
        fig.legend(handles=legend_elems, loc="lower right", framealpha=0.95, fontsize=9)

    plt.tight_layout(rect=[0.03, 0.03, 1, 0.97])
    plt.savefig(FIG_DIR / "fig6_regression_coefficient_comparison.png")
    # Also write SVG + PNG copies under the fig7 name (per Blake 2026-05-20):
    # same chart, ported to SVG for Figma import, named fig7 to distinguish
    # from the fig6{a,b,c} alternatives.
    plt.savefig(FIG_DIR / "fig7_regression_grid_scatter.svg", format="svg")
    plt.savefig(FIG_DIR / "fig7_regression_grid_scatter.png", format="png", dpi=150)
    plt.close()
    print(f"wrote {FIG_DIR / 'fig6_regression_coefficient_comparison.png'}")
    print(f"wrote {FIG_DIR / 'fig7_regression_grid_scatter.svg'} + .png")


def main():
    fig1_entropy_recovery()
    fig2_threshold_breakdown()
    fig3_expected_topline_error()
    fig4_q9_reasoning_gap()
    fig5_crossmodel_canary()
    fig6_regression_coefficient_comparison()
    print(f"\nAll 6 figures written to {FIG_DIR}")


if __name__ == "__main__":
    main()
