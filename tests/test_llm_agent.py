from fastapi.testclient import TestClient


def test_agent_tool_history_then_final(monkeypatch):
    # Enable agent mode
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    # Directly turn on agent to avoid reloading settings
    import app.settings as app_settings
    monkeypatch.setattr(app_settings.settings, "llm_agent", True, raising=False)

    # Fake provider that first asks to call indicator history, then returns FINAL
    class FakeProvider:
        def __init__(self):
            self.calls = 0

        def complete(self, prompt: str) -> str:
            self.calls += 1
            if self.calls == 1:
                return (
                    "TOOL get_indicator_history {\"indicator_id\":\"reserves_w\",\"horizon\":\"1w\",\"days\":30}"
                )
            return "FINAL Recent reserves_w history shows a stable negative trend."

    # Patch provider factory to return our fake provider
    # Patch orchestrator's imported get_provider (not the providers module function)
    import app.llm.orchestrator as orchestrator
    fake = FakeProvider()
    monkeypatch.setattr(orchestrator, "get_provider", lambda: fake)

    # Now call the endpoint
    from api.main import app

    client = TestClient(app)
    r = client.post(
        "/llm/ask",
        params={"question": "What's the recent trend in reserves_w?", "horizon": "1w"},
    )
    assert r.status_code == 200, r.text
    data = r.json()

    # Basic shape
    assert data.get("horizon") == "1w"
    assert isinstance(data.get("answer"), str)
    assert isinstance(data.get("tool_trace"), list)
    assert len(data["tool_trace"]) >= 1

    # Golden fragment: first tool call must be get_indicator_history with indicator_id reserves_w
    first = data["tool_trace"][0]
    assert first.get("tool") == "get_indicator_history"
    args = first.get("args") or {}
    assert args.get("indicator_id") == "reserves_w"


def test_agent_series_latest_path(monkeypatch):
    # Enable agent mode
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    import app.settings as app_settings
    monkeypatch.setattr(app_settings.settings, "llm_agent", True, raising=False)

    # Fake provider: choose get_series_latest when asked for latest value
    class FakeProvider3:
        def __init__(self):
            self.calls = 0

        def complete(self, prompt: str) -> str:
            self.calls += 1
            if self.calls == 1:
                return 'TOOL get_series_latest {"series_ids":["RESPPLLOPNWW"]}'
            return "FINAL Used latest series value."

    import app.llm.orchestrator as orchestrator
    fake = FakeProvider3()
    monkeypatch.setattr(orchestrator, "get_provider", lambda: fake)

    from api.main import app
    client = TestClient(app)
    r = client.post(
        "/llm/ask",
        params={"question": "What is the latest value for RESPPLLOPNWW?", "horizon": "1w"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data.get("tool_trace"), list)
    assert len(data["tool_trace"]) >= 1
    first = data["tool_trace"][0]
    assert first.get("tool") == "get_series_latest"
    args = first.get("args") or {}
    assert args.get("series_ids") == ["RESPPLLOPNWW"]


def test_agent_invalid_json_then_valid(monkeypatch):
    # Enable agent mode
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    import app.settings as app_settings
    monkeypatch.setattr(app_settings.settings, "llm_agent", True, raising=False)

    # Fake provider: first emits invalid JSON args, then valid TOOL, then FINAL
    class FakeProvider2:
        def __init__(self):
            self.calls = 0

        def complete(self, prompt: str) -> str:
            self.calls += 1
            if self.calls == 1:
                # Missing quotes around keys/values -> invalid JSON
                return "TOOL get_indicator_history {indicator_id:reserves_w}"
            if self.calls == 2:
                return (
                    'TOOL get_indicator_history {"indicator_id":"reserves_w","horizon":"1w","days":30}'
                )
            return "FINAL Trend fetched."

    # Patch orchestrator's provider factory
    import app.llm.orchestrator as orchestrator
    fake = FakeProvider2()
    monkeypatch.setattr(orchestrator, "get_provider", lambda: fake)

    # Call the endpoint
    from api.main import app

    client = TestClient(app)
    r = client.post(
        "/llm/ask",
        params={"question": "What's the recent trend in reserves_w? contact me at foo@example.com", "horizon": "1w"},
    )
    assert r.status_code == 200, r.text
    data = r.json()

    # Should record two tool attempts: first invalid json args, second valid
    assert isinstance(data.get("tool_trace"), list)
    assert len(data["tool_trace"]) >= 2

    first = data["tool_trace"][0]
    assert first.get("tool") == "get_indicator_history"
    err = (first.get("result") or {}).get("error", "")
    assert "invalid_json_args" in err

    second = data["tool_trace"][1]
    assert second.get("tool") == "get_indicator_history"
    args = second.get("args") or {}
    assert args.get("indicator_id") == "reserves_w"
    # Answer should be present and PII redacted
    assert data.get("answer")
    assert "foo@example.com" not in data.get("answer", "")

