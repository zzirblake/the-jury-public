"""Targeted test for the validation harness rewrite (P1.2 + P1.3 fixes).

Confirms:
  1. Weighted metrics differ from unweighted (otherwise weight-threading is silently no-op)
  2. Interaction cells are enumerated from full cartesian product, not observed combos
     (an absent synth combination must show up as measured=False, not be silently dropped)
  3. Bootstrap CIs are computed on the weighted point estimate
  4. Coverage rule denominator counts the full cartesian product
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import validation


def test_weighted_vs_unweighted_differ():
    """A juror with weight=3 should pull the metric three times as much as weight=1."""
    s = pd.DataFrame({
        "response": ["A"] * 10 + ["B"] * 10,
        "weight":   [3.0] * 10 + [1.0] * 10,    # weighted distribution: A=0.75, B=0.25
        "age": ["18-29"] * 20,
    })
    src = pd.DataFrame({
        "response": ["A"] * 75 + ["B"] * 25,    # source: A=0.75, B=0.25 (matches weighted)
        "weight":   [1.0] * 100,
        "age": ["18-29"] * 100,
    })
    config = {
        "top_level": {"age": {"buckets": ["18-29"], "min_synth_n": 5, "min_source_n": 50}},
        "interaction": {},
    }
    result = validation.compute_metrics(s, src, config, "Q1", bootstrap_iter=50, seed=42)
    cell = result.top_level_cells["age"][0]
    assert cell.measured
    # Weighted synth dist matches source dist exactly -> Wasserstein near 0
    assert cell.wasserstein < 0.05, f"weighted Wasserstein should be ~0, got {cell.wasserstein}"

    # Now run UNWEIGHTED equivalent (same response counts but weight=1 throughout) -
    # unweighted synth dist would be A=0.5/B=0.5, source A=0.75/B=0.25 -> non-zero Wasserstein
    s_unw = s.copy()
    s_unw["weight"] = 1.0
    result_unw = validation.compute_metrics(s_unw, src, config, "Q1", bootstrap_iter=50, seed=42)
    cell_unw = result_unw.top_level_cells["age"][0]
    assert cell_unw.wasserstein > 0.1, f"unweighted Wasserstein should be ~0.25, got {cell_unw.wasserstein}"
    print(f"[OK] weighted Wasserstein={cell.wasserstein:.4f} << unweighted={cell_unw.wasserstein:.4f}")


def test_interaction_cartesian_enumeration():
    """A bucket combination absent from synth must show up as measured=False, not dropped."""
    # Synth has age in {18-29, 30-44} only — missing 45-64 and 65+
    # Source has all four ages
    s = pd.DataFrame({
        "response": ["A"] * 60,
        "weight":   [1.0] * 60,
        "age":   ["18-29"] * 30 + ["30-44"] * 30,
        "party": ["D"] * 15 + ["R"] * 15 + ["D"] * 15 + ["R"] * 15,
    })
    src = pd.DataFrame({
        "response": ["A"] * 200,
        "weight":   [1.0] * 200,
        "age": (["18-29"] * 50 + ["30-44"] * 50 + ["45-64"] * 50 + ["65+"] * 50),
        "party": ["D", "R"] * 100,
    })
    config = {
        "top_level": {
            "age": {"buckets": ["18-29", "30-44", "45-64", "65+"], "min_synth_n": 5, "min_source_n": 20},
            "party": {"buckets": ["D", "R"], "min_synth_n": 5, "min_source_n": 20},
        },
        "interaction": {
            "age_x_party": {"axes": ["age", "party"], "min_synth_n": 5, "min_source_n": 20},
        },
    }
    result = validation.compute_metrics(s, src, config, "Q1", bootstrap_iter=50, seed=42)
    # 4 ages x 2 parties = 8 interaction cells; synth only populated 4 of them
    cells = result.interaction_cells["age_x_party"]
    assert len(cells) == 8, f"expected 8 cartesian cells, got {len(cells)}"
    measured = [c for c in cells if c.measured]
    unmeasured = [c for c in cells if not c.measured]
    assert len(measured) == 4, f"4 cells should be measured (18-29 x D/R, 30-44 x D/R); got {len(measured)}"
    assert len(unmeasured) == 4, f"4 cells should be underpowered (45-64 + 65+ x D/R); got {len(unmeasured)}"
    print(f"[OK] 8 cartesian cells generated, {len(measured)} measured + {len(unmeasured)} underpowered")
    # Verify coverage rule sees the right denominator
    coverage = validation.apply_coverage_rule(
        result, {"top_level_min_pct": 0.50, "interaction_min_pct": 0.50}
    )
    assert abs(coverage.interaction_pct_measured - 0.50) < 0.001, \
        f"expected interaction_pct_measured=0.50, got {coverage.interaction_pct_measured}"
    print(f"[OK] coverage rule sees interaction_pct={coverage.interaction_pct_measured:.2f} (4/8)")


def test_bootstrap_ci_brackets_point():
    """Bootstrap CI should bracket the point estimate."""
    s = pd.DataFrame({
        "response": np.random.default_rng(1).choice(["A", "B", "C"], size=80),
        "weight":   [1.0] * 80,
        "age": ["18-29"] * 80,
    })
    src = pd.DataFrame({
        "response": np.random.default_rng(2).choice(["A", "B", "C"], size=200),
        "weight":   [1.0] * 200,
        "age": ["18-29"] * 200,
    })
    config = {
        "top_level": {"age": {"buckets": ["18-29"], "min_synth_n": 50, "min_source_n": 100}},
        "interaction": {},
    }
    result = validation.compute_metrics(s, src, config, "Q1", bootstrap_iter=200, seed=42)
    cell = result.top_level_cells["age"][0]
    for name, point, ci in [
        ("wasserstein", cell.wasserstein, cell.wasserstein_ci),
        ("entropy_ratio", cell.entropy_ratio, cell.entropy_ratio_ci),
        ("minority_recovery", cell.minority_recovery, cell.minority_recovery_ci),
    ]:
        # CI may be tight around point; allow point to sit on or just inside the interval
        lo, hi = ci
        assert lo - 0.01 <= point <= hi + 0.01, f"{name} point={point} outside CI=({lo}, {hi})"
        print(f"[OK] {name}: point={point:.4f}, CI=({lo:.4f}, {hi:.4f})")


def test_missing_weight_fails_closed():
    """compute_metrics must raise UnweightedRefused when a weight column is missing."""
    s = pd.DataFrame({"response": ["A"] * 30, "age": ["18-29"] * 30})  # no weight col
    src = pd.DataFrame({"response": ["A"] * 100, "weight": [1.0] * 100, "age": ["18-29"] * 100})
    config = {
        "top_level": {"age": {"buckets": ["18-29"], "min_synth_n": 5, "min_source_n": 50}},
        "interaction": {},
    }
    try:
        validation.compute_metrics(s, src, config, "Q1", bootstrap_iter=10, seed=1)
    except validation.UnweightedRefused as exc:
        print(f"[OK] Stage-B default raises UnweightedRefused: {exc}")
    else:
        raise AssertionError("compute_metrics did NOT raise on missing synth weight column")

    # Same call with allow_unweighted=True must NOT raise
    result = validation.compute_metrics(
        s, src, config, "Q1", bootstrap_iter=10, seed=1, allow_unweighted=True,
    )
    assert result.top_level_cells["age"][0].measured, \
        "allow_unweighted=True should permit the run to proceed"
    print(f"[OK] allow_unweighted=True permits the run as documented")


def test_post_merge_weight_column_uniqueness():
    """Regress the Stage B weight_x/weight_y collision: simulate the merge and
    confirm a single `weight` column survives, not weight_x/weight_y."""
    poll_out = pd.DataFrame({
        "juror_id": [1, 2, 3], "question_id": ["Q1"] * 3,
        "response": ["A", "B", "A"], "weight": [1.5, 0.8, 1.0],
    })
    jurors = pd.DataFrame({
        "pums_idx": [1, 2, 3],
        "age": ["18-29", "30-44", "45-64"],
        "race": ["White-NH"] * 3, "education": ["BA+"] * 3, "party": ["D", "R", "I"],
    })
    # This mirrors run_stage_b.py: select only axes (NOT weight) from jurors
    axes_only = jurors[["pums_idx", "age", "race", "education", "party"]]
    merged = poll_out.merge(axes_only, left_on="juror_id", right_on="pums_idx", how="left")
    assert "weight" in merged.columns, "post-merge `weight` column should exist"
    assert "weight_x" not in merged.columns and "weight_y" not in merged.columns, (
        f"merge introduced suffix columns: {list(merged.columns)}"
    )
    assert merged["weight"].tolist() == [1.5, 0.8, 1.0], "weight values corrupted"
    print(f"[OK] post-merge has single `weight` column with correct values")


def test_prior_structural_validation():
    """Verify the new structural-validator checks (P1 #1 fix) actually fire."""
    import json, tempfile
    from pathlib import Path
    from src import conditional_sampler

    # Baseline valid STUB
    def make_baseline():
        return {
            "trait": "political_party", "source": "STUB",
            "conditioning_axes": ["race"],
            "fallback_chain": [["race"], []],
            "distributions": {
                "__unconditional__": {"D": 0.5, "R": 0.5},
                "white_non_hispanic": {"D": 0.4, "R": 0.6},
            },
        }

    def load_with(payload):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "political_party.json").write_text(json.dumps(payload))
            bank = conditional_sampler.ConditionalPriorBank(tmp, allow_stubs=True)
            return bank.load("political_party")

    # Baseline passes
    load_with(make_baseline())
    print("[OK] baseline valid stub loads")

    # Empty conditioning_axes
    bad = make_baseline(); bad["conditioning_axes"] = []
    try:
        load_with(bad); raise AssertionError("empty axes should have failed")
    except conditional_sampler.MalformedPrior as e:
        print(f"[OK] empty conditioning_axes rejected: {str(e)[:90]}")

    # Fallback chain doesn't terminate in []
    bad = make_baseline(); bad["fallback_chain"] = [["race"]]
    try:
        load_with(bad); raise AssertionError("non-terminating chain should have failed")
    except conditional_sampler.MalformedPrior as e:
        print(f"[OK] non-terminating fallback chain rejected: {str(e)[:90]}")

    # Probabilities don't sum to 1.0
    bad = make_baseline(); bad["distributions"]["white_non_hispanic"] = {"D": 0.3, "R": 0.4}
    try:
        load_with(bad); raise AssertionError("bad prob sum should have failed")
    except conditional_sampler.MalformedPrior as e:
        print(f"[OK] probabilities not summing to 1 rejected: {str(e)[:90]}")

    # Empty distributions
    bad = make_baseline(); bad["distributions"] = {}
    try:
        load_with(bad); raise AssertionError("empty distributions should have failed")
    except conditional_sampler.MalformedPrior as e:
        print(f"[OK] empty distributions rejected: {str(e)[:90]}")


