import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

from hr_absence.service import Workflow, WorkflowError, initialize


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'hr.db'
        initialize(self.path, 'hr', 'test-password-123')
        self.hr = Workflow.login(self.path, 'hr', 'test-password-123')
        self.addCleanup(self.hr.close)
        self.hr.add_user('manager', 'test-password-123', 'manager')
        self.hr.add_user('other', 'test-password-123', 'manager')
        self.employee = self.hr.add_employee('SYN-001', 'Alex Example', 'Analyst', 'Operations', '2026-01-01', 'manager', 600)
        self.manager = Workflow.login(self.path, 'manager', 'test-password-123')
        self.addCleanup(self.manager.close)
        self.other = Workflow.login(self.path, 'other', 'test-password-123')
        self.addCleanup(self.other.close)

    def credit(self, minutes=2400):
        self.hr.adjust(self.employee, minutes, 'Synthetic opening balance')

    def request(self, start='2026-11-09', end='2026-11-10'):
        return self.manager.request_leave(self.employee, start, end)

    def test_login_rejects_wrong_password_and_unknown_user(self):
        for username, password in [('hr', 'wrong'), ('missing', 'test-password-123')]:
            with self.subTest(username=username), self.assertRaises(WorkflowError):
                Workflow.login(self.path, username, password)

    def test_employee_files_are_hr_only_and_persist(self):
        self.hr.add_file_note(self.employee, 'Synthetic contract: full time')
        self.assertEqual(self.hr.employee_file(self.employee)['notes'][0]['note'], 'Synthetic contract: full time')
        self.assertEqual(self.hr.employees()[0]['name'], 'Alex Example')
        for actor in [self.manager, self.other]:
            for operation in [lambda: actor.employees(), lambda: actor.employee_file(self.employee),
                              lambda: actor.add_file_note(self.employee, 'no'),
                              lambda: actor.adjust(self.employee, 60, 'no'),
                              lambda: actor.audit(self.employee)]:
                with self.assertRaises(WorkflowError):
                    operation()

    def test_accrual_is_once_per_employee_and_full_completed_month(self):
        late = self.hr.add_employee('SYN-002', 'Sam Sample', 'Clerk', 'Operations', '2026-10-02', 'manager', 600)
        self.assertEqual(self.hr.accrue('2026-10', today=date(2026, 11, 1)), 1)
        self.assertEqual(self.hr.accrue('2026-10', today=date(2026, 11, 1)), 0)
        self.assertEqual(self.hr.balance(self.employee), 600)
        self.assertEqual(self.hr.balance(late), 0)
        self.assertEqual(self.hr.accrue('2026-11', today=date(2026, 12, 1)), 2)
        self.assertEqual(self.hr.balance(late), 600)
        for month in ['2026-12', '2026-13', '2026-1']:
            with self.subTest(month=month), self.assertRaises(WorkflowError):
                self.hr.accrue(month, today=date(2026, 12, 1))
        with self.assertRaises(WorkflowError):
            self.manager.accrue('2026-10', today=date(2026, 11, 1))

    def test_adjustments_require_reason_and_cannot_overdraw(self):
        self.credit(600)
        self.hr.adjust(self.employee, -120, 'Correct opening entry')
        self.assertEqual(self.hr.balance(self.employee), 480)
        for amount, reason in [(-481, 'too much'), (0, 'zero'), (30, ' '), (1.5, 'fraction')]:
            with self.subTest(amount=amount), self.assertRaises(WorkflowError):
                self.hr.adjust(self.employee, amount, reason)
        self.assertEqual(len(self.hr.audit(self.employee)), 2)
        row = self.hr.audit(self.employee)[-1]
        self.assertEqual((row['delta_minutes'], row['balance_minutes'], row['actor']), (-120, 480, 'hr'))
        self.assertTrue(row['created_at'])

    def test_adjustment_overflow_is_rejected_without_partial_history(self):
        for minutes in [2**63, -(2**63) - 1]:
            with self.subTest(minutes=minutes), self.assertRaises(WorkflowError):
                self.hr.adjust(self.employee, minutes, 'Invalid extreme input')
        self.hr.adjust(self.employee, 2**63 - 1, 'Upper storage boundary')
        with self.assertRaises(WorkflowError):
            self.hr.adjust(self.employee, 1, 'Would overflow resulting balance')
        self.assertEqual(self.hr.balance(self.employee), 2**63 - 1)
        self.assertEqual(len(self.hr.audit(self.employee)), 1)

    def test_request_counts_weekdays_and_rejects_overlap_and_invalid_dates(self):
        request_id = self.request('2026-11-06', '2026-11-09')
        row = self.manager.requests()[0]
        self.assertEqual((row['id'], row['minutes'], row['status']), (request_id, 960, 'pending'))
        for start, end in [('2026-11-09', '2026-11-10'), ('2026-11-08', '2026-11-07'),
                           ('2026-11-07', '2026-11-08'), ('bad', '2026-11-09'),
                           ('2025-12-31', '2026-01-02')]:
            with self.subTest(start=start), self.assertRaises(WorkflowError):
                self.request(start, end)

    def test_managers_only_see_and_decide_their_team_requests(self):
        request_id = self.request()
        self.assertEqual(self.other.requests(), [])
        with self.assertRaises(WorkflowError):
            self.other.request_leave(self.employee, '2026-12-01', '2026-12-01')
        with self.assertRaises(WorkflowError):
            self.other.decide(request_id, 'rejected', 'no')
        self.assertEqual(len(self.hr.requests()), 1)
        self.assertNotIn('notes', self.manager.requests()[0])
        self.assertNotIn('hire_date', self.manager.requests()[0])

    def test_approval_debits_once_and_rechecks_balance(self):
        self.credit(960)
        request_id = self.request()
        self.hr.adjust(self.employee, -480, 'Correct entitlement')
        with self.assertRaises(WorkflowError):
            self.manager.decide(request_id, 'approved', 'Team coverage arranged')
        self.assertEqual(self.manager.requests()[0]['status'], 'pending')
        self.credit(480)
        self.manager.decide(request_id, 'approved', 'Team coverage arranged')
        self.assertEqual(self.hr.balance(self.employee), 0)
        with self.assertRaises(WorkflowError):
            self.manager.decide(request_id, 'approved', 'again')
        self.assertEqual(self.hr.audit(self.employee)[-1]['kind'], 'leave')

    def test_rejection_does_not_change_balance_and_records_reason(self):
        self.credit()
        request_id = self.request()
        self.manager.decide(request_id, 'rejected', 'Coverage unavailable')
        self.assertEqual(self.hr.balance(self.employee), 2400)
        self.assertEqual(self.manager.requests()[0]['decision_reason'], 'Coverage unavailable')
        self.assertEqual(len(self.hr.audit(self.employee)), 1)
        self.assertEqual(self.hr.events()[-1]['action'], 'request_rejected')

    def test_self_approval_and_blank_decision_are_rejected(self):
        own = self.hr.add_employee('SYN-003', 'Morgan Example', 'Lead', 'Operations', '2026-01-01', 'manager', 600, user='manager')
        self.hr.adjust(own, 960, 'Opening balance')
        request_id = self.hr.request_leave(own, '2026-11-09', '2026-11-10')
        with self.assertRaises(WorkflowError):
            self.manager.decide(request_id, 'approved', 'my own leave')
        for decision, reason in [('approved', ' '), ('cancelled', 'invalid')]:
            with self.assertRaises(WorkflowError):
                self.hr.decide(request_id, decision, reason)
        self.hr.decide(request_id, 'approved', 'Independent HR approval')

    def test_approved_cancellation_refunds_once_and_keeps_history(self):
        self.credit()
        request_id = self.request()
        self.manager.decide(request_id, 'approved', 'Covered')
        self.manager.cancel(request_id, 'Plans changed')
        self.assertEqual(self.hr.balance(self.employee), 2400)
        self.assertEqual([r['delta_minutes'] for r in self.hr.audit(self.employee)], [2400, -960, 960])
        self.assertEqual(self.manager.requests()[0]['status'], 'cancelled')
        with self.assertRaises(WorkflowError):
            self.manager.cancel(request_id, 'again')
        self.request()  # cancelled dates are available again

    def test_pending_cancellation_has_no_balance_effect(self):
        request_id = self.request()
        self.manager.cancel(request_id, 'Entered wrong dates')
        self.assertEqual(self.hr.audit(self.employee), [])
        self.assertEqual(self.hr.balance(self.employee), 0)

    def test_audit_is_append_only_in_database(self):
        self.credit()
        with sqlite3.connect(self.path) as conn:
            for sql in ['DELETE FROM ledger', 'UPDATE ledger SET delta_minutes=1',
                        'DELETE FROM events', "UPDATE events SET action='changed'"]:
                with self.subTest(sql=sql), self.assertRaises(sqlite3.IntegrityError):
                    conn.execute(sql)
        self.assertEqual(self.hr.balance(self.employee), 2400)

    def test_concurrent_approvals_cannot_spend_same_balance(self):
        self.credit(480)
        first = self.request('2026-11-09', '2026-11-09')
        second = self.request('2026-11-10', '2026-11-10')

        def approve(request_id):
            actor = Workflow.login(self.path, 'manager', 'test-password-123')
            try:
                actor.decide(request_id, 'approved', 'Covered')
                return True
            except WorkflowError:
                return False
            finally:
                actor.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(approve, [first, second])), [False, True])
        self.assertEqual(self.hr.balance(self.employee), 0)
        self.assertEqual(sum(r['status'] == 'approved' for r in self.hr.requests()), 1)

    def test_invalid_employee_and_account_inputs_leave_no_partial_records(self):
        for code, hired, manager, rate in [('SYN-001', '2026-01-01', 'manager', 600),
                                          ('SYN-X', 'bad', 'manager', 600),
                                          ('SYN-X', '2026-01-01', 'missing', 600),
                                          ('SYN-X', '2026-01-01', 'manager', -1)]:
            with self.subTest(code=code), self.assertRaises(WorkflowError):
                self.hr.add_employee(code, 'Example', 'Clerk', 'Ops', hired, manager, rate)
        self.assertEqual(len(self.hr.employees()), 1)
        with self.assertRaises(WorkflowError):
            self.manager.add_user('rogue', 'test-password-123', 'hr')
        with self.assertRaises(WorkflowError):
            initialize(self.path, 'replace', 'test-password-123')
        with self.assertRaises(WorkflowError):
            self.hr.balance(999)


if __name__ == '__main__':
    unittest.main()
