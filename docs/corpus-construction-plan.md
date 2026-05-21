---
type: build-plan
created: 2026-05-15
updated: 2026-05-17
project: the-jury
status: public-package methods context
status_context: Stage B W158 n=1000 complete (2026-05-17). W158 marginal-shift analysis + cross-model + option-order canary both complete (2026-05-17). Project repositioned toward a methods writeup rather than a product; W163/W161 stay parked.
target: Stage A n=200 (complete); Stage B W158 n=1000 (complete; coverage passed, thresholds failed via marginal-error shifts rather than broad entropy compression); 4-arm cross-model + option-order canary at n=200 x 4 questions (complete; confirmed Q8 vaccine bias structural, Q9 astrology partially recoverable, Q11 fragmentation mostly option-order, Q5 calibration order-dependent; Opus 4.5 left the main W158 errors largely intact). W163/W161 staged but parked.
tags: [the-jury, corpus, sampling, calibration]
companion_docs: [sanitized-chronology.md, prior-provenance-schema.md, stage-b-w158-results.md, w158-marginal-shift-analysis.md, literature-bisbee-methods-review.md]
---

# Pew Replication Corpus Construction Plan (Two-Stage)

Top-level decisions, justifications, and tradeoffs for the corpus underlying the Pew replication artifact. Companion to `sanitized-chronology.md` (chronological build log, sanitized for public release) and `prior-provenance-schema.md` (methodologist-ready provenance contract for every conditional-prior JSON file).

---

## Current state (2026-05-17)

**Stage A complete (2026-05-16).** End-to-end LLM expansion ran against the real IPUMS ACS 2024 1-year extract (2.76M adult records). 200 jurors produced. Four rounds of code-review-agent review; all 13 findings closed.

**Option B complete (2026-05-16).** All 7 conditional priors + non-modal opinion bank real-sourced per `docs/prior-provenance-schema.md` (Pew NPORS 2025 / Pew ATP W133 / Pew RLS 2023-24 / Pew News Platform + Social Media Fact Sheets / Pew Political Gap + AllSides v11 / Census CPS ASEC 2023 / GSS 2018-2022 pooled). All 8 prior files load under production strict mode (`--no-stubs`).

**Stage B W158 n=1000 complete (2026-05-17).** First Stage B credibility artifact ran against Pew ATP Wave 158 (Oct 21-27 2024; climate / COVID retrospective / trust in scientists / spirituality). 11 questions, probability-vector polling, all 17 build-policy guards active. Output at `build/out/stage_b/W158_n1000_probvec_20260516_v1/`. 11,000 / 11,000 responses captured (410 transient API errors during a mid-run credit window all recovered by the failed-row repoll guard). **Coverage rule passed on all 11 questions. Thresholds failed on all 11, but the failure mode changed from the within-cell variance compression the plan worried about to systematic marginal directional bias on specific topics.** Median entropy ratio across 383 measured cells: 1.035 (within-cell variance is as spread as Pew). Q9 astrology is the one Bisbee-style holdout (17% entropy CI pass rate vs 85-97% on the other 10 questions). Full results in `docs/stage-b-w158-results.md`.

**W158 marginal-shift analysis complete (2026-05-17, no API spend).** Full diagnostic in `docs/w158-marginal-shift-analysis.md` (Q5 + Q11 calls partly superseded by the canary below; see top-of-doc supersession banner). Headline: sampling noise from the deterministic hash-sampler is ≤3pp on every question (≤1pp on Q9/Q11), so the marginal bias lives in the LLM's per-juror probability vectors. The 11 questions resolve into three distinct failure modes: clean directional swap (Q8 vaccine, dominantly LLM prior bias on temporal topline), Bisbee-class binary minority suppression (Q9 astrology, with a Meister/Guestrin/Hashimoto 2025 knowledge-to-simulation gap signature where reasoning articulates the correct base-rate logic then probvec under-applies it), and fragmentation of Pew-modal moderate options into surrounding alternatives (Q7 school closures, Q11 police). Errors cluster by question rather than as a single demographic-cell artifact. The 70-juror outlier slate adds little on these four questions because its non-modal opinion priors were calibrated against GSS issues (abortion / guns / immigration / marriage / marijuana) rather than W158 topics. Topic match matters.

**Cross-model + option-order canary complete (2026-05-17 evening, ~4h 12m).** 4-arm 2x2 factorial at n=200 x 4 questions (Q5/Q8/Q9/Q11) reusing the Stage B v1 expanded corpus. Full results in `docs/w158-crossmodel-canary-results.md`. Headline: (a) Opus 4.5 left the main W158 errors largely intact at Pew-canonical option order, while a real model x order interaction emerged on Q5 reversed where Sonnet vs Opus diverged by 14.1pp on "Better"; (b) option-order effect is large and direction-dependent — Q5 calibration degraded under reversal (1.8→12.3pp on Sonnet), Q9 + Q11 both substantially improve (5-6pp recovery on both models), Q8 remains stable on bias direction; (c) two morning diagnoses corrected — Q5 "near-perfect calibration" was order-dependent; Q11 "LLM over-polarizes police" was mostly option-order; (d) Q8 vaccine bias is structural ("Probably not" at 43-46% on every arm vs Pew 60%); (e) Q9 astrology has both components (best arm Opus-rev closes 6.3pp of 12.7pp, ~7pp residual structural).