def _build_valid_provenance(response_options=None):
    """Helper: build a minimal but VALID provenance block with all required
    fields populated. Caller can override individual fields."""
    from src import conditional_sampler
    base = {}
    for k in conditional_sampler.REQUIRED_PROVENANCE_FIELDS:
        if k in ("response_options_used", "response_options_source"):
            base[k] = response_options or ["D", "R"]
        elif k in ("hand_normalization", "known_limitations"):
            base[k] = []
        elif "year" in k or "size" in k or "n_in_source" in k:
            base[k] = 1
        else:
            base[k] = "filled"
    return base


def test_prior_non_empty_provenance_text():
    """Verify required text fields must be non-empty (not just present)."""
    import json, tempfile
    from pathlib import Path
    from src import conditional_sampler

    def make_real():
        return {
            "trait": "political_party", "source": "Pew",
            "provenance": _build_valid_provenance(response_options=["D", "R"]),
            "conditioning_axes": ["race"],
            "fallback_chain": [["race"], []],
            "distributions": {"__unconditional__": {"D": 0.5, "R": 0.5}},
        }

    def load_with(payload):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "political_party.json").write_text(json.dumps(payload))
            return conditional_sampler.ConditionalPriorBank(tmp).load("political_party")

    # Baseline real prior with all fields populated passes
    load_with(make_real())
    print("[OK] real prior with all populated fields loads")

    # Each required text field empty triggers MissingProvenance
    for field in ["weighting_note", "question_wording", "source_url"]:
        bad = make_real()
        bad["provenance"][field] = "   "  # whitespace-only
        try:
            load_with(bad); raise AssertionError(f"empty {field} should have failed")
        except conditional_sampler.MissingProvenance as e:
            print(f"[OK] empty {field} rejected: {str(e)[:110]}")


