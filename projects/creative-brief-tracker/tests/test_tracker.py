from copy import deepcopy

import pytest

from brief_tracker.tracker import plan_brief, seed

DATA = {
    "assignees": [
        {"key": "artist", "name": "Avery", "email": "avery@example.test", "capacity_hours": 10}
    ],
    "briefs": [
        {
            "key": "launch",
            "name": "Home opener",
            "due": "2026-11-16",
            "description": "Synthetic campaign",
            "steps": [
                {
                    "key": "poster",
                    "name": "Poster",
                    "assignee": "artist",
                    "days": 2,
                    "hours": 12,
                    "approval": True,
                }
            ],
        }
    ],
}


class MemoryAPI:
    def __init__(self):
        self.tables = {k: [] for k in ("Briefs", "Assignees", "Deliverables", "Approvals")}
        self.writes = 0

    def list_records(self, table):
        return deepcopy(self.tables[table])

    def upsert(self, table, fields):
        self.writes += 1
        result = []
        for value in fields:
            matches = [r for r in self.tables[table] if r["fields"]["Key"] == value["Key"]]
            if matches:
                record = matches[0]
                record["fields"].update(value)
            else:
                record = {"id": f"rec{table}{len(self.tables[table])}", "fields": dict(value)}
                self.tables[table].append(record)
            result.append(deepcopy(record))
        return result


def test_seed_linked_idempotent_preserves_progress():
    api = MemoryAPI()
    seed(api, DATA)
    task = api.tables["Deliverables"][0]
    approval = api.tables["Approvals"][0]
    assert task["fields"]["Brief"] == [api.tables["Briefs"][0]["id"]]
    assert task["fields"]["Assignee"] == [api.tables["Assignees"][0]["id"]]
    assert approval["fields"]["Deliverable"] == [task["id"]]
    task["fields"]["Status"] = "Done"
    approval["fields"]["Status"] = "Approved"
    seed(api, DATA)
    assert [len(api.tables[t]) for t in api.tables] == [1, 1, 1, 1]
    assert task["fields"]["Status"] == "Done"
    assert approval["fields"]["Status"] == "Approved"


def test_replan_changes_dates_keeps_progress():
    api = MemoryAPI()
    seed(api, DATA)
    api.tables["Deliverables"][0]["fields"]["Status"] = "In progress"
    plan_brief(api, "launch", "2026-11-20", DATA["briefs"][0]["steps"])
    assert api.tables["Deliverables"][0]["fields"]["Due"] == "2026-11-20"
    assert api.tables["Approvals"][0]["fields"]["Due"] == "2026-11-20"
    assert api.tables["Deliverables"][0]["fields"]["Status"] == "In progress"


@pytest.mark.parametrize(
    "change",
    [
        "unknown_person",
        "duplicate_person",
        "bad_date",
        "bad_capacity",
        "duplicate_brief",
        "bad_email",
    ],
)
def test_invalid_seed_has_no_writes(change):
    data = deepcopy(DATA)
    if change == "unknown_person":
        data["briefs"][0]["steps"][0]["assignee"] = "missing"
    elif change == "duplicate_person":
        data["assignees"] *= 2
    elif change == "bad_date":
        data["briefs"][0]["due"] = "bad"
    elif change == "duplicate_brief":
        data["briefs"] *= 2
    elif change == "bad_email":
        data["assignees"][0]["email"] = "no-address"
    else:
        data["assignees"][0]["capacity_hours"] = -1
    api = MemoryAPI()
    with pytest.raises(ValueError):
        seed(api, data)
    assert api.writes == 0


def test_replan_refuses_removed_steps_before_write():
    api = MemoryAPI()
    seed(api, DATA)
    before = api.writes
    with pytest.raises(ValueError, match="remove"):
        plan_brief(
            api, "launch", "2026-11-20", [dict(DATA["briefs"][0]["steps"][0], key="different")]
        )
    assert api.writes == before


@pytest.mark.parametrize("description", [["mistyped"], None, 12, {}])
def test_invalid_description_has_no_writes(description):
    data = deepcopy(DATA)
    data["assignees"][0]["capacity_hours"] = 99
    data["briefs"][0]["description"] = description
    api = MemoryAPI()
    with pytest.raises(ValueError, match="description"):
        seed(api, data)
    assert api.writes == 0
