# Scoring Mechanism — Current Implementation vs. Long-Term Ideal

This document describes (1) the scoring mechanism actually built for the 2-hour
prototype, and (2) the mechanism we'd want if this were a real, ongoing system
rather than a case-study exercise. It's meant to sit alongside `BUILD_LOG.md`
and give a longer, standalone answer to "how does the score arrive at a number,
and what would we do differently with more time."

---

## Part 1 — Current Mechanism (as built)

### Summary

One LLM call per evaluation. The rubric is not a separate config — it *is*
the RFQ's own JSON structure. The model is instructed to reason against five
fixed dimensions derived directly from the RFQ fields, apply a hard gate on
mandatory requirements, and return a structured object we can render without
further interpretation.

### The five scoring dimensions

| # | Dimension | Sourced from RFQ field | Behavior |
|---|---|---|---|
| 1 | **Mandatory compliance** | `mandatory` | Hard gate. If the vendor profile doesn't clearly evidence a mandatory item (e.g. AS9100D, NADCAP), the score is capped low (≤40) regardless of strength elsewhere. |
| 2 | **Technical capability fit** | `technical` | Can the vendor actually meet the stated technical spec (tolerances, thickness range, process capability)? |
| 3 | **Process/documentation compliance** | `required` | Certs, test reports, traceability documentation — present or not, as stated in the vendor profile. |
| 4 | **Differentiators** | `preferred` | Nice-to-haves. Can only raise the score, never lower it if absent. |
| 5 | **Logistics fit** | `quantity` + `delivery` | Can the vendor plausibly meet volume/lead-time? Lowest-weighted dimension. |

### Prompt structure

- **System prompt** fixes the rubric, the gate rule, and the output contract
  (score 0–100, exactly 3 reasons, exactly 2 gaps, each tagged with the
  dimension it came from).
- **User content** = the RFQ rendered as labeled sections (title, category,
  quantity, material, delivery, then bulleted `technical` / `mandatory` /
  `required` / `preferred` lists) followed by the vendor profile as raw text.
- No retrieval, no multi-step tool use — the entire "agent" is one prompt in,
  one structured object out.

### Output contract (structured/tool-forced)

```json
{
  "score": 0-100,
  "reasons": [
    { "dimension": "mandatory | technical | required | preferred | logistics", "text": "..." },
    { "dimension": "...", "text": "..." },
    { "dimension": "...", "text": "..." }
  ],
  "gaps": [
    { "dimension": "...", "text": "..." },
    { "dimension": "...", "text": "..." }
  ]
}
```

Enforced via the model's native structured-output / tool-forced mechanism
(JSON schema), not prompted-and-hoped-for JSON. This removes an entire class
of parsing failures.

### Model and failure handling

- **Model:** `z-ai/glm-5.3-flash` via OpenRouter — chosen for cost, native
  structured-output support, and adequate reasoning quality for a
  rubric-following judgment task (see model comparison discussion for
  alternatives considered: DeepSeek V4.1 Flash, Gemini 3.1/3.5 Flash-Lite,
  Claude Haiku 4.5).
- **On schema validation failure:** exactly one retry with the same prompt.
  If the retry also fails, the service layer returns a clean "evaluation
  failed, try again" response — no framework-level retry loop, no silent
  storage of malformed data.
- **No fallback model** in this version. If GLM-5.3-Flash structured output
  is unreliable in practice, there is currently no automatic recovery beyond
  the single retry.

### What this mechanism deliberately does NOT do

- No deterministic keyword/regex pre-matching of certs or specs — out of
  scope per the assignment ("no RAG-like retrieval machinery"), and brittle
  for free-text input within the timebox.
- No multi-model ensembling or self-consistency sampling — one call, one
  answer, matching "one LLM call per evaluation."
- No persistence of *why* the model weighted things the way it did beyond
  the dimension tags on reasons/gaps — there's no confidence score, no
  raw model reasoning trace stored.
- No calibration against historical outcomes — the rubric is authored
  intuitively (mandatory > technical/required > preferred > logistics),
  not derived from data.

### Known weaknesses of the current mechanism

1. **Single point of failure per call.** One model, one provider, no
   fallback — a provider outage or a persistent malformed-output loop
   fails the evaluation with no recovery path other than manual retry.
2. **No consistency guarantee.** Running the same RFQ/vendor pair twice
   is not guaranteed to produce the same score — there's no temperature
   control documented, no self-consistency check, no variance measurement.
3. **Rubric weighting is implicit in prose**, not an explicit numeric
   formula — "cap at 40" is an instruction, not a computed constraint, so
   it's only as reliable as the model's instruction-following on that turn.
4. **No historical calibration.** Nothing ties a "73" on RFQ-001 to any
   ground truth about what a 73 should mean, or whether it's consistent
   with a "73" on RFQ-002.

---

## Part 2 — Ideal Long-Term Mechanism