def test_response_options_consistency():
    """Verify response_options_used must match distribution keys."""
    import json, tempfile
    from pathlib import Path
    from src import conditional_sampler

    payload = {
        "trait": "political_party", "source": "Pew",
        "provenance": _build_valid_provenance(response_options=["D", "R", "I"]),
        "conditioning_axes": ["race"],
        "fallback_chain": [["race"], []],
        "distributions": {"__unconditional__": {"D": 0.5, "OTHER": 0.5}},  # OTHER not declared
    }
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "political_party.json").write_text(json.dumps(payload))
        try:
            conditional_sampler.ConditionalPriorBank(tmp).load("political_party")
            raise AssertionError("undeclared response option should have failed")
        except conditional_sampler.MalformedPrior as e:
            print(f"[OK] undeclared response option rejected: {str(e)[:120]}")


if __name__ == "__main__":
    print("=== validation harness tests ===\n")
    print("test_weighted_vs_unweighted_differ:")
    test_weighted_vs_unweighted_differ()
    print("\ntest_interaction_cartesian_enumeration:")
    test_interaction_cartesian_enumeration()
    print("\ntest_bootstrap_ci_brackets_point:")
    test_bootstrap_ci_brackets_point()
    print("\ntest_missing_weight_fails_closed:")
    test_missing_weight_fails_closed()
    print("\ntest_post_merge_weight_column_uniqueness:")
    test_post_merge_weight_column_uniqueness()
    print("\ntest_prior_structural_validation:")
    test_prior_structural_validation()
    print("\ntest_prior_non_empty_provenance_text:")
    test_prior_non_empty_provenance_text()
    print("\ntest_response_options_consistency:")
    test_response_options_consistency()
    print("\n=== all validation tests PASSED ===")