**Next moves (no canary firing, no W163/W161):**

1. **Public methods writeup** (LinkedIn / arXiv-tier, ~3-4k words). Synthesizes the architecture, the W158 result, the marginal-shift analysis, and the cross-model canary. Hooks the post-Bisbee literature framing (Meister/Guestrin/Hashimoto knowledge-to-simulation gap). Substrate exists; drafting is the next active task.
2. **Per-juror option-order randomization** (~10 lines in `src/poll_runner.py`, shuffle `q["options"]` with `sha256(juror_id|question_id|run_seed)` seed). Becomes the standard for any subsequent run.
3. **Q7 school closures single-question follow-up** (optional). Determines whether Q7's 12pp gap behaves like Q11 (option-order recoverable) or Q8 (structural). Refines the three-failure-mode typology.
4. **W163 + W161** remain staged in the working tree but parked. A tighter W158-only story is the stronger writeup.

**Active runtime guards (17 build-policy elements summarized below):**
- Stage B refuses STUB priors (`StubPriorRefused`) and provenance-incomplete priors (`MissingProvenance`)
- API preflight before any paid expansion (`scripts/preflight.py`)
- `expand_corpus` fails closed at >5% failure rate (`ExpansionFailureThreshold`)
- Validation harness refuses unweighted runs (`UnweightedRefused`)
- Per-question polling failure gate plus failed-row repoll (`PollingFailureThreshold`)
- Calibrated weight cap [0.33x, 3x] with re-selection on breach
- Coverage rule on validation cells (≥80% top-level + ≥50% interaction)
- Full bootstrap CIs on every per-cell metric
- Expected-vs-sampled diagnostics split in Stage B output

---

## Decisions

### D1. Source of joint structure: IPUMS ACS 2024 1-year PUMS microdata

**Why.** PUMS gives 2.76M actual adult person-records (post-AGE>=18 filter on the IPUMS extract) with real joint covariance across the major demographic variables (age, sex, race, ethnicity, education, occupation, income, household composition, geography, language, citizenship, disability, veteran status, housing tenure). Avoiding assumed independence.

**Tradeoff.** PUMS only covers Census-collected variables. Political party, religion, media diet, household composition (beyond what HHTYPE provides), and life-stage transitions for non-PUMS axes are all PUMS-out. These get a second-pass conditional sampler against Pew / GSS / BRFSS / ATUS crosstabs. Lower-fidelity than PUMS but the best available substrate. Document where conditional independence had to be assumed.

**Refinement (post-review-round-2).** Life-stage transitions (`life_stage_recent`) was originally specified for second-pass conditional sampling. Five PUMS event-flag variables (FERTYR, DIVINYR, MARRINYR, MIGRATE1, MARST) were added to the IPUMS extract cart, and `life_stage_recent` is now derived directly from PUMS at first-pass via `src/buckets.py:derive_life_stage_recent`. This is a strict upgrade: PUMS event flags carry real Census joint covariance with the rest of the trait vector, where second-pass conditional sampling would have used inferred event-rate priors. Known limitation: WIDINYR was missed during cart construction, so `recently_widowed` is not a transition this implementation can detect; currently-widowed status is still visible via the MARST translation but is correctly NOT flagged as a past-year event.

**Rejected alternative.** Building a Bayesian network with explicit conditional probability tables across all 90+ trait classes. Engineering cost is materially higher; for the Pew replication artifact (n=200 dry run, n=1000 public) the variance-reduction return is near zero. Reconsider when corpus crosses ~5K jurors.

**Vintage.** ACS 2024 1-year (not 2023 5-year). Most current, ~3M records is sufficient sample basis for n=200/1000 PPS draws without pandemic-era window averaging. Marginals computed at runtime from the extract's own PERWT-weighted distribution via `src/sampler.py:compute_marginals_from_pums`; no hardcoded vintage targets, no vintage-drift risk.

### D2. Sampling method: PPS selection from PUMS with raked analysis weights to avoid parametric draw

**Why.** At Stage A and Stage B sample sizes (n=200 and n=1000), the right move is to sample real person-records from the PUMS substrate via PPS (probability-proportional-to-size against ACS person-weights), then post-stratify with raked analysis weights (D3). This carries the joint covariance forward by construction. No parametric model means no parametric bias. (D3 specifies the raking procedure and the weight cap; D2 here names the high-level choice.)

**Tradeoff.** A PPS+raked sample is not a simple random sample. The published methodology footnote names this explicitly: "PPS selection from ACS 5-year PUMS, post-stratified via iterative proportional fitting against ACS marginals on race x age x education x Census region, calibrated analysis weights bounded to [0.33x, 3x]." This is standard survey-research practice and survives review; pretending it's a simple random sample does not.

### D3. Marginal-target raking on race x age x education x Census region to avoid cell-quota stratification

**Why the change.** A 7 x 5 x 4 x 4 frame produces 560 cells. At n=200, a 0.2% population-share floor implies a 0.4 expected juror per cell, which is mathematically incoherent as a quota — the floor would either over-represent small cells with forced inclusion or be unsatisfiable across the frame. Cell-quota stratification overfits the construction to a sample size that cannot support it.

**What we do instead.** PPS (probability-proportional-to-size) selection from PUMS using ACS person-weights to produce the n raw juror records, then iterative proportional fitting (raking) on the four-axis *marginals* to produce **calibrated analysis weights** per juror to avoid duplicated draws. The selection step is the random sample; the raking step is the post-stratification calibration. Every published metric (marginal accuracy, Wasserstein, entropy ratio, minority recovery) is computed against the calibrated weights, not the raw juror counts. Matching ACS marginals "to within ~1%" is only honest under this two-step framing; an attempt to match marginals via duplicated raw selection at n=200 would be misleading.

**Weight cap.** Calibrated weights are bounded to [0.33x, 3x] per juror. No single juror counts as less than one-third or more than three normal jurors in any analysis. This is standard survey-research practice (cf. Kalton & Flores-Cervantes 2003) and prevents one weirdly weighted juror from dominating an interaction cell. Jurors that would require weights outside this range trigger a re-selection on the relevant stratum rather than weight-clipping (which would silently bias the marginal away from the ACS target).

**Tradeoff.** Marginal raking with capped weights does not guarantee any specific small interaction cell (e.g., AIAN women 75+ in Northeast) is represented in the raw selection. The defensible position is honest reporting: "the corpus is calibrated to ACS marginals on race, age, education, and region via raked analysis weights bounded to [0.33x, 3x]; joint structure on additional interactions reflects the natural PUMS resample and is not separately controlled at n=200." Joint-cell guarantees move in at the n=1K+ scale where raw selection populates the frame.

### D4. Second-pass conditional sampling for non-PUMS traits — narrowed to the cheap-experiment minimum

**Why narrowed.** The full second-pass (political party, religion, religiosity, media diet, hobbies, music genre, identity flags, OCEAN, moral foundations, health, life-stage transitions, etc.) belongs in the v0.2 sampler when the construction technique is validated. For the cheap experiment, only the traits that load on the Pew replication question's response distribution belong in the construction. Building unvalidated synthetic texture for traits the validation harness cannot measure adds work, expands the failure surface, and produces colorful jurors that are not actually accurate on the dimensions we report on.

**v0.1 sampler scope (cheap experiment only).** Seven conditional-prior traits, sourced per `docs/prior-provenance-schema.md`. Canonical list is `V01_TRAITS` in `src/conditional_sampler.py`.

- Political party (Pew political typology crosstabs by race x education x age x region)
- Political ideology (GSS conditional on party x age x education)
- Religion (Pew Religious Landscape Study crosstabs by race x age x region)
- Religiosity (Pew Religious Landscape Study crosstabs by religion)
- Media diet primary (Pew News Consumption Study by party x age x education)
- Media diet slant (Pew News Consumption Study by party)
- Household composition (supplements PUMS HHTYPE/NFAMS/MULTGEN with coherence trait)

Plus one non-modal opinion bank: `non_modal_priors.json` (GSS multi-issue batteries, used by the outlier mechanism).

**`life_stage_recent` is NOT a second-pass conditional trait.** It is derived directly from PUMS event flags (`FERTYR`, `DIVINYR`, `MARRINYR`, `MIGRATE1`, `MARST`) in `src/buckets.py:derive_life_stage_recent`. This is a strict upgrade over conditional sampling: real Census joint covariance vs. inferred event-rate priors. Documented per the D1 refinement above.

**v0.2 (deferred).** OCEAN, moral foundations, music genre, hobbies, identity flags, health conditions, chronic disease, addiction recovery, sexual orientation beyond what PUMS captures, `caregiver_status` (no published US-population conditional crosstab found yet; deferred until source identified). Re-enter when the question being polled requires them and the calibration substrate exists for the relevant trait.

**Tradeoff.** v0.1 jurors are demographically and politically coherent but personally thin compared to the Round-2 PERSONAS.md richness. This is the right tradeoff for a methodological smoke test: the validation harness is the gate, and the harness only measures dimensions the corpus is conditionally sampled on. Personality breadth without calibration is exactly the failure mode this plan exists to defend against.

