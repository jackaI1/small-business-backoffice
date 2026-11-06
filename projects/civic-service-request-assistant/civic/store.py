import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4

from civic.settings import CONFIG


class Conflict(Exception):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path):
        self.path = path
        with self.connection() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS requests (
                    id TEXT PRIMARY KEY, receipt TEXT NOT NULL UNIQUE,
                    service TEXT NOT NULL, department TEXT NOT NULL,
                    location TEXT NOT NULL, description TEXT NOT NULL, contact TEXT NOT NULL,
                    status TEXT NOT NULL, version INTEGER NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    graph_id TEXT
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY, request_id TEXT NOT NULL REFERENCES requests(id),
                    status TEXT NOT NULL, note TEXT NOT NULL, at TEXT NOT NULL,
                    version INTEGER NOT NULL
                );
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self, body):
        service = next(s for s in CONFIG["services"] if s["id"] == body.service)
        stamp = now()
        row = dict(
            id=str(uuid4()),
            receipt=secrets.token_urlsafe(32),
            service=body.service,
            department=service["department"],
            location=body.location,
            description=body.description,
            contact=body.contact,
            status="submitted",
            version=1,
            created_at=stamp,
            updated_at=stamp,
            graph_id=None,
        )
        with self.connection() as db:
            db.execute(
                f"INSERT INTO requests ({','.join(row)}) VALUES ({','.join('?' for _ in row)})",
                list(row.values()),
            )
            db.execute(
                "INSERT INTO events (request_id,status,note,at,version) VALUES (?,?,?,?,?)",
                (row["id"], "submitted", "Request received", stamp, 1),
            )
        return row

    def get(self, request_id):
        with self.connection() as db:
            row = db.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone()
            return dict(row) if row else None

    def track(self, receipt):
        with self.connection() as db:
            row = db.execute(
                "SELECT id,status,created_at,updated_at FROM requests WHERE receipt=?", (receipt,)
            ).fetchone()
            return dict(row) if row else None

    def queue(self, status=None, service=None):
        clauses, values = [], []
        for key, value in [("status", status), ("service", service)]:
            if value:
                clauses.append(f"{key}=?")
                values.append(value)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self.connection() as db:
            return [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM requests" + where + " ORDER BY created_at DESC LIMIT 200", values
                )
            ]

    def events(self, request_id):
        with self.connection() as db:
            return [
                dict(r)
                for r in db.execute(
                    "SELECT status,note,at,version FROM events WHERE request_id=? ORDER BY id",
                    (request_id,),
                )
            ]

    def transition(self, request_id, body):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone()
            if not row:
                raise KeyError(request_id)
            if row["version"] != body.version:
                raise Conflict("Another staff member changed this request. Refresh the queue.")
            if body.status not in CONFIG["transitions"][row["status"]]:
                raise Conflict("That status change is not allowed.")
            stamp = now()
            db.execute(
                "UPDATE requests SET status=?,version=version+1,updated_at=? WHERE id=?",
                (body.status, stamp, request_id),
            )
            db.execute(
                "INSERT INTO events (request_id,status,note,at,version) VALUES (?,?,?,?,?)",
                (request_id, body.status, body.note, stamp, body.version + 1),
            )
        return self.get(request_id)
