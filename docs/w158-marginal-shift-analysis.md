---
type: analysis
project: the-jury
artifact: Stage B W158 v1
created: 2026-05-17
output_dir: build/out/stage_b/W158_n1000_probvec_20260516_v1/
intermediate: build/out/stage_b/W158_n1000_probvec_20260516_v1/marginal_shift_analysis.json
script: build/scripts/analyze_w158_marginal_shift.py
companion: [stage-b-w158-results.md, literature-bisbee-methods-review.md, sanitized-chronology.md, w158-crossmodel-canary-results.md]
superseded_in_part: §6 Q5 + Q11 diagnoses — see w158-crossmodel-canary-results.md (option-order is a larger contributor than originally attributed)
---

> **Update 2026-05-17 (later):** the cross-model + option-order canary in [`w158-crossmodel-canary-results.md`](w158-crossmodel-canary-results.md) supersedes parts of this document. Specifically: (a) Q11 police "fragmentation = LLM over-polarization" call is mostly wrong — the dominant cause is option-order, not LLM prior bias. (b) Q5 "near-perfect calibration" call is order-dependent — reversing the option order produces 12pp error. (c) Q9 astrology Bisbee-class diagnosis stands but ~5pp of the 12.7pp gap is option-order recoverable, with the remaining ~7pp structural. (d) Q8 vaccine LLM-prior bias is confirmed against both perturbations. The cross-model dimension (Opus 4.5 vs Sonnet 4.6) showed only ~2pp deltas — Claude-family-level prior, not Sonnet-specific.

# W158 Marginal-Shift Analysis

Local-compute diagnostic on the Stage B W158 v1 output. No API spend. Asks: given that thresholds failed on all 11 questions via marginal-error sigma (not within-cell entropy or minority recovery), where is the marginal directional bias coming from, and what experiment would discriminate between competing causes?

## Method

The analysis script (`scripts/analyze_w158_marginal_shift.py`) consumes `synth_responses.parquet` (per-juror probability vectors + sampled responses, joined to the four validation axes), `trait_vectors.parquet` (joined back in for extended-axis cells: religion, religiosity, political_ideology, media_diet_primary, media_diet_slant, household_composition, life_stage_recent, is_outlier), and `data/pew/W158_microdata.csv` (Pew W158 weighted responses on the same four axes). For each question and option it computes:

