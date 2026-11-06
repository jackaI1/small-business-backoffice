"""Read current table state, report deadline risks, and save unsent email drafts."""

import json
from collections import Counter, defaultdict
from datetime import timedelta
from email import policy
from email.message import EmailMessage
from pathlib import Path

from .schedule import key, number, parse_date
from .tracker import valid_email

CLOSED = {"Done", "Cancelled", "Approved"}


def build_report(api, today, days=7):
    if type(days) is not int or not 1 <= days <= 366:
        raise ValueError("days must be an integer from 1 to 366")
    today = parse_date(today)
    end = today + timedelta(days=days - 1)
    records = {
        table: api.list_records(table)
        for table in ("Assignees", "Briefs", "Deliverables", "Approvals")
    }
    people = {r["id"]: r["fields"] for r in records["Assignees"]}
    person_keys = Counter(p.get("Key") for p in people.values() if isinstance(p.get("Key"), str))
    briefs = {r["id"]: r["fields"] for r in records["Briefs"]}
    tasks = {r["id"]: r["fields"] for r in records["Deliverables"]}
    report = {
        "as_of": today.isoformat(),
        "through": end.isoformat(),
        "overdue_approvals": [],
        "overloaded": [],
        "warnings": [],
        "drafts": [],
    }
    grouped, hours = defaultdict(list), defaultdict(float)

    def warning(record, reason):
        report["warnings"].append({"record": record["id"], "reason": reason})

    def linked(fields, name, available):
        links = fields.get(name, [])
        return links[0] if len(links) == 1 and links[0] in available else None

    for table in ("Deliverables", "Approvals"):
        for record in records[table]:
            f = record["fields"]
            if f.get("Status") in CLOSED:
                continue
            task = f
            if table == "Approvals":
                task_id = linked(f, "Deliverable", tasks)
                if task_id is None:
                    warning(record, "Approval needs one existing deliverable")
                    continue
                task = tasks[task_id]
                if task.get("Status") == "Cancelled":
                    continue
            brief_id = linked(task, "Brief", briefs)
            if brief_id is None:
                warning(record, "Task needs one existing brief")
                continue
            if briefs[brief_id].get("Status") in CLOSED:
                continue
            try:
                due = parse_date(f.get("Due", ""))
            except (ValueError, TypeError):
                warning(record, "Missing or invalid Due date")
                continue
            item = {
                "id": record["id"],
                "kind": "approval" if table == "Approvals" else "task",
                "name": f.get("Name", record["id"]),
                "brief": briefs[brief_id].get("Name", brief_id),
                "due": due.isoformat(),
                "overdue": due < today,
            }
            if table == "Approvals" and due < today:
                report["overdue_approvals"].append(item)
            person_id = linked(f, "Assignee", people)
            if person_id is None:
                warning(record, "Needs one existing assignee")
                continue
            if table == "Deliverables":
                try:
                    start = parse_date(f.get("Start", ""))
                    effort = number(f.get("Hours", 0), "Hours")
                    if start > due:
                        raise ValueError("Start after Due")
                    if start <= end:
                        hours[person_id] += effort
                except (ValueError, TypeError):
                    warning(record, "Invalid Start or Hours; excluded from capacity")
            if due <= end:
                grouped[person_id].append(item)

    for person_id, effort in sorted(hours.items()):
        person = people[person_id]
        try:
            capacity = number(person.get("CapacityHours"), "CapacityHours")
        except ValueError:
            report["warnings"].append({"record": person_id, "reason": "Invalid CapacityHours"})
            continue
        if effort > capacity:
            report["overloaded"].append(
                {
                    "assignee": person.get("Name", person_id),
                    "hours": effort,
                    "capacity_hours": capacity,
                }
            )

    for person_id, items in sorted(grouped.items()):
        person = people[person_id]
        if not valid_email(person.get("Email")):
            report["warnings"].append({"record": person_id, "reason": "Missing or invalid Email"})
            continue
        try:
            person_key = key(person.get("Key"))
        except ValueError:
            report["warnings"].append({"record": person_id, "reason": "Missing or invalid Key"})
            continue
        if person_keys[person_key] > 1:
            report["warnings"].append({"record": person_id, "reason": "Duplicate assignee Key"})
            continue
        report["drafts"].append(
            {
                "key": person_key,
                "name": person.get("Name", person_key),
                "email": person["Email"],
                "items": sorted(items, key=lambda i: (i["due"], i["id"])),
            }
        )
    return report


def write_drafts(report, output):
    """Create one .eml per person and a JSON report. This never sends email.

    Refuse an occupied output directory so a shorter subsequent run cannot leave
    old drafts that appear current, or overwrite an owner's edited message.
    """
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Output directory must be empty; choose a new dated folder")
    output.mkdir(parents=True, exist_ok=True)
    paths = []
    for draft in report["drafts"]:
        person_key = key(draft["key"])
        message = EmailMessage(policy=policy.SMTP)
        message["To"] = draft["email"]
        message["Subject"] = f"Creative deadlines through {report['through']}"
        lines = [f"Hi {draft['name']},", "", "Please check these creative deadlines:"]
        for item in draft["items"]:
            label = "OVERDUE " if item["overdue"] else ""
            lines.append(
                f"- {label}{item['kind']}: {item['name']} ({item['brief']}), due {item['due']}"
            )
        lines.extend(["", "Please flag any blockers or changes to these dates."])
        message.set_content("\n".join(lines) + "\n")
        path = output / f"{person_key}.eml"
        path.write_bytes(message.as_bytes())
        paths.append(path)
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return paths
