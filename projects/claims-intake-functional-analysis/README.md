# claims-intake-functional-analysis

I built a claim intake checker to learn how the underlying idea works. This is a learning project.

## What I wanted to decide

I compared a manual checklist, a shared spreadsheet and rules-assisted intake. The [short decision note](docs/decision-summary.md) explains my recommendation, costs, risks and what would change the decision. At an assumed 1,000 submissions per month and 30% needing review, the assisted option estimates 95 handling hours per month versus 200 manually. These are planning assumptions, not measured savings.

I chose to build the assisted option so I could test the written requirements against actual results. The [functional analysis](docs/functional-analysis.md) includes the current and future process maps, people involved, inputs, business rules and limits. The [requirements template](docs/requirements-template.md) is reusable; the [completed catalogue](docs/requirements.json) holds the 15 requirements for this process.

## Follow a claim through review

The third sample record has a blank description. I can record a follow-up action using its internal record number:

```sh
python3 -m claims_intake --db demo.sqlite show 3
python3 -m claims_intake --db demo.sqlite review 3 --action request_information --reviewer DEMO-R01
python3 -m claims_intake --db demo.sqlite summary
```

Now 9 records remain pending. The original reasons remain stored, along with who recorded the action and when. Other actions are `refer_adjuster` and `close_duplicate`; closing as a duplicate requires a duplicate/conflict flag. Actions record triage, not a completed claim investigation. One action is allowed per flagged record. A corrected submission gets its own version for a person to compare; it does not silently clear previous flags.

The `show` command displays the submitted details, audit history, recorded review action and related record numbers. I can open those numbers with `show` too when I need to compare a conflict. Related numbers are navigation hints; they do not change earlier routing decisions.

To try my own synthetic examples, I copy [samples/claims.json](samples/claims.json), edit the details and submit the new file with an explicit evaluation date. The [data contract and rule table](docs/functional-analysis.md#data-contract) explain accepted fields. Amounts are whole cents, dates use YYYY-MM-DD and evidence labels stand in for documents. Remove the local `demo.sqlite` file when finished, or choose another database filename for a fresh run.

## How the pieces fit

The command line reads a JSON file, a plain text format for structured records. [core.py](claims_intake/core.py) checks the rules and stores results in SQLite, a database held in one local file. Each new submission stores its original contents, reasons and an audit event. A batch either saves completely or saves nothing. Exact retries return the original decision, while a changed submission under an existing reference or a possible repeated loss goes to review.

## Tests and limits

There are 3 test source files in this copy. No test pass count is claimed here: I have not re-run the project suite as part of this move. This is a source snapshot, and running it on a new machine may need environment-specific setup.


Project checks run from this directory through the path-filtered hub workflows: `claims-intake-functional-analysis-qa.yml`.

Generated output omitted: reports/ (generated output).
