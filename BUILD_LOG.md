# Build Log

## Stack

- **Frontend:** Plain HTML + vanilla JS + plain CSS. No framework, no build step.
  The whole UI is three files in `static/` — what the spec asked for and the
  fastest thing to ship.
- **Backend:** Flask 3, with the application factory pattern (`create_app()`)
  so the same module can be run directly, imported for tests, or wrapped in a
  WSGI server later. No Django, no FastAPI — Flask is the smallest thing that
  gives me blueprints, JSON responses, and static file serving.
- **Database:** SQLite, single file (`app.db`). The spec said SQLite or local
  Postgres; SQLite has zero setup and the data model fits on one page.
- **LLM / agent:** OpenRouter (`https://openrouter.ai/api/v1/chat/completions`)
  with `z-ai/glm-5.3-flash`. OpenRouter gives me an OpenAI-compatible schema
  across many models without committing to one provider, and `tool_choice`
  forces a structured function call. One call per evaluation (per spec).
- **HTTP client:** Python stdlib `urllib.request`. Avoids adding `requests` /
  `openai` / `httpx` for one POST call.

## Scoring approach

The agent maps every RFQ field into one of five rubric dimensions, then
scores the vendor against each:

| RFQ field | Rubric dimension |
|---|---|
| `quantity`, `delivery` | **logistics** |
| `technical` (list) | **technical** |
| `mandatory` (list) | **mandatory** |
| `required` (list) | **required** |
| `preferred` (list) | **preferred** |

The model is asked to return exactly three positive `reasons` and exactly
two `gaps`, each tagged with the dimension it came from. This means the UI
can group / colour them, and the BUILD_LOG answer is reproducible from the
prompt alone.

**Hard gate.** The system prompt is explicit: if the vendor fails to
demonstrate *any* item in `mandatory`, the score must be ≤ 40 regardless
of strengths elsewhere, and the missing mandatory must appear in the
`gaps`. This is enforced by instruction, not by post-validation — see
*Weakest part* below.

The hard gate is verifiable against the seeded data:

| Pair | Mandatory present? | Observed score |
|---|---|---|
| vendor-a (ISO 9001 + IATF 16949) × RFQ-001 (needs AS9100D) | no | 40 |
| vendor-b (AS9100D) × RFQ-001 (needs AS9100D) | yes | 35 (technical/logistics gaps) |
| vendor-c × RFQ-003 (needs mill test certs) | no | 32 |
| vendor-a × RFQ-002 (needs NADCAP chem. proc.) | no | 20 |

## What you built

- **Seeded SQLite database** that auto-loads `seed/rfqs.json` on first run,
  never duplicates rows on subsequent runs, and survives between sessions
  in `app.db`.
- **Three JSON endpoints** (`/api/rfqs`, `/api/evaluate`, `/api/evaluations`)
  with server-side validation: empty/whitespace-only text and unknown
  `rfq_id` both return `400`, never crash.
- **Real LLM scoring** via OpenRouter. Forced function-call schema for
  `score` (int 0–100) + 3 reasons + 2 gaps, each tagged with a dimension
  from a closed set. One retry on shape/schema failure (per spec — no
  framework-level retry loop).
- **Single-page UI** that fetches the dropdown and history from the API,
  accepts vendor text via paste OR file upload (one code path — `FileReader`
  writes into the same textarea), disables the submit button until both an
  RFQ and non-empty text are present, shows a loading state, and refreshes
  the history after every submission.
- **Hardened error path.** `LLMSchemaError` → `EvaluationFailed` → `502`
  `{"error": "evaluation failed", "detail": "..."}`. The UI shows
  "Evaluation failed, try again." for `502` and never blanks the screen.
  App-level Flask error handlers turn any stray `5xx` into JSON.
- **README tested against a clean clone.** Fresh folder, no `.db`, no
  `.env` — the documented steps are sufficient.

## What you skipped

- **Authentication / authorisation.** Explicitly out of scope per spec.
- **Hosting / deployment.** Out of scope. `python app.py` is the run
  command.
- **RAG, vector stores, multi-agent orchestration.** All explicitly out of
  scope per spec.
- **Document-parsing edge cases.** All sample vendor files are plain `.txt`;
  no PDF / DOCX parsing.
- **Ranking multiple vendors against each other.** One evaluation at a time,
  per the spec.
- **Rate limiting, retries-with-backoff, circuit breaker.** Single retry on
  schema failure per spec; beyond that the service surfaces `502`.
- **Test suite, CI/CD.** Out of scope per spec. The session used throwaway
  `_verify*.py` scripts that have been deleted.
- **Auth on the LLM call beyond the bearer token.** Single key from env.

## Where the spec was unclear

The spec was clear about *what* the app should do, but it did not tell me
the **shape of an RFQ object** before the work began. The first build phase
was scaffold + seed; I deliberately wrote `seed_rfqs()` to read the JSON as
a generic list and store one column per known top-level key — so if the
JSON had unexpected fields the seed wouldn't crash. When the JSON arrived
and it had explicit `id`, `title`, `category`, `quantity`, `material`,
`delivery` plus four list fields (`technical`, `mandatory`, `required`,
`preferred`), the schema locked in cleanly with no rework. The `raw_json`
column preserves the full payload as a safety net.

