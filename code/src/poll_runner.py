"""Pew-question runner: ask each juror in the corpus the same question.

Each juror's persona context is the narrative PLUS a structured trait block
(age, race, education, region, party, ideology, religion, religiosity, media
diet, household, life-stage transition, plus the outlier non-modal opinion
if present). The trait block carries dimensions the narrative may not
explicitly mention. The question is asked verbatim with the source-poll's
published response options, framed in the field date of the source survey
so 2026 hindsight does not contaminate retrospective questions.

The polling prompt explicitly discourages safe-middle defaulting (a known
LLM survey-simulation failure mode; cf. Argyle 2023 "Out of One, Many",
Park 2024 "Generative Agent Simulations"). Real survey respondents use
endpoint options at population rates that reflect lived certainty, fear,
trust, distrust, and identity — not at the rate an uncertain LLM picks
the most-defensible-looking option.

Public API:
    run_poll(jurors, questions, field_date_iso, model) -> responses_df
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import time
from typing import Literal

import anthropic
import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential
from tqdm import tqdm

# Probability-vector validation tolerances
_PROBVEC_SUM_TOL = 0.05      # accept sum in [0.95, 1.05] (LLMs aren't exact)

# Failed-row repoll cooldown — InternalServerErrors are typically transient
_REPOLL_COOLDOWN_SECONDS = 15


# ============================================================
# Option-order presentation (per W158 cross-model + option-order canary
# 2026-05-17 finding: option order is a non-trivial confound; reversal moves
# topline error by 5-12pp on different questions in different directions.
# `randomize` makes each (juror, question) see its own deterministic shuffle
# so the panel-level result averages over presentation-order primacy/recency.)
# ============================================================

OptionOrder = Literal["canonical", "reverse", "randomize"]


def _options_as_presented(
    options: list[str],
    juror_id,
    question_id: str,
    run_seed: int,
    mode: OptionOrder,
) -> list[str]:
    """Return options in the order they will be presented to the LLM.

    - "canonical": as given (Pew/source order)
    - "reverse":   reversed once (diagnostic; per-question, not per-juror)
    - "randomize": per-(juror, question) deterministic shuffle keyed by
                   sha256(juror_id|question_id|run_seed|"order"). Same triple
                   always yields the same order across reruns.
    """
    if mode == "canonical":
        return list(options)
    if mode == "reverse":
        return list(reversed(options))
    if mode == "randomize":
        key = f"{juror_id}|{question_id}|{run_seed}|order".encode("utf-8")
        digest_int = int.from_bytes(hashlib.sha256(key).digest()[:8], "big")
        rng = random.Random(digest_int)
        shuffled = list(options)
        rng.shuffle(shuffled)
        return shuffled
    raise ValueError(f"unknown option_order mode: {mode!r}")


POLL_SYSTEM_PROMPT_PROBVEC = """You are this person. You are answering a survey as them.

For each question, you will report your estimated probability distribution over the offered response options — not a single committed pick. The probabilities represent your uncertainty about the exact answer this specific person would give, given everything in their narrative and structured traits. They are NOT meant to express a desire to be moderate, balanced, or random.

Calibration rules:
- Assign meaningful probability to a strong-endpoint option when this person could plausibly hold that view based on their party, religion, religiosity, education, life experience, region, media diet, or identity. Do not artificially zero out endpoints.
- Assign meaningful probability to a moderate option when moderation is genuinely plausible for this person. Do not artificially suppress legitimate moderate answers.
- The narrative may not surface every trait that matters. Use the structured trait block to reason about dimensions the narrative is silent on.
- Probabilities should reflect the population of plausible answers this person might give in different survey contexts — not the model's defensiveness about committing.

Output schema (no commentary, no code fences):
{
  "option_probabilities": {"<EXACT option text 1>": <p1>, "<EXACT option text 2>": <p2>, ...},
  "reasoning": "<1-2 sentences on what's driving the distribution shape>"
}

Rules:
- Include EVERY offered option in the probabilities dict. Do not omit options. Do not add extras.
- Each option key must be character-for-character exact match to an offered option.
- All probabilities must be non-negative. The sum should be approximately 1.0 (we tolerate sum in [0.95, 1.05] and renormalize).
- Reasoning is what's driving the distribution shape — not why you picked one answer.
- Do not speculate about the person's vote, do not name specific politicians.
"""


POLL_SYSTEM_PROMPT = """You are this person. You are answering a survey as them.

