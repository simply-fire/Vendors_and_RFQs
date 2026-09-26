# Vendor RFQ Evaluator

A small Flask app that scores a vendor profile against a stored RFQ (Request
for Quotation) using an LLM, persists results, and shows a history of past
evaluations in the browser.

## Requirements

- Python 3.10+
- An OpenRouter API key — https://openrouter.ai/

## Setup

```bash
git clone <repo-url> vendor-rfq-app
cd vendor-rfq-app

python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

Copy the env template and add your OpenRouter key:

```bash
# Windows:
copy .env.example .env
# macOS / Linux:
cp .env.example .env
```

Edit `.env` so it contains:

```
OPENROUTER_API_KEY=sk-or-v1-...
```

The other variables in `.env.example` have working defaults; only
`OPENROUTER_API_KEY` needs a real value.

## Run

```bash
python app.py
```

Open `http://127.0.0.1:5000/` in a browser.

## Seed data

The three RFQs in `seed/rfqs.json` are loaded **automatically the first time
the app starts**. On startup `app.py` calls `init_db()` (creates tables if
missing) then `seed_rfqs()` (inserts RFQs from `seed/rfqs.json` only if the
`rfqs` table is empty). Re-running the app is safe — it never duplicates rows.

To force a re-seed, delete `app.db` and run again.

## Environment variables

All optional except `OPENROUTER_API_KEY`.

| Variable | Default | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | _(none — required)_ | Auth for the LLM call |
| `OPENROUTER_MODEL` | `z-ai/glm-5.3-flash` | OpenRouter model id |
| `OPENROUTER_TIMEOUT` | `60` | HTTP timeout in seconds |
| `DATABASE_PATH` | `app.db` | SQLite file location |
| `SEED_PATH` | `seed/rfqs.json` | RFQ seed file |
| `HOST` | `127.0.0.1` | Bind host for `python app.py` |
| `PORT` | `5000` | Bind port for `python app.py` |
| `LOG_LEVEL` | `INFO` | Python logging level |

## API

All API endpoints return JSON. Error responses look like
`{"error": "...", "detail": "..."}` with the appropriate HTTP status code.

- `GET /api/rfqs` — list RFQs for the dropdown.
- `POST /api/evaluate` — body `{rfq_id, vendor_text}`. Returns
  `{id, rfq_id, score, reasons: [{text, dimension}], gaps: [{text, dimension}]}`.
  Returns `400` for missing/empty fields or unknown `rfq_id`, `502` if the
  LLM cannot produce a valid result (one retry is attempted first).
- `GET /api/evaluations` — past evaluations, newest first.

## Project layout

```
app.py            Flask factory, startup hook (init_db + seed), error handlers
db.py             schema, seed loader, query functions
services.py       business logic (calls llm.py, persists via db.py)
routes.py         Flask blueprint at /api — thin request parsing only
llm.py            OpenRouter client, prompt builder, schema validation + retry
static/           single-page frontend (HTML, JS, CSS, no build step)
seed/rfqs.json    RFQ data — loaded automatically on first run
samples/          sample vendor profiles for testing
```

## Sample data

`samples/vendor-a.txt`, `vendor-b.txt`, `vendor-c.txt` are three vendor
profiles. Paste any of them into the textarea (or upload the file) and pick
an RFQ to see a real evaluation.