### D5. Within-cell variance instrumentation: layered across five mechanisms

The Bisbee 2024 critique kills any plan that puts variance in one place. The plan puts it in five.

1. **PUMS resampling itself.** Real Census records carry real within-cell variance on the PUMS-covered traits. This is variance for free; the alternative (parametric draw) is what generates the Bisbee failure.
2. **Full-distribution second-pass sampling.** For non-PUMS traits, sample from the *full conditional distribution*, not the modal value. A juror with the demographic vector "white evangelical woman, age 52, Tennessee, HS-only, $45K income" gets her political party drawn from the actual conditional distribution (which is ~75% Republican, ~10% Democrat, ~15% Independent), which were not assigned the modal "Republican." 25% of those jurors come out non-Republican by construction.
3. **Persona-expansion temperature variation.** When the LLM expands the trait vector into a coherent narrative, temperature is varied across the corpus: 30% at T=0.3 (tight, stereotype-anchored), 50% at T=0.7 (varied), 20% at T=1.0 (atypical). The persona-expansion stage stops being a variance-collapser. Note: original plan called for T=0.4/0.8/1.1 but Anthropic API caps temperature at 1.0; T=1.1 calls failed in the first paid run. Patched to {0.3, 0.7, 1.0}, which preserves the low/mid/high spread intent within the API range. Original Stage A corpus carries actual call-time temperatures (0.4/0.8/1.0) for the legacy rows; `review_sample.py` aliases at read time.
4. **Calibrated outlier injection — at panel level with concrete priors, not vague flags per cell.** 7% of jurors per stage carry outlier status (14 jurors at n=200, 70 jurors at n=1000), allocated across coarse cells (party x age, four buckets each producing 16 coarse cells, with a fixed seed) rather than the 560-cell construction frame. At n=200 this is roughly one outlier per coarse cell; at n=1000 it averages ~4-5 per coarse cell with the surplus distributed proportional to ACS coarse-cell weight. Each outlier juror is assigned a *concrete non-modal prior* on at least one tracked opinion, drawn from the actual non-modal distribution in GSS / Pew source microdata for that juror's coarse cell — e.g., a white evangelical assigned a pro-choice position drawn from the real ~25% of white evangelicals who hold that position, not a generic "this person is atypical" instruction. The non-modal prior enters the expansion prompt as a specific committed opinion the juror holds and reasons from, with the persona's narrative built around the tension between the demographic baseline and the held position. The 7% rate is calibrated against measured non-modal-opinion density in GSS multi-issue batteries; the rate is stage-invariant.
5. **Lived-constraint axis from PUMS event flags.** `life_stage_recent` is derived first-pass from PUMS event variables (`FERTYR`, `DIVINYR`, `MARRINYR`, `MIGRATE1`, `MARST`) per `src/buckets.py:derive_life_stage_recent`. This carries real Census joint covariance forward into the third-axis perturbation, not the inferred event-rate priors the original plan called for. Observed at Stage A (n=200): {75% no transition, 11% recently_relocated_metro, 3.5% recent_parent_under_2yr, 3% recently_divorced_separated, 0.5% recently_married}. The Round-2 ideator work demonstrated the third-axis perturbation works at n=20; this construction technique brings it to population scale at both stage sizes.

   **Known limitations:** (a) `WIDINYR` was missed during IPUMS extract construction, so `recently_widowed` is not in this trait's value set; currently-widowed adults (MARST=5) are visible to the persona layer but are correctly NOT flagged as a past-year event. Fix in v0.2: re-pull IPUMS extract with WIDINYR included. (b) `caregiver_status` is deferred to v0.2; no published US-population conditional crosstab found yet, and PUMS does not directly identify caregivers.

**Tradeoff.** Five mechanisms is more engineering than one. The defense is layered specifically so no single mechanism carries the load. If the validation harness shows entropy ratio passing, the layering is empirically justified; if any single mechanism is later shown ineffective, the others provide redundancy.

### D6. Validation gate — coarse cells with minimum-n thresholds and bootstrap CIs, not per-construction-cell metrics

**Why the change.** Per-cell Wasserstein, entropy ratio, and minority-position recovery are not meaningful when most construction cells have 0-2 jurors and the matching Pew source-microdata cells are also sparse. Reporting per-560-cell metrics at finite n (especially below n=1000) produces false precision and is the methodologist's first attack — exactly the credibility damage the Bisbee defense exists to prevent. The validation surface needs to scale with sample size, not pretend the construction frame can be measured at any n.

**Validation cells are defined separately from construction cells.** Coarse, defensible aggregations where both synthetic n and Pew source-microdata n exceed minimum thresholds:

