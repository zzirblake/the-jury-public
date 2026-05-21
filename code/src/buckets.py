"""Bucketers for ACS PUMS variables → identity-inception trait classes.

Centralized so the sampler, the conditional second-pass, and the validation
harness all agree on cell membership. Bucket definitions match
`docs/identity-inception.csv` exactly.

IPUMS USA harmonized code values are documented inline per function. All code
mappings verified against the 2024 ACS extract on 2026-05-15.
"""

from __future__ import annotations

import pandas as pd


# ============================================================================
# AGE — IPUMS AGE is integer (0-90+; we filtered to 18+ at extract time)
# ============================================================================

def bucket_age(age: pd.Series) -> pd.Series:
    """5-bucket age class for raking + construction."""
    bins = [17, 24, 34, 44, 54, 64, 200]
    labels = ["18-24", "25-34", "35-44", "45-54", "55-64", "65+"]
    return pd.cut(age, bins=bins, labels=labels)


def bucket_age_validation(age: pd.Series) -> pd.Series:
    """4-bucket Pew-aligned age for validation cells."""
    bins = [17, 29, 44, 64, 200]
    labels = ["18-29", "30-44", "45-64", "65+"]
    return pd.cut(age, bins=bins, labels=labels)


def bucket_age_outlier(age: pd.Series) -> pd.Series:
    """4-bucket age for outlier-slate coarse cells (party x age)."""
    bins = [17, 34, 49, 64, 200]
    labels = ["18-34", "35-49", "50-64", "65+"]
    return pd.cut(age, bins=bins, labels=labels)


# ============================================================================
# RACE / HISPANIC — IPUMS RACE + HISPAN
#
# IPUMS RACE codes:
#   1 = White, 2 = Black/AA, 3 = American Indian/Alaska Native,
#   4 = Chinese, 5 = Japanese, 6 = Other Asian or Pacific Islander,
#   7 = Other race, 8 = Two major races, 9 = Three+ major races
#
# IPUMS HISPAN codes:
#   0 = Not Hispanic; 1 = Mexican, 2 = Puerto Rican, 3 = Cuban, 4 = Other
#   (anything != 0 is Hispanic; Hispanic supersedes RACE per Census convention)
# ============================================================================

def bucket_race(race: pd.Series, hispan: pd.Series) -> pd.Series:
    """7-bucket race class matching identity-inception.csv.

    IPUMS RACE has known comparability changes after 2020 (see
    https://usa.ipums.org/usa-action/variables/RACE). For v0.1 we collapse:
      - codes 4 (Chinese), 5 (Japanese), 6 (Other Asian/PI) → asian_american
      - code 7 (Other race) → multiracial (no schema bucket exists for "other";
        IPUMS treats both 7 and 8/9 as "doesn't fit a major-group category")
      - codes 8 (Two major races) and 9 (Three+ major races) → multiracial

    For finer Pacific Islander resolution, switch to RACED (detailed code) in v0.2.
    """
    out = pd.Series(index=race.index, dtype="object")
    is_hisp = hispan != 0
    out[is_hisp] = "hispanic_latino"
    nh = ~is_hisp
    out[nh & (race == 1)] = "white_non_hispanic"
    out[nh & (race == 2)] = "black_african_american"
    out[nh & (race == 3)] = "native_american"
    out[nh & race.isin([4, 5, 6])] = "asian_american"
    out[nh & race.isin([7, 8, 9])] = "multiracial"
    return out


def bucket_race_validation(race_bucket: pd.Series) -> pd.Series:
    """Collapse to 4 validation buckets (synth-n at n=1000 is thin in 7 cells)."""
    mapping = {
        "white_non_hispanic": "White-NH",
        "hispanic_latino": "Hispanic",
        "black_african_american": "Black",
        "asian_american": "Asian/Other",
        "native_american": "Asian/Other",
        "multiracial": "Asian/Other",
    }
    return race_bucket.map(mapping)