If this were a production system rather than a 2-hour case study, the goal
would shift from "produce *a* defensible number" to "produce a number that's
**reproducible, calibrated, auditable, and resilient to model/provider
failure**." Below is what that looks like, roughly in the order it would
be built.

### 1. Hybrid scoring: deterministic gate + LLM judgment (two-stage)

Rather than asking one model call to both check mandatory compliance *and*
render a nuanced technical judgment, split the two:

- **Stage A — deterministic/structured extraction pass:** a cheap,
  low-temperature (or even non-LLM, rules-based) pass extracts explicit
  claims from the vendor profile against each `mandatory` and `required`
  item (e.g. "does the text contain evidence of AS9100D?" as a yes/no/unclear
  per item). This can still use an LLM, but as a narrow extraction task with
  a much smaller, more checkable output space than full scoring.
- **Stage B — LLM judgment pass:** given Stage A's extracted compliance
  facts (not the raw prompt asking the model to also decide compliance),
  the model reasons about technical/preferred/logistics fit and produces
  the narrative reasons/gaps.

This keeps the "no RAG, no multi-agent" spirit (it's still two narrow LLM
calls or one call plus one rules pass, not an orchestrated agent swarm) while
making the hard-gate behavior provable rather than instruction-dependent.

### 2. Explicit, versioned, numeric rubric

Move the rubric out of prose instructions and into a small config object:

```json
{
  "weights": { "mandatory": 0.40, "technical": 0.30, "required": 0.20, "preferred": 0.05, "logistics": 0.05 },
  "gate_rule": "any missing mandatory item caps total score at 40",
  "version": "rubric-v1"
}
```

Store this config's version alongside every evaluation row. This makes the
score auditable ("this vendor was scored under rubric-v1, here's exactly
what that weighted") and lets the rubric evolve without silently changing
the meaning of historical scores.

### 3. Consistency and confidence

- Run each evaluation N times (small N, e.g. 3) at low temperature and
  report the **median score plus a spread** (e.g. "78 ± 4") rather than a
  single point estimate, or at minimum log variance across repeated runs
  during a calibration period to know how noisy the current model/prompt
  combination actually is.
- Surface a **confidence flag** when reasons/gaps are thin, contradictory,
  or when the vendor text doesn't clearly address a mandatory item either
  way (as opposed to clearly failing it) — "insufficient evidence" is a
  different, useful signal from "fails requirement."

### 4. Model resilience

- **Primary + fallback model pair**, both required to honor the same
  structured-output contract, with automatic failover on repeated schema
  failures or provider errors (this was already flagged as the immediate
  next-48-hours item).
- **Provider-level retries with backoff** for transient failures, distinct
  from the schema-validation retry (these are different failure modes and
  arguably should be handled differently — one is "the network/provider
  hiccupped," the other is "the model didn't follow the contract").
- Periodic **shadow evaluation** against a second model to catch silent
  drift if the primary model is updated upstream (a risk specific to
  hosted/served models rather than self-hosted checkpoints).

### 5. Human-in-the-loop calibration

- A small set of vendor/RFQ pairs scored by a human evaluator, used as a
  **held-out calibration set** to check whether the model's scores track
  human judgment, and to catch cases where the model over- or
  under-weights a dimension relative to what a real procurement reviewer
  would.
- A feedback mechanism (even a simple "was this score reasonable?"
  thumbs-up/down on each evaluation) feeding into periodic rubric or
  prompt revisions — turning "we wrote a rubric once" into "the rubric is
  maintained against outcomes."

### 6. Auditability and traceability

- Store the **full prompt sent and raw model response**, not just the
  parsed score/reasons/gaps — essential for debugging disputes ("why did
  this vendor get a 60?") and for reproducing an evaluation exactly.
- Tie every stored evaluation to the **rubric version**, **model
  identifier**, and **model response** used, so a change in any of the
  three is traceable rather than silently baked into a bare number.

### 7. What stays out even in the long-term version

To be clear about scope discipline — even the "ideal" version above should
**not** grow into:
- Full RAG over a vendor knowledge base (this is single-document scoring,
  not corpus retrieval)
- Cross-vendor ranking/leaderboards (explicitly out of scope for this
  product's purpose — it's a single-vendor-against-one-RFQ tool)
- A general-purpose agent framework with autonomous tool use beyond the
  narrow extraction/judgment split above

The upgrade path is "make the existing single-purpose scoring mechanism more
reliable and auditable," not "turn it into a different, more complex kind of
system."

---

## One-paragraph summary (for BUILD_LOG or a verbal explanation)

*Right now, one LLM call applies a five-dimension rubric derived directly
from the RFQ's own JSON structure, with a hard gate on mandatory
requirements, forced structured output, and a single retry on malformed
JSON — deliberately simple, matching the "one LLM call per evaluation"
constraint. Long-term, the same rubric would be made explicit and versioned,
split into a deterministic compliance-extraction stage plus a judgment
stage, run with repeated sampling for a confidence measure, backed by a
fallback model for resilience, and calibrated against human-scored examples
over time — moving from "a defensible number" to "a reproducible,
auditable one."*