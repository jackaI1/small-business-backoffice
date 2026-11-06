# Service desk design

I wanted the same report to move through intake, review and completion without copying it between tools. The two screens share the service and workflow definitions in `civic/data/app.json`. The resident gets a private receipt; staff get an authenticated queue with filters and an audit trail.

## Moving parts

- `civic/app.py` validates web requests and protects every staff endpoint with the configured bearer token. Validation failures return a generic message instead of echoing personal input.
- `civic/store.py` opens short-lived SQLite connections. Status changes use a write transaction, check the version, update the record and append an event atomically. Closed requests cannot be reopened. Existing records are retained on restart.
- `civic/static/` contains the responsive, keyboard-usable resident and staff screens. Dynamic content is inserted with `textContent`, not interpreted as HTML. Credentials stay in memory. Staff queue results exclude the resident's private receipt.
- `civic/assistant.py` performs topic retrieval and a conservative query-term evidence gate, then asks a local model to decide if one passage supports the question. Only a boolean `true` and the exact known passage ID permit an answer. The answer is always the complete source passage. The model cannot access tools, the request database or the export client.
- `civic/privacy.py` detects common emails, telephone numbers, postal codes, street addresses and name introductions. Questions containing those patterns are declined before inference. It cannot recognize every possible name or identifier. Export privacy instead uses a strict field allowlist and never includes resident prose.
- `civic/graph.py` posts a new list item or patches the fields of an existing exported item. A SQLite transaction serializes export calls and saves the returned item ID. Redirects are not followed; proxy environment variables are ignored by outbound clients.
- `civic/sandbox.py` implements the small Graph contract needed here, with its own persistent SQLite database and a different bearer token. It rejects fields outside the schema.

## Workflow

```text
submitted -> approved -> in_progress -> resolved
          -> rejected
```

Every arrow requires a staff token, the current integer version and a nonblank note. A rejected or resolved request is terminal. Changing the allowed arrows among these existing statuses in `app.json` changes the dashboard and server validation on restart. Adding an entirely new status also requires updating the API's validation model. This is configuration-driven, not a visual app builder.

## Graph contract

The request paths and body format follow [LifeOS Open's public Graph client](https://github.com/jackaI1/lifeos-open/blob/main/integrations/m365/src/graph-client.ts), specifically `createListItem` and `updateListItemFields`, and [Microsoft's list-item API](https://learn.microsoft.com/en-us/graph/api/listitem-create?view=graph-rest-1.0).

```http
POST /v1.0/sites/demo-city/lists/service-requests/items
Authorization: Bearer <GRAPH_TOKEN>
Content-Type: application/json

{"fields":{"Title":"Service request 12345678","RequestId":"<uuid>","ServiceType":"pothole","Department":"Roads","Status":"submitted","CreatedAt":"<ISO-8601>","UpdatedAt":"<ISO-8601>","Version":1}}
```

The sandbox returns `201` with `{"id":"<item-id>","fields":{...}}`. A later export sends:

```http
PATCH /v1.0/sites/demo-city/lists/service-requests/items/<item-id>/fields
Authorization: Bearer <GRAPH_TOKEN>
Content-Type: application/json

{"Title":"Service request 12345678","RequestId":"<uuid>","ServiceType":"pothole","Department":"Roads","Status":"approved","CreatedAt":"<ISO-8601>","UpdatedAt":"<ISO-8601>","Version":2}
```

`GET` on the collection returns `{"value":[{"id":"...","fields":{...}}]}`. The sandbox implements this small subset only, without Microsoft accounts, list provisioning, pagination or tenant permissions.

| Column | SharePoint-style column type | Meaning |
| --- | --- | --- |
| Title | Text | Generated public-safe label |
| RequestId | Text, unique in a real list | Stable local request UUID |
| ServiceType | Choice | Configured service ID |
| Department | Choice | Configured staff department |
| Status | Choice | Current workflow state |
| CreatedAt | Date/time | UTC intake timestamp |
| UpdatedAt | Date/time | UTC last workflow change |
| Version | Number | Local workflow version |

No Microsoft 365 account is needed. Follow the README's `.env` and two app-server commands to start the emulator in about two minutes after dependency installation. Read the sandbox with:

```sh
set -a; source .env; set +a
curl --fail -H "Authorization: Bearer $GRAPH_TOKEN" \
  'http://127.0.0.1:8091/v1.0/sites/demo-city/lists/service-requests/items'
```

The current adapter intentionally rejects non-loopback endpoints. For an actual tenant, I would first provision the columns, add reviewed OAuth token handling and permissions, enforce the tenant origin and test reconciliation. I have not tested that deployment.

### An uncertain first export

An external service can accept a POST while the response is lost. The app does not blindly retry it. If the first export fails, check the sandbox list by `RequestId` before repeating it. If an item was created, stop the app, set that request's `graph_id` in the local SQLite database to the returned item ID, then restart. Subsequent exports PATCH that item. A crash between the remote POST and local commit has the same uncertainty. Full distributed exactly-once delivery is outside this demo; a production list should enforce a unique RequestId and implement reconciliation.

## Model boundaries

The API uses [Ollama's generate endpoint](https://docs.ollama.com/api/generate) with a JSON schema, zero temperature, a bounded context and output, a 90-second timeout and `keep_alive: 0` to unload after each call. The checked model is `qwen2.5:0.5b`. The live fixture starts its own Ollama instance with cloud use disabled and its own temporary model directory. The model download requires internet; inference does not.

The query-term evidence gate is a routing heuristic, not a calibrated confidence score. It may decline useful paraphrases. A model can also incorrectly judge relevance, so a source quote is still something a resident must read, not a guarantee that every question has been understood. Multi-topic requests and obvious unsupported topics abstain before inference. No chat history, questions or model output are stored. Do not put real resident details into this demonstration.

## Verification and resource ownership

`pytest` uses isolated temporary databases and controlled model responses to test failures deterministically. The real smoke script downloads and runs the model without replacing its responses, starts the app and Graph sandbox on spare loopback ports, and drives one owned browser page through both desks. It saves synthetic-only evidence. CI runs it on Linux as well as the local Mac check.

Each temporary server has an owned process group. `artifacts/resources.json` records its PID, start time, port, cleanup command and final stopped state. Browser processes are recorded with their start metadata; the page, context and browser are explicitly closed. A `finally` block terminates owned servers and checks their ports are closed. Downloaded fixture models and databases are removed when the temporary directory exits. Existing Ollama instances, user tabs and normal app processes are not touched.