| Validation cell | Cells in frame | Min synthetic n per cell | Min source n per cell |
|---|---|---|---|
| Age (5 buckets) | 5 | 25 | 100 |
| Education (4 buckets) | 4 | 30 | 150 |
| Race/ethnicity (4 collapsed buckets) | 4 | 25 | 100 |
| Political party (3 buckets: D / R / I) | 3 | 50 | 200 |
| Age x party | 15 | 8 | 50 |
| Race x education | 16 | 8 | 50 |

Cells that fall below the minimum n on either side are reported as "underpowered, not measured" rather than fabricated.

**Metrics published with bootstrap confidence intervals.** Wasserstein distance, Shannon entropy ratio, and minority-position recovery rate per validation cell, each with 1000-iteration nonparametric bootstrap 90% CI. The CI is the credibility move: a metric without uncertainty quantification at finite n (especially below n=1000) is misleading by construction. Thresholds (entropy ratio point estimate >0.80 with CI lower bound >0.70; minority recovery point estimate >0.60 with CI lower bound >0.45) apply to the validation cells, not the construction frame.

**Minimum validation coverage rule.** A run only counts as having passed (or failed) the harness if the validation surface itself is sufficiently covered: at least 80% of top-level cells (≥13 of the 16 cells across age + education + race + party) AND at least 50% of interaction cells (≥16 of the 31 cells across age x party + race x education) must clear the minimum-n thresholds and be measured. A run where most cells fall under "underpowered, not measured" is not a passing run regardless of how the measured cells score; it triggers a re-selection at larger n or a stratification adjustment, not a green light. This prevents the harness from passing by silently measuring only the easy cells.

**Iteration budget.** If the harness fails on first pass with the coverage rule satisfied, iterate construction techniques (raise temperature variation, increase outlier fraction, enrich conditional sampling granularity on a specific failing axis) and re-run. Budget two iteration cycles. If both fail at the validation-cell level with bootstrap CIs respected, the Bisbee critique is structural at this execution level.

---

## Sequence — two-stage program

The original "200-juror cheap experiment" is restructured into a two-stage program. n=200 is the construction-pipeline dry run; n=1000 is the public credibility artifact. n=200 alone is methodologically too thin for a publishable replication: at that size, validation cells average ~13 jurors per top-level cell and ~3 per interaction cell, the topline margin of error is roughly ±7 points before any synthetic-respondent complications, and most interaction cells will trip "underpowered, not measured." n=1000 brings the topline MoE to ~±3 points, age x party averages ~67 per cell, and the harness gains the resolution to actually distinguish a Bisbee failure from a sample-too-small artifact. n=1000 does not solve Bisbee by itself (a variance-compressing model compresses variance at any sample size) but it gives the harness enough signal to know which is happening.

### Stage A: n=200 internal dry run (COMPLETE — 2026-05-16)

| Step | Action | Actual outcome |
|---|---|---|
| 1 | Pull IPUMS ACS 2024 1-year PUMS US-adult sample (2.76M records post-AGE filter) | done, parquet at `build/data/raw/usa_acs2024.parquet` (124 MB) |
| 2 | PPS selection n=200 from PUMS; rake to four-axis marginals; produce calibrated weights bounded [0.33x, 3x] | converged within 0.4% on all four axes; weights [0.362, 2.365] |
| 3 | v0.1 second-pass sampler (7 traits; life_stage_recent moved to first-pass PUMS-derived per D1 refinement) | STUB priors only; production replacement is the Option B deliverable |
| 4 | Variance instrumentation: 14-juror outlier slate with concrete non-modal opinion priors; expansion temperatures (30/50/20) | 14 outliers across 12 distinct coarse cells, 100% with concrete non-modal opinions |
| 5 | LLM persona expansion: 200 trait vectors → 200 narrative jurors | done; 200/200 narratives produced after re-expansion fixed the 54 initial bugs |
| 6 | Internal validation pass + QA review pack stratified by temperature band + outliers | passed; review pack at `build/out/stage_a/run_01/qa_review_pack.md` (102 KB) |
| **Stage A actual** | | **Complete; 4 code-review-agent rounds applied; 13 findings closed** |

Pass criterion for Stage A: sampler runs to completion, calibrated weights respect the cap, persona expansion produces narratively coherent jurors, and top-level validation cells either clear minimum-n or any cell that misses (e.g., the collapsed race bucket failing the n≥25 floor on a 200 draw, which is plausible) is *explainable* (which axis, which selection step, expected per the n=200 sample size) and *fixable* by a specific Stage B adjustment (larger n, raked-weight rebalancing, or a stratification tweak) before Stage B runs. Interaction-cell coverage failure is expected at n=200 and is not a Stage A failure. Stage A exists to surface bugs and structural surprises in the pipeline, not to gate on the same coverage rule the public artifact must satisfy.

