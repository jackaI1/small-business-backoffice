"""Validate plans and synchronize linked records without resetting human progress."""

import re

from .schedule import key, number, parse_date, workback

TABLES = ("Assignees", "Briefs", "Deliverables", "Approvals")


def valid_email(value):
    return (
        isinstance(value, str)
        and re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", value) is not None
    )


def index(records):
    result = {}
    for record in records:
        value = record["fields"].get("Key")
        if value:
            if value in result:
                raise ValueError(f"Duplicate Key in Airtable: {value}")
            result[value] = record
    return result


def _sync(api, table, rows, existing):
    # Default status applies only to new records. User updates survive every rerun.
    values = []
    for row in rows:
        value = dict(row)
        if row["Key"] in existing:
            value.pop("Status", None)
        values.append(value)
    return index(api.upsert(table, values))


def _validate_people(people):
    seen = set()
    for person in people:
        person_key = key(person.get("key"))
        if person_key in seen:
            raise ValueError("Assignee keys must be unique")
        seen.add(person_key)
        if not isinstance(person.get("name"), str) or not person["name"].strip():
            raise ValueError("Assignees need names")
        if not valid_email(person.get("email")):
            raise ValueError("Assignees need a valid email")
        number(person.get("capacity_hours"), "Capacity")
    return seen


def _validate_brief(brief, people):
    key(brief.get("key"))
    if not isinstance(brief.get("description", ""), str):
        raise ValueError("Brief description must be text")
    if not isinstance(brief.get("name"), str) or not brief["name"].strip():
        raise ValueError("Brief needs a name")
    tasks = workback(brief["due"], brief["steps"])
    if any(t["assignee"] not in people for t in tasks):
        raise ValueError("Unknown assignee in review steps")
    return tasks


def _check_removed(brief_key, tasks, deliverables, approvals):
    task_keys = {f"{brief_key}:{t['key']}" for t in tasks}
    approval_keys = {f"{brief_key}:{t['key']}:approval" for t in tasks if t.get("approval")}
    for table, allowed in ((deliverables, task_keys), (approvals, approval_keys)):
        stale = [
            k
            for k, r in table.items()
            if k.startswith(f"{brief_key}:")
            and k not in allowed
            and r["fields"].get("Status") != "Cancelled"
        ]
        if stale:
            raise ValueError(
                "Cannot remove existing steps or approvals; cancel obsolete "
                "records in Airtable first"
            )


def _write_tasks(api, brief, tasks, people, deliverables, approvals):
    brief_id = brief["id"]
    rows = [
        {
            "Key": f"{brief['fields']['Key']}:{t['key']}",
            "Name": t["name"],
            "Brief": [brief_id],
            "Assignee": [people[t["assignee"]]["id"]],
            "Start": t["start"],
            "Due": t["due"],
            "Hours": t["hours"],
            "Status": "Planned",
        }
        for t in tasks
    ]
    saved = _sync(api, "Deliverables", rows, deliverables)
    review_rows = []
    for task, row in zip(tasks, rows, strict=True):
        if task.get("approval"):
            review_rows.append(
                {
                    "Key": row["Key"] + ":approval",
                    "Name": task["name"],
                    "Deliverable": [saved[row["Key"]]["id"]],
                    "Assignee": row["Assignee"],
                    "Due": task["due"],
                    "Status": "Pending",
                }
            )
    _sync(api, "Approvals", review_rows, approvals)
    return list(saved.values())


def seed(api, data):
    """Validate entire input before any write; stable keys make retries safe."""
    people_keys = _validate_people(data["assignees"])
    seen, planned = set(), []
    for brief in data["briefs"]:
        tasks = _validate_brief(brief, people_keys)
        if brief["key"] in seen:
            raise ValueError("Brief keys must be unique")
        seen.add(brief["key"])
        planned.append((brief, tasks))
    existing = {table: index(api.list_records(table)) for table in TABLES}
    for brief, tasks in planned:
        _check_removed(brief["key"], tasks, existing["Deliverables"], existing["Approvals"])
    people = _sync(
        api,
        "Assignees",
        [
            {
                "Key": p["key"],
                "Name": p["name"],
                "Email": p["email"],
                "CapacityHours": p["capacity_hours"],
            }
            for p in data["assignees"]
        ],
        existing["Assignees"],
    )
    briefs = _sync(
        api,
        "Briefs",
        [
            {
                "Key": b["key"],
                "Name": b["name"],
                "Description": b.get("description", ""),
                "Due": parse_date(b["due"]).isoformat(),
                "Status": "Active",
            }
            for b, _ in planned
        ],
        existing["Briefs"],
    )
    for brief, tasks in planned:
        _write_tasks(
            api,
            briefs[brief["key"]],
            tasks,
            people,
            existing["Deliverables"],
            existing["Approvals"],
        )
    return {"briefs": len(planned), "tasks": sum(len(t) for _, t in planned)}


def plan_brief(api, brief_key, due, steps):
    """Replan one existing brief from new ordered steps and a final deadline."""
    key(brief_key)
    existing = {table: index(api.list_records(table)) for table in TABLES}
    if brief_key not in existing["Briefs"]:
        raise ValueError("Unknown brief key")
    brief = existing["Briefs"][brief_key]
    spec = {"key": brief_key, "name": brief["fields"]["Name"], "due": due, "steps": steps}
    tasks = _validate_brief(spec, existing["Assignees"])
    _check_removed(brief_key, tasks, existing["Deliverables"], existing["Approvals"])
    api.upsert("Briefs", [{"Key": brief_key, "Due": parse_date(due).isoformat()}])
    return _write_tasks(
        api, brief, tasks, existing["Assignees"], existing["Deliverables"], existing["Approvals"]
    )
