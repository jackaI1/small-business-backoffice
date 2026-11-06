"""Authenticated HR operations, with all balance changes in write transactions."""
from __future__ import annotations

import calendar
import hashlib
import hmac
import json
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path

from .schema import SCHEMA


class WorkflowError(ValueError):
    """An expected validation or authorization failure, safe to show in the CLI."""


def _text(value, label):
    if not isinstance(value, str) or not value.strip() or len(value) > 4000:
        raise WorkflowError(f'{label} must be nonempty text, at most 4000 characters')
    return value.strip()


def _date(value):
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError()
        return parsed
    except (ValueError, TypeError):
        raise WorkflowError('Use a valid date in YYYY-MM-DD format') from None


def _integer(value, label):
    if type(value) is not int or not -(2**63) <= value <= 2**63 - 1:
        raise WorkflowError(f'{label} must be a whole integer within the signed 64-bit storage range')
    return value


def _password(password, salt):
    return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 260_000)


def _credentials(username, password, role):
    if not isinstance(username, str) or not re.fullmatch(r'[a-zA-Z0-9_.-]{1,64}', username):
        raise WorkflowError('Username must contain 1-64 letters, numbers, dots, underscores or hyphens')
    if not isinstance(password, str) or not 12 <= len(password) <= 1024:
        raise WorkflowError('Password must contain 12-1024 characters')
    if role not in ('hr', 'manager'):
        raise WorkflowError('Role must be hr or manager')
    salt = os.urandom(16)
    return username, role, salt, _password(password, salt)


def initialize(path, username, password):
    """Create a new database and the first HR account; never overwrite a file."""
    account = _credentials(username, password, 'hr')
    path = Path(path)
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise WorkflowError('Database already exists; choose a new path') from None
    os.close(descriptor)
    conn = None
    try:
        conn = sqlite3.connect(path)
        conn.executescript(SCHEMA)
        conn.execute('INSERT INTO users VALUES (?, ?, ?, ?)', account)
        conn.commit()
    except Exception:
        if conn:
            conn.close()
        path.unlink(missing_ok=True)
        raise
    finally:
        if conn:
            conn.close()