### Stage B: n=1000 public credibility artifact

| Step | Action | Estimated time |
|---|---|---|
| 1 | Reuse Stage A pipeline; PPS selection n=1000 from PUMS; rake; produce calibrated weights | 1 hr |
| 2 | Second-pass sampler: same scope as Stage A, run at n=1000 | 30 min |
| 3 | Variance instrumentation: 70-juror panel-level outlier slate (7%) with concrete non-modal opinion priors; expansion temperatures (30/50/20) | 30 min |
| 4 | LLM persona expansion: 1000 trait vectors → 1000 narrative jurors (Opus on the 70 outliers) | 4 hr |
| 5 | Validation: 5-question Pew replication on coarse validation cells, Wasserstein + entropy ratio + minority recovery with 1000-iter bootstrap 90% CIs, coverage rule applied | 2 hr |
| 6 | If validation fails with coverage rule satisfied: iterate construction techniques and re-run | up to 2 cycles |
| 7 | Publish: methodology footnote, validation results table, raw juror trait vectors (anonymized), bootstrap-CI plots | 3-4 hr |
| **Stage B total** | | **~12-16 hr base; up to ~24 hr across two iteration cycles** |

### Combined program

**Total: ~20-26 hr base.** If skipping Stage A and going straight to Stage B (the artifact is the only deliverable), drop ~8 hr.

Recommendation: run Stage A. The marginal cost is small, the construction-pipeline confidence gained is large, and a Stage B run that fails because of a sampler bug rather than a calibration finding is an expensive way to learn the bug existed.

---

## Polling protocol (added 2026-05-16 after n=100 canary diagnosis)

The polling layer — how synthetic jurors answer Pew questions — went through three iterations during Stage B canary work. The first paid canary surfaced systematic LLM bias that traced to the polling protocol, not to the architecture upstream. Documenting because it materially shapes what the Stage B artifact says.

### v1: direct-choice (initial implementation)
Minimal prompt: send the LLM the persona narrative + answer options, ask it to "pick one" + reasoning. Standard survey-replication LLM pattern. At n=100 produced systematic center-mass concentration and extreme-option refusal across 11 W158 questions: Q4 scientist confidence collapsed to 84% "Fair amount" (vs Pew 51%); Q9 astrology to 99% "No, don't believe" (vs Pew 73%); Q5 scientists-policy to 78% "Neither" (vs Pew 47%). Median entropy ratio across measured cells: 0.53.

### v2: anti-center + structured trait block + field-date + exact-option validation
Improvements: explicit anti-center system-prompt language, compact per-juror trait block sent alongside the narrative (carries traits the narrative may not surface), field-date context ("you are answering this Pew survey in October 2024"), and exact-option validation (responses outside the offered set are recorded as failures rather than fabricated near-matches). Median entropy ratio moved baseline 0.53 → v2 0.56 — small. Anti-center overshot on questions where center IS modal (Q3 climate-policy "Make no difference" purged from 6.5% to 0% even though Pew has it at 31%; Q6 COVID restrictions "Fewer" overshot to 64% vs Pew 38%). The patch hit some real bias but introduced symmetric over-correction.

### v3: probability-vector polling (Argyle 2023 / Park 2024 primitive)
Instead of direct-choice, the LLM returns a probability distribution over the offered options. Code samples one option post-hoc using `sha256(juror_id|question_id|run_seed)` as a deterministic RNG seed. The system prompt frames probabilities as "uncertainty about the exact survey response, not a desire to be moderate or random." Both calibration extremes get explicit handling: "Assign meaningful probability to strong endpoints when this person could plausibly hold that view; assign meaningful probability to moderate options when moderation is genuinely plausible."

