"""Explicit fictional fixtures, never real employee data."""
from .service import Workflow, initialize

DEMO_ACCOUNTS = {'hr': 'synthetic-hr-2026', 'mgr-north': 'synthetic-north-2026', 'mgr-south': 'synthetic-south-2026'}


def create_demo(path):
    initialize(path, 'hr', DEMO_ACCOUNTS['hr'])
    with Workflow.login(path, 'hr', DEMO_ACCOUNTS['hr']) as workflow:
        for username in ('mgr-north', 'mgr-south'):
            workflow.add_user(username, DEMO_ACCOUNTS[username], 'manager')
        for code, name, title, department, manager, user in [
            ('SYN-001', 'Alex Example', 'Lab Assistant', 'Research', 'mgr-north', None),
            ('SYN-002', 'Sam Sample', 'Coordinator', 'Operations', 'mgr-south', None),
            ('SYN-003', 'Morgan Example', 'Team Lead', 'Research', 'mgr-north', 'mgr-north'),
        ]:
            employee_id = workflow.add_employee(code, name, title, department, '2026-01-01', manager, 600, user=user)
            workflow.add_file_note(employee_id, 'Synthetic onboarding record: fictional full-time employee.')
            workflow.adjust(employee_id, 4800, 'Synthetic opening balance: 80 hours')
