"""Run with python -m hr_absence. Passwords are prompted, never command arguments."""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sqlite3
import sys
from pathlib import Path

from .demo import DEMO_ACCOUNTS, create_demo
from .reports import balance_csv, employment_letter
from .service import Workflow, WorkflowError, initialize


def _secret(variable, prompt):
    if variable in os.environ:
        return os.environ[variable]
    if not sys.stdin.isatty():
        raise WorkflowError(f'Set {variable} for noninteractive use, or run in a terminal for a password prompt')
    return getpass.getpass(prompt)


def _json(value):
    print(json.dumps(value, indent=2))


def _output(render, destination):
    if destination is None:
        print(render(), end='')
        return
    path = Path(destination)
    # Exclusive creation prevents accidental replacement of a letter or report.
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8', newline='') as stream:
            stream.write(render())
    except Exception:
        path.unlink(missing_ok=True)
        raise
    _json({'saved': str(path)})


def parser():
    root = argparse.ArgumentParser(description='Synthetic HR absence workflow. Full-day leave uses 8-hour weekdays.')
    root.add_argument('--db', default='hr-demo.db', help='SQLite database file (default: hr-demo.db)')
    root.add_argument('--user', default='hr', help='Saved account username (default: hr)')
    commands = root.add_subparsers(dest='command', required=True)
    init = commands.add_parser('init', help='Create a new database, never overwrite one')
    init.add_argument('--demo', action='store_true', help='Seed three fictional employees and public demo accounts')
    account = commands.add_parser('user-add', help='HR: create a saved account')
    account.add_argument('username')
    account.add_argument('--role', choices=['hr', 'manager'], required=True)
    employee = commands.add_parser('employee-add', help='HR: add a synthetic employee file')
    employee.add_argument('code')
    employee.add_argument('name')
    employee.add_argument('--title', required=True)
    employee.add_argument('--department', required=True)
    employee.add_argument('--hired', required=True, help='YYYY-MM-DD')
    employee.add_argument('--manager', required=True, help='Existing manager username')
    employee.add_argument('--monthly-minutes', required=True, type=int)
    employee.add_argument('--account', help='Link this employee to a saved account to prevent self-approval')
    commands.add_parser('employees', help='HR: list employee records')
    for command, help_text in [('file', 'HR: show employee file and notes'), ('audit', 'HR: show balance journal')]:
        child = commands.add_parser(command, help=help_text)
        child.add_argument('employee', type=int)
    note = commands.add_parser('note', help='HR: append a synthetic employee file note')
    note.add_argument('employee', type=int)
    note.add_argument('text')
    adjustment = commands.add_parser('adjust', help='HR: post a signed balance correction in minutes')
    adjustment.add_argument('employee', type=int)
    adjustment.add_argument('minutes', type=int)
    adjustment.add_argument('--reason', required=True)
    accrual = commands.add_parser('accrue', help='HR: credit one completed full month, safely repeatable')
    accrual.add_argument('month', help='YYYY-MM')
    leave = commands.add_parser('request', help='Create leave for an employee in your scope')
    leave.add_argument('employee', type=int)
    leave.add_argument('start', help='YYYY-MM-DD, inclusive')
    leave.add_argument('end', help='YYYY-MM-DD, inclusive')
    commands.add_parser('requests', help='List requests: managers see only their team')
    decision = commands.add_parser('decide', help='Approve or reject a pending request in your scope')
    decision.add_argument('request', type=int)
    decision.add_argument('decision', choices=['approved', 'rejected'])
    decision.add_argument('--reason', required=True)
    cancellation = commands.add_parser('cancel', help='Cancel pending/approved leave; refund approved leave once')
    cancellation.add_argument('request', type=int)
    cancellation.add_argument('--reason', required=True)
    letter = commands.add_parser('letter', help='HR: generate an employment confirmation letter')
    letter.add_argument('employee', type=int)
    letter.add_argument('--template', help='Optional UTF-8 text template with $placeholders')
    letter.add_argument('--output', help='New text file; defaults to stdout')
    report = commands.add_parser('export', help='HR: export current employee balance report as CSV')
    report.add_argument('--output', help='New CSV file; defaults to stdout')
    commands.add_parser('events', help='HR: show operation audit trail')
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == 'init':
            if args.demo:
                create_demo(args.db)
                _json({'created': args.db, 'synthetic_only': True, 'demo_accounts': DEMO_ACCOUNTS})
            else:
                initialize(args.db, args.user, _secret('HRWF_PASSWORD', 'New HR password (12+ characters): '))
                _json({'created': args.db, 'hr_user': args.user})
            return 0
        with Workflow.login(args.db, args.user, _secret('HRWF_PASSWORD', 'Password: ')) as workflow:
            command = args.command
            if command == 'user-add':
                workflow._hr()
                workflow.add_user(args.username, _secret('HRWF_NEW_PASSWORD', 'New account password (12+ characters): '), args.role)
            elif command == 'employee-add':
                employee_id = workflow.add_employee(args.code, args.name, args.title, args.department,
                    args.hired, args.manager, args.monthly_minutes, user=args.account)
                _json({'employee_id': employee_id})
                return 0
            elif command == 'employees':
                _json(workflow.employees())
                return 0
            elif command == 'file':
                _json(workflow.employee_file(args.employee))
                return 0
            elif command == 'note':
                workflow.add_file_note(args.employee, args.text)
            elif command == 'adjust':
                workflow.adjust(args.employee, args.minutes, args.reason)
            elif command == 'accrue':
                _json({'credited_employees': workflow.accrue(args.month)})
                return 0
            elif command == 'request':
                _json({'request_id': workflow.request_leave(args.employee, args.start, args.end)})
                return 0
            elif command == 'requests':
                _json(workflow.requests())
                return 0
            elif command == 'decide':
                workflow.decide(args.request, args.decision, args.reason)
            elif command == 'cancel':
                workflow.cancel(args.request, args.reason)
            elif command == 'audit':
                _json(workflow.audit(args.employee))
                return 0
            elif command == 'events':
                _json(workflow.events())
                return 0
            elif command == 'letter':
                workflow._hr()
                template = Path(args.template).read_text(encoding='utf-8') if args.template else None
                _output(lambda: employment_letter(workflow, args.employee, template=template), args.output)
                return 0
            elif command == 'export':
                workflow._hr()
                _output(lambda: balance_csv(workflow), args.output)
                return 0
            _json({'status': 'saved'})
        return 0
    except (WorkflowError, sqlite3.Error, OSError, UnicodeError) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
