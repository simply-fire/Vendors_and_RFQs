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
