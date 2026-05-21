"""LLM persona expansion: uses a trait vector to produce a coherent juror narrative.

Wraps the Anthropic SDK with prompt caching on the static instruction and
trait-dictionary chunk so per-juror cost remains at a marginal rate.
Outlier-flagged jurors are routed to Opus 4.7 with the non-modal opinion
explicitly committed in the prompt; default jurors go to Sonnet 4.6 at the
juror's assigned expansion temperature.

Public API:
    expand_corpus(jurors, config, dictionary_excerpt) -> jurors_with_narrative

Cost estimates (matching the corpus-construction-plan.md sequence):
    Stage A (n=200): ~$10 API
    Stage B (n=1000): ~$45 API
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import anthropic
import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential
from tqdm import tqdm


SYSTEM_PROMPT = """You are constructing a synthetic respondent for a calibrated public-opinion panel.

Your task is to produce a single coherent first-person narrative paragraph (300-500 words) describing this person: who they are, what they do, what they care about, how they reason about the world, what their daily texture looks like. The narrative will become the persona this respondent speaks from when later asked survey questions.

Hard rules:
- Treat the trait vector as a constraint, not a costume. Real people are not the sum of their demographics; they are individuals whose demographics shape but do not determine their reasoning.
- Do not perform stereotypes. A "white evangelical 52yo Tennessee homemaker" is not a caricature; she is a specific person whose traits inform her reasoning without dictating it.
- If the trait vector includes a non_modal_position, this person genuinely holds that position and reasons from it. The narrative should make their reasoning legible without apologizing for the divergence from the demographic baseline. People with atypical positions for their cell are common in the real world.
- Do not name the person. Use "this person" or third-person voice if needed. The corpus uses juror IDs, not names.
- Do not speculate about the person's vote in elections that have not yet occurred or about specific named politicians. The narrative is about who they are, not how they will vote.
- Do not invent factually or legally specific claims that go beyond the trait vector. Concretely: do not name specific employers, schools, or workplaces; do not invent military deployment locations or units; do not fabricate voting eligibility or voting history details (e.g., a non-citizen "voted in local elections"); do not invent specific immigration timelines or visa categories beyond what the trait vector supports. Plausible-sounding fabrications are the most damaging because they look credible. When in doubt, stay general: "she works in healthcare" not "she's an RN at Mass General"; "he served in the Army" not "he served two tours in Vietnam with the 101st Airborne."
- Sincerity outranks cleverness. Write what a careful researcher would write if asked to summarize a real survey respondent's interview transcript.
"""


DICTIONARY_PREAMBLE = """Reference: identity-inception trait dictionary (excerpt). Use these as the controlled vocabulary when interpreting the trait vector below.

