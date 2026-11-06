import json

import httpx
import pytest

from civic.assistant import Assistant
from civic.privacy import redact
from civic.settings import HANDBOOK, Settings


@pytest.mark.parametrize(
    "question,index",
    [
        ("How do I report a pothole?", 0),
        ("How do I report a streetlight outage?", 1),
        ("When should I report missed waste collection?", 2),
        ("How do I report park maintenance?", 3),
    ],
)
def test_supported_answer_quotes_exact_source(client, model, question, index):
    data = client.post("/api/faq", json={"question": question}).json()
    assert not data["abstained"]
    assert data["answer"] == data["citation"]["passage"] == HANDBOOK[index]["passage"]
    assert data["citation"]["id"] == HANDBOOK[index]["id"]
    assert len(model[1]) == 1
    assert model[1][0]["keep_alive"] == 0


@pytest.mark.parametrize(
    "question",
    [
        "Who is the mayor?",
        "What is my property tax?",
        "What is the pothole warranty reimbursement fee?",
        "How much are pothole repair fees?",
        "Tell me about park and pothole reports",
    ],
)
def test_unsupported_or_multiple_topics_abstain_without_model(client, model, question):
    data = client.post("/api/faq", json={"question": question}).json()
    assert data["abstained"] and data["citation"] is None
    assert model[1] == []


@pytest.mark.parametrize(
    "value",
    ["ada@example.invalid", "519-555-0100", "N2L 3G1", "123 Maple Street", "My name is Ada Sample"],
)
def test_personal_details_redacted_and_not_sent(client, model, value):
    question = f"How do I report a pothole? {value}"
    assert value not in redact(question)
    data = client.post("/api/faq", json={"question": question}).json()
    assert data["abstained"] and data["reason"] == "personal_details"
    assert value not in json.dumps(data)
    assert model[1] == []


@pytest.mark.parametrize(
    "choice",
    [
        {"supported": False, "passage_id": "roads-potholes"},
        {"supported": True, "passage_id": "invented-source"},
        {"supported": "true", "passage_id": "roads-potholes"},
        [],
        None,
        "invalid JSON",
    ],
)
def test_untrusted_model_responses_fail_closed(settings, choice):
    raw = choice if isinstance(choice, str) else json.dumps(choice)
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"response": raw}))
    ) as client:
        data = Assistant(settings, client).answer("How do I report a pothole?")
        assert data["abstained"] and data["citation"] is None


def test_model_down_abstains(settings):
    def down(request):
        raise httpx.ConnectError("Offline")

    with httpx.Client(transport=httpx.MockTransport(down)) as client:
        data = Assistant(settings, client).answer("How do I report a pothole?")
        assert data["abstained"] and data["reason"] == "model_unavailable"


def test_injected_model_prose_never_displayed(settings):
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={
                    "response": json.dumps(
                        {
                            "supported": True,
                            "passage_id": "roads-potholes",
                            "answer": "Secret leaked or invented repair promise",
                        }
                    )
                },
            )
        )
    ) as client:
        data = Assistant(settings, client).answer("How do I report a pothole?")
        assert data["answer"] == HANDBOOK[0]["passage"]
        assert "Secret" not in json.dumps(data)


@pytest.mark.parametrize(
    "url",
    [
        "https://external.invalid",
        "http://127.0.0.1@external.invalid",
        "http://localhost:8091/?token=secret",
    ],
)
def test_remote_services_rejected(url):
    with pytest.raises(ValueError):
        Settings(graph_url=url)
