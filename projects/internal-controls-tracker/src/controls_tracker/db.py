"""SQLite storage and append-only audit records."""

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    kind TEXT NOT NULL CHECK(kind IN ('process','control')),
    id TEXT NOT NULL, version INTEGER NOT NULL CHECK(version > 0),
    payload TEXT NOT NULL, author TEXT NOT NULL, reason TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(kind,id,version)
);
CREATE TABLE IF NOT EXISTS populations (
    id TEXT PRIMARY KEY, control_id TEXT NOT NULL,
    control_version INTEGER NOT NULL, process_id TEXT NOT NULL,
    process_version INTEGER NOT NULL, period_start TEXT NOT NULL, period_end TEXT NOT NULL,
    source TEXT NOT NULL, reconciliation TEXT NOT NULL, payload TEXT NOT NULL,
    sha256 TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY, population_id TEXT NOT NULL REFERENCES populations(id),
    seed TEXT NOT NULL, size INTEGER NOT NULL CHECK(size > 0), rationale TEXT NOT NULL,
    tester TEXT NOT NULL, algorithm TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS selections (
    run_id INTEGER NOT NULL REFERENCES runs(id), item_id TEXT NOT NULL,
    rank INTEGER NOT NULL, PRIMARY KEY(run_id,item_id), UNIQUE(run_id,rank)
);
CREATE TABLE IF NOT EXISTS evidence (
    id INTEGER PRIMARY KEY, filename TEXT NOT NULL, content BLOB NOT NULL,
    sha256 TEXT NOT NULL, size_bytes INTEGER NOT NULL, actor TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS results (
    id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL, item_id TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK(outcome IN ('pass','exception')), notes TEXT NOT NULL,
    tester TEXT NOT NULL, evidence_id INTEGER NOT NULL REFERENCES evidence(id),
    created_at TEXT NOT NULL, UNIQUE(run_id,item_id),
    FOREIGN KEY(run_id,item_id) REFERENCES selections(run_id,item_id)
);
CREATE TABLE IF NOT EXISTS deficiencies (
    id INTEGER PRIMARY KEY, result_id INTEGER NOT NULL UNIQUE REFERENCES results(id),
    owner TEXT NOT NULL, due TEXT NOT NULL, action TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','closed')),
    resolution TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS requests (
    id TEXT PRIMARY KEY, control_id TEXT NOT NULL, description TEXT NOT NULL,
    owner TEXT NOT NULL, due TEXT NOT NULL, requested_by TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','received','fulfilled')),
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS request_evidence (
    request_id TEXT NOT NULL REFERENCES requests(id),
    evidence_id INTEGER NOT NULL REFERENCES evidence(id),
    PRIMARY KEY(request_id,evidence_id)
);
CREATE TABLE IF NOT EXISTS followups (
    id INTEGER PRIMARY KEY, request_id TEXT NOT NULL REFERENCES requests(id),
    description TEXT NOT NULL, owner TEXT NOT NULL, due TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','resolved')),
    resolution TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY, entity TEXT NOT NULL, entity_id TEXT NOT NULL,
    action TEXT NOT NULL, actor TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL
);
"""

TABLES = (
    "documents",
    "populations",
    "runs",
    "selections",
    "results",
    "evidence",
    "deficiencies",
    "requests",
    "request_evidence",
    "followups",
    "events",
)
IMMUTABLE = (
    "documents",
    "populations",
    "runs",
    "selections",
    "results",
    "evidence",
    "request_evidence",
    "events",
)


def connect(path):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    if db.execute("PRAGMA user_version").fetchone()[0] not in (0, 1):
        db.close()
        raise ValueError("Unsupported database schema version")
    db.executescript(SCHEMA)
    for table in IMMUTABLE:
        for operation in ("UPDATE", "DELETE"):
            db.execute(f"""CREATE TRIGGER IF NOT EXISTS {table}_{operation.lower()}_blocked
                BEFORE {operation} ON {table} BEGIN
                SELECT RAISE(ABORT, 'audit record is append-only'); END""")
    db.execute("PRAGMA user_version=1")
    db.commit()
    return db
