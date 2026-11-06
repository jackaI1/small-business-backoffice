"""HR-only text letters and spreadsheet-safe CSV reporting."""
from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal
from pathlib import Path
from string import Template

from .service import WorkflowError, _date


def employment_letter(workflow, employee_id, *, template=None, issued=None):
    workflow._hr()
    issued = issued or date.today().isoformat()
    _date(issued)
    if template is None:
        template = (Path(__file__).parent / 'templates' / 'employment.txt').read_text(encoding='utf-8')
    if not isinstance(template, str) or not template.strip() or len(template) > 100_000:
        raise WorkflowError('Letter template must contain 1-100000 characters')
    with workflow._write():
        employee = workflow._employee(employee_id)
        fields = dict(employee_code=employee['code'], employee_name=employee['name'],
                      title=employee['title'], department=employee['department'],
                      hire_date=employee['hire_date'], issued_date=issued,
                      company='Example Works Ltd. (fictional)', signatory=workflow.username)
        try:
            rendered = Template(template).substitute(fields)
        except (KeyError, ValueError):
            raise WorkflowError('Invalid template; use only the documented $placeholders') from None
        workflow._event('letter_generated', employee_id, issued_date=issued)
        return rendered


def _safe_text(value):
    # Quoting handles commas/newlines; apostrophes prevent formula evaluation.
    if value.lstrip().startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r', '\n')):
        return "'" + value
    return value


def balance_csv(workflow):
    workflow._hr()
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow(['employee_code', 'employee_name', 'department', 'balance_minutes', 'balance_hours',
                     'pending_minutes', 'approved_minutes', 'accrual_minutes', 'adjustment_minutes'])
    # One consistent snapshot, including the audit event, even during approvals.
    with workflow._write():
        for employee in workflow._conn.execute('SELECT * FROM employees ORDER BY id').fetchall():
            employee_id = employee['id']
            ledger = dict(workflow._conn.execute('''SELECT kind, sum(delta_minutes)
                FROM ledger WHERE employee_id=? GROUP BY kind''', (employee_id,)).fetchall())
            requests = dict(workflow._conn.execute('''SELECT status, sum(minutes)
                FROM requests WHERE employee_id=? GROUP BY status''', (employee_id,)).fetchall())
            balance = sum(ledger.values())
            writer.writerow([_safe_text(employee['code']), _safe_text(employee['name']),
                             _safe_text(employee['department']), balance, f'{Decimal(balance) / 60:.2f}',
                             requests.get('pending', 0), requests.get('approved', 0),
                             ledger.get('accrual', 0), ledger.get('adjustment', 0)])
        workflow._event('report_exported', report='current_balances')
    return output.getvalue()