"""


@dataclass
class ExpansionConfig:
    default_model: str = "claude-sonnet-4-6"
    # We attempted Opus 4.7 but it rejects the `temperature` parameter (extended-thinking
    # mode). Opus 4.5 accepts temperature and preserves the variance mechanism
    # for the outlier slice end-to-end. Revisit when 4.7 supports temperature
    # or we add a model-aware param-stripping wrapper.
    outlier_model: str = "claude-opus-4-5"
    max_tokens_out: int = 1500
    cache_static_context: bool = True
    retries: int = 5


# Code translation tables. Mapping any PUMS code to its human-meaningful string
# before it enters the prompt so the LLM never has to parse "STATEFIP: 6" or
# "MARST: 3" alongside curated values. Codes without a translator are passed
# through verbatim only if they are inherently meaningful (AGE, INCTOT, etc.).

_SEX_LABELS = {1: "male", 2: "female"}

_MARST_LABELS = {
    1: "married, spouse present",
    2: "married, spouse absent",
    3: "separated",
    4: "divorced",
    5: "widowed",
    6: "never married",
}

_OWNERSHP_LABELS = {0: "N/A", 1: "owned (or being bought)", 2: "rented"}

_CITIZEN_LABELS = {
    0: "born in the US",
    1: "born abroad of US parents",
    2: "naturalized US citizen",
    3: "not a US citizen",
}

_VETSTAT_LABELS = {0: "N/A", 1: "not a veteran", 2: "veteran"}

_EMPSTAT_LABELS = {
    0: "N/A",
    1: "employed",
    2: "unemployed",
    3: "not in labor force",
}

_METRO_LABELS = {
    0: "metro status not identifiable",
    1: "not in a metropolitan area",
    2: "in metro area, central / principal city",
    3: "in metro area, outside central / principal city",
    4: "in metro area, central-city status unknown",
}

# FIPS state codes — Census standard
_STATEFIP_LABELS = {
    1: "Alabama", 2: "Alaska", 4: "Arizona", 5: "Arkansas", 6: "California",
    8: "Colorado", 9: "Connecticut", 10: "Delaware", 11: "District of Columbia",
    12: "Florida", 13: "Georgia", 15: "Hawaii", 16: "Idaho", 17: "Illinois",
    18: "Indiana", 19: "Iowa", 20: "Kansas", 21: "Kentucky", 22: "Louisiana",
    23: "Maine", 24: "Maryland", 25: "Massachusetts", 26: "Michigan",
    27: "Minnesota", 28: "Mississippi", 29: "Missouri", 30: "Montana",
    31: "Nebraska", 32: "Nevada", 33: "New Hampshire", 34: "New Jersey",
    35: "New Mexico", 36: "New York", 37: "North Carolina", 38: "North Dakota",
    39: "Ohio", 40: "Oklahoma", 41: "Oregon", 42: "Pennsylvania",
    44: "Rhode Island", 45: "South Carolina", 46: "South Dakota",
    47: "Tennessee", 48: "Texas", 49: "Utah", 50: "Vermont", 51: "Virginia",
    53: "Washington", 54: "West Virginia", 55: "Wisconsin", 56: "Wyoming",
}


def _translate(col: str, val):
    """Map a raw PUMS code value to its human-meaningful string, if known."""
    if pd.isna(val):
        return None
    table = {
        "SEX": _SEX_LABELS, "MARST": _MARST_LABELS,
        "OWNERSHP": _OWNERSHP_LABELS, "CITIZEN": _CITIZEN_LABELS,
        "VETSTAT": _VETSTAT_LABELS, "EMPSTAT": _EMPSTAT_LABELS,
        "METRO": _METRO_LABELS, "STATEFIP": _STATEFIP_LABELS,
    }.get(col)
    if table is None:
        return val  # AGE, INCTOT, HHINCOME, etc. — meaningful as-is
    return table.get(int(val), f"unknown code {val}")


# Explicit allow-list of trait columns to surface in the persona-expansion prompt.
# Each column is rendered as a human-readable string (codes translated via _translate)
# so the LLM never sees opaque numbers alongside curated values.
EXPANSION_TRAIT_ALLOWLIST = [
    # Curated demographic buckets
    ("age_bucket", "age range"),
    ("race_bucket", "race / ethnicity"),
    ("education_bucket", "highest education"),
    ("region_bucket", "Census region"),
    # Inherently meaningful integer/string fields
    ("AGE", "age (years)"),
    ("SEX", "sex"),
    ("STATEFIP", "state"),
    ("METRO", "metro status"),
    ("INCTOT", "personal income (USD/yr)"),
    ("HHINCOME", "household income (USD/yr)"),
    ("POVERTY", "poverty ratio (% of federal poverty line)"),
    ("FAMSIZE", "family size"),
    ("NCHILD", "own children in household"),
    ("MARST", "marital status"),
    ("OWNERSHP", "housing tenure"),
    ("CITIZEN", "citizenship status"),
    ("VETSTAT", "veteran status"),
    ("EMPSTAT", "employment status"),
    # PUMS-derived life-stage transition
    ("life_stage_recent", "most-recent past-year life-stage transition"),
    # v0.1 second-pass sampled traits
    ("political_party", "political party"),
    ("political_ideology", "political ideology"),
    ("religion", "religion"),
    ("religiosity", "religiosity (attendance frequency)"),
    ("media_diet_primary", "primary news / media source"),
    ("media_diet_slant", "media-diet political slant"),
    ("household_composition", "household composition"),
]


def _format_juror_prompt(row: pd.Series, dictionary_excerpt: str) -> tuple[list[dict], str]:
    """Build the cached system blocks + per-juror user message.

    The trait projection is an *explicit allow-list* (EXPANSION_TRAIT_ALLOWLIST)
    with each raw PUMS code translated to its human-meaningful string via
    `_translate()`. The LLM never sees opaque numbers like "MARST: 3" or
    "STATEFIP: 47" alongside curated values.
    """
    system_blocks = [
        {"type": "text", "text": SYSTEM_PROMPT},
        {
            "type": "text",
            "text": DICTIONARY_PREAMBLE + dictionary_excerpt,
            "cache_control": {"type": "ephemeral"},
        },
    ]

    trait_lines = []
    for col, label in EXPANSION_TRAIT_ALLOWLIST:
        if col not in row.index:
            continue
        raw_val = row[col]
        if pd.isna(raw_val):
            continue
        translated = _translate(col, raw_val)
        if translated is None or translated == "" or translated == "N/A":
            continue
        trait_lines.append(f"  {label}: {translated}")
    trait_block = "\n".join(trait_lines)

    if row.get("is_outlier", False) and pd.notna(row.get("non_modal_issue")):
        outlier_clause = (
            f"\n\nThis person genuinely holds the following non-modal opinion: "
            f"on the issue of '{row['non_modal_issue']}', this person {row['non_modal_position']}. "
            f"Approximately {float(row['non_modal_density']) * 100:.0f}% of people in this person's "
            f"demographic cell hold this position; it is uncommon for the cell but not rare. "
            f"Make their reasoning around this position legible in the narrative without apology."
        )
    else:
        outlier_clause = ""

    user_message = (
        f"Trait vector for this respondent:\n\n{trait_block}{outlier_clause}\n\n"
        f"Produce the 300-500 word first-person narrative now."
    )

    return system_blocks, user_message


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=30))
def _call(
    client: anthropic.Anthropic,
    model: str,
    system_blocks: list[dict],
    user_message: str,
    temperature: float,
    max_tokens: int,
) -> str:
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system_blocks,
        messages=[{"role": "user", "content": user_message}],
    )
    return response.content[0].text


class ExpansionFailureThreshold(RuntimeError):
    """Raised when expansion failure rate exceeds max_failure_rate.

    Without this guard, expand_corpus silently produces an `[EXPANSION FAILED:`-
    prefixed narrative for every API failure and returns an apparently-complete
    DataFrame. That mode hid 54/200 failures in a real paid run. Production
    paths must fail closed.
    """

    def __init__(self, message: str, failures: list[dict]):
        super().__init__(message)
        self.failures = failures


def expand_corpus(
    jurors: pd.DataFrame,
    config: ExpansionConfig,
    dictionary_excerpt: str,
    api_key: str | None = None,
    max_failure_rate: float = 0.05,
    allow_failures: bool = False,
) -> pd.DataFrame:
    """Expand every juror in the frame to a narrative paragraph.

    Uses Sonnet for default jurors at their assigned temperature; routes
    outlier-flagged jurors to Opus. Prompt caching applies to the
    instruction + dictionary system blocks across all calls.

    Fails closed (raises ExpansionFailureThreshold) if the failure rate
    exceeds max_failure_rate. Pass allow_failures=True to use the legacy
    fail-open behavior — only for explicit one-off debug paths like
    reexpand_failed.py operating on a known-mixed corpus.
    """
    client = anthropic.Anthropic(api_key=api_key or os.environ["LLM_API_KEY"])
    out = jurors.copy()
    narratives = []
    usage_log = []
    failures: list[dict] = []
    for idx, row in tqdm(out.iterrows(), total=len(out), desc="expanding jurors"):
        is_outlier = bool(row.get("is_outlier", False))
        model = config.outlier_model if is_outlier else config.default_model
        temp = float(row.get("expansion_temperature", 0.7))
        system_blocks, user_msg = _format_juror_prompt(row, dictionary_excerpt)
        try:
            text = _call(
                client, model, system_blocks, user_msg, temp, config.max_tokens_out
            )
        except Exception as exc:
            text = f"[EXPANSION FAILED: {exc}]"
            failures.append({
                "juror_idx": idx, "model": model, "temp": temp,
                "is_outlier": is_outlier, "error": str(exc)[:200],
            })
        narratives.append(text)
        usage_log.append({"model": model, "temp": temp, "outlier": is_outlier})

    out["narrative"] = narratives
    out["expansion_model"] = [u["model"] for u in usage_log]

    fail_rate = len(failures) / max(len(out), 1)
    if failures and not allow_failures and fail_rate > max_failure_rate:
        # Group failures by error type for quick triage.
        error_buckets: dict[str, int] = {}
        for f in failures:
            key = f["error"].split(":")[0][:80]
            error_buckets[key] = error_buckets.get(key, 0) + 1
        summary = ", ".join(f"{k}({v})" for k, v in sorted(
            error_buckets.items(), key=lambda kv: -kv[1]
        ))
        raise ExpansionFailureThreshold(
            f"{len(failures)}/{len(out)} expansions failed "
            f"({fail_rate * 100:.1f}% > {max_failure_rate * 100:.0f}% threshold). "
            f"Top errors: {summary}. "
            f"Pass allow_failures=True only for explicit debug paths.",
            failures=failures,
        )
    return out
