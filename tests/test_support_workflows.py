from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from satmi_agent.config import settings
from satmi_agent.main import app
import satmi_agent.main as main_module


def _auth_headers(role: str | None = None) -> dict[str, str]:
    headers = {"X-API-Key": "secret"}
    if role:
        headers["X-Role"] = role
    return headers


def test_handoff_lifecycle_end_to_end(monkeypatch) -> None:
    settings.auth_required = True
    settings.api_key = "secret"
    handoff_id = f"HND-{uuid4().hex[:8].upper()}"

    def fake_invoke(state, config=None):
        return {
            "status": "awaiting_human",
            "response": "Escalating to human support.",
            "intent": "support",
            "confidence": 0.92,
            "action": "cancel_order",
            "handoff_id": handoff_id,
            "handoff_reason": "Customer requested human agent",
            "errors": [],
            "internal_logs": [{"event": "handoff_created"}],
            "message_history": state.get("message_history", []),
            "tool_result": {"order_id": "#1001"},
            "message": state.get("message", ""),
            "conversation_id": state.get("conversation_id", ""),
            "user_id": state.get("user_id", ""),
        }

    monkeypatch.setattr(main_module.compiled_graph, "invoke", fake_invoke)

    with TestClient(app) as client:
        chat_response = client.post(
            "/chat",
            headers=_auth_headers(),
            json={
                "user_id": "cust-5",
                "conversation_id": "thread-5",
                "message": "I need a human for my cancellation",
            },
        )
        assert chat_response.status_code == 200
        chat_body = chat_response.json()
        assert chat_body["status"] == "awaiting_human"
        assert chat_body["handoff_id"] == handoff_id

        get_handoff = client.get(f"/handoffs/{handoff_id}", headers=_auth_headers("support_agent"))
        assert get_handoff.status_code == 200
        handoff_body = get_handoff.json()
        assert handoff_body["status"] == "open"

        mark_in_progress = client.post(
            f"/handoffs/{handoff_id}/status",
            headers=_auth_headers("support_agent"),
            json={"status": "in_progress", "note": "Agent picked the ticket"},
        )
        assert mark_in_progress.status_code == 200
        assert mark_in_progress.json()["status"] == "in_progress"

        resume = client.post(
            f"/handoffs/{handoff_id}/resume",
            headers=_auth_headers("support_agent"),
            json={"agent_message": "Hi, I have resolved your issue manually."},
        )
        assert resume.status_code == 200
        resume_body = resume.json()
        assert resume_body["status"] == "resolved"


def test_conversation_events_require_support_role(monkeypatch) -> None:
    settings.auth_required = True
    settings.api_key = "secret"

    def fake_invoke(state, config=None):
        return {
            "status": "active",
            "response": "Your order is in transit.",
            "intent": "support",
            "confidence": 0.9,
            "errors": [],
            "internal_logs": [],
            "message_history": state.get("message_history", []),
            "conversation_id": state.get("conversation_id", ""),
            "user_id": state.get("user_id", ""),
            "message": state.get("message", ""),
        }

    monkeypatch.setattr(main_module.compiled_graph, "invoke", fake_invoke)

    with TestClient(app) as client:
        chat_response = client.post(
            "/chat",
            headers=_auth_headers(),
            json={
                "user_id": "cust-7",
                "conversation_id": "thread-7",
                "message": "track my order",
            },
        )
        assert chat_response.status_code == 200

        forbidden = client.get("/conversations/thread-7/events", headers=_auth_headers())
        assert forbidden.status_code == 403

        allowed = client.get("/conversations/thread-7/events", headers=_auth_headers("support_agent"))
        assert allowed.status_code == 200
        events = allowed.json()
        assert len(events) >= 2
