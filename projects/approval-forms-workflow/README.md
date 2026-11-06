# approval-forms-workflow

I built a form approval tracker to learn how the underlying idea works. This is a learning project.

## Try it

Install Java 21, then run these commands in a terminal:

```sh
./gradlew demo
```

On a Mac with Homebrew, I can install Java with `brew install openjdk@21` and select it with `export JAVA_HOME="$(brew --prefix openjdk@21)"`.

The demo creates a purchase request, submits it, shows a blocked approval by the wrong role, and completes the manager and finance reviews. It prints the saved decisions and messages, then removes its temporary data. No account or email setup is needed. The first run downloads Gradle, the tool that runs the scripts and tests.

## Track a request

I keep one JSON file, a plain text record, for each command I want to run. The examples use fictional people and a shared lab supply request. To create, submit and approve that request:

```sh
./gradlew workflow -Prequest=examples/create.json
./gradlew workflow -Prequest=examples/submit.json
./gradlew workflow -Prequest=examples/approve-manager.json
./gradlew workflow -Prequest=examples/approve-finance.json
./gradlew workflow -Prequest=examples/show.json
./gradlew workflow -Prequest=examples/outbox.json
```

The default saved file is `build/forms.json`. Running the create command twice reports a duplicate ID instead of replacing the form. I use `-Pstore=/path/to/forms.json` to keep a separate file outside the build folder, since `./gradlew clean` deletes the build folder. I copy an example and change its ID, title, type and amount for a new request.

## Who reviews what

Amounts use one currency, CAD, with at most two decimal places. I write them as quoted strings, such as `"6000.00"`, so JSON tools cannot round or wrap large numbers. Zero is allowed; negative amounts are rejected.

| Request | Amount | Review order |
| --- | --- | --- |
| Purchase | Up to $500 | Supervisor |
| Purchase | $500.01 to $5,000 | Manager |
| Purchase | Over $5,000 | Manager, then finance |
| Expense | Up to $100 | Manager |
| Expense | Over $100 | Manager, then finance |
| Access | Must be $0 | IT |

A form starts as `DRAFT`. Its requester can submit it or cancel it. A submitted form is `PENDING`; its current reviewer can approve or reject it, and its requester can cancel it. It becomes `APPROVED` after every review. Approved, rejected and cancelled forms cannot change again.

## Change the rules

I put the decisions in four Groovy scripts, small programs that can use conditions and functions:

- `rules/routing.groovy` chooses reviewers by form type and amount.
- `rules/transitions.groovy` controls which actions can change a form's status.
- `rules/permissions.groovy` checks the person's role, ownership and current review step.
- `rules/notifications.groovy` writes messages for the requester and next reviewer.

The [owner guide](docs/rules-and-storage.md) explains the command format, script inputs, saved history and failure handling.

## What this version does locally

This is a command-line backend, with no web form or sign-in screen. The person and role in each command are supplied by the caller. The permission checks are real, but a shared service would need to get that identity from a trusted sign-in system. The rules folder contains trusted code with access to the computer; it is not a safe place for scripts uploaded by strangers.

Notifications are saved in an outbox, a list of messages waiting to be sent. I can read them with the outbox command. This version does not send email or chat messages. Forms and messages are stored together; the file is intended for local use, not as a shared database.

## Tests and limits

There are 0 test source files in this copy. No test pass count is claimed here: I have not re-run the project suite as part of this move. This is a source snapshot, and running it on a new machine may need environment-specific setup.


Project checks run from this directory through the path-filtered hub workflows: `approval-forms-workflow-ci.yml`.