# ============================================================================
# EDUCATION — IPUMS EDUC code
#
# 0 = N/A or no schooling, 1 = Nursery-grade 4, 2 = grade 5-8,
# 3 = grade 9, 4 = grade 10, 5 = grade 11,
# 6 = grade 12 (HS diploma equivalent),
# 7 = 1 year college, 8 = 2 years college (associate-equivalent),
# 10 = 4 years college (BA), 11 = 5+ years college (MA/Prof/PhD)
# ============================================================================

def bucket_education(educ: pd.Series) -> pd.Series:
    """4-bucket education attainment matching identity-inception.csv."""
    out = pd.Series(index=educ.index, dtype="object")
    out[educ <= 5] = "<HS"
    out[educ == 6] = "HS"
    out[educ.isin([7, 8])] = "SomeCollege/AA"
    out[educ.isin([10, 11])] = "BA+"
    return out


# ============================================================================
# REGION — IPUMS REGION is a 2-digit code; first digit = Census region
#   1x = Northeast (11=New England, 12=Middle Atlantic)
#   2x = Midwest (21=East North Central, 22=West North Central)
#   3x = South (31=South Atlantic, 32=ESC, 33=WSC)
#   4x = West (41=Mountain, 42=Pacific)
# ============================================================================

def bucket_region(region: pd.Series) -> pd.Series:
    """4-bucket Census region from IPUMS REGION 2-digit code."""
    first_digit = region // 10
    mapping = {1: "NE", 2: "MW", 3: "S", 4: "W"}
    return first_digit.map(mapping)


# ============================================================================
# LIFE-STAGE EVENTS — derived from PUMS event flags (D5 mechanism #5)
#
# Pulled out of the v0.1 second-pass conditional sampler because PUMS carries
# these events directly and that's strictly better than inferred conditional
# draws against ACS event-rate priors.
#
# IPUMS event-flag codes (consistent across these 4 variables):
#   0 = N/A (not in universe), 1 = No, 2 = Yes
#
# MIGRATE1: 1 = same house, 2-5 = moved (different scope of move)
# MARST: 5 = widowed (proxy for life_stage_recent="recently_widowed" since
# WIDINYR was not included in the extract; we use MARST=5 + AGE proxy below)
# ============================================================================

def derive_life_stage_recent(df: pd.DataFrame) -> pd.Series:
    """Single life_stage_recent value per row, deterministic from PUMS event vars.

    Reserved strictly for *past-year* transitions, not stable statuses. Widowed
    status (MARST==5) is intentionally NOT mapped here because the IPUMS extract
    lacks WIDINYR; current marital status of "widowed" includes adults widowed
    decades ago and is a stable status, not a recent transition. The persona
    layer can still read MARST=5 directly for narrative context. Similarly,
    MARST==3 (separated) is not used as a recently_divorced proxy because it
    represents a stable status, not a past-year event; only DIVINYR==2 qualifies.

    Priority order (later overwrites earlier; most-specific transition wins):
      1. recently_relocated_metro       (MIGRATE1 in {2,3,4,5})
      2. recently_married               (MARRINYR == 2)
      3. recently_divorced_separated    (DIVINYR == 2)
      4. recent_parent_under_2yr        (FERTYR == 2)
      5. (default) no_major_transition
    """
    n = len(df)
    out = pd.Series(["no_major_transition"] * n, index=df.index, dtype="object")

    moved = df.get("MIGRATE1", pd.Series([1] * n, index=df.index)).isin([2, 3, 4, 5])
    out[moved] = "recently_relocated_metro"

    married_recent = df.get("MARRINYR", pd.Series([1] * n, index=df.index)) == 2
    out[married_recent] = "recently_married"

    divorced_recent = df.get("DIVINYR", pd.Series([1] * n, index=df.index)) == 2
    out[divorced_recent] = "recently_divorced_separated"

    new_parent = df.get("FERTYR", pd.Series([0] * n, index=df.index)) == 2
    out[new_parent] = "recent_parent_under_2yr"

    return out
