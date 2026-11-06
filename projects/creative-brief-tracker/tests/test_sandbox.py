import socket

import pytest

from brief_tracker.airtable import Airtable
from brief_tracker.sandbox import sandbox


def test_real_http_pagination_upsert_and_cleanup():
    with sandbox(page_size=2) as fixture:
        port = fixture["port"]
        with Airtable(
            "appSandbox", "sandbox-only", endpoint=fixture["endpoint"], sleep=lambda _: None
        ) as api:
            rows = [{"Key": str(i), "Name": "Task"} for i in range(13)]
            created = api.upsert("Deliverables", rows)
            api.upsert("Deliverables", [{"Key": "0", "Status": "Done"}])
            listed = api.list_records("Deliverables")
            assert len(listed) == 13
            assert listed[0]["id"] == created[0]["id"]
            assert listed[0]["fields"]["Name"] == "Task"
            assert listed[0]["fields"]["Status"] == "Done"
    with socket.socket() as probe:
        assert probe.connect_ex(("127.0.0.1", port)) != 0
    assert fixture["closed"] is True


def test_cleanup_on_failure():
    with pytest.raises(RuntimeError), sandbox() as fixture:
        raise RuntimeError("simulated test failure")
    assert fixture["closed"] is True