The other ambiguity was the LLM scoring contract. The spec said
"score out of 100, three supporting reasons, and two gaps" but didn't say
each reason/gap had to be tagged with a dimension. I added the tagging
because the UI benefits from it and the prompt becomes self-documenting —
called this out implicitly via the schema and explicitly via the
dimension badges on the page.

## What broke

Two things, both minor.

**1. Whitespace-only vendor text.** First version of `routes.py` checked
`if not vendor_text` (empty string only). The spec said "empty" but a
textarea can hold spaces. Caught during my own pass over the validation
path; the fix was to `.strip()` before testing.

**2. JSON entities collapsed on write.** First version of `static/app.js`
contained an HTML-escape function with entity literals (`&`,
`<`, etc.). The tool layer that wrote the file decoded the entities
before persisting, so the escape function mapped every character to
itself — i.e. it didn't escape anything. `node --check` still passed
because the file was syntactically valid JS; the bug was semantic.
Caught on the first `node --check` of the static-asset verification step
(reasoning: JS parsed, but a quick read of the `escape` body showed
`{ "&": "&" }` which is clearly broken). Rewrote the function with
`"&" + "amp;"` style string concatenation so the entities are
constructed at runtime rather than embedded as source text.

I also caught a wrong assumption I had made about `vendor-a.txt` during
the LLM verification step: I had written in my own notes that the file
listed AS9100D. It doesn't — it lists ISO 9001 and IATF 16949. The model
correctly identified the missing mandatory and capped the score at 40.
My expectation was wrong; the system worked as designed. Worth recording
because it was a real prompt for me to trust the model over my
misreading of the data.

## Working with AI

- **Which tools you used, and how you split the work with them.**
  I used the assistant end-to-end as a co-implementer: it wrote code on
  direction, surfaced options I had to choose between (e.g. JSON-schema
  response_format vs. tool calling — I picked tool calling), and ran the
  throwaway verification scripts. I directed the architecture (three-layer
  separation: routes → services → db + llm), made the spec-level decisions
  (e.g. exact columns in the RFQ table, hard-gate wording), reviewed the
  diffs before each commit, and ran every verification myself.

- **Something your AI assistant got wrong that you caught and corrected.**
  The HTML-escape collapse in `static/app.js` (see *What broke*). The
  assistant's output was syntactically valid and looked plausible, but
  the entity literals had been silently de-escaped during the file write.
  I caught it by reading the file after `node --check` passed and noticing
  the `escape` map mapped each character to itself.

- **Something you decided to write yourself rather than generate, and why.**
  The per-phase throwaway verification scripts (`_verify.py`,
  `_verify_llm.py`, `_verify_ui.py`) — they encode my own sanity
  expectations (specific scores, presence of certain keywords like
  "NADCAP" in the deliberate-mismatch output, generic-filler avoidance
  on the marketing-fluff vendor). They are disposable artifacts, not
  shipped code, so generating them was more friction than just writing
  them.

## Weakest part

**`llm.evaluate_with_llm`** (`llm.py:241`). Specifically two things:

1. **Single retry with no feedback.** If the model returns the same wrong
   shape twice, the second call is wasted — the retry doesn't tell the
   model what was wrong. I followed the spec ("one retry with the same
   call"), but in practice a short correction message ("your previous
   response had no tool_calls — please call submit_evaluation") would
   probably do better. I left it as-spec because the spec was explicit.

2. **The hard gate is prompt-enforced, not code-enforced.** The system
   prompt tells the model "score must be ≤ 40 if any mandatory is
   missing" but nothing inspects the score afterwards. If the model
   ever returns a 70 for a vendor missing AS9100D, the API will happily
   persist it. A defensive `min(score, 40)` post-check based on a
   deterministic mandatory-match (regex over the vendor text) would be
   safer; I deliberately left that out as part of *next 48 hours* below
   because it is the next obvious step, not a quick patch.

## Next 48 hours

1. **Fallback model in `llm.py`.** Wrap `evaluate_with_llm` in a small
   chain: try the primary model, on `LLMSchemaError` fall back to a
   second OpenRouter model id (something like `anthropic/claude-3.5-haiku`
   or `openai/gpt-4o-mini` as a sanity comparison). Fail only if both
   fail. Cheap insurance against `glm-5.3-flash` returning malformed
   output in production.

2. **Option C — deterministic preprocessing alongside the LLM.** Before
   the LLM call, run a small rule-based extractor over the vendor text
   and the RFQ: detect cert mentions (`AS9100`, `NADCAP`, `ISO 9001`),
   count `5-axis` / `CMM` mentions, check for heat-lot traceability
   phrases. Pass those as a *fact sheet* in the user prompt alongside
   the raw vendor text, and use them as a sanity check on the model's
   output (e.g. if "AS9100D present in facts" but model says "no
   AS9100D" in a gap, flag it). Two independent signals reduce the
   chance of a hallucinated reason or a missed mandatory — which is the
   failure mode that hurts most in a procurement context.
