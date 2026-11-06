import json

import httpx
import pytest
from fastapi.testclient import TestClient

from civic.app import create_app
from civic.settings import Settings


@pytest.fixture
def settings(tmp_path):
    return Settings(
        db=str(tmp_path / "requests.sqlite3"), staff_token="test-staff", graph_token="test-graph"
    )


@pytest.fixture
def model():
    calls = []

    def respond(request):
        body = json.loads(request.content)
        calls.append(body)
        passage = json.loads(body["prompt"])
        return httpx.Response(
            200,
            json={"response": json.dumps({"supported": True, "passage_id": passage["passage_id"]})},
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        yield client, calls


@pytest.fixture
def client(settings, model):
    with TestClient(create_app(settings, model_client=model[0])) as client:
        yield client


@pytest.fixture
def headers():
    return {"Authorization": "Bearer test-staff"}


@pytest.fixture
def intake():
    return {
        "service": "pothole",
        "location": "Maple Road at Cedar Street",
        "description": "A deep pothole by the east curb.",
        "contact": "fiction@example.invalid",
    }
