import csv
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from hr_absence.reports import balance_csv, employment_letter
from hr_absence.service import Workflow, WorkflowError, initialize


class OutputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'output.db'
        initialize(self.path, 'hr', 'test-password-123')
        self.hr = Workflow.login(self.path, 'hr', 'test-password-123')
        self.addCleanup(self.hr.close)
        self.hr.add_user('manager', 'test-password-123', 'manager')
        self.employee = self.hr.add_employee('SYN-001', 'Alex Example', 'Lab Assistant', 'Research', '2026-01-05', 'manager', 600)

    def test_default_letter_uses_employee_file_and_omits_private_notes_and_balances(self):
        self.hr.add_file_note(self.employee, 'PRIVATE SYNTHETIC NOTE')
        self.hr.adjust(self.employee, 600, 'Opening')
        letter = employment_letter(self.hr, self.employee, issued='2026-11-06')
        for value in ['Alex Example', 'Lab Assistant', 'Research', '2026-01-05', '2026-11-06', 'SYNTHETIC']:
            self.assertIn(value, letter)
        self.assertNotIn('PRIVATE SYNTHETIC NOTE', letter)
        self.assertNotIn('600', letter)
        self.assertEqual(self.hr.events()[-1]['action'], 'letter_generated')

    def test_custom_letter_requires_known_complete_placeholders(self):
        self.assertEqual(employment_letter(self.hr, self.employee, template='$employee_name: $title'), 'Alex Example: Lab Assistant')
        count = len(self.hr.events())
        for template in ['$salary', '${employee_name', '$']:
            with self.subTest(template=template), self.assertRaises(WorkflowError):
                employment_letter(self.hr, self.employee, template=template)
        with self.assertRaises(WorkflowError):
            employment_letter(self.hr, self.employee, issued='tomorrow')
        self.assertEqual(len(self.hr.events()), count)

    def test_csv_reports_exact_balances_pending_and_current_approved_leave(self):
        self.hr.adjust(self.employee, 1440, 'Opening')
        one = self.hr.request_leave(self.employee, '2026-11-09', '2026-11-09')
        self.hr.decide(one, 'approved', 'Covered')
        self.hr.request_leave(self.employee, '2026-11-10', '2026-11-10')
        row = list(csv.DictReader(io.StringIO(balance_csv(self.hr))))[0]
        self.assertEqual((row['balance_minutes'], row['balance_hours'], row['pending_minutes'], row['approved_minutes']),
                         ('960', '16.00', '480', '480'))
        self.assertEqual(row['adjustment_minutes'], '1440')
        self.hr.cancel(one, 'Plans changed')
        row = list(csv.DictReader(io.StringIO(balance_csv(self.hr))))[0]
        self.assertEqual((row['balance_minutes'], row['approved_minutes']), ('1440', '0'))
        self.assertEqual(self.hr.events()[-1]['action'], 'report_exported')

    def test_csv_quotes_multiline_fields_and_neutralizes_formulas(self):
        self.hr.add_employee('=1+1', ' \t=HYPERLINK("https://example.invalid")', '+Risk,\nTeam', '@Ops', '2026-01-01', 'manager', 0)
        row = list(csv.DictReader(io.StringIO(balance_csv(self.hr))))[1]
        self.assertTrue(row['employee_code'].startswith("'="))
        self.assertTrue(row['employee_name'].startswith("'"))
        self.assertEqual(row['department'], "'@Ops")

    def test_managers_cannot_generate_letters_or_export_employee_report(self):
        with Workflow.login(self.path, 'manager', 'test-password-123') as manager:
            with self.assertRaises(WorkflowError):
                employment_letter(manager, self.employee)
            with self.assertRaises(WorkflowError):
                balance_csv(manager)


class CLITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'demo.db'

    def cli(self, *args, user='hr', password='synthetic-hr-2026', expected=0, db=None):
        env = {**os.environ, 'HRWF_PASSWORD': password}
        result = subprocess.run([sys.executable, '-m', 'hr_absence', '--db', str(db or self.path), '--user', user, *args],
                                text=True, capture_output=True, env=env, timeout=20)
        self.assertEqual(result.returncode, expected, result.stderr)
        return result

    def test_documented_demo_approval_letter_and_export_work_across_processes(self):
        self.cli('init', '--demo')
        records = json.loads(self.cli('employees').stdout)
        self.assertEqual(len(records), 3)
        request_id = json.loads(self.cli('request', '1', '2026-11-09', '2026-11-10', user='mgr-north', password='synthetic-north-2026').stdout)['request_id']
        self.cli('decide', str(request_id), 'approved', '--reason', 'Team coverage arranged', user='mgr-north', password='synthetic-north-2026')
        ledger = json.loads(self.cli('audit', '1').stdout)
        self.assertEqual(ledger[-1]['balance_minutes'], 3840)
        self.assertEqual(ledger[-1]['delta_minutes'], -960)
        letter = Path(self.tmp.name) / 'letter.txt'
        report = Path(self.tmp.name) / 'balances.csv'
        self.cli('letter', '1', '--output', str(letter))
        self.cli('export', '--output', str(report))
        self.assertIn('Alex Example', letter.read_text())
        with report.open(encoding='utf-8', newline='') as stream:
            self.assertEqual(list(csv.DictReader(stream))[0]['balance_hours'], '64.00')
        self.cli('letter', '1', '--output', str(letter), expected=2)
        self.assertIn('Alex Example', letter.read_text())
        self.cli('init', '--demo', expected=2)

    def test_cli_enforces_permissions_and_does_not_create_mistyped_database(self):
        self.cli('init', '--demo')
        for args in [('employees',), ('file', '1'), ('audit', '1'), ('export',), ('letter', '1'), ('adjust', '1', '600', '--reason', 'unauthorized')]:
            result = self.cli(*args, user='mgr-north', password='synthetic-north-2026', expected=2)
            self.assertIn('HR access required', result.stderr)
        self.assertEqual(json.loads(self.cli('requests', user='mgr-south', password='synthetic-south-2026').stdout), [])
        self.cli('employees', password='wrong', expected=2)
        missing = Path(self.tmp.name) / 'missing.db'
        self.cli('employees', db=missing, expected=2)
        self.assertFalse(missing.exists())

    def test_extreme_adjustment_returns_validation_error_without_traceback(self):
        self.cli('init', '--demo')
        result = self.cli('adjust', '1', str(2**63), '--reason', 'Invalid extreme input', expected=2)
        self.assertIn('Error:', result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        self.assertEqual(len(json.loads(self.cli('audit', '1').stdout)), 1)

    def test_non_demo_initialization_and_record_management(self):
        self.cli('init', password='local-password-123')
        self.cli('user-add', 'manager', '--role', 'manager', password='local-password-123', expected=2)
        # The second account password has a separate environment variable.
        env = {**os.environ, 'HRWF_PASSWORD': 'local-password-123', 'HRWF_NEW_PASSWORD': 'manager-password-123'}
        result = subprocess.run([sys.executable, '-m', 'hr_absence', '--db', str(self.path), '--user', 'hr',
                                 'user-add', 'manager', '--role', 'manager'], env=env, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.cli('employee-add', 'SYN-NEW', 'Taylor Example', '--title', 'Coordinator', '--department', 'Ops',
                 '--hired', '2026-01-01', '--manager', 'manager', '--monthly-minutes', '600', password='local-password-123')
        self.cli('note', '1', 'Synthetic onboarding complete', password='local-password-123')
        self.assertIn('Synthetic onboarding complete', self.cli('file', '1', password='local-password-123').stdout)
        self.cli('accrue', '2026-01', password='local-password-123')
        self.cli('accrue', '2026-01', password='local-password-123')
        self.assertEqual(json.loads(self.cli('audit', '1', password='local-password-123').stdout)[0]['balance_minutes'], 600)


if __name__ == '__main__':
    unittest.main()
