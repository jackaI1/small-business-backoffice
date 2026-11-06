import json

import httpx
import pytest

from brief_tracker.airtable import Airtable
from brief_tracker.setup import setup_tables


def test_create_tables_in_link_order():
    saved = []

    def handler(request):
        assert request.url.path == "/v0/meta/bases/appTest/tables"
        if request.method == "GET":
            return httpx.Response(200, json={"tables": saved})
        body = json.loads(request.content)
        for field in body["fields"]:
            if field["type"] == "multipleRecordLinks":
                assert field["options"]["linkedTableId"] in [t["id"] for t in saved]
        saved.append({"id": f"tbl{len(saved)}", **body})
        return httpx.Response(200, json=saved[-1])

    with Airtable(
        "appTest", "fake", transport=httpx.MockTransport(handler), sleep=lambda _: None
    ) as api:
        assert setup_tables(api) == ["Assignees", "Briefs", "Deliverables", "Approvals"]
        assert setup_tables(api) == []
    assert len(saved) == 4
    assert saved[2]["fields"][0] == {"name": "Key", "type": "singleLineText"}


def test_setup_refuses_incompatible_existing_table():
    def handler(request):
        assert request.method == "GET"
        return httpx.Response(
            200, json={"tables": [{"id": "tblPeople", "name": "Assignees", "fields": []}]}
        )

    with (
        Airtable(
            "appTest", "fake", transport=httpx.MockTransport(handler), sleep=lambda _: None
        ) as api,
        pytest.raises(ValueError, match="schema"),
    ):
        setup_tables(api)