The full vector is persisted per row (`probabilities_json`, `prob_sum_before_norm`, `prob_max`, `prob_entropy`) so two distributions can be reported: SAMPLED (what a real poll-replication would produce) and EXPECTED (weighted sum of per-juror probability vectors, the model's latent calibration). The breakthrough claim of probvec polling is that the model's latent distribution calibrates to the source survey — making that claim inspectable requires persisting both.

Validation: option key set must equal the offered set exactly (no missing, no extras); values non-negative; sum in [0.95, 1.05] (LLMs aren't exact); renormalize after validation, log pre-normalization sum.

**v3 result at n=100:** median entropy ratio jumped to 0.91 (baseline 0.53). Every single question improved. Expected-distribution accuracy reached 1pp max error on Q5 (matches Pew within 1pp); within 5-6pp on Q2/Q3/Q6 (climate cause, climate-policy economy, COVID restrictions); 8-10pp on Q1/Q4 (climate impact, scientist confidence); 11-16pp on Q7/Q8/Q11 (school closures, vaccine, police). Q9 astrology expected yes-rate 14.3% vs Pew 27% (vs baseline 1.3%) — large recovery but still the hardest question.

**Conclusion: v3 probvec is the Stage B polling protocol.** The polling layer was the bottleneck; the upstream architecture (PUMS + raked weights + 7 real-sourced conditional priors + 5-layer within-cell variance instrumentation) was already calibrated. Direct-choice polling was indicting the architecture for a problem the architecture didn't have.

## Build-policy elements (introduced through review rounds 1-4 + Stage B canary)

Each of these is a runtime guard or contract enforced by the code. Together they make the architecture difficult to misuse and easy for a methodologist to verify.

1. **Stub-prior runtime guard** (`StubPriorRefused`). Conditional priors and the non-modal opinion bank refuse to load files with `source == "STUB"` unless `--allow-stubs` (Stage A debug) is explicit. Stage B never sets this flag.

2. **Provenance runtime guard** (`MissingProvenance`). Non-STUB prior files must carry a `provenance` block with the required fields specified in `docs/prior-provenance-schema.md`. Production runs refuse priors that fail this check. Provides the methodology-footnote substrate by construction.

3. **API preflight** (`scripts/preflight.py`). One `max_tokens=8` canary call per `(configured_model x configured_temperature)` cell before any paid expansion. Catches model-ID mismatches, parameter restrictions (e.g., the Opus-4.7-rejects-temperature class of bug), permission issues, and out-of-range temperatures. Wired into Stage A and Stage B as a hard gate. ~$0.01 to run.

4. **Fail-closed expansion** (`ExpansionFailureThreshold`). `expand_corpus` raises if the failure rate exceeds `max_failure_rate=0.05` default. Reports failures grouped by error class. Pass `allow_failures=True` only for explicit debug paths like `reexpand_failed.py`.

5. **Validation harness fail-closed on missing weights** (`UnweightedRefused`). The validation contract is weighted (D3). If either weight column is absent, the harness refuses to run unless `allow_unweighted=True` is set deliberately. Stage B never sets this flag.

6. **Validation cells decoupled from construction frame.** Per-cell metrics are computed on coarse validation cells with documented minimum-n thresholds, not on the 560-cell construction frame. Cells below the n-threshold are reported as `underpowered, not measured` and do not enter the threshold counts.

7. **Coverage rule.** A run does not count as having passed or failed the harness unless ≥80% of top-level cells AND ≥50% of interaction cells clear minimum-n. Prevents the harness from passing by silently measuring only the easy cells.

8. **Cartesian-product interaction-cell enumeration.** Interaction cells are generated from the full configured cartesian product (e.g., age buckets x party buckets), not from observed combinations in the synthetic panel. Cells absent from synth correctly count as underpowered, not silently dropped.

9. **Bootstrap CIs everywhere.** Every published per-cell metric carries a 1000-iteration nonparametric bootstrap 90% CI. Thresholds apply to point estimate AND CI lower bound. A metric without uncertainty quantification at finite n is misleading by construction.

10. **Expansion prompt fabrication guard.** The system prompt explicitly forbids inventing factually or legally specific claims (voting history, immigration timeline, employer names, military deployment locations) beyond what the trait vector supports. Caught after a re-read of juror 101 (review round 4) revealed a plausible-sounding non-citizen "voted in local elections" fabrication.

11. **Curated trait projection for LLM expansion.** The LLM persona-expansion prompt uses an explicit allow-list of trait fields with raw PUMS codes translated to human-readable strings (`MARST=5` → `"marital status: widowed"`). Eight code translation tables in `src/expansion.py`; no opaque numbers reach the LLM.

12. **Capped analysis weights with re-selection.** Raked weights bounded to [0.33x, 3x]. Jurors that would require weights outside the cap trigger PPS re-selection on the affected stratum rather than weight-clipping (which would silently bias the marginal away from ACS target).

13. **Per-question polling failure gate** (`PollingFailureThreshold`). `run_poll` raises if any single question's failure rate exceeds 5%, even if overall rate is under 5%. Caught the v3 canary failure mode where Q4 had 26% API errors while overall was 2.4% — overall-only gate would have passed a run that lost a quarter of one question.

14. **Failed-row repoll with cooldown.** After main polling pass, `api_error` failures (transient, retry-able) are retried after 15s cooldown; `option_mismatch` and `probvec_invalid` failures (LLM output problems, not transient) are not retried. Gates evaluate post-repoll. Reduces brittle-network noise without papering over LLM-side problems.

15. **Polling-protocol minimum-n floor.** n=25 canary was refused by `WeightCapBreach` (raking cap structurally unsatisfiable at small n given 4-axis marginals). Practical lower bound for honest raked Stage B-style runs is ≈ n=100. Stage A n=200 dry-run sits comfortably above.

16. **Probability-vector polling as the production primitive.** Direct-choice polling forces the LLM into a single most-defensible answer per juror and produces center-mass concentration even with rich trait priors. Probvec polling elicits a probability distribution over options per (juror, question), validates it (exact set equality + non-negative + sum ∈ [0.95, 1.05]), and samples deterministically post-hoc. Persists `probabilities_json` + `prob_sum_before_norm` + `prob_max` + `prob_entropy` per row for inspection.

17. **Expected-vs-sampled distribution split in Stage B output.** Probvec mode writes both `validation_results.json` (sampled distribution scored against Pew; what a real poll-replication would produce) and `expected_distribution_diagnostics.json` (weighted aggregate of per-juror probability vectors; the model's latent calibration). At finite n, sampled outcomes carry hash-sampling noise that expected does not — methodologist needs both to evaluate the calibration claim distinct from the realized sample.

## Open construction questions deferred to execution

- Which Pew poll is the validation target? Recent, microdata-available, multi-issue, ideally polled within last 6 months. (Candidates: Pew American Trends Panel waves 2025-Q4 or 2026-Q1.)
- Which IPUMS sample year exactly? 2023 5-year PUMS is most stable; 2024 1-year if released by execution date and political-party / media-diet crosstabs from Pew are aligned to same vintage.
- Whether to ship Stage A's n=200 dry-run output anywhere (internal artifact only vs. published as "construction-pipeline validation"). Default: internal only; Stage B is the public artifact.

---

## Two-paragraph summary

The program runs in two stages: an n=200 internal dry run that debugs the construction pipeline (sampler, weighting, expansion, harness) at low cost, then an n=1000 public credibility artifact that is the actual replication. Stage A completed 2026-05-16. n=200 alone is methodologically too thin for a publishable claim — topline MoE around ±7 points and most interaction validation cells under-powered — so the public artifact uses n=1000 where MoE drops to ±3 and the harness has the resolution to distinguish a Bisbee failure from a sample-too-small artifact. Both stages use the same pipeline: PPS selection from IPUMS ACS 2024 1-year PUMS microdata (2.76M adult records post-AGE>=18 filter), iterative-proportional-fitting on four marginal axes (race, age, education, Census region) with marginals computed at runtime from the extract's own PERWT-weighted distribution, producing calibrated analysis weights bounded to [0.33x, 3x] per juror (selection is the random sample; raking is post-stratification calibration; weight cap prevents one weirdly-weighted juror from dominating an interaction cell). A narrowed v0.1 second-pass sampler conditionally draws political party, ideology, religion, religiosity, media-diet primary, media-diet slant, and household composition from Pew typology / Religious Landscape Study / News Consumption Study crosstabs conditional on the PUMS-resolved demographic vector — 7 traits, sourced per the provenance schema in `docs/prior-provenance-schema.md`. `life_stage_recent` is NOT a second-pass trait; it is derived first-pass from PUMS event flags (`FERTYR`, `DIVINYR`, `MARRINYR`, `MIGRATE1`, `MARST`) in `src/buckets.py:derive_life_stage_recent`, carrying real Census joint covariance forward. The full ontology (OCEAN, moral foundations, music, hobbies, identity flags, health, caregiver status) is deferred to v0.2.

Within-cell variance is defended by five layered mechanisms because Bisbee 2024 warns single-mechanism defenses fail: (1) PUMS resampling preserves real joint variance for free, (2) the second-pass sampler draws from full conditional distributions not modal values so a "white evangelical Tennessee woman" comes out 25% non-Republican by construction, (3) LLM persona-expansion temperature is varied across the corpus (30/50/20 across T=0.3/0.7/1.0 — original plan called for T=0.4/0.8/1.1 but Anthropic API caps at 1.0; patched in Stage A first paid run), (4) 14 outliers in Stage A and 70 outliers in Stage B (7% of n in both cases), allocated at panel level across 16 coarse party-by-age cells with a fixed seed rather than the construction frame, each carry a concrete non-modal opinion prior drawn from the actual GSS/Pew non-modal distribution for their coarse cell, and (5) `life_stage_recent` brings the third-axis perturbation to population scale via PUMS event flags. Validation is decoupled from construction: metrics (Wasserstein, entropy ratio, minority-position recovery) are computed on coarse validation cells (age, education, race, party, age x party, race x education) where both synthetic and Pew source-microdata n clear minimum thresholds, with 1000-iteration bootstrap 90% confidence intervals published alongside every point estimate, weighted against the calibrated analysis weights (the harness refuses to run unweighted via `UnweightedRefused`), and a coverage rule (≥80% of top-level cells AND ≥50% of interaction cells must clear minimum-n) that prevents the harness from passing by silently measuring only the easy cells. If both Stage B iteration cycles fail to meet the entropy-ratio and minority-recovery thresholds at the validation-cell level with CIs respected and coverage satisfied, the Bisbee critique is structural at this execution level.
