import os
from fastapi.testclient import TestClient

from api.main import app


def test_brief_endpoint_mock_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    client = TestClient(app)
    r = client.post("/llm/brief", params={"horizon": "1w", "k": 5})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("horizon") == "1w"
    assert "snapshot" in data and isinstance(data["snapshot"], dict)
    assert "router" in data and isinstance(data["router"], dict)
    assert isinstance(data.get("markdown"), str)


def test_ask_endpoint_requires_question(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    client = TestClient(app)
    r = client.post("/llm/ask", params={"question": "  ", "horizon": "1w"})
    assert r.status_code == 400


def test_ask_endpoint_answers(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    client = TestClient(app)
    r = client.post("/llm/ask", params={"question": "What is the current regime?", "horizon": "1w"})
    assert r.status_code == 200
    data = r.json()
    assert data.get("horizon") == "1w"
    assert isinstance(data.get("answer"), str)
    assert data.get("citations") == ["snapshot"]


