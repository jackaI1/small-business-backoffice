from email import policy
from email.parser import BytesParser

from test_tracker import DATA, MemoryAPI

from brief_tracker.reminders import build_report, write_drafts
from brief_tracker.tracker import seed


def prepared():
    api = MemoryAPI()
    seed(api, DATA)
    return api


def test_overdue_approval_overload_and_grouped_draft(tmp_path):
    api = prepared()
    report = build_report(api, "2026-11-17", 7)
    assert len(report["overdue_approvals"]) == 1
    assert report["overloaded"][0]["hours"] == 12
    assert report["overloaded"][0]["capacity_hours"] == 10
    assert len(report["drafts"]) == 1
    assert len(report["drafts"][0]["items"]) == 2
    paths = write_drafts(report, tmp_path)
    message = BytesParser(policy=policy.default).parsebytes(paths[0].read_bytes())
    assert message["To"] == "avery@example.test"
    assert "OVERDUE approval" in message.get_content()
    assert "Poster" in message.get_content()
    assert (tmp_path / "report.json").exists()


def test_done_work_and_approved_reviews_are_suppressed():
    api = prepared()
    api.tables["Deliverables"][0]["fields"]["Status"] = "Done"
    api.tables["Approvals"][0]["fields"]["Status"] = "Approved"
    report = build_report(api, "2026-11-17", 7)
    assert report["drafts"] == []
    assert report["overloaded"] == []
    assert report["overdue_approvals"] == []


def test_completed_task_still_has_pending_approval():
    api = prepared()
    api.tables["Deliverables"][0]["fields"]["Status"] = "Done"
    assert len(build_report(api, "2026-11-17", 7)["overdue_approvals"]) == 1


def test_missing_links_and_blank_fields_visible_as_warnings():
    api = prepared()
    api.tables["Deliverables"][0]["fields"].pop("Assignee")
    api.tables["Approvals"][0]["fields"].pop("Due")
    report = build_report(api, "2026-11-17", 7)
    assert len(report["warnings"]) == 2
    assert report["drafts"] == []


def test_missing_email_does_not_make_invalid_draft():
    api = prepared()
    api.tables["Assignees"][0]["fields"].pop("Email")
    report = build_report(api, "2026-11-17", 7)
    assert report["drafts"] == []
    assert report["warnings"]
    assert report["overdue_approvals"]


def test_closed_brief_suppresses_all_child_work():
    api = prepared()
    api.tables["Briefs"][0]["fields"]["Status"] = "Cancelled"
    report = build_report(api, "2026-11-17", 7)
    assert report["drafts"] == report["overloaded"] == report["overdue_approvals"] == []


def test_future_work_outside_window_is_not_reminded():
    assert build_report(prepared(), "2026-11-01", 7)["drafts"] == []


def test_due_today_is_not_overdue():
    report = build_report(prepared(), "2026-11-16", 7)
    assert report["overdue_approvals"] == []
    assert len(report["drafts"]) == 1
    assert all(not item["overdue"] for item in report["drafts"][0]["items"])


def test_output_preserves_edited_draft(tmp_path):
    import pytest

    path = tmp_path / "avery.eml"
    path.write_text("My edited email")
    with pytest.raises(ValueError, match="empty"):
        write_drafts(build_report(prepared(), "2026-11-17", 7), tmp_path)
    assert path.read_text() == "My edited email"


def test_duplicate_person_key_is_warned_instead_of_overwriting_draft():
    from copy import deepcopy

    api = prepared()
    other = deepcopy(api.tables["Assignees"][0])
    other["id"] = "recOther"
    other["fields"]["Email"] = "other@example.test"
    api.tables["Assignees"].append(other)
    task = deepcopy(api.tables["Deliverables"][0])
    task["id"] = "recOtherTask"
    task["fields"]["Assignee"] = ["recOther"]
    api.tables["Deliverables"].append(task)
    report = build_report(api, "2026-11-17", 7)
    assert report["drafts"] == []
    assert any("Duplicate" in warning["reason"] for warning in report["warnings"])