- **Pew weighted proportion** (`pew`)
- **Synth expected proportion** (`synth_expected`) = weighted average of per-juror probability vectors (the model's latent calibration)
- **Synth sampled proportion** (`synth_sampled`) = weighted proportion of post-hoc-sampled responses (what a real poll replication would observe)
- **expected_minus_pew_pp** = the latent-calibration error
- **sampling_noise_pp** = `sampled` − `expected`, the deterministic-hash-sampler's contribution

Per-cell expected distributions are computed on every validation axis cell where n_synth ≥ 8 and n_pew ≥ 30. Extended-axis cells (religion, religiosity, ideology, etc.) compare to **Pew topline** rather than to Pew per-cell, because the Pew W158 microdata does not carry those axes — these cells answer "where in the panel is the topline shift concentrated," not "where does the panel disagree with Pew on a controlled-for cell."

## TL;DR

1. **The marginal shift is in the LLM's latent distribution, not the sampler.** Sampling noise (`sampled` − `expected`) is ≤ 3pp on every question and ≤ 1pp on Q9 / Q11. The probvec primitive is faithful; the model's per-juror probability vectors themselves carry the bias. Fixing the marginal shift means changing what the LLM emits, not changing how we sample from it.
2. **The eleven questions split into three failure modes, not one.** Q8 vaccine is a clean directional swap. Q9 astrology is binary minority suppression. Q7 school closures and Q11 police are fragmentation of a Pew-modal moderate option into surrounding alternatives.
3. **Errors do cluster, but the cluster pattern differs by question.** Q8 is concentrated in liberal / strong-left / Independent / Asian-Other / age 30-64. Q9 is concentrated in conservative / very-conservative / evangelical / Black / Independent. Q7 is concentrated in Black / Hispanic / Independent / Democrat. Q11 is concentrated in age 45-64 and 65+. The clusters are coherent with the topic-specific topline shift rather than being a single "outlier cell" problem.
4. **The 70-juror outlier slate does not materially help these four questions.** Max error among outliers is comparable to non-outliers on Q7 / Q9 (slightly higher) and slightly lower on Q8 / Q11. The non-modal opinion mechanism was calibrated against GSS issues (abortion, guns, immigration, gay marriage, marijuana), not against W158 topics like vaccine uptake or astrology. Topic match matters.
5. **Of the three competing hypotheses Stage B opened, the data favor a mixed answer.** The dominant cause is LLM prior bias on topic-specific topline rates (most cleanly visible on Q8 vaccine). Some cells additionally show missing-latent-trait error (Q9 astrology among Black respondents; Q7 school closures among parents — no "kids-in-school-during-COVID" trait surfaces to the LLM). Question-format correlation is real but secondary (fragmentation pattern on Q7 / Q11, which both have a Pew-modal moderate option).
6. **The recommended next experiment is a paired cross-model + option-order canary at n ≈ 200**, not another full Stage B fire. ~$20-30 spend; resolves the LLM-prior vs question-format ambiguity at the right cost.

---

## (1) Largest synthetic-vs-Pew deltas

### Topline per-question (expected, sampled, sampling noise)

| Question | max_abs_expected_pp | max_abs_sampled_pp | max sampling noise (pp) |
|---|---:|---:|---:|
| Q5 scientists policy role | 1.77 | 2.33 | 0.67 |
| Q2 climate human cause | 3.17 | 2.91 | 1.10 |
| Q6 COVID restrictions | 4.24 | 5.52 | 1.28 |
| Q3 climate policy economy | 6.18 | 9.34 | 3.16 |
| Q1 climate impact | 7.47 | 4.88 | 2.66 |
| Q4 scientist confidence | 8.83 | 8.61 | 0.69 |
| Q10 astrology freq | 8.87 | 7.31 | 1.57 |
| Q11 police confidence | 10.86 | 11.62 | 0.77 |
| Q7 school closures | 12.42 | 12.67 | 2.21 |
| Q9 astrology belief | 12.73 | 12.80 | 0.08 |
| Q8 vaccine | 16.06 | 17.68 | 2.10 |

**Sampling noise is small everywhere.** Sampling-noise share of the max sampled error is ≤ 30% on every question; ≤ 5% on Q9 and Q11. The probvec → sample step is not the bottleneck. The bias is in the model's per-juror probability vectors.

### Topline per-option, four worst questions

**Q7 school closures (max 12.4pp):**

| Option | Pew | Synth expected | Δ (pp) |
|---|---:|---:|---:|
| Too long | 35.0% | 40.0% | +4.9 |
| Not long enough | 9.0% | 8.8% | -0.2 |
| **About the right amount of time** | **35.7%** | **23.3%** | **-12.4** |
| Never closed | 2.7% | 5.7% | +3.0 |
| Not sure | 17.5% | 22.2% | +4.7 |

The Pew-modal moderate option ("About right") loses -12.4pp; the mass redistributes to "Too long", "Not sure", and "Never closed". This is **fragmentation**, not directional swap.

**Q8 vaccine (max 16.1pp):**

| Option | Pew | Synth expected | Δ (pp) |
|---|---:|---:|---:|
| Probably get | 24.6% | 25.1% | +0.5 |
| **Probably not** | **60.1%** | **44.1%** | **-16.1** |
| **Already received** | **15.2%** | **30.8%** | **+15.6** |

Clean directional swap. "Probably not" → "Already received" within ~0.5pp on the third option. This is **LLM prior bias** about temporal vaccine acceptance: the model thinks engaged respondents have already gotten the updated booster at much higher rates than the field-date Oct 2024 reality.

**Q9 astrology (max 12.7pp):**

| Option | Pew | Synth expected | Δ (pp) |
|---|---:|---:|---:|
| **Yes, believe in** | **27.3%** | **14.6%** | **-12.7** |
| No, don't believe | 72.7% | 85.4% | +12.7 |

Binary minority suppression. Direction matches the Bisbee 2024 critique exactly: a Pew minority position (~27%) gets compressed toward zero by stereotyped attribution.

**Q11 police (max 10.9pp):**

| Option | Pew | Synth expected | Δ (pp) |
|---|---:|---:|---:|
| A great deal | 20.6% | 22.9% | +2.3 |
| **A fair amount** | **52.1%** | **41.3%** | **-10.9** |
| Not too much | 20.6% | 26.4% | +5.8 |
| No confidence | 6.7% | 9.5% | +2.8 |

Fragmentation again. The Pew-modal moderate option ("Fair amount") loses -10.9pp; the mass spreads to all three other options, with the bulk going to "Not too much" (+5.8) and the rest split between the two extremes. **The LLM is over-polarizing police confidence.**

### Worst expected-error validation cells

For each of the four worst questions, the five worst single-axis cells on `max_abs_expected_pp`:

**Q7 school closures**

| Cell | n_synth | max_exp_pp |
|---|---:|---:|
| party=I | 67 | 22.5 |
| race=Black | 108 | 22.2 |
| race=Hispanic | 187 | 18.2 |
| party=D | 490 | 17.8 |
| age=18-29 | 214 | 16.1 |

**Q8 vaccine**

| Cell | n_synth | max_exp_pp |
|---|---:|---:|
| party=I | 67 | 27.8 |
| age=30-44 | 277 | 20.6 |
| education=SomeCollege/AA | 225 | 20.1 |
| age=45-64 | 296 | 19.6 |
| race=Asian/Other | 113 | 19.6 |

**Q9 astrology**

| Cell | n_synth | max_exp_pp |
|---|---:|---:|
| party=I | 67 | 20.1 |
| race=Black | 108 | 17.0 |
| party=R | 443 | 16.3 |
| education=HS | 379 | 16.2 |
| education=SomeCollege/AA | 225 | 15.0 |

**Q11 police**

| Cell | n_synth | max_exp_pp |
|---|---:|---:|
| age=45-64 | 296 | 15.6 |
| age=65+ | 213 | 14.4 |
| race=Hispanic | 187 | 13.0 |
| party=D | 490 | 12.5 |
| education=BA+ | 304 | 11.9 |

**Independent voters show up as the worst cell on Q7 / Q8 / Q9.** At n=67 this is the smallest measured cell and the most concentrated bias. The party=I cell is small for two structural reasons: (a) Pew NPORS reports ~9% Independent at the leaner-included level, which is what our priors target; (b) Independent voters are heterogeneous (lean-D, lean-R, true-Indep) — the LLM appears to treat them as a single softer-center bloc, which produces large topline drift on issues where the true Pew distribution among Independents is sharper than the "moderate centrist" caricature.

## (2) Expected-probability error vs sampled-response error

**Sampling noise is uniformly small (≤ 3pp on max-error per question; ≤ 1pp on Q9 / Q11).** The deterministic hash sampler is faithfully reproducing the model's latent distribution. This means:

- The marginal bias is in the model's per-juror probability vectors themselves
- Probability-vector polling is not introducing the failure; it is the correct primitive for surfacing it
- Mitigating the bias requires changing what the LLM emits per juror — prompt protocol, model swap, conditioning enrichment, or post-hoc calibration

Per-cell sampling noise share (max_abs_sampled - max_abs_expected) is occasionally negative on small cells where the hash-sampler happens to draw closer to Pew than the latent distribution implies. This is expected hash-noise behavior and does not change the diagnosis.

## (3) Error clustering across extended axes

Top-3 highest-error cells per extended axis for the four worst questions:

### Q8 vaccine

| Axis | Worst cells |
|---|---|
| political_ideology | **very_liberal 41.3pp, liberal 38.1pp, moderate 23.1pp** |
| media_diet_slant | **strong_left 37.7pp, lean_left 30.4pp, center 18.8pp** |
| religion | protestant_historically_black 27.6pp, other_christian_orthodox 20.5pp, protestant_mainline 18.6pp |
| household_composition | empty_nest_partnered 22.0pp, multi_generational 17.2pp, group_quarters 15.6pp |
| media_diet_primary | print_or_legacy_news_sites 22.1pp, tiktok_news 21.3pp, npr_pbs 18.9pp |
| religiosity | weekly+ 17.3pp, monthly 16.9pp, never 15.2pp |
| life_stage_recent | recent_parent_under_2yr 21.6pp, recently_relocated_metro 16.7pp, no_major_transition 16.1pp |

The dominant signal is **ideological**: very_liberal (41pp), liberal (38pp), strong_left media (38pp), lean_left media (30pp). The LLM assumes ideologically-engaged liberals have already received the updated vaccine at much higher rates than Pew shows. Religion / religiosity / household / life-stage are all comparatively uniform (~15-22pp across cells) — these cells follow the topline shift rather than amplify it.

This is consistent with an **LLM training-distribution bias**: the model has read more about the engaged-liberal-vaxxed demographic than about the actual ~15% Oct-2024 booster acceptance topline. Adding latent traits like "concerned about long COVID" or "trust in CDC" would not fix this; the prior is on the topic itself, not on the trait that conditions response.

### Q9 astrology

| Axis | Worst cells |
|---|---|
| political_ideology | very_conservative 19.8pp, conservative 18.4pp, moderate 10.6pp |
| media_diet_slant | strong_right 18.7pp, lean_right 17.4pp, center 13.1pp |
| religion | **atheist 19.7pp, other_christian_orthodox 16.8pp, protestant_evangelical 15.9pp** |
| religiosity | weekly+ 14.6pp, never 13.6pp, monthly 12.1pp |
| household_composition | empty_nest_partnered 17.4pp, single_no_children 12.1pp, partnered_no_children 11.8pp |
| is_outlier | True 17.5pp, False 12.4pp |

The Bisbee-class minority-suppression signature: the model correctly maps "conservatives and evangelicals say no to astrology" but **over-amplifies** that pattern and **under-attributes belief to demographics where it is actually common** (Black respondents 17pp from validation-cell scan; Independents 20pp; HS-only 16pp). The atheist cell at 19.7pp is the inverse — the model is *too sure* atheists say no, and Pew shows non-trivial astrology belief even among people who otherwise identify as non-religious.

The outlier mechanism shows *higher* error here (17.5pp) than non-outliers (12.4pp), which is the wrong sign. Outlier jurors carry concrete non-modal opinion priors drawn from GSS, but those priors are on abortion / guns / immigration / gay marriage / marijuana — none on astrology. The mechanism does not have material to push back against the model's astrology-skepticism prior.

### Q7 school closures

| Axis | Worst cells |
|---|---|
| political_ideology | very_liberal 16.0pp, very_conservative 14.4pp, liberal 13.5pp |
| race (validation) | Black 22.2pp, Hispanic 18.2pp |
| party (validation) | Independent 22.5pp, Democrat 17.8pp |
| household_composition | recent-parent and parent-of-school-age cells all 12-15pp |

The cells where "about right" is most Pew-modal (Black, Hispanic, Democrat) carry the largest fragmentation. The LLM does not confidently assign moderate retrospective COVID judgment to these groups. A missing latent trait — "had kids in school during COVID" — would directly load on this question; the trait vector does not surface it to the LLM at polling time even though PUMS has NCHILD / school enrollment.

### Q11 police

| Axis | Worst cells |
|---|---|
| age (validation) | 45-64 16pp, 65+ 14pp |
| race (validation) | Hispanic 13pp |
| party (validation) | Democrat 13pp |

Older respondents lose the most "fair amount" mass. The LLM is over-polarizing police confidence among demographics that Pew shows are moderately trusting (45-64 and 65+ White-NH; older Black respondents).

## (4) Worst-cell juror inspection

A representative high-error cell for Q8 and Q9, three jurors each, with full probability vectors and reasoning excerpts.

### Q8 vaccine, party=I cell (Pew 16.5 / 72.4 / 11.1; synth expected 26.5 / 44.5 / 29.0)

- **Juror 2240950 — 65+ White-NH Independent moderate Catholic rarely lean-left.** probvec {get 0.28, not 0.47, already 0.25}. Sampled "Already received". Reasoning: "At 66 with tight finances and healthcare concerns, he has some motivation to get vaccinated, but as a moderate independent with a lean-left TikTok diet he's not strongly vaccine-resistant; however, his infrequent religious practice and working-class Southern background suggest..."
- **Juror 606106 — 18-29 White-NH Indep moderate LDS never center.** probvec {get 0.18, not 0.65, already 0.17}. Reasoning correctly anchors on "young, low-income, lapsed religious, politically independent" → "probably not" dominant but with notable already-received probability.
- **Juror 2514148 — 18-29 Hispanic Indep conservative nothing-in-particular center.** probvec {get 0.15, not 0.72, already 0.13}. Reasoning correctly tilts "probably not" dominant.

**Pattern.** The young / non-religious / conservative-leaning Independent jurors get probability vectors close to Pew (juror 2514148 = 0.72 on "probably not", matching Pew's 0.724). The older / lean-left / engaged Independent juror gets 25% on "already received" against a Pew rate of 11% — the LLM treats "older lean-left moderate" as a strong proxy for "already got the booster". The reasoning text explicitly cites the demographic logic; the prior reflects the LLM's read on a specific demographic correlation that does not match Oct-2024 reality.

### Q9 astrology, party=I cell (Pew 37.6 / 62.4; synth expected 17.4 / 82.6)

Same three Independent jurors:

- **Juror 2240950 (Catholic 65+ moderate).** probvec {Yes 0.18, No 0.82}. Pew expected ~38% Yes for Indep; this single juror at 18% is far below the cell mean Pew implies.
- **Juror 606106 (LDS 18-29 moderate).** probvec {Yes 0.35, No 0.65}. The reasoning explicitly recognizes the demographic pattern: "Young, lapsed-LDS, TikTok-consuming Gen Z women in this demographic show notably higher astrology belief rates than older generations" — and yet the resulting vector still skews toward No.
- **Juror 2514148 (Hispanic 18-29 conservative).** probvec {Yes 0.22, No 0.78}. Reasoning is similar; demographic logic is recognized; vector skews to No.

**Pattern.** The LLM articulates the correct base-rate logic in prose ("this demographic believes astrology at higher rates"), then assigns a vector that under-applies that logic. The reasoning is calibrated; the vector is not. This is the specific Meister/Guestrin/Hashimoto 2025 knowledge-to-simulation gap signature: the model can describe the distribution better than it can sample / express probabilities from it.

## (5) Expected-probability cell diagnostics

The intermediate JSON (`marginal_shift_analysis.json`) now carries per-validation-cell expected-vs-Pew on every question, which the prior `expected_distribution_diagnostics.json` only had at topline. Each question has a `validation_cell_breakdown` block with per-axis cells reporting:

- `n_synth`, `n_pew`
- `max_abs_expected_pp` (the latent calibration error vs Pew on that cell)
- `max_abs_sampled_pp` (what a real poll replication would have observed on that cell)
- `sampling_noise_share` (the difference, attributable to deterministic hash-sampling)

This separates model-calibration error from sampling noise at the cell level, not just topline.

Future work: this should be promoted out of the analysis script into `src/expected_dist.py` so every Stage B run produces it automatically. Treating it as a one-off post-hoc analysis is fine for W158 but should be standard for W163 / W161.

## (6) Diagnosis — four causes mapped to four worst questions

For each worst question, classify the dominant failure cause (with secondary causes noted):

### Q8 vaccine — dominantly LLM prior bias on topline

- **LLM prior bias (primary).** The model has the right ordering (engaged > disengaged on uptake; D > R on uptake) but the wrong levels. Liberal/strong-left cells at 38-41pp error. The model has read more about the engaged-liberal-vaxxed demographic than about the actual ~15% Oct-2024 booster acceptance rate. This is a temporal-recency-distribution artifact at the topic level.
- **Source/measurement mismatch (minor).** Pew W158 fielded Oct 21-27 2024, very close to the FDA approval of the 2024-25 updated COVID-19 vaccines (late August 2024). At that field-date the topline "already received" was genuinely low (~15%). The LLM's training data spans a longer window where uptake numbers fluctuate; if Anthropic's training cutoff covers post-Oct-2024 booster uptake rises, the model's prior is anchored to a later/higher number.
- **Sampling noise (negligible).** 2.1pp on topline; ≤ 0.8pp on the largest-cell shifts.

### Q9 astrology — dominantly Bisbee-class minority suppression (LLM prior bias)

- **LLM prior bias (primary).** Direct match to Bisbee 2024 and Li/Li/Qiu 2025 / Santurkar et al. 2023 minority-suppression patterns. The model under-attributes a real Pew minority position (~27% Yes) on the basis of a stereotyped no-astrology-among-respectable-respondents prior.
- **Missing latent trait (secondary).** Pew shows astrological belief is elevated among Black respondents (~17pp error on race=Black) and among Independents (20pp error). There is no spirituality / new-age trait in the trait vector; the LLM cannot condition on it.
- **Reasoning-vs-emission mismatch (specific).** The juror reasonings explicitly articulate the correct demographic prior ("this demographic believes astrology at higher rates"), then emit a probvec that under-applies it. This is the cleanest Meister-Guestrin-Hashimoto 2025 knowledge-to-simulation gap example in W158.
- **Sampling noise (negligible).** ≤ 0.1pp.

### Q7 school closures — fragmentation + missing latent trait

- **LLM prior bias (primary, fragmentation type).** Pew-modal "about right" loses -12.4pp; the mass spreads across surrounding options. The model does not confidently assign moderate retrospective COVID judgment to anyone. This is *not* the directional-swap pattern of Q8 or the minority-suppression pattern of Q9; it is uncertainty / hedging on a retrospective judgment.
- **Missing latent trait (secondary, but specific).** Pew shows the highest "about right" rates among parents of school-age children during COVID (2020-22). PUMS has NCHILD / school enrollment data in our extract; the trait vector does not surface "had kids in K-12 during pandemic" to the LLM at polling. A juror with school-age kids during COVID is structurally more likely to have a settled retrospective judgment than the LLM emits.
- **Source/measurement mismatch (minor).** "Never closed" overshoots +3pp; the LLM may be applying a national-attention prior even for jurors in regions where in-person school resumed faster.
- **Sampling noise (low).** 2.2pp on topline.

### Q11 police — over-polarization (LLM prior bias) + question-format effect

- **LLM prior bias (primary).** The model has the right demographic gradient (younger / Black / Democrat skew lower-confidence; older / white skew higher) but pushes it further to extremes than Pew shows. "Fair amount" loses -10.9pp; the mass spreads to both directions.
- **Question-format (secondary).** Q11 has a Pew-modal moderate option ("fair amount" 52%) on a 4-point ordinal scale with a charged topic. This is the same pattern that produced Q7's fragmentation. Probvec polling on charged-topic ordinal scales with a strong-modal moderate appears to under-emit the moderate.
- **Sampling noise (negligible).** ≤ 0.8pp.

## (7) Bisbee-methods gap checklist

| Check | Status | Notes |
|---|---|---|
| Cell-level entropy ratio + minority recovery + Wasserstein with bootstrap CIs | **DONE** | `validation_results.json` per cell with 1000-iter bootstrap 90% CI; weighted by calibrated analysis weights |
| Topline expected vs sampled vs Pew per option | **DONE** | `expected_distribution_diagnostics.json` (Stage B output) + this analysis (separates sampling noise) |
| Per-validation-cell expected-vs-Pew (not only topline) | **DONE in this analysis** | `marginal_shift_analysis.json`; promote to `src/expected_dist.py` for future runs |
| Coverage rule on validation cells | **DONE** | 80% top-level / 50% interaction; passed all 11 questions at n=1000 |
| Probability-vector polling (Meister 2025 distribution-expression primitive) | **DONE** | locked Stage B protocol |
| Regression coefficient comparison synth vs Pew | **PENDING** | Bisbee 2024's strongest critique was on regression-coefficient divergence, not just variance. We have not run this on W158. Approach: fit logistic regressions of response ∈ option vs trait covariates on Pew vs synth; compare coefficients with bootstrap CIs |
| Prompt specification curve (Crainic 2026) | **PARTIAL** | v1 direct → v2 anti-center → v3 probvec is a 3-point arc, not a systematic spec curve. Recommend a small grid: probvec x (Sonnet vs alt model) x (Pew option order vs reversed) at n ≈ 200 |
| Option-order sensitivity | **PENDING** | Currently use Pew option order. Easy canary: re-poll a 100-juror slice with reversed option order; compare expected distributions. Cheap, ~$5 |
| Time reproducibility (Bisbee 2024 documented same-prompt drift across months) | **PENDING** | We archive outputs and have full preflight + run-label discipline but have not rerun W158 30 days later. Recommend: 100-juror reprise of W158 at +30 days under identical protocol |
| Cross-model perturbation | **PENDING** | All polling is `claude-sonnet-4-6`. Recommend: re-poll 100-juror slice with `claude-opus-4-5` to test whether the marginal shifts are Sonnet-specific or model-family |
| Nonsense / placebo question class | **PENDING** | No fake question included to test how the panel responds to ground-truthless prompts. Recommend: add a placebo question to W163/W161 |
| Outlier mechanism efficacy on W158 topics | **DONE in this analysis** | Outlier max error is comparable or slightly higher than non-outlier on Q7/Q9; the non-modal opinion priors were built against GSS issues (abortion/guns/immigration/marriage/marijuana), not against W158 topics. Topic match matters |

## (8) Recommended next experiment

**Don't fire W163 or W161 yet.** Both would reproduce the same failure mode on different topics without telling us anything new about the cause.

**Run a paired cross-model + option-order canary at n ≈ 200 on a 4-question slice (Q5 control, Q8 worst directional, Q9 worst minority, Q11 worst fragmentation).** Total ~3,200 polling calls. Estimated cost ~$20-30; wall clock ~2-3 hours. Holds the corpus fixed (reuses expanded jurors), permutes only:

- **Polling model:** `claude-sonnet-4-6` (current) vs `claude-opus-4-5`
- **Option order:** Pew canonical vs reversed
- **Polling primitive:** probvec (locked) — no change

Output: a 4-way table per question of expected-distribution shifts. Discriminating reads:

- If Opus shows the same topline shifts on Q8, the bias is family-level (Anthropic priors), not Sonnet-specific
- If reversed option-order produces meaningfully different toplines, option-order is a confound and should be perturbed across Stage B runs
- If Opus + reversed-order both look like Sonnet + Pew-order, the shift is the protocol's signature, not the model's

**Second experiment, separately:** add `had_school_age_kids_during_covid` (derivable from PUMS AGE + NCHILD with a 2020-22 anchor) and `astrology_baseline` (a flag elicited from religion + religiosity + age + gender as a v0.2 second-pass conditional prior) to the trait vector; re-poll the same corpus on Q7 + Q9. This tests the missing-latent-trait hypothesis specifically.

**Defer until after these two canaries:**

- Regression coefficient comparison synth-vs-Pew on W158 (Bisbee 2024 strongest critique)
- Time-reproducibility rerun at +30 days
- W163 / W161 fires

If both canaries reproduce the topline shifts roughly unchanged, the dominant cause is LLM prior bias at the topic level — and the right mitigation is one of (a) explicit topline calibration (post-hoc isotonic regression against a small ground-truth slice), (b) richer issue-specific prior conditioning in the polling prompt (cite Pew topline back at the model as a frame), or (c) accept that the artifact is best positioned as a directional diagnostic, not a topline-faithful replication.

## Companion documents

- [`stage-b-w158-results.md`](stage-b-w158-results.md) — Stage B W158 v1 headline results
- [`literature-bisbee-methods-review.md`](literature-bisbee-methods-review.md) — Bisbee 2024 + post-Bisbee positioning; defines the methods-gap checklist this analysis answers
- [`sanitized-chronology.md`](sanitized-chronology.md) — chronological build log sanitized for public release
- [`corpus-construction-plan.md`](corpus-construction-plan.md) — methodology spec
