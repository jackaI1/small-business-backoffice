import json

import httpx
import pytest
from fastapi.testclient import TestClient

from civic.app import create_app
from civic.sandbox import create_sandbox


def test_export_roundtrip_update_persistence_and_privacy(settings, tmp_path, headers, intake):
    path = str(tmp_path / "graph.sqlite3")
    with TestClient(create_sandbox(path, "test-graph")) as sandbox:

        def forward(request):
            response = sandbox.request(
                request.method,
                request.url.path,
                content=request.content,
                headers=dict(request.headers),
            )
            return httpx.Response(response.status_code, json=response.json())

        with httpx.Client(transport=httpx.MockTransport(forward)) as graph:
            with TestClient(create_app(settings, graph_client=graph)) as client:
                intake.update(
                    location="123 Maple Street",
                    description="My name is Ada Sample. Call 519-555-0100.",
                )
                row = client.post("/api/requests", json=intake).json()
                root = f"/api/staff/requests/{row['id']}"
                preview = client.get(root + "/export", headers=headers).json()
                assert set(preview["fields"]) == {
                    "Title",
                    "RequestId",
                    "ServiceType",
                    "Department",
                    "Status",
                    "CreatedAt",
                    "UpdatedAt",
                    "Version",
                }
                text = json.dumps(preview)
                for secret in [intake["contact"], "Maple", "Ada", "519-555", row["receipt"]]:
                    assert secret not in text
                first = client.post(root + "/export", headers=headers).json()
                client.post(
                    root + "/status",
                    headers=headers,
                    json={"status": "approved", "version": 1, "note": "Ada asked for review"},
                )
                again = client.post(root + "/export", headers=headers).json()
                assert first["id"] == again["id"]
                assert again["fields"]["Status"] == "approved"
    with TestClient(create_sandbox(path, "test-graph")) as restarted:
        response = restarted.get(
            "/v1.0/sites/demo-city/lists/service-requests/items",
            headers={"Authorization": "Bearer test-graph"},
        )
        assert len(response.json()["value"]) == 1
        assert response.json()["value"][0]["fields"]["Version"] == 2


def test_graph_failure_is_bounded_no_retry_or_raw_error(settings, intake, headers):
    calls = []

    def fail(request):
        calls.append(request)
        return httpx.Response(503, json={"error": {"message": "private upstream detail"}})

    with httpx.Client(transport=httpx.MockTransport(fail)) as graph:
        with TestClient(create_app(settings, graph_client=graph)) as client:
            row = client.post("/api/requests", json=intake).json()
            response = client.post(f"/api/staff/requests/{row['id']}/export", headers=headers)
            assert response.status_code == 502
            assert "private upstream" not in response.text
            assert len(calls) == 1
            assert client.app.state.store.get(row["id"])["graph_id"] is None


def test_sandbox_rejects_extra_personal_fields(tmp_path):
    with TestClient(create_sandbox(str(tmp_path / "graph.sqlite3"), "test")) as client:
        path = "/v1.0/sites/demo/lists/requests/items"
        assert client.get(path).status_code == 401
        response = client.post(
            path,
            headers={"Authorization": "Bearer test"},
            json={"fields": {"Contact": "private@example.invalid"}},
        )
        assert response.status_code == 422


@pytest.mark.parametrize("body", [None, {}, {"id": None}, {"id": ""}])
def test_malformed_graph_reply_does_not_mark_export_saved(settings, intake, headers, body):
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(201, content=json.dumps(body)))
    ) as graph:
        with TestClient(create_app(settings, graph_client=graph)) as client:
            row = client.post("/api/requests", json=intake).json()
            response = client.post(f"/api/staff/requests/{row['id']}/export", headers=headers)
            assert response.status_code == 502
            assert client.app.state.store.get(row["id"])["graph_id"] is None
