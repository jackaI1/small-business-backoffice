"""SQLite storage. The journal, rather than a mutable total, defines balances."""

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE users (
    username TEXT PRIMARY KEY,
    role TEXT NOT NULL CHECK (role IN ('hr', 'manager')),
    salt BLOB NOT NULL,
    password_hash BLOB NOT NULL
);
CREATE TABLE employees (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    title TEXT NOT NULL,
    department TEXT NOT NULL,
    hire_date TEXT NOT NULL,
    manager TEXT NOT NULL REFERENCES users(username),
    monthly_minutes INTEGER NOT NULL CHECK (monthly_minutes >= 0),
    user TEXT UNIQUE REFERENCES users(username)
);
CREATE TABLE file_notes (
    id INTEGER PRIMARY KEY,
    employee_id INTEGER NOT NULL REFERENCES employees(id),
    note TEXT NOT NULL,
    actor TEXT NOT NULL REFERENCES users(username),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE TABLE requests (
    id INTEGER PRIMARY KEY,
    employee_id INTEGER NOT NULL REFERENCES employees(id),
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    minutes INTEGER NOT NULL CHECK (minutes > 0),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'cancelled')),
    requested_by TEXT NOT NULL REFERENCES users(username),
    decided_by TEXT REFERENCES users(username),
    decision_reason TEXT,
    decided_at TEXT,
    cancelled_by TEXT REFERENCES users(username),
    cancellation_reason TEXT,
    cancelled_at TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE TABLE ledger (
    id INTEGER PRIMARY KEY,
    employee_id INTEGER NOT NULL REFERENCES employees(id),
    kind TEXT NOT NULL CHECK (kind IN ('accrual', 'adjustment', 'leave', 'refund')),
    delta_minutes INTEGER NOT NULL CHECK (delta_minutes != 0),
    balance_minutes INTEGER NOT NULL CHECK (balance_minutes >= 0),
    reason TEXT NOT NULL,
    actor TEXT NOT NULL REFERENCES users(username),
    period TEXT,
    request_id INTEGER REFERENCES requests(id),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (employee_id, period),
    UNIQUE (request_id, kind)
);
CREATE TABLE events (
    id INTEGER PRIMARY KEY,
    actor TEXT NOT NULL REFERENCES users(username),
    action TEXT NOT NULL,
    employee_id INTEGER REFERENCES employees(id),
    details TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX request_employee_dates ON requests(employee_id, start_date, end_date);
CREATE INDEX ledger_employee ON ledger(employee_id, id);
CREATE TRIGGER ledger_no_update BEFORE UPDATE ON ledger BEGIN
    SELECT RAISE(ABORT, 'Balance history is append-only');
END;
CREATE TRIGGER ledger_no_delete BEFORE DELETE ON ledger BEGIN
    SELECT RAISE(ABORT, 'Balance history is append-only');
END;
CREATE TRIGGER events_no_update BEFORE UPDATE ON events BEGIN
    SELECT RAISE(ABORT, 'Audit events are append-only');
END;
CREATE TRIGGER events_no_delete BEFORE DELETE ON events BEGIN
    SELECT RAISE(ABORT, 'Audit events are append-only');
END;
PRAGMA user_version = 1;
"""
