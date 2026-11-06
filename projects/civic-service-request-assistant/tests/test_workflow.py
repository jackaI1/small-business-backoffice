from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from civic.app import Transition, create_app
from civic.store import Conflict, Store


def submit(client, intake):
    response = client.post("/api/requests", json=intake)
    assert response.status_code == 201
    return response.json()


def test_full_workflow_persists_and_tracks_privately(client, settings, intake, headers):
    receipt = submit(client, intake)
    path = f"/api/staff/requests/{receipt['id']}"
    for version, status in enumerate(["approved", "in_progress", "resolved"], 1):
        response = client.post(
            path + "/status",
            headers=headers,
            json={"status": status, "version": version, "note": "Checked safely"},
        )
        assert response.status_code == 200
        assert response.json()["version"] == version + 1
    with TestClient(create_app(settings)) as restarted:
        row = restarted.get(path, headers=headers).json()
        assert [e["status"] for e in row["events"]] == [
            "submitted",
            "approved",
            "in_progress",
            "resolved",
        ]
        assert row["contact"] == intake["contact"]
        public = restarted.post("/api/track", json={"receipt": receipt["receipt"]}).json()
        assert public["status"] == "resolved"
        assert set(public) == {"id", "status", "created_at", "updated_at"}
        assert "receipt" not in row


def test_rejection_is_terminal(client, intake, headers):
    row = submit(client, intake)
    path = f"/api/staff/requests/{row['id']}/status"
    assert (
        client.post(
            path,
            headers=headers,
            json={"status": "rejected", "version": 1, "note": "Outside city boundary"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            path,
            headers=headers,
            json={"status": "approved", "version": 2, "note": "Attempt reopen"},
        ).status_code
        == 409
    )


def test_no_skipped_approval_or_stale_update(client, intake, headers):
    row = submit(client, intake)
    path = f"/api/staff/requests/{row['id']}"
    for status, version, code in [("resolved", 1, 409), ("approved", 1, 200), ("rejected", 1, 409)]:
        assert (
            client.post(
                path + "/status",
                headers=headers,
                json={"status": status, "version": version, "note": "Review complete"},
            ).status_code
            == code
        )
    assert len(client.get(path, headers=headers).json()["events"]) == 2


def test_concurrent_decisions_only_one_wins(client, settings, intake):
    row = submit(client, intake)

    def change(status):
        try:
            Store(settings.db).transition(
                row["id"], Transition(status=status, version=1, note="Reviewed")
            )
            return "saved"
        except Conflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(change, ["approved", "rejected"])) == ["conflict", "saved"]
    assert len(Store(settings.db).events(row["id"])) == 2


@pytest.mark.parametrize(
    "path,method",
    [
        ("/api/staff/requests", "get"),
        ("/api/staff/requests/missing", "get"),
        ("/api/staff/requests/missing/status", "post"),
        ("/api/staff/requests/missing/export", "get"),
        ("/api/staff/requests/missing/export", "post"),
    ],
)
def test_staff_endpoints_protected(client, path, method):
    kwargs = (
        {"json": {"status": "approved", "version": 1, "note": "Review"}}
        if method == "post" and path.endswith("status")
        else {}
    )
    assert getattr(client, method)(path, **kwargs).status_code == 401


def test_disabled_staff_fails_closed(settings):
    settings.staff_token = ""
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/staff/requests").status_code == 503


@pytest.mark.parametrize(
    "changes",
    [
        {"service": "unknown"},
        {"location": " "},
        {"description": "short"},
        {"contact": "x" * 201},
        {"status": "resolved"},
    ],
)
def test_validation(client, intake, changes):
    assert client.post("/api/requests", json={**intake, **changes}).status_code == 422


def test_filtering_and_receipt_boundary(client, intake, headers):
    row = submit(client, intake)
    assert (
        len(
            client.get(
                "/api/staff/requests?service=pothole&status=submitted", headers=headers
            ).json()
        )
        == 1
    )
    assert client.get("/api/staff/requests?service=park", headers=headers).json() == []
    assert client.post("/api/track", json={"receipt": "x" * 43}).status_code == 404
    assert client.post("/api/track", json={"receipt": row["id"]}).status_code == 404


def test_no_cross_origin_writes_and_security_headers(client, intake):
    assert (
        client.post(
            "/api/requests", headers={"Origin": "https://attacker.invalid"}, json=intake
        ).status_code
        == 403
    )
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert "script-src 'self'" in response.headers["content-security-policy"]


def test_no_blank_notes(client, intake, headers):
    row = submit(client, intake)
    assert (
        client.post(
            f"/api/staff/requests/{row['id']}/status",
            headers=headers,
            json={"status": "approved", "version": 1, "note": " "},
        ).status_code
        == 422
    )
