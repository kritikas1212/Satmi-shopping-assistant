from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from satmi_agent.config import settings
from satmi_agent.main import app
import satmi_agent.main as main_module
from satmi_agent.persistence import persistence_service


def test_health_endpoint() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_masks_pii_before_graph_invoke(monkeypatch) -> None:
    seen = {"message": ""}

    def fake_invoke(state, config=None):
        seen["message"] = state["message"]
        return {
            "status": "active",
            "response": "Done",
            "intent": "support",
            "confidence": 0.9,
            "internal_logs": [],
            "message_history": state.get("message_history", []),
        }

    monkeypatch.setattr(main_module.compiled_graph, "invoke", fake_invoke)

    with TestClient(app) as client:
        payload = {
            "user_id": "u-1",
            "conversation_id": "c-1",
            "message": "My email is test@example.com and card is 4242424242424242",
        }
        response = client.post("/chat", json=payload)

    assert response.status_code == 200
    assert "[masked-email]" in seen["message"]
    assert ("[masked-card]" in seen["message"]) or ("[masked-phone]" in seen["message"])
    assert "test@example.com" not in seen["message"]


def test_chat_requires_api_key_when_enabled() -> None:
    settings.auth_required = True
    settings.api_key = "secret"

    with TestClient(app) as client:
        payload = {
            "user_id": "u-2",
            "conversation_id": "c-2",
            "message": "track my order",
        }

        response = client.post("/chat", json=payload)
    assert response.status_code == 401



def test_support_endpoint_requires_support_role() -> None:
    settings.auth_required = True
    settings.api_key = "secret"

    with TestClient(app) as client:
        response = client.get("/conversations/c-1/events", headers={"X-API-Key": "secret"})

    assert response.status_code == 403


def test_chat_rate_limit_enforced(monkeypatch) -> None:
    settings.rate_limit_enabled = True
    settings.rate_limit_requests = 1
    settings.rate_limit_window_seconds = 60

    def fake_invoke(state, config=None):
        return {
            "status": "active",
            "response": "Done",
            "intent": "support",
            "confidence": 0.9,
            "internal_logs": [],
            "message_history": state.get("message_history", []),
        }

    monkeypatch.setattr(main_module.compiled_graph, "invoke", fake_invoke)

    with TestClient(app) as client:
        payload = {
            "user_id": "u-rate",
            "conversation_id": "c-rate",
            "message": "track order",
        }

        first = client.post("/chat", json=payload)
        second = client.post("/chat", json=payload)

    assert first.status_code == 200
    assert second.status_code == 429


def test_metrics_endpoint_requires_support_role_when_auth_enabled() -> None:
    settings.auth_required = True
    settings.api_key = "secret"

    with TestClient(app) as client:
        unauthorized = client.get(settings.metrics_endpoint_path)
        forbidden = client.get(settings.metrics_endpoint_path, headers={"X-API-Key": "secret"})
        allowed = client.get(
            settings.metrics_endpoint_path,
            headers={"X-API-Key": "secret", "X-Role": "support_agent"},
        )

    assert unauthorized.status_code == 401
    assert forbidden.status_code == 403
    assert allowed.status_code == 200


def test_metrics_payload_contains_satmi_metrics() -> None:
    settings.auth_required = True
    settings.api_key = "secret"

    with TestClient(app) as client:
        response = client.get(
            settings.metrics_endpoint_path,
            headers={"X-API-Key": "secret", "X-Role": "support_agent"},
        )

    assert response.status_code == 200
    text = response.text
    assert "satmi_http_requests_total" in text
    assert "satmi_http_request_duration_seconds" in text
    assert "satmi_chat_outcomes_total" in text
    assert "satmi_handoffs_created_total" in text
    assert "satmi_shopify_errors_total" in text
    assert "satmi_rate_limit_hits_total" in text


def test_chat_returns_async_task_metadata(monkeypatch) -> None:
    def fake_invoke(state, config=None):
        return {
            "status": "active",
            "response": "Cancellation queued",
            "intent": "support",
            "confidence": 0.9,
            "action": "cancel_order",
            "async_task_id": "CXL-123",
            "async_task_status": "queued",
            "internal_logs": [],
            "message_history": state.get("message_history", []),
        }

    monkeypatch.setattr(main_module.compiled_graph, "invoke", fake_invoke)

    with TestClient(app) as client:
        payload = {
            "user_id": "u-async",
            "conversation_id": "c-async",
            "message": "cancel my order #1001",
        }
        response = client.post("/chat", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["metadata"]["async_task_id"] == "CXL-123"
    assert body["metadata"]["async_task_status"] == "queued"


def test_get_async_task_requires_support_role_and_returns_task() -> None:
    settings.auth_required = True
    settings.api_key = "secret"
    task_id = f"CXL-{uuid4().hex[:8].upper()}"
    persistence_service.init_db()
    persistence_service.create_async_task(
        task_id=task_id,
        task_type="cancel_order",
        conversation_id="c-task",
        user_id="u-task",
        payload={"order_id": "#1001"},
        status="queued",
    )

    with TestClient(app) as client:
        forbidden = client.get(f"/tasks/{task_id}", headers={"X-API-Key": "secret"})
        allowed = client.get(f"/tasks/{task_id}", headers={"X-API-Key": "secret", "X-Role": "support_agent"})

    assert forbidden.status_code == 403
    assert allowed.status_code == 200
    body = allowed.json()
    assert body["task_id"] == task_id
    assert body["status"] == "queued"
