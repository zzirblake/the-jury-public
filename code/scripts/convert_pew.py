"""Convert a Pew ATP .sav file into the long-format CSV Stage B expects.

Input: a Pew Research Center American Trends Panel SPSS file (.sav), plus
a small JSON config naming the questions to extract and the demographic +
weight column names. Output: a long-format CSV at the path Stage B reads.

Output schema (one row per respondent x question):
    respondent_id, question_id, response, weight, age, race, education, party

Where `age`, `race`, `education`, `party` are bucket-aligned to our scheme:
    age:       18-29, 30-44, 45-64, 65+
    race:      White-NH, Hispanic, Black, Asian/Other
    education: <HS, HS, SomeCollege/AA, BA+
    party:     D, R, I

Usage:
    python scripts/convert_pew.py \
        --sav   data/pew/ATP_W158.sav \
        --spec  data/pew/W158_spec.json \
        --out   data/pew/W158_microdata.csv

The spec JSON declares:
{
  "wave": 158,
  "weight_col": "WEIGHT_W158",        # Pew names weights as WEIGHT_W<wave>
  "axis_cols": {
    "age":       {"col": "F_AGECAT",   "map": {1: "18-29", 2: "30-44", 3: "45-64", 4: "65+"}},
    "race":      {"col": "F_RACETHN",  "map": {1: "White-NH", 2: "Black", 3: "Hispanic",
                                                4: "Asian/Other", 5: "Asian/Other",
                                                9: "Asian/Other"}},
    "education": {"col": "F_EDUCCAT",  "map": {1: "BA+", 2: "SomeCollege/AA", 3: "HS"}},
    "party":     {"col": "F_PARTYSUM_FINAL",
                  "map": {1: "R", 2: "D", 3: "I"}}
  },
  "questions": [
    {"id": "Q1",  "pew_var": "CLIMATE1", "options": {"1": "Major threat", "2": "Minor threat", "3": "Not a threat"}},
    {"id": "Q2",  "pew_var": "VACCINE2", "options": {"1": "Required", "2": "Personal choice"}}
  ]
}

The mapping dicts use SPSS integer codes (what's actually in the .sav file)
as keys and bucket labels as values. Codes not in the map are dropped from
that axis (i.e., the respondent gets a NaN, and most validation cells will
exclude them — see below).

Behaviors:
  - Rows where ANY bucket-axis column is NaN after mapping are reported but kept;
    Stage B validation will exclude them from cells they can't fit into.
  - Rows where the weight is NaN or <=0 are dropped (refused / non-respondent).
  - Each question is melted into its own row; respondent_id is repeated.
  - Response value uses the question's `options` map for human-readable text;
    integer codes not in `options` are preserved as raw integers (so a 99
    refused/missing shows as 99 unless mapped).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import pyreadstat


def _apply_mapping(series: pd.Series, mapping: dict) -> pd.Series:
    """Apply integer-keyed mapping; tolerate string-keyed JSON loads."""
    int_map = {}
    for k, v in mapping.items():
        try:
            int_map[int(k)] = v
        except (TypeError, ValueError):
            int_map[k] = v
    return series.map(int_map)


def convert(sav_path: Path, spec_path: Path, out_path: Path) -> dict:
    print(f"reading {sav_path}...")
    df, meta = pyreadstat.read_sav(str(sav_path))
    print(f"  loaded {len(df):,} respondents x {len(df.columns)} variables")

    spec = json.loads(spec_path.read_text())
    weight_col = spec["weight_col"]
    if weight_col not in df.columns:
        print(f"FATAL: weight column '{weight_col}' not in .sav. Available weight columns:",
              file=sys.stderr)
        print("  " + ", ".join(c for c in df.columns if "WEIGHT" in c.upper()),
              file=sys.stderr)
        sys.exit(2)

    # Build axis columns
    out_axes = pd.DataFrame({"respondent_id": df.index, "weight": df[weight_col]})
    for axis_name, axis_spec in spec["axis_cols"].items():
        col = axis_spec["col"]
        if col not in df.columns:
            print(f"FATAL: axis column '{col}' (for axis '{axis_name}') not in .sav",
                  file=sys.stderr)
            print(f"  available columns matching '{col[:3]}*': "
                  + ", ".join(c for c in df.columns if c.startswith(col[:3])),
                  file=sys.stderr)
            sys.exit(2)
        out_axes[axis_name] = _apply_mapping(df[col], axis_spec["map"])
        n_unmapped = out_axes[axis_name].isna().sum()
        if n_unmapped:
            print(f"  axis '{axis_name}': {n_unmapped} respondents NaN after mapping "
                  f"(source codes: {sorted(set(df[col].dropna()) - set(int(k) for k in axis_spec['map']))})")

    # Drop respondents with missing/zero weight
    before = len(out_axes)
    out_axes = out_axes[out_axes["weight"].notna() & (out_axes["weight"] > 0)]
    dropped = before - len(out_axes)
    if dropped:
        print(f"  dropped {dropped} respondents with missing/zero weight")
    print(f"  retained: {len(out_axes):,}")

    # Melt each question into long format
    print(f"  melting {len(spec['questions'])} questions to long format...")
    long_rows = []
    for q in spec["questions"]:
        qid = q["id"]
        pew_var = q["pew_var"]
        opts = q.get("options", {})
        if pew_var not in df.columns:
            print(f"  WARNING: question variable '{pew_var}' not in .sav; skipping {qid}",
                  file=sys.stderr)
            continue
        # Re-attach axes per question
        sub = out_axes.copy()
        sub["question_id"] = qid
        raw = df.loc[sub["respondent_id"], pew_var].reset_index(drop=True)
        sub = sub.reset_index(drop=True)
        # Map integer codes to human-readable response text. Codes NOT in the
        # options map (refused, web-blank, "don't know" — Pew uses 99) become
        # NaN and are dropped, rather than leaking through as the raw integer.
        if opts:
            int_opts = {}
            for k, v in opts.items():
                try:
                    int_opts[int(k)] = v
                except (TypeError, ValueError):
                    int_opts[k] = v
            sub["response"] = raw.map(int_opts)  # unmapped -> NaN
        else:
            sub["response"] = raw
        # Drop responses NaN (NA / refused / unmapped codes)
        sub_keep = sub[sub["response"].notna()].copy()
        if opts:
            n_unmapped = (sub["response"].isna() & raw.notna()).sum()
            if n_unmapped:
                unmapped_codes = sorted(set(raw[sub["response"].isna() & raw.notna()].dropna().astype(int)))
                print(f"      dropped {n_unmapped} responses with unmapped codes {unmapped_codes} (likely refused/DK)")
        # Output column order: stable IDs + all axes from spec (dynamic; supports
        # spec extensions like v4.1's 8-axis set for regression analysis).
        axis_names = list(spec["axis_cols"].keys())
        output_cols = ["respondent_id", "question_id", "response", "weight"] + axis_names
        long_rows.append(sub_keep[output_cols])
        print(f"    {qid} ({pew_var}): {len(sub_keep):,} non-missing responses")

    if not long_rows:
        print("FATAL: no questions extracted; check spec.", file=sys.stderr)
        sys.exit(2)

    long_df = pd.concat(long_rows, ignore_index=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    long_df.to_csv(out_path, index=False)
    print(f"\nwrote {out_path}: {len(long_df):,} rows x {len(long_df.columns)} cols")

    # Summary stats per question
    print(f"\nper-question summary:")
    for qid, grp in long_df.groupby("question_id"):
        n = len(grp)
        wsum = grp["weight"].sum()
        top = grp.groupby("response", observed=True)["weight"].sum().nlargest(3)
        top_pct = (top / wsum * 100).round(1).to_dict()
        print(f"  {qid}: n={n:,} (Σw={wsum:,.0f}), top3 weighted: {top_pct}")

    return {
        "n_respondents": len(out_axes),
        "n_questions": len(long_rows),
        "n_rows": len(long_df),
        "out_path": str(out_path),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sav", required=True, help="path to Pew .sav file")
    parser.add_argument("--spec", required=True, help="path to conversion spec JSON")
    parser.add_argument("--out", required=True, help="output long-format CSV path")
    args = parser.parse_args()
    convert(Path(args.sav), Path(args.spec), Path(args.out))


if __name__ == "__main__":
    main()
