import json

import httpx
import pytest

from brief_tracker.airtable import Airtable, AirtableError


def client(handler, sleeps=None):
    return Airtable(
        "appTest",
        "synthetic-token",
        transport=httpx.MockTransport(handler),
        sleep=(sleeps.append if sleeps is not None else lambda _: None),
    )


def test_pagination_and_auth():
    seen = []

    def handler(request):
        seen.append(request)
        assert request.headers["authorization"] == "Bearer synthetic-token"
        if "offset" not in request.url.params:
            return httpx.Response(
                200, json={"records": [{"id": "rec1", "fields": {}}], "offset": "next/page"}
            )
        assert request.url.params["offset"] == "next/page"
        return httpx.Response(200, json={"records": [{"id": "rec2", "fields": {}}]})

    with client(handler) as api:
        assert len(api.list_records("Creative Briefs")) == 2
    assert seen[0].url.path == "/v0/appTest/Creative Briefs"


def test_upsert_batches_and_key():
    sizes = []

    def handler(request):
        body = json.loads(request.content)
        assert request.method == "PATCH"
        assert body["performUpsert"] == {"fieldsToMergeOn": ["Key"]}
        sizes.append(len(body["records"]))
        return httpx.Response(
            200,
            json={"records": [{"id": "rec" + r["fields"]["Key"], **r} for r in body["records"]]},
        )

    with client(handler) as api:
        assert len(api.upsert("Deliverables", [{"Key": str(i)} for i in range(23)])) == 23
    assert sizes == [10, 10, 3]


def test_throttles_and_retries_429():
    sleeps, calls = [], []

    def handler(request):
        calls.append(1)
        return httpx.Response(429 if len(calls) == 1 else 200, json={"records": []})

    with client(handler, sleeps) as api:
        assert api.list_records("Briefs") == []
    assert 30 in sleeps


@pytest.mark.parametrize("status", [401, 403, 422, 500])
def test_errors_bounded_and_redacted(status):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(status, text="synthetic-token private content")

    with client(handler) as api, pytest.raises(AirtableError) as exc:
        api.list_records("Briefs")
    assert "synthetic-token" not in str(exc.value)
    assert "private content" not in str(exc.value)
    assert len(calls) == (3 if status == 500 else 1)


def test_connection_failure_redacted():
    def handler(request):
        raise httpx.ConnectError("synthetic-token", request=request)

    with client(handler) as api, pytest.raises(AirtableError, match="network"):
        api.list_records("Briefs")


def test_empty_upsert_uses_no_request():
    with client(lambda _: pytest.fail("unexpected request")) as api:
        assert api.upsert("Briefs", []) == []


def test_rejects_non_airtable_endpoint_for_live_token():
    with pytest.raises(ValueError):
        Airtable("appTest", "real-secret", endpoint="http://example.com/v0")


def test_schema_creation_is_not_retried_after_uncertain_failure():
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout("uncertain create", request=request)

    with client(handler) as api, pytest.raises(AirtableError):
        api.schema_request("POST", {"name": "Briefs", "fields": []})
    assert len(calls) == 1


def test_repeated_offset_is_rejected():
    def handler(request):
        return httpx.Response(200, json={"records": [], "offset": "same"})

    with client(handler) as api, pytest.raises(AirtableError, match="Repeated"):
        api.list_records("Briefs")