CRITICAL: do not default to the safest-sounding moderate or middle option. Real respondents pick strong-endpoint options at meaningful rates — they say "a great deal," "no confidence at all," "yes, believe in," "too long," "fewer restrictions" — when their beliefs, distrust, certainty, fear, identity, life experience, or community position genuinely point that way. LLMs systematically over-pick the safe middle answer; you must not do this. Read the structured trait block carefully. If the person's party, religion, religiosity, education, region, media diet, life-stage, or non-modal opinion would genuinely support a strong-endpoint answer, pick the strong-endpoint answer.

Respond ONLY in this JSON format, no commentary, no code fences:
{"response": "<EXACT text of one offered option, character-for-character>", "reasoning": "<1-2 sentences from this person's perspective explaining the choice>"}

Rules:
- The `response` value MUST be an exact verbatim match of one of the offered options. Match every character. The harness validates this.
- Do not refuse the question, do not break character, do not describe yourself in the third person.
- Reasoning is what this person would say to a friendly interviewer asking why.
- Do not speculate about the person's vote, do not name specific politicians.
"""


def _format_trait_block(juror: pd.Series) -> str:
    """Compact structured trait summary; complements the narrative.

    Carries the dimensions the narrative may have buried or omitted. Especially
    important for traits where the narrative might be silent (e.g., religion
    might not surface that someone attends weekly, which is the key trait for
    questions about astrology or trust in scientists)."""
    bits = []
    def add(label, key, transform=lambda x: x):
        if key in juror.index and pd.notna(juror[key]):
            bits.append(f"  - {label}: {transform(juror[key])}")
    add("age", "age_bucket")
    add("race/ethnicity", "race_bucket")
    add("education", "education_bucket")
    add("Census region", "region_bucket")
    add("political party", "political_party")
    add("political ideology", "political_ideology")
    add("religion", "religion")
    add("religiosity", "religiosity")
    add("media diet (primary)", "media_diet_primary")
    add("media diet (slant)", "media_diet_slant")
    add("household composition", "household_composition")
    add("life-stage transition (past year)", "life_stage_recent")
    # Outlier non-modal opinion if present — this is a critical input
    if juror.get("is_outlier") and pd.notna(juror.get("non_modal_issue")):
        bits.append(
            f"  - non-modal opinion held: on the issue of '{juror['non_modal_issue']}', "
            f"this person {juror['non_modal_position']} — they hold this position with conviction "
            f"despite it being uncommon for their demographic baseline. If a survey question "
            f"touches this issue, answer accordingly."
        )
    return "\n".join(bits)


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=2, max=20))
def _ask_one(
    client: anthropic.Anthropic,
    model: str,
    narrative: str,
    trait_block: str,
    field_date_iso: str,
    question_text: str,
    options: list[str],
) -> dict:
    options_list = "\n".join(f"  - {o}" for o in options)
    user_msg = (
        f"You are this person.\n\n"
        f"NARRATIVE (who this person is, how they live, how they reason):\n{narrative}\n\n"
        f"STRUCTURED TRAITS (the dimensions the narrative may not fully surface — "
        f"use these to answer if the narrative is silent on a relevant trait):\n{trait_block}\n\n"
        f"SURVEY CONTEXT: You are being asked this question as part of the Pew Research American "
        f"Trends Panel, fielded in {field_date_iso}. Answer as this person would have answered "
        f"AT THAT TIME — do not let knowledge from later dates contaminate your answer (e.g., for "
        f"COVID retrospective questions, you should answer from the {field_date_iso} vantage point).\n\n"
        f"SURVEY QUESTION: {question_text}\n\n"
        f"RESPONSE OPTIONS (pick exactly one, exact verbatim text):\n{options_list}"
    )
    response = client.messages.create(
        model=model,
        max_tokens=400,
        temperature=0.7,
        system=POLL_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    text = response.content[0].text.strip()
    # Tolerate the model wrapping JSON in code fences.
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.startswith("json"):
            text = text[4:].strip()
    return json.loads(text)


def _validate_response(result: dict, options: list[str]) -> tuple[str | None, str]:
    """Return (response, reasoning) where response is exactly one of options or None.

    If the LLM returned a response that doesn't exactly match any option,
    try a forgiving normalization (strip whitespace, case-fold) once.
    If still no match, return None so the row is dropped by the validation
    harness (better than recording a fabricated option that misleads metrics).
    """
    raw_response = result.get("response", "")
    reasoning = result.get("reasoning", "")
    if raw_response in options:
        return raw_response, reasoning
    # Forgiving normalization
    norm = {o.strip().casefold(): o for o in options}
    key = str(raw_response).strip().casefold()
    if key in norm:
        return norm[key], reasoning
    # No match — record None with diagnostic reasoning
    return None, f"[OPTION MISMATCH] returned={raw_response!r}; reasoning={reasoning!r}"


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=2, max=20))
def _ask_one_probvec(
    client: anthropic.Anthropic,
    model: str,
    narrative: str,
    trait_block: str,
    field_date_iso: str,
    question_text: str,
    options: list[str],
) -> dict:
    """Probability-vector polling: LLM returns option probabilities + reasoning;
    sampling is done post-hoc deterministically."""
    options_list = "\n".join(f"  - {o}" for o in options)
    user_msg = (
        f"You are this person.\n\n"
        f"NARRATIVE (who this person is, how they live, how they reason):\n{narrative}\n\n"
        f"STRUCTURED TRAITS (the dimensions the narrative may not fully surface — "
        f"use these to reason about probabilities even when the narrative is silent):\n{trait_block}\n\n"
        f"SURVEY CONTEXT: You are being asked this question as part of the Pew Research American "
        f"Trends Panel, fielded in {field_date_iso}. Estimate probabilities as this person would have "
        f"answered AT THAT TIME — do not let knowledge from later dates contaminate the distribution.\n\n"
        f"SURVEY QUESTION: {question_text}\n\n"
        f"RESPONSE OPTIONS (your probability dict must include EVERY one of these as a key, exact text):\n{options_list}"
    )
    response = client.messages.create(
        model=model,
        max_tokens=600,  # probvec output is longer than single-pick
        temperature=0.7,
        system=POLL_SYSTEM_PROMPT_PROBVEC,
        messages=[{"role": "user", "content": user_msg}],
    )
    text = response.content[0].text.strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.startswith("json"):
            text = text[4:].strip()
    return json.loads(text)


def _validate_probvec(
    result: dict, options: list[str]
) -> tuple[dict[str, float] | None, float, str]:
    """Validate the LLM's probability vector.

    Checks (all required):
      - `option_probabilities` is a dict
      - Keys are EXACTLY the set of offered options (no missing, no extra)
      - Values are non-negative numbers
      - Sum is in [1 - _PROBVEC_SUM_TOL, 1 + _PROBVEC_SUM_TOL]

    Returns (renormalized_probs, raw_sum_before_norm, reason).
    On failure, returns (None, raw_sum, diagnostic_reason).
    """
    raw = result.get("option_probabilities")
    if not isinstance(raw, dict):
        return None, 0.0, f"[PROBVEC INVALID] not a dict; got {type(raw).__name__}"
    # Exact set equality on keys
    raw_keys = set(raw.keys())
    option_set = set(options)
    missing = option_set - raw_keys
    extra = raw_keys - option_set
    if missing or extra:
        return None, 0.0, (f"[PROBVEC INVALID] missing={sorted(missing)} extra={sorted(extra)}")
    # Non-negative numeric values
    try:
        vals = {k: float(v) for k, v in raw.items()}
    except (TypeError, ValueError) as exc:
        return None, 0.0, f"[PROBVEC INVALID] non-numeric value: {exc}"
    if any(v < 0 for v in vals.values()):
        neg = [(k, v) for k, v in vals.items() if v < 0]
        return None, sum(vals.values()), f"[PROBVEC INVALID] negative probabilities: {neg}"
    raw_sum = sum(vals.values())
    if abs(raw_sum - 1.0) > _PROBVEC_SUM_TOL:
        return None, raw_sum, f"[PROBVEC INVALID] sum={raw_sum:.3f} outside [{1-_PROBVEC_SUM_TOL:.2f}, {1+_PROBVEC_SUM_TOL:.2f}]"
    # Renormalize
    renormed = {k: v / raw_sum for k, v in vals.items()}
    return renormed, raw_sum, ""


def _sample_from_probvec(
    probs: dict[str, float], juror_id, question_id: str, run_seed: int, options: list[str]
) -> str:
    """Deterministic sampling: sha256(juror_id|question_id|run_seed) → seed → choice.

    Reproducible across runs with the same triple. Uses options list (not dict keys)
    for deterministic ordering since dict iteration order may vary across runs.
    """
    key = f"{juror_id}|{question_id}|{run_seed}".encode("utf-8")
    digest_int = int.from_bytes(hashlib.sha256(key).digest()[:8], "big")
    rng = random.Random(digest_int)
    weights = [probs.get(opt, 0.0) for opt in options]
    return rng.choices(options, weights=weights, k=1)[0]


def _probvec_entropy(probs: dict[str, float]) -> float:
    """Shannon entropy in nats of a probability distribution."""
    return -sum(p * math.log(p) for p in probs.values() if p > 0)


class PollingFailureThreshold(RuntimeError):
    """Raised when polling failure/mismatch rate exceeds max_failure_rate.

    Without this guard, run_poll silently produces an apparently-complete
    long-format DataFrame even when many rows have response=None (API failures
    or option-mismatch fabrications). At Stage B scale (1000 jurors x 11
    questions = 11,000 calls), a 5% failure rate is 550 dropped rows that
    would silently underpower validation cells. Production paths must fail
    closed; canary runs (--n < 500) may opt into fail-open via allow_failures.
    """

    def __init__(self, message: str, failures: list[dict]):
        super().__init__(message)
        self.failures = failures


def run_poll(
    jurors: pd.DataFrame,
    questions: list[dict],
    field_date_iso: str = "the survey field date",
    model: str = "claude-sonnet-4-6",
    api_key: str | None = None,
    max_failure_rate: float = 0.05,
    allow_failures: bool = False,
    polling_mode: Literal["direct", "probvec"] = "direct",
    run_seed: int = 0,
    option_order: OptionOrder = "canonical",
) -> pd.DataFrame:
    """Ask each juror each question. Return long-format frame.

    Args:
        jurors: DataFrame with narrative + trait columns (output of expansion + sampler)
        questions: list of {"id": str, "text": str, "options": [str, ...]}
        field_date_iso: e.g. "October 2024" — passed to the LLM as the survey-field
            date so retrospective questions are answered from that vantage point
            and 2026 hindsight does not contaminate.
        model: Sonnet 4.6 by default; can swap to Opus 4.5 if Sonnet underperforms.
        max_failure_rate: production gate (default 0.05). Failures include API
            errors, exact-option mismatches, and probvec-validation failures.
        allow_failures: bypass the threshold gate. Set True only for canary runs
            where we deliberately want to see the data even if some calls fail.
        polling_mode:
            "direct"  — LLM picks one option (legacy mode)
            "probvec" — LLM returns option-probability vector; we sample deterministically
        run_seed: seed for the deterministic probvec sampling. Use the run's master seed
            so the sampled responses are reproducible across re-runs of identical data.
        option_order: how options are presented to the LLM per (juror, question).
            "canonical" (default) — Pew/source order, as in the questions JSON.
            "reverse"             — reverse once per question (diagnostic only).
            "randomize"           — deterministic per-(juror, question) shuffle keyed by
                                    sha256(juror_id|question_id|run_seed|"order"). Removes
                                    presentation-order primacy/recency at the panel level
                                    while staying reproducible across reruns. Recommended
                                    for production runs (see W158 cross-model + option-order
                                    canary 2026-05-17).

    Output columns:
        Common: juror_id, question_id, response, reasoning, weight, options_as_presented
        Probvec adds: probabilities_json (full vector), prob_sum_before_norm,
                      prob_max, prob_entropy
    """
    client = anthropic.Anthropic(api_key=api_key or os.environ["LLM_API_KEY"])
    rows = []
    failures: list[dict] = []
    total = len(jurors) * len(questions)
    pbar = tqdm(total=total, desc=f"polling jurors ({polling_mode}, order={option_order})")
    for q in questions:
        for _, juror in jurors.iterrows():
            jid = juror.get("pums_idx", juror.name)
            trait_block = _format_trait_block(juror)
            # Per-call presentation order. Validation always uses q["options"]
            # for set membership / probvec key validation; presentation order
            # only affects the LLM prompt and the sampler's weight order.
            options_presented = _options_as_presented(
                q["options"], jid, q["id"], run_seed, option_order,
            )
            row: dict = {
                "juror_id": jid, "question_id": q["id"],
                "weight": juror.get("weight", 1.0),
                "options_as_presented": json.dumps(options_presented),
            }
            failure_type = None

            if polling_mode == "direct":
                try:
                    result = _ask_one(
                        client, model, juror["narrative"], trait_block,
                        field_date_iso, q["text"], options_presented,
                    )
                    response, reasoning = _validate_response(result, q["options"])
                    if response is None:
                        failure_type = "option_mismatch"
                except Exception as exc:
                    response = None
                    reasoning = f"[CALL FAILED: {exc}]"
                    failure_type = "api_error"
                row.update({"response": response, "reasoning": reasoning})

            elif polling_mode == "probvec":
                try:
                    result = _ask_one_probvec(
                        client, model, juror["narrative"], trait_block,
                        field_date_iso, q["text"], options_presented,
                    )
                    probs, raw_sum, validation_reason = _validate_probvec(result, q["options"])
                    reasoning_from_llm = result.get("reasoning", "")
                    if probs is None:
                        response = None
                        reasoning = f"{validation_reason} reasoning={reasoning_from_llm!r}"
                        failure_type = "probvec_invalid"
                        row.update({
                            "response": None, "reasoning": reasoning,
                            "probabilities_json": json.dumps(result.get("option_probabilities", {})),
                            "prob_sum_before_norm": raw_sum,
                            "prob_max": None, "prob_entropy": None,
                        })
                    else:
                        # Sample using the canonical option list so per-juror responses
                        # are comparable across presentation orders.
                        response = _sample_from_probvec(probs, jid, q["id"], run_seed, q["options"])
                        row.update({
                            "response": response, "reasoning": reasoning_from_llm,
                            "probabilities_json": json.dumps(probs),
                            "prob_sum_before_norm": raw_sum,
                            "prob_max": max(probs.values()),
                            "prob_entropy": _probvec_entropy(probs),
                        })
                except Exception as exc:
                    row.update({
                        "response": None, "reasoning": f"[CALL FAILED: {exc}]",
                        "probabilities_json": None, "prob_sum_before_norm": None,
                        "prob_max": None, "prob_entropy": None,
                    })
                    failure_type = "api_error"
            else:
                raise ValueError(f"unknown polling_mode: {polling_mode!r}")

            rows.append(row)
            if failure_type:
                failures.append({
                    "juror_id": jid, "question_id": q["id"], "type": failure_type,
                    "reasoning_snippet": str(row.get("reasoning"))[:120],
                })
            pbar.update(1)
    pbar.close()

    # ============================================================
    # Failed-row repoll: retry transient failures (API errors) after cooldown
    # before applying gates. InternalServerErrors and rate-limit errors are
    # typically transient; option_mismatch and probvec_invalid are NOT (they
    # indicate the LLM produced bad output, which retry won't fix). So we
    # only retry api_error type.
    # ============================================================
    api_failures = [f for f in failures if f["type"] == "api_error"]
    if api_failures and not allow_failures:
        print(f"\nfound {len(api_failures)} api_error failures — retrying after "
              f"{_REPOLL_COOLDOWN_SECONDS}s cooldown...")
        time.sleep(_REPOLL_COOLDOWN_SECONDS)
        question_by_id = {q["id"]: q for q in questions}
        juror_by_id: dict = {}
        for _, j in jurors.iterrows():
            juror_by_id[j.get("pums_idx", j.name)] = j
        retried, recovered = 0, 0
        for f in api_failures:
            jid, qid = f["juror_id"], f["question_id"]
            if jid not in juror_by_id or qid not in question_by_id:
                continue
            juror, q = juror_by_id[jid], question_by_id[qid]
            trait_block = _format_trait_block(juror)
            # Find the original row index
            row_idx = next((i for i, r in enumerate(rows)
                            if r["juror_id"] == jid and r["question_id"] == qid), None)
            if row_idx is None:
                continue
            retried += 1
            # Reproduce the same presentation order this (jid, qid) saw on the first pass.
            options_presented = _options_as_presented(
                q["options"], jid, qid, run_seed, option_order,
            )
            try:
                if polling_mode == "direct":
                    result = _ask_one(
                        client, model, juror["narrative"], trait_block,
                        field_date_iso, q["text"], options_presented,
                    )
                    response, reasoning = _validate_response(result, q["options"])
                    if response is not None:
                        rows[row_idx].update({"response": response, "reasoning": reasoning})
                        recovered += 1
                elif polling_mode == "probvec":
                    result = _ask_one_probvec(
                        client, model, juror["narrative"], trait_block,
                        field_date_iso, q["text"], options_presented,
                    )
                    probs, raw_sum, validation_reason = _validate_probvec(result, q["options"])
                    if probs is not None:
                        response = _sample_from_probvec(probs, jid, qid, run_seed, q["options"])
                        rows[row_idx].update({
                            "response": response,
                            "reasoning": result.get("reasoning", ""),
                            "probabilities_json": json.dumps(probs),
                            "prob_sum_before_norm": raw_sum,
                            "prob_max": max(probs.values()),
                            "prob_entropy": _probvec_entropy(probs),
                        })
                        recovered += 1
            except Exception:
                pass  # still failed; keep original row
        print(f"  repoll: {recovered}/{retried} recovered")
        # Rebuild failures list from current state of rows
        failures = [
            {"juror_id": r["juror_id"], "question_id": r["question_id"],
             "type": "unrecovered", "reasoning_snippet": str(r.get("reasoning", ""))[:120]}
            for r in rows if r["response"] is None
        ]

    # ============================================================
    # Failure-rate gates: overall AND per-question
    # Per-question gate catches the failure mode where one question loses a
    # disproportionate share of rows (e.g., Q4 hit 25% in the v3 canary while
    # overall was 2.4%). Both gates must pass.
    # ============================================================
    fail_rate = len(failures) / max(total, 1)
    by_type: dict[str, int] = {}
    by_q: dict[str, int] = {}
    for f in failures:
        by_type[f["type"]] = by_type.get(f["type"], 0) + 1
        by_q[f["question_id"]] = by_q.get(f["question_id"], 0) + 1
    per_q_total = {q["id"]: 0 for q in questions}
    for r in rows:
        per_q_total[r["question_id"]] = per_q_total.get(r["question_id"], 0) + 1
    per_q_rate = {q: by_q.get(q, 0) / max(per_q_total[q], 1) for q in per_q_total}
    if failures:
        print(f"\npolling failures (post-repoll): {len(failures)}/{total} ({fail_rate * 100:.1f}%)")
        print(f"  by type: {by_type}")
        print(f"  per-question rates: "
              + ", ".join(f"{q}={per_q_rate[q]*100:.1f}%" for q in sorted(per_q_rate, key=lambda x: -per_q_rate[x])[:5]))

    if not allow_failures:
        overall_breach = fail_rate > max_failure_rate
        worst_q_rate = max(per_q_rate.values()) if per_q_rate else 0
        worst_q = max(per_q_rate, key=per_q_rate.get) if per_q_rate else None
        per_q_breach = worst_q_rate > max_failure_rate
        if overall_breach or per_q_breach:
            msg_parts = []
            if overall_breach:
                msg_parts.append(
                    f"overall failure rate {fail_rate*100:.1f}% > {max_failure_rate*100:.0f}% threshold"
                )
            if per_q_breach:
                msg_parts.append(
                    f"per-question failure rate {worst_q_rate*100:.1f}% > {max_failure_rate*100:.0f}% on '{worst_q}'"
                )
            raise PollingFailureThreshold(
                f"polling gate failure: {'; '.join(msg_parts)}. "
                f"By type: {by_type}. Per-question rates: {per_q_rate}. "
                f"Pass allow_failures=True only for explicit canary runs.",
                failures=failures,
            )
    return pd.DataFrame(rows)
