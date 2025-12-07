from __future__ import annotations

from fastapi.testclient import TestClient


def make_client(monkeypatch):
    # Ensure auth disabled for test simplicity
    import argo_brain.web.app as web_app

    monkeypatch.setattr(web_app, "API_TOKEN", None)
    return TestClient(web_app.app)


def test_health(monkeypatch):
    with make_client(monkeypatch) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


def test_chat_non_stream(monkeypatch):
    import argo_brain.web.app as web_app

    class DummyResponse:
        text = "hi"
        context = None

    monkeypatch.setattr(web_app, "API_TOKEN", None)
    monkeypatch.setattr(web_app, "_run_chat", lambda req, sid: DummyResponse())

    with TestClient(web_app.app) as client:
        payload = {"message": "hello", "session_id": "test", "mode": "quick_lookup"}
        resp = client.post("/chat", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["session_id"] == "test"
        assert body["text"] == "hi"
        assert body["mode"] == "quick_lookup"


def test_chat_stream(monkeypatch):
    import argo_brain.web.app as web_app

    class DummyResponse:
        text = "streamed"
        context = None

    monkeypatch.setattr(web_app, "API_TOKEN", None)
    monkeypatch.setattr(web_app, "_run_chat", lambda req, sid: DummyResponse())

    with TestClient(web_app.app) as client:
        payload = {"message": "hello", "session_id": "abc", "mode": "research"}
        resp = client.post("/chat/stream", json=payload)
        assert resp.status_code == 200
        body = resp.text
        assert "event: session" in body
        assert "event: message" in body
        assert "streamed" in body
        assert "event: done" in body
