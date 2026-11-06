"""Validated financial-close workflows, independent of the CLI or Excel export."""

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path

from .db import TABLES, connect

FREQUENCIES = {"daily", "weekly", "monthly", "quarterly", "annually", "per-transaction"}
ALGORITHM = "sha256-rank-v1"
MAX_EVIDENCE_BYTES = 10 * 1024 * 1024


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def now():
    return datetime.now(UTC).isoformat(timespec="microseconds")


def text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    if "\x00" in value:
        raise ValueError(f"{label} cannot contain a null character")
    return value.strip()


def iso_date(value, label):
    value = text(value, label)
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{label} must be a real YYYY-MM-DD date") from None
    if parsed.isoformat() != value:
        raise ValueError(f"{label} must use YYYY-MM-DD")
    return value


class Tracker:
    def __init__(self, path):
        self.path = Path(path)
        self.db = connect(self.path)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.db.close()

    def _one(self, table, id):
        if table not in TABLES:
            raise ValueError("Unknown table")
        row = self.db.execute(f"SELECT * FROM {table} WHERE id=?", (id,)).fetchone()
        if row is None:
            raise ValueError(f"No {table} record {id}")
        return dict(row)

    def _event(self, entity, entity_id, action, actor, detail):
        self.db.execute(
            "INSERT INTO events(entity,entity_id,action,actor,detail,created_at) "
            "VALUES(?,?,?,?,?,?)",
            (entity, str(entity_id), action, text(actor, "actor"), canonical(detail), now()),
        )

    def rows(self, table):
        """Stable snapshots with evidence metadata only, never raw file bytes."""
        if table not in TABLES:
            raise ValueError("Unknown table")
        columns = "id,filename,sha256,size_bytes,actor,created_at" if table == "evidence" else "*"
        return [dict(r) for r in self.db.execute(f"SELECT {columns} FROM {table} ORDER BY rowid")]

    def document(self, kind, id, version=None):
        query = "SELECT * FROM documents WHERE kind=? AND id=?"
        params = [kind, id]
        if version is not None:
            query += " AND version=?"
            params.append(version)
        row = self.db.execute(query + " ORDER BY version DESC LIMIT 1", params).fetchone()
        if row is None:
            raise ValueError(f"No {kind} document {id}")
        return dict(row)

    def _save_document(self, kind, payload, author, reason):
        author, reason = text(author, "author"), text(reason, "reason")
        with self.db:
            version = self.db.execute(
                "SELECT COALESCE(MAX(version),0)+1 FROM documents WHERE kind=? AND id=?",
                (kind, payload["id"]),
            ).fetchone()[0]
            self.db.execute(
                "INSERT INTO documents VALUES(?,?,?,?,?,?,?)",
                (kind, payload["id"], version, canonical(payload), author, reason, now()),
            )
            self._event(
                kind,
                payload["id"],
                "document_version_added",
                author,
                {"version": version, "reason": reason},
            )
        return version

    def save_process(self, *, id, name, narrative, author, reason):
        payload = {
            k: text(v, k) for k, v in {"id": id, "name": name, "narrative": narrative}.items()
        }
        return self._save_document("process", payload, author, reason)

    def save_control(
        self,
        *,
        id,
        process_id,
        risk,
        description,
        owner,
        frequency,
        key,
        assertion,
        test_procedure,
        evidence_expected,
        author,
        reason,
    ):
        payload = {
            k: text(v, k)
            for k, v in dict(
                id=id,
                process_id=process_id,
                risk=risk,
                description=description,
                owner=owner,
                frequency=frequency,
                assertion=assertion,
                test_procedure=test_procedure,
                evidence_expected=evidence_expected,
            ).items()
        }
        if type(key) is not bool:
            raise ValueError("key must be true or false")
        if frequency not in FREQUENCIES:
            raise ValueError(f"frequency must be one of {', '.join(sorted(FREQUENCIES))}")
        payload["key"] = key
        self.document("process", payload["process_id"])
        previous = self.db.execute(
            "SELECT payload FROM documents WHERE kind='control' AND id=? LIMIT 1",
            (payload["id"],),
        ).fetchone()
        if previous and json.loads(previous[0])["process_id"] != payload["process_id"]:
            raise ValueError("A control cannot move between processes. Use a new control ID.")
        return self._save_document("control", payload, author, reason)

    def add_population(
        self, *, id, control_id, period_start, period_end, source, reconciliation, items
    ):
        id, control_id = text(id, "id"), text(control_id, "control_id")
        start, end = iso_date(period_start, "period_start"), iso_date(period_end, "period_end")
        if start > end:
            raise ValueError("period_start must be on or before period_end")
        source = text(source, "source")
        reconciliation = text(reconciliation, "reconciliation")
        if not isinstance(items, list) or not items:
            raise ValueError("items must be a non-empty list")
        cleaned, seen = [], set()
        for item in items:
            if not isinstance(item, dict) or set(item) != {"id", "date", "description"}:
                raise ValueError("Each item needs exactly id, date and description")
            item_id = text(item["id"], "item.id")
            item_date = iso_date(item["date"], "item.date")
            if item_id in seen:
                raise ValueError(f"Duplicate population item {item_id}")
            if not start <= item_date <= end:
                raise ValueError(f"Item {item_id} is outside the population period")
            seen.add(item_id)
            cleaned.append(
                dict(
                    id=item_id,
                    date=item_date,
                    description=text(item["description"], "item.description"),
                )
            )
        control = self.document("control", control_id)
        process_id = json.loads(control["payload"])["process_id"]
        process = self.document("process", process_id)
        payload = canonical(sorted(cleaned, key=lambda i: i["id"]))
        with self.db:
            self.db.execute(
                "INSERT INTO populations VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    id,
                    control_id,
                    control["version"],
                    process_id,
                    process["version"],
                    start,
                    end,
                    source,
                    reconciliation,
                    payload,
                    hashlib.sha256(payload.encode()).hexdigest(),
                    now(),
                ),
            )
        return id

    def sample(self, *, population_id, size, seed, rationale, tester):
        seed, rationale, tester = (
            text(seed, "seed"),
            text(rationale, "rationale"),
            text(tester, "tester"),
        )
        pop = self._one("populations", population_id)
        items = json.loads(pop["payload"])
        if type(size) is not int or not 1 <= size <= len(items):
            raise ValueError(f"size must be an integer between 1 and {len(items)}")
        ordered = sorted(
            items,
            key=lambda item: (
                hashlib.sha256(canonical([seed, item["id"]]).encode()).hexdigest(),
                item["id"],
            ),
        )
        with self.db:
            cursor = self.db.execute(
                "INSERT INTO runs(population_id,seed,size,rationale,tester,algorithm,created_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (population_id, seed, size, rationale, tester, ALGORITHM, now()),
            )
            run_id = cursor.lastrowid
            self.db.executemany(
                "INSERT INTO selections VALUES(?,?,?)",
                ((run_id, item["id"], rank) for rank, item in enumerate(ordered[:size], 1)),
            )
        return run_id

    def selected(self, run_id):
        self._one("runs", run_id)
        return [
            dict(r)
            for r in self.db.execute(
                "SELECT * FROM selections WHERE run_id=? ORDER BY rank", (run_id,)
            )
        ]

    def _evidence(self, file, actor):
        actor = text(actor, "actor")
        path = Path(file)
        # Bounded read prevents large inputs from exhausting memory even if the file grows.
        with path.open("rb") as handle:
            content = handle.read(MAX_EVIDENCE_BYTES + 1)
        if not content or len(content) > MAX_EVIDENCE_BYTES:
            raise ValueError("Evidence must contain between 1 byte and 10 MiB")
        return self.db.execute(
            "INSERT INTO evidence(filename,content,sha256,size_bytes,actor,created_at) "
            "VALUES(?,?,?,?,?,?)",
            (path.name, content, hashlib.sha256(content).hexdigest(), len(content), actor, now()),
        ).lastrowid

    def extract_evidence(self, evidence_id, path):
        row = self._one("evidence", evidence_id)
        if hashlib.sha256(row["content"]).hexdigest() != row["sha256"]:
            raise ValueError("Evidence hash mismatch")
        with Path(path).open("xb") as handle:
            handle.write(row["content"])

    def record_result(
        self,
        *,
        run_id,
        item_id,
        outcome,
        notes,
        tester,
        evidence_file,
        owner=None,
        due=None,
        remediation=None,
    ):
        notes, tester = text(notes, "notes"), text(tester, "tester")
        if outcome not in {"pass", "exception"}:
            raise ValueError("outcome must be pass or exception")
        if not self.db.execute(
            "SELECT 1 FROM selections WHERE run_id=? AND item_id=?", (run_id, item_id)
        ).fetchone():
            raise ValueError("Result item must belong to the saved sample selection")
        if outcome == "exception":
            owner, due, remediation = (
                text(owner, "owner"),
                iso_date(due, "due"),
                text(remediation, "remediation"),
            )
        elif any(v is not None for v in (owner, due, remediation)):
            raise ValueError("Remediation fields only apply to exception results")
        with self.db:
            evidence_id = self._evidence(evidence_file, tester)
            rid = self.db.execute(
                "INSERT INTO results(run_id,item_id,outcome,notes,tester,evidence_id,created_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (run_id, item_id, outcome, notes, tester, evidence_id, now()),
            ).lastrowid
            if outcome == "exception":
                did = self.db.execute(
                    "INSERT INTO deficiencies(result_id,owner,due,action,created_at) "
                    "VALUES(?,?,?,?,?)",
                    (rid, owner, due, remediation, now()),
                ).lastrowid
                self._event(
                    "deficiency",
                    did,
                    "deficiency_opened",
                    tester,
                    dict(result_id=rid, owner=owner, due=due, action=remediation),
                )
            self._event(
                "result",
                rid,
                "result_recorded",
                tester,
                dict(outcome=outcome, evidence_id=evidence_id),
            )
        return rid

    def remediate(self, *, deficiency_id, owner, due, action, actor):
        deficiency = self._one("deficiencies", deficiency_id)
        if deficiency["status"] != "open":
            raise ValueError("Only an open deficiency can be updated")
        plan = dict(
            owner=text(owner, "owner"), due=iso_date(due, "due"), action=text(action, "action")
        )
        with self.db:
            self.db.execute(
                "UPDATE deficiencies SET owner=?,due=?,action=? WHERE id=?",
                (*plan.values(), deficiency_id),
            )
            self._event("deficiency", deficiency_id, "remediation_updated", actor, plan)

    def close_deficiency(self, *, deficiency_id, retest_result_id, reviewer, notes):
        deficiency = self._one("deficiencies", deficiency_id)
        if deficiency["status"] != "open":
            raise ValueError("Deficiency is already closed")
        original = self._one("results", deficiency["result_id"])
        retest = self._one("results", retest_result_id)
        run = self._one("runs", original["run_id"])
        retest_run = self._one("runs", retest["run_id"])
        pop = self._one("populations", run["population_id"])
        retest_pop = self._one("populations", retest_run["population_id"])
        if (
            retest["outcome"] != "pass"
            or retest_run["created_at"] <= original["created_at"]
            or retest_pop["control_id"] != pop["control_id"]
        ):
            raise ValueError(
                "Closure needs a passing retest for the same control from a run "
                "created after the exception"
            )
        resolution = dict(
            retest_result_id=retest_result_id,
            reviewer=text(reviewer, "reviewer"),
            notes=text(notes, "notes"),
            closed_at=now(),
        )
        with self.db:
            self.db.execute(
                "UPDATE deficiencies SET status='closed',resolution=? WHERE id=?",
                (canonical(resolution), deficiency_id),
            )
            self._event("deficiency", deficiency_id, "deficiency_closed", reviewer, resolution)

    def add_request(self, *, id, control_id, description, owner, due, requested_by):
        values = [
            text(v, k)
            for k, v in dict(
                id=id, control_id=control_id, description=description, owner=owner
            ).items()
        ]
        due, requested_by = iso_date(due, "due"), text(requested_by, "requested_by")
        self.document("control", values[1])
        with self.db:
            self.db.execute(
                "INSERT INTO requests(id,control_id,description,owner,due,requested_by,"
                "created_at) VALUES(?,?,?,?,?,?,?)",
                (*values, due, requested_by, now()),
            )
            self._event("request", values[0], "request_opened", requested_by, {"due": due})
        return values[0]

    def _open_request(self, request_id):
        row = self._one("requests", request_id)
        if row["status"] == "fulfilled":
            raise ValueError("Request is already fulfilled. Create a new request for new work.")
        return row

    def attach_evidence(self, *, request_id, file, actor):
        self._open_request(request_id)
        with self.db:
            eid = self._evidence(file, actor)
            self.db.execute("INSERT INTO request_evidence VALUES(?,?)", (request_id, eid))
            self.db.execute("UPDATE requests SET status='received' WHERE id=?", (request_id,))
            self._event("request", request_id, "evidence_received", actor, {"evidence_id": eid})
        return eid

    def add_followup(self, *, request_id, description, owner, due, actor):
        self._open_request(request_id)
        description, owner = text(description, "description"), text(owner, "owner")
        due = iso_date(due, "due")
        with self.db:
            fid = self.db.execute(
                "INSERT INTO followups(request_id,description,owner,due,created_at) "
                "VALUES(?,?,?,?,?)",
                (request_id, description, owner, due, now()),
            ).lastrowid
            self._event(
                "followup",
                fid,
                "followup_opened",
                actor,
                dict(request_id=request_id, description=description, owner=owner, due=due),
            )
        return fid

    def resolve_followup(self, *, followup_id, actor, notes):
        row = self._one("followups", followup_id)
        if row["status"] != "open":
            raise ValueError("Follow-up is already resolved")
        resolution = dict(actor=text(actor, "actor"), notes=text(notes, "notes"), resolved_at=now())
        with self.db:
            self.db.execute(
                "UPDATE followups SET status='resolved',resolution=? WHERE id=?",
                (canonical(resolution), followup_id),
            )
            self._event("followup", followup_id, "followup_resolved", actor, resolution)

    def fulfill_request(self, *, request_id, actor, notes):
        self._open_request(request_id)
        notes = text(notes, "notes")
        if not self.db.execute(
            "SELECT 1 FROM request_evidence WHERE request_id=?", (request_id,)
        ).fetchone():
            raise ValueError("Request needs evidence before fulfillment")
        if self.db.execute(
            "SELECT 1 FROM followups WHERE request_id=? AND status='open'", (request_id,)
        ).fetchone():
            raise ValueError("Resolve open follow-ups before fulfillment")
        with self.db:
            self.db.execute("UPDATE requests SET status='fulfilled' WHERE id=?", (request_id,))
            self._event("request", request_id, "request_fulfilled", actor, {"notes": notes})

    def status(self, as_of):
        as_of = iso_date(as_of, "as_of")
        summary = {"as_of": as_of}
        for table, completed in (
            ("requests", "fulfilled"),
            ("followups", "resolved"),
            ("deficiencies", "closed"),
        ):
            rows = [r for r in self.rows(table) if r["status"] != completed]
            summary[f"open_{table}"] = len(rows)
            summary[f"overdue_{table}"] = sum(r["due"] < as_of for r in rows)
        summary["untested_samples"] = self.db.execute(
            "SELECT COUNT(*) FROM selections s LEFT JOIN results r "
            "ON s.run_id=r.run_id AND s.item_id=r.item_id WHERE r.id IS NULL"
        ).fetchone()[0]
        summary["pass_results"] = self.db.execute(
            "SELECT COUNT(*) FROM results WHERE outcome='pass'"
        ).fetchone()[0]
        summary["exception_results"] = self.db.execute(
            "SELECT COUNT(*) FROM results WHERE outcome='exception'"
        ).fetchone()[0]
        return summary
