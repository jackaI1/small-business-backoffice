# Rules and saved forms

## Commands

Run `./gradlew workflow -Prequest=<command.json> -Pstore=<forms.json> -Prules=<rules-folder>`. Paths are relative to the project directory unless absolute. Each invocation loads the four rules from disk. The defaults are `examples/create.json`, `build/forms.json` and `rules`.

Create a form with this request. The caller must have the `REQUESTER` role. Amounts must be quoted decimal strings, such as `"6000.00"`. Unquoted JSON numbers are rejected so large integers cannot silently wrap during JSON parsing.

```json
{"operation":"create","actor":{"id":"requester-1","role":"REQUESTER"},"form":{"id":"LAB-001","title":"Shared lab supplies","type":"purchase","amount":"6000.00"}}
```

Submit, approve, reject or cancel with an action request:

```json
{"operation":"action","formId":"LAB-001","action":"submit","actor":{"id":"requester-1","role":"REQUESTER"}}
```

For approval, change `action` to `approve` and use a different person with the current reviewer role. Rejection uses `reject`. A requester uses `cancel` to stop a draft or pending form. There is no administrative override or reopening action.

Read one form with `{"operation":"show","formId":"LAB-001"}`. Read the whole saved notification outbox with `{"operation":"outbox"}`. Reads do not send or remove messages. All commands print JSON. Errors print a diagnostic to standard error and return a nonzero exit code. Unknown commands, missing fields and duplicate IDs are errors.

Form IDs contain 1 to 64 letters, digits, underscores or hyphens. Titles contain 1 to 200 nonblank characters. Actor IDs must be nonblank strings. Supported roles are `REQUESTER`, `SUPERVISOR`, `MANAGER`, `FINANCE` and `IT`. Use a single currency, CAD; no currency conversion happens. Access forms have a zero amount.

## Editing scripts

Each file returns a Groovy closure, a function stored in a variable. The scripts receive maps, collections of named values, and return the following:

| File | Arguments | Return value |
| --- | --- | --- |
| `routing.groovy` | `form` | Nonempty list of distinct reviewer roles |
| `transitions.groovy` | `form, action` | Next status string, or throw for an invalid action |
| `permissions.groovy` | `form, action, actor` | Boolean `true` or `false` |
| `notifications.groovy` | `form, action` | Nonempty list of `{recipient, message}` maps |

The form includes `id`, `title`, `type`, `amount`, `requester`, `status`, `route`, `step` and `history`. The amount is a `BigDecimal`, an exact decimal number. `step` is the zero-based index of the next reviewer. On the final approval it equals the route length. The notification function receives the updated form. Its recipient strings use `user:<id>` or `role:<ROLE>`.

Routing is validated at creation and evaluated again at submission. Only submission saves the route. This means a draft follows the latest threshold, while an already submitted request keeps the approvals it originally needed. Permissions, transitions and notification templates use the current scripts on every command. Review those edits carefully for pending forms. To add a new form type, update routing. To add a new role or status, also update the engine's supported values and tests.

Keep rule files under version control and review changes. Edit a copy of the full rules directory and use `-Prules` to try it with a disposable store. Avoid changing files during an active command; the four files are loaded sequentially, not as a versioned package. Scripts execute with the application's permissions. There is no script sandbox.

## Persistence and limitations

The saved JSON has `forms` keyed by ID and a `notifications` list. Each form keeps its creation and decision history, including actor ID, role, action, timestamp, previous status and new status. Each notification has its own ID, form ID, timestamp, recipient and message. A successful action appends history and outbox messages together.

The engine works on a copy and publishes it only after every rule succeeds. The store locks a sibling `.lock` file, reads the current state, applies the command and writes a temporary file in the same directory. It then atomically replaces the saved file. If the filesystem cannot do an atomic replacement, the command fails instead of falling back to a partial overwrite. Invalid JSON, denied actions, invalid script results and script exceptions leave the previous saved bytes untouched. The lock is released in `finally`; the empty lock file stays so concurrent processes always lock the same file. Do not delete it while commands are running. A busy file reports an error; retry once the other command finishes.

Use local storage with filesystem locking and atomic rename support. This is not a database, a tamper-proof audit log, an identity provider or a mail delivery service. Do not put real personal data in the examples or commit saved stores. Protect real saved files with filesystem permissions. A web or shared service would authenticate callers, restrict reads, queue message delivery with retries and use a database for multi-user storage. The current CLI trusts its local operator, who can already edit the store file directly.