class Workflow:
    def __init__(self, conn, username, role):
        self._conn = conn
        self.username = username
        self.role = role

    @classmethod
    def login(cls, path, username, password):
        # mode=rw prevents a mistyped path silently creating an empty database.
        try:
            conn = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=rw', uri=True, timeout=10)
            conn.row_factory = sqlite3.Row
            conn.execute('PRAGMA foreign_keys=ON')
            row = conn.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
            if row is None or not hmac.compare_digest(_password(password, row['salt']), row['password_hash']):
                raise WorkflowError('Invalid username or password')
            return cls(conn, row['username'], row['role'])
        except Exception:
            if 'conn' in locals():
                conn.close()
            raise

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    @contextmanager
    def _write(self):
        try:
            self._conn.execute('BEGIN IMMEDIATE')
            yield
            self._conn.commit()
        except sqlite3.IntegrityError as error:
            self._conn.rollback()
            raise WorkflowError(f'Record conflicts with existing data: {error}') from None
        except Exception:
            self._conn.rollback()
            raise

    def _hr(self):
        if self.role != 'hr':
            raise WorkflowError('HR access required')

    def _employee(self, employee_id):
        _integer(employee_id, 'Employee ID')
        row = self._conn.execute('SELECT * FROM employees WHERE id=?', (employee_id,)).fetchone()
        if row is None:
            raise WorkflowError('Employee not found')
        return row

    def _team(self, employee):
        if self.role != 'hr' and employee['manager'] != self.username:
            raise WorkflowError('Request is outside your team')

    def _event(self, action, employee_id=None, **details):
        self._conn.execute('INSERT INTO events(actor, action, employee_id, details) VALUES (?, ?, ?, ?)',
                           (self.username, action, employee_id, json.dumps(details, sort_keys=True)))

    def _balance(self, employee_id):
        return self._conn.execute('SELECT coalesce(sum(delta_minutes), 0) FROM ledger WHERE employee_id=?',
                                  (employee_id,)).fetchone()[0]

    def _entry(self, employee_id, delta, kind, reason, period=None, request_id=None):
        balance = self._balance(employee_id) + delta
        _integer(balance, 'Resulting balance')
        if balance < 0:
            raise WorkflowError('Insufficient balance; no changes were saved')
        self._conn.execute('''INSERT INTO ledger
            (employee_id, kind, delta_minutes, balance_minutes, reason, actor, period, request_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (employee_id, kind, delta, balance, reason, self.username, period, request_id))
        self._event('balance_' + kind, employee_id, delta_minutes=delta,
                    balance_minutes=balance, reason=reason, period=period, request_id=request_id)

    def add_user(self, username, password, role):
        self._hr()
        account = _credentials(username, password, role)
        with self._write():
            self._conn.execute('INSERT INTO users VALUES (?, ?, ?, ?)', account)
            self._event('user_created', username=username, role=role)

    def add_employee(self, code, name, title, department, hire_date, manager, monthly_minutes, user=None):
        self._hr()
        values = [_text(value, label) for value, label in
                  [(code, 'Employee code'), (name, 'Name'), (title, 'Title'), (department, 'Department')]]
        _date(hire_date)
        if _integer(monthly_minutes, 'Monthly accrual') < 0:
            raise WorkflowError('Monthly accrual cannot be negative')
        with self._write():
            account = self._conn.execute('SELECT role FROM users WHERE username=?', (manager,)).fetchone()
            if account is None or account['role'] != 'manager':
                raise WorkflowError('Assign an existing manager account')
            cursor = self._conn.execute('''INSERT INTO employees
                (code, name, title, department, hire_date, manager, monthly_minutes, user)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', (*values, hire_date, manager, monthly_minutes, user))
            self._event('employee_created', cursor.lastrowid, code=code)
            return cursor.lastrowid

    def employees(self):
        self._hr()
        return [dict(row) for row in self._conn.execute('SELECT * FROM employees ORDER BY id')]

    def employee_file(self, employee_id):
        self._hr()
        employee = dict(self._employee(employee_id))
        employee['notes'] = [dict(row) for row in self._conn.execute(
            'SELECT note, actor, created_at FROM file_notes WHERE employee_id=? ORDER BY id', (employee_id,))]
        employee['balance_minutes'] = self._balance(employee_id)
        return employee

    def add_file_note(self, employee_id, note):
        self._hr()
        note = _text(note, 'File note')
        with self._write():
            self._employee(employee_id)
            self._conn.execute('INSERT INTO file_notes(employee_id, note, actor) VALUES (?, ?, ?)',
                               (employee_id, note, self.username))
            self._event('file_note_added', employee_id)

    def balance(self, employee_id):
        self._hr()
        self._employee(employee_id)
        return self._balance(employee_id)

    def audit(self, employee_id):
        self._hr()
        self._employee(employee_id)
        return [dict(row) for row in self._conn.execute(
            'SELECT * FROM ledger WHERE employee_id=? ORDER BY id', (employee_id,))]

    def events(self):
        self._hr()
        return [dict(row) for row in self._conn.execute('SELECT * FROM events ORDER BY id')]

    def adjust(self, employee_id, minutes, reason):
        self._hr()
        _integer(minutes, 'Adjustment')
        reason = _text(reason, 'Reason')
        if minutes == 0:
            raise WorkflowError('Adjustment must be nonzero')
        with self._write():
            self._employee(employee_id)
            self._entry(employee_id, minutes, 'adjustment', reason)

    def accrue(self, month, *, today=None):
        self._hr()
        if not isinstance(month, str) or not re.fullmatch(r'\d{4}-\d{2}', month):
            raise WorkflowError('Use YYYY-MM for the accrual month')
        first = _date(month + '-01')
        last = first.replace(day=calendar.monthrange(first.year, first.month)[1])
        if last >= (today or date.today()):
            raise WorkflowError('Only completed calendar months can be accrued')
        with self._write():
            eligible = self._conn.execute('''SELECT * FROM employees e
                WHERE hire_date <= ? AND monthly_minutes > 0
                AND NOT EXISTS (SELECT 1 FROM ledger l WHERE l.employee_id=e.id AND l.period=?)
                ORDER BY id''', (first.isoformat(), month)).fetchall()
            for employee in eligible:
                self._entry(employee['id'], employee['monthly_minutes'], 'accrual',
                            'Full-month accrual for ' + month, period=month)
            return len(eligible)

    def request_leave(self, employee_id, start, end):
        first, last = _date(start), _date(end)
        if not 0 <= (last - first).days <= 365:
            raise WorkflowError('Leave must end on or after its start, within 366 days')
        minutes = sum((first + timedelta(days=i)).weekday() < 5
                      for i in range((last - first).days + 1)) * 480
        if not minutes:
            raise WorkflowError('Request must include at least one weekday')
        with self._write():
            employee = self._employee(employee_id)
            self._team(employee)
            if start < employee['hire_date']:
                raise WorkflowError('Leave cannot begin before the hire date')
            overlap = self._conn.execute('''SELECT id FROM requests WHERE employee_id=?
                AND status IN ('pending', 'approved') AND start_date <= ? AND end_date >= ?''',
                (employee_id, end, start)).fetchone()
            if overlap:
                raise WorkflowError('Dates overlap a pending or approved request')
            cursor = self._conn.execute('''INSERT INTO requests
                (employee_id, start_date, end_date, minutes, requested_by) VALUES (?, ?, ?, ?, ?)''',
                (employee_id, start, end, minutes, self.username))
            self._event('request_created', employee_id, request_id=cursor.lastrowid,
                        start=start, end=end, minutes=minutes)
            return cursor.lastrowid

    def requests(self):
        # Explicit projection keeps private employment data out of manager views.
        query = '''SELECT r.*, e.code AS employee_code, e.name AS employee_name
                   FROM requests r JOIN employees e ON e.id=r.employee_id'''
        args = ()
        if self.role != 'hr':
            query += ' WHERE e.manager=?'
            args = (self.username,)
        return [dict(row) for row in self._conn.execute(query + ' ORDER BY r.id', args)]

    def _request(self, request_id):
        _integer(request_id, 'Request ID')
        request = self._conn.execute('SELECT * FROM requests WHERE id=?', (request_id,)).fetchone()
        if request is None:
            raise WorkflowError('Request not found')
        employee = self._employee(request['employee_id'])
        self._team(employee)
        return request, employee

    def decide(self, request_id, decision, reason):
        reason = _text(reason, 'Decision reason')
        if decision not in ('approved', 'rejected'):
            raise WorkflowError('Decision must be approved or rejected')
        with self._write():
            request, employee = self._request(request_id)
            if request['status'] != 'pending':
                raise WorkflowError('Only pending requests can be decided')
            if employee['user'] == self.username:
                raise WorkflowError('An independent approver must decide your leave')
            if decision == 'approved':
                self._entry(employee['id'], -request['minutes'], 'leave', reason, request_id=request_id)
            self._conn.execute('''UPDATE requests SET status=?, decided_by=?, decision_reason=?,
                decided_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id=?''',
                (decision, self.username, reason, request_id))
            self._event('request_' + decision, employee['id'], request_id=request_id, reason=reason)

    def cancel(self, request_id, reason):
        reason = _text(reason, 'Cancellation reason')
        with self._write():
            request, employee = self._request(request_id)
            if request['status'] not in ('pending', 'approved'):
                raise WorkflowError('Only pending or approved requests can be cancelled')
            if request['status'] == 'approved':
                self._entry(employee['id'], request['minutes'], 'refund', reason, request_id=request_id)
            self._conn.execute('''UPDATE requests SET status='cancelled', cancelled_by=?, cancellation_reason=?,
                cancelled_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id=?''',
                (self.username, reason, request_id))
            self._event('request_cancelled', employee['id'], request_id=request_id, reason=reason)
