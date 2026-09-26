import json
import os
import sqlite3

DB_PATH = os.environ.get("DATABASE_PATH", "app.db")
SEED_PATH = os.environ.get("SEED_PATH", "seed/rfqs.json")

SCHEMA = """
CREATE TABLE IF NOT EXISTS rfqs (
    id        TEXT PRIMARY KEY,
    title     TEXT NOT NULL,
    category  TEXT NOT NULL,
    quantity  TEXT NOT NULL,
    material  TEXT NOT NULL,
    delivery  TEXT NOT NULL,
    technical TEXT NOT NULL,
    mandatory TEXT NOT NULL,
    required  TEXT NOT NULL,
    preferred TEXT NOT NULL,
    raw_json  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evaluations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    rfq_id      TEXT NOT NULL,
    vendor_text TEXT NOT NULL,
    score       INTEGER NOT NULL,
    reasons     TEXT NOT NULL,
    gaps        TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (rfq_id) REFERENCES rfqs(id)
);
"""


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def seed_rfqs():
    conn = get_connection()
    try:
        existing = conn.execute("SELECT COUNT(*) FROM rfqs").fetchone()[0]
        if existing > 0:
            return False

        with open(SEED_PATH, "r", encoding="utf-8") as f:
            rfqs = json.load(f)

        rows = []
        for r in rfqs:
            rows.append((
                r["id"],
                r["title"],
                r["category"],
                r["quantity"],
                r["material"],
                r["delivery"],
                json.dumps(r.get("technical", [])),
                json.dumps(r.get("mandatory", [])),
                json.dumps(r.get("required", [])),
                json.dumps(r.get("preferred", [])),
                json.dumps(r),
            ))

        conn.executemany(
            """
            INSERT INTO rfqs (
                id, title, category, quantity, material, delivery,
                technical, mandatory, required, preferred, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
        return True
    finally:
        conn.close()


def rfq_exists(rfq_id):
    conn = get_connection()
    try:
        row = conn.execute("SELECT 1 FROM rfqs WHERE id = ?", (rfq_id,)).fetchone()
        return row is not None
    finally:
        conn.close()


def fetch_rfqs():
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, title FROM rfqs ORDER BY id"
        ).fetchall()
        return [{"id": r["id"], "title": r["title"]} for r in rows]
    finally:
        conn.close()


def fetch_rfq(rfq_id):
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM rfqs WHERE id = ?", (rfq_id,)).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "title": row["title"],
            "category": row["category"],
            "quantity": row["quantity"],
            "material": row["material"],
            "delivery": row["delivery"],
            "technical": json.loads(row["technical"]),
            "mandatory": json.loads(row["mandatory"]),
            "required": json.loads(row["required"]),
            "preferred": json.loads(row["preferred"]),
            "raw_json": json.loads(row["raw_json"]),
        }
    finally:
        conn.close()


def insert_evaluation(rfq_id, vendor_text, score, reasons, gaps):
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            INSERT INTO evaluations (rfq_id, vendor_text, score, reasons, gaps)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                rfq_id,
                vendor_text,
                score,
                json.dumps(reasons),
                json.dumps(gaps),
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def fetch_evaluations():
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, rfq_id, vendor_text, score, reasons, gaps, created_at
            FROM evaluations
            ORDER BY id DESC
            """
        ).fetchall()
        return [
            {
                "id": r["id"],
                "rfq_id": r["rfq_id"],
                "vendor_text": r["vendor_text"],
                "score": r["score"],
                "reasons": json.loads(r["reasons"]),
                "gaps": json.loads(r["gaps"]),
                "created_at": r["created_at"],
            }
            for r in rows
        ]
    finally:
        conn.close()
