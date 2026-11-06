# internal-controls-tracker

I built a small tracker for financial-close checks to learn how the underlying idea works. This is a learning project.

## What I keep together

- **Process narratives:** short explanations of who prepares, reviews and keeps each record.
- **Risk and control matrix:** a table connecting what could go wrong to the check meant to catch it, its owner, how often it happens and whether I treat it as a key check.
- **Sample selections:** saved lists of records to inspect. The same starting list and seed, a repeatable selection label, give the same selection even if I reorder the input.
- **Results and deficiencies:** a pass or exception for each inspected record. An exception opens a tracked problem with an owner, action and due date. Closure requires a passing retest from a new run for the same control.
- **Evidence requests:** who owes which files, what has arrived and what still needs clarification. A request stays unfinished until files are attached and all follow-ups are resolved.

I keep the original file bytes and a file fingerprint with each result. Moving or deleting the source file does not lose the saved evidence. When I edit a narrative or control, I add a numbered version with a reason instead of overwriting the old wording.

## Trying my own review

I can also start from the small JSON files in `examples/`. JSON is a plain text format with named fields. I edit those files to describe a process, its control and the complete list of occurrences to choose from:

```sh
controls --db practice.sqlite record process examples/process.json
controls --db practice.sqlite record control examples/control.json
controls --db practice.sqlite record population examples/population.json
controls --db practice.sqlite sample POP-BANK-H1 --size 3 --seed my-review \
  --rationale "Inspect three months for this walkthrough" --tester "Internal reviewer"
controls --db practice.sqlite list selections
```

I choose the sample size and write down why. The program does not decide whether that size is enough for an audit. I use [the step-by-step guide](docs/usage.md) to record an exception, gather evidence, change an action plan and close a deficiency after a retest. It includes an exact walkthrough that works without editing any example files.

## How I built it

I use Python for the commands and SQLite, a database stored in one file, for the records. Foreign keys connect a test to an actual saved selection. Transactions save an exception and its deficiency together, so a failure cannot leave half the record behind. The database blocks edits and deletes to original documents, selections, results, evidence and history entries.

I rank each occurrence using SHA-256, a repeatable fingerprint function, applied to the seed and occurrence ID. Each population saves the complete input list, its fingerprint, source notes and the process and control versions used. Later document changes do not rewrite earlier test records. I explain the selection method and record relationships in [my design notes](docs/design.md).

The Excel pack includes the current matrix, request log, follow-ups, deficiencies, populations, selected items, every document version, evidence fingerprints and change history. Due dates are real spreadsheet dates. Filters, frozen headers and wrapped text make the tables easier to inspect. Evidence IDs connect the pack to files I can recover with `controls extract`. The workbook is a snapshot; editing it does not update the database.

## Boundaries I kept explicit

This is a SOX-style exercise, meaning it follows the idea of documenting and testing checks over financial reporting. It is not an audit opinion or a compliance certification. I cannot prove an imported population is complete, judge the seriousness of a deficiency or establish that a sample is sufficient. The example files are fictional training records, not evidence from a real business.

This is a local, single-user tool. Someone who controls the database file can replace it or disable its protections. I have not built logins, independent reviewer permissions, encryption or a tamper-proof archive. I keep backups of the database file after commands finish. `--as-of` evaluates deadlines on the current records; it does not reconstruct what the database looked like on that date. Long fields remain available in JSON; an Excel export fails clearly if a field exceeds Excel's cell limit.

## Tests and limits

There are 5 test source files in this copy. That source count does not establish an execution result. This is a source snapshot, and running it on a new machine may need environment-specific setup.



The relocated workflow did not complete successfully within the migration batch. Local test sources remain available.

No project-specific GitHub Actions workflow was retained. The local test sources remain in this folder.
