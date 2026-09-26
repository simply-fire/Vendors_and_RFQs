# Implementation Plan

**Locked stack:** Python backend (Flask) serving a static HTML/JS single page · SQLite · OpenRouter `z-ai/glm-5.3-flash` via forced structured output, single call, single retry on malformed JSON, no fallback model (documented as next-48h item) · 3-layer separation: `routes.py` → `services.py` → `db.py` / `llm.py` · Rubric = RFQ's own `mandatory` / `technical` / `required` / `preferred` / `quantity`+`delivery` fields, with `mandatory` acting as a near-hard-gate.

---

## Commit 1 — Scaffold + seeded database

**Purpose:** Get a running skeleton with real data in it before any feature logic exists.

**Functionality:**
- Project structure, dependency file, env template
- SQLite schema creation on startup
- Seed loader: reads `seed/rfqs.json`, populates `rfqs` table with explicit columns (`id`, `title`, `category`, `quantity`, `material`, `delivery`) + JSON-serialized list columns (`technical`, `mandatory`, `required`, `preferred`) + `raw_json` backup column
- Idempotent seeding — only inserts if table is empty, so re-running the app never duplicates rows

**Files:** `app.py` (Flask factory + startup hook), `db.py` (schema + seed function), `.env.example`, `requirements.txt`, `.gitignore` (exclude the `.db` file and `.env`)

**Implementation details:**
- `rfqs` table matches the confirmed JSON shape exactly — no guessing needed anymore
- Seed function is a plain Python loop reading the JSON list, no framework needed

**Verify:** Run app once, inspect the SQLite file (`sqlite3 app.db "select id,title from rfqs;"`) — 3 rows, correct titles. Run app a second time, confirm still 3 rows (no duplication).

**Capability at this point:** Backend boots, DB is seeded correctly. No API, no UI yet.

**Commit message:** `Scaffold app structure and seed RFQ database from provided JSON`

---

## Commit 2 — API + persistence (LLM stubbed)

**Purpose:** Prove the full data path works before wiring in anything non-deterministic (the LLM call).

**Functionality:**
- `GET /api/rfqs` — list seeded RFQs (id + title, for the dropdown)
- `POST /api/evaluate` — accepts `{rfq_id, vendor_text}`, **returns a hardcoded fake score/reasons/gaps**, but writes the result to the `evaluations` table for real
- `GET /api/evaluations` — list past evaluations, most recent first
- `evaluations` table: `id, rfq_id, vendor_text, score, reasons (json list), gaps (json list), created_at`

**Files:** `routes.py` (Flask blueprint, thin — just request parsing + calling the service), `services.py` (`evaluate_vendor()` stub, `list_rfqs()`, `list_evaluations()`), `db.py` (add evaluations table + insert/select functions)

**Implementation details:**
- Routes never touch SQL directly — everything goes through `services.py` → `db.py`. This seam is what makes the live-modification interview easy later.
- Server-side validation now: reject if `rfq_id` doesn't exist or `vendor_text` is empty — return 400, not a crash.

**Verify:** `curl` all three endpoints manually. Confirm an evaluate call persists a row and shows up in the evaluations list, in the right order.

**Capability at this point:** Entire app skeleton works end-to-end with fake scoring — nothing left but swapping the stub for a real model call.

**Commit message:** `Add RFQ/evaluation API endpoints and persistence layer (LLM stubbed)`

---

## Commit 3 — Real LLM integration (rubric + structured output)

**Purpose:** Replace the stub with the actual scoring engine — this is the commit that matters most for BUILD_LOG's "scoring approach" question.

**Functionality:**
- `llm.py`: builds the prompt from an RFQ row (rendering `technical`/`mandatory`/`required`/`preferred` as labeled sections, `quantity`+`delivery` as a logistics line) + the raw vendor text
- Calls OpenRouter (`z-ai/glm-5.3-flash`) with a **forced JSON schema / tool-call** requiring: `score (int 0-100)`, exactly 3 `reasons`, exactly 2 `gaps`, each reason/gap tagged with which rubric dimension it came from
- System prompt explicitly instructs: missing an item in `mandatory` should cap the score low (e.g. ≤40) regardless of strength elsewhere — this is the hard-gate behavior discussed
- On schema validation failure: one retry with the same call; if that also fails, raise a typed error the service layer turns into a clean "evaluation failed" response (no framework-level retry loop)
- `services.evaluate_vendor()` now calls `llm.py` instead of returning the stub

