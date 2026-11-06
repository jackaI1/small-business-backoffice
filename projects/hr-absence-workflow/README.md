# hr-absence-workflow

I built a small HR absence-balance tracker to learn how the underlying idea works. This is a learning project.

## Try a leave request

The demo starts with three employees, each with 80 hours. Employee 1 is Alex Example, managed by `mgr-north`. I submit and approve two weekdays of leave using the manager password `synthetic-north-2026`:

```sh
python3 -m hr_absence --user mgr-north request 1 2026-11-09 2026-11-10
python3 -m hr_absence --user mgr-north requests
python3 -m hr_absence --user mgr-north decide 1 approved --reason "Team coverage arranged"
```

Each command prompts for a password. These commands use `hr-demo.db` by default. For a different file, I put `--db PATH` before the command.

Alex now has 64 hours. I check the full file and balance history as HR, then save a letter and report:

```sh
python3 -m hr_absence file 1
python3 -m hr_absence audit 1
python3 -m hr_absence letter 1 --output employment-example.txt
python3 -m hr_absence export --output balances-example.csv
```

The HR password is `synthetic-hr-2026`. Letters and reports refuse to overwrite existing files. The letter is plain text, clearly marked as a synthetic demonstration. I can print it or copy it into a document editor. The report includes exact minutes and a readable hours total.

To reverse the approved leave, I run:

```sh
python3 -m hr_absence --user mgr-north cancel 1 --reason "Plans changed"
```

That returns 16 hours to Alex and adds a separate refund entry. The original approval stays in the history.

## Keep records and balances

I use these HR commands with the same demo database:

```sh
python3 -m hr_absence note 1 "Synthetic onboarding check completed"
python3 -m hr_absence accrue 2026-10
python3 -m hr_absence adjust 1 -60 --reason "Correct a synthetic opening balance"
python3 -m hr_absence events
```

`accrue` adds each employee's monthly allowance after a calendar month has finished. Running the same month twice adds nothing the second time. A person hired partway through that month waits until their first complete month. Demo employees receive 600 minutes, or 10 hours, per full month.

`adjust` accepts a signed whole number of minutes and requires a reason. Corrections cannot leave a negative balance. Pending requests do not reserve hours, so approval checks the balance again. A manager can reject a request with `decide ID rejected --reason "..."` without changing the balance.

## Accounts and employee files

The demo accounts are deliberately public and must only be used with synthetic data:

| Account | Password | View |
| --- | --- | --- |
| `hr` | `synthetic-hr-2026` | All employee files, balances, requests, letters and reports |
| `mgr-north` | `synthetic-north-2026` | Requests for employees 1 and 3 |
| `mgr-south` | `synthetic-south-2026` | Requests for employee 2 |

Managers can enter and decide requests for their team, but cannot see private file notes, hire dates or balance reports. Employee 3 is linked to the north manager's account, so that manager cannot approve their own leave. HR must decide it.

For a separate synthetic dataset, I create an empty file and add saved accounts and employees:

```sh
python3 -m hr_absence --db practice.db --user hr init
python3 -m hr_absence --db practice.db user-add team-lead --role manager
python3 -m hr_absence --db practice.db employee-add SYN-004 "Taylor Example" \
  --title "Coordinator" --department "Operations" --hired 2026-01-01 \
  --manager team-lead --monthly-minutes 600
```

The first command sets an HR password; `user-add` asks for both the current HR password and the new account password. If an employee also has an account, I add `--account USERNAME` when creating their record so self-approval is blocked. Employee codes and linked accounts must be unique. File notes are added as new entries instead of replacing previous notes.

I can customize letters with `letter ID --template path/to/template.txt`. The supported fields and all command details are in [the usage notes](docs/usage.md). `python3 -m hr_absence --help` lists commands, and each command accepts `--help`.

## Rules and limits

I chose one leave pool, full weekdays and eight hours per day. Weekends do not use hours; public holidays still count as weekdays. Requests use inclusive dates, cannot overlap pending or approved leave, cannot start before employment, and cannot span more than 366 calendar days. Requests can be recorded after the fact for reconciliation. Cancellation is allowed for pending or approved leave and refunds an approval only once.

This is a local learning project, not a payroll system or a hosted employee portal. It does not calculate statutory entitlements, prorate partial months, handle termination or edit employment details after creation. Accounts cannot be reset or disabled through the app yet. I only use synthetic records. Someone who controls the database file can change it outside the app, so the role checks and history are not a security boundary against the computer's owner. I describe the storage and transaction choices in [the design notes](docs/design.md).

## Tests and limits

There are 3 test source files in this copy. No test pass count is claimed here: I have not re-run the project suite as part of this move. This is a source snapshot, and running it on a new machine may need environment-specific setup.


Project checks run from this directory through the path-filtered hub workflows: `hr-absence-workflow-test.yml`.
