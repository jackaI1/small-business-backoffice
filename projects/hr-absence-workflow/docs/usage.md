# Usage notes

All records must be fictional. Commands run from the repository root. Options `--db` and `--user` come before the command; command-specific options come after it.

## Passwords and automation

Interactive use asks for passwords without displaying them. For a script, `HRWF_PASSWORD` supplies the current account password and `HRWF_NEW_PASSWORD` supplies a new account password for `user-add`. Passwords must contain 12 to 1024 characters. Do not put real passwords into shell scripts, commit them, or pass them as command arguments.

For example, with the public synthetic demo account:

```sh
HRWF_PASSWORD=synthetic-hr-2026 python3 -m hr_absence employees
```

`init` creates an empty database with the `--user` account as the first HR user. `init --demo` instead creates the documented fixed demo accounts and three synthetic employees. Initialization refuses an existing file. Later commands also refuse a missing database rather than creating an empty one accidentally.

## Command reference

| Command | Purpose | Access |
| --- | --- | --- |
| `user-add NAME --role hr\|manager` | Create a saved account | HR |
| `employee-add CODE NAME --title TEXT --department TEXT --hired YYYY-MM-DD --manager USER --monthly-minutes N [--account USER]` | Add an employee; optionally link their login | HR |
| `employees` | List employee records | HR |
| `file ID` | Show employment details, notes and current balance | HR |
| `note ID TEXT` | Append a dated file note | HR |
| `adjust ID MINUTES --reason TEXT` | Credit or debit a balance | HR |
| `accrue YYYY-MM` | Credit eligible employees for one completed month | HR |
| `audit ID` | List every balance change, in order | HR |
| `events` | List operation history, including non-balance actions | HR |
| `request ID START END` | Record a full-day leave request for an employee | HR or assigned manager |
| `requests` | List all requests or the manager's team requests | HR or assigned manager |
| `decide ID approved\|rejected --reason TEXT` | Decide a pending request | HR or assigned manager, excluding the employee |
| `cancel ID --reason TEXT` | Cancel pending/approved leave; refund an approval | HR or assigned manager |
| `letter ID [--template FILE] [--output FILE]` | Generate a text employment confirmation | HR |
| `export [--output FILE]` | Produce a CSV balance report | HR |

Employee IDs and request IDs are separate. The JSON response from `employee-add` or `request` gives the new ID. Most commands return JSON, a structured text format. `letter` and `export` return their content directly unless an output file is supplied. Errors go to standard error with exit status 2. Successful commands exit with status 0.

## Letter templates

Templates are UTF-8 plain text. The default is `hr_absence/templates/employment.txt`. Use these placeholders:

| Placeholder | Source |
| --- | --- |
| `$employee_code` | Employee reference |
| `$employee_name` | Name |
| `$title` | Position |
| `$department` | Department |
| `$hire_date` | Employment start date |
| `$issued_date` | Current local date |
| `$company` | Fixed fictional company name |
| `$signatory` | Authenticated HR username |

Use `$$` for a literal dollar sign. Unknown placeholders and malformed templates fail without recording a successful letter event. The rendering context never contains file notes, pay information or leave balances. Keep a synthetic-data notice in custom templates too.

## Report columns

Each row covers one employee. `employee_code`, `employee_name` and `department` identify the record. `balance_minutes` is exact; `balance_hours` is rounded to two decimal places for reading. `pending_minutes` and `approved_minutes` total requests in those current states. `accrual_minutes` and `adjustment_minutes` total the corresponding journal entries over all time. Cancelled approvals no longer contribute to `approved_minutes`; the refund remains in the journal.

CSV quoting preserves commas and newlines. Text fields that could be treated as spreadsheet formulas receive a leading apostrophe. Numeric columns remain numeric. The report is one current snapshot, not a payroll period report. `events` records report and letter generation, not proof that a file was delivered elsewhere.

## Local files

Databases and generated outputs are created with owner-only permissions on systems that support them. New files are never overwritten. `.gitignore` excludes databases, `.env`, and the `letters/` and `reports/` folders. Keep generated letters and reports in those folders if you keep them at all. To reset the demo, choose a new `--db` path rather than deleting a file whose contents you still need.