**Files:** `llm.py` (new), `services.py` (wire in), `.env.example` (add `OPENROUTER_API_KEY`)

**Verify:** Run real evaluations for all combinations of the 3 sample vendor `.txt` files against their most relevant RFQ (and at least one deliberate mismatch, e.g. vendor-a against RFQ-002). Manually sanity-check: does a vendor missing a stated mandatory cert actually score low? Do reasons/gaps reference real content from the vendor text, not generic filler?

**Capability at this point:** Full scoring pipeline works correctly via API calls (no UI yet, but fully testable with curl/Postman).

**Commit message:** `Integrate GLM-5.3-Flash via OpenRouter with rubric-based structured scoring`

---

## Commit 4 — Single-page frontend

**Purpose:** Wire the working backend to the UI the spec actually asks for.

**Functionality:**
- One HTML page, plain JS (no build step), served as static files by Flask
- RFQ dropdown populated from `/api/rfqs`
- Vendor input: textarea (paste) + file input (reads `.txt` client-side via `FileReader`, populates the same textarea — one code path, not two)
- Submit → `POST /api/evaluate`, shows loading state, then renders score/reasons/gaps
- Past evaluations list below, populated from `/api/evaluations`, refreshed after each new submission
- Client-side validation mirroring the server's (no RFQ selected / empty text → disable submit, don't rely on the server alone)

**Files:** `static/index.html`, `static/app.js`, `static/style.css` (legible only, per spec — no design system needed), `app.py` (add static route/serving)

**Verify:** Full manual click-through in a browser: pick each RFQ, paste and upload each of the 3 sample vendor files, confirm results render, confirm history list updates and persists across a page refresh.

**Capability at this point:** Feature-complete per spec — this is a working submission if stopped here.

**Commit message:** `Build single-page UI for RFQ selection, vendor input, and evaluation history`

---

## Commit 5 — Hardening, README, BUILD_LOG, submission polish

**Purpose:** Turn a working app into a gradeable, README-followable, honestly-documented submission.

**Functionality:**
- Error handling pass: LLM/network failure surfaces a clear UI message, never a raw 500 or blank screen; malformed-JSON-after-retry case shows "evaluation failed, try again" instead of storing garbage
- `README.md`: setup steps, required env vars, how seed data loads (automatic on first run — call this out explicitly), how to run, written and then **tested against a literal clean clone**
- `BUILD_LOG.md` filled in completely:
  - Stack + one-line rationale per choice (this conversation's decisions, compressed)
  - Scoring approach: the rubric mapping to RFQ fields, and the mandatory-gate behavior
  - What was built / what was skipped (rate limiting, retries-with-backoff, auth, doc-parsing edge cases — all explicitly out of scope per spec)
  - Where the spec was unclear: **the RFQ field shape wasn't provided upfront** — solved by designing a generic-JSON-safe loader before seeing the file, then locking exact columns once it arrived
  - What broke: whatever surfaces during commit 3/4 testing — log it honestly rather than leaving this section thin
  - Working with AI: how the coding agent was used, one thing you personally caught/corrected, one thing you wrote yourself and why
  - Weakest part: name the actual file/function you're least comfortable defending (likely `llm.py`'s single-retry error path, or prompt robustness)
  - Next 48 hours: (a) fallback/backup model if GLM-5.3-Flash structured output proves unreliable in practice, (b) the deterministic-preprocessing option (Option C from the scoring discussion) layered alongside the LLM judgment for extra grounding

**Files:** `README.md`, `BUILD_LOG.md`, minor fixes across `llm.py`/`routes.py`/`app.js` as hardening surfaces issues

**Verify:** Fresh `git clone` into a new folder, follow only what the README says, confirm the app runs and seeds correctly with zero tribal knowledge.

**Capability at this point:** Complete, submission-ready prototype — 5 commits, working README, honest BUILD_LOG, secrets in env only.

**Commit message:** `Harden error handling and finalize README/BUILD_LOG for submission`