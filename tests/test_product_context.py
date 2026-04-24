import pytest
from fastapi.testclient import TestClient

from satmi_agent.main import app
from satmi_agent.config import settings
from satmi_agent.tools import tooling_service


@pytest.fixture
def client():
    return TestClient(app)


def _auth_headers():
    return {"X-API-Key": settings.api_key or "testkey"}


def test_metrics_endpoint_enabled(client):
    # Ensure the metrics endpoint path matches config and is enabled
    assert settings.metrics_endpoint_enabled is True
    response = client.get(settings.metrics_endpoint_path, headers=_auth_headers())
    assert response.status_code == 200
    # Basic sanity: payload contains prometheus content type header.
    assert "text/plain" in response.headers.get("content-type", "")


def test_product_search_response_inr_format(monkeypatch, client):
    monkeypatch.setattr("satmi_agent.nodes.classify_intent_with_llm", lambda **kwargs: ("shopping", 1.0))
    # Mock the search tool result to keep response deterministic.
    def fake_search_products(query: str):
        return {
            "query": query,
            "comparison_requested": False,
            "results": [
                {
                    "product_id": "P-9999",
                    "variant_id": "V-9999",
                    "sku": "TESTSKU",
                    "name": "Test Mala",
                    "price": 29.99,
                    "currency": "INR",
                    "description": "A test product for unit testing.",
                    "relevance": 10,
                }
            ],
            "source": "stub",
        }

    monkeypatch.setattr(tooling_service, "search_products", fake_search_products)

    # Send a chat request that triggers product search.
    payload = {
        "user_id": "test_user",
        "conversation_id": "test_conv",
        "message": "show me a mala",
    }

    response = client.post("/chat", json=payload, headers=_auth_headers())
    assert response.status_code == 200
    data = response.json()

    # Response should contain INR formatting and a clear next step.
    assert data["response_text"]
    assert data["recommended_products"]
    assert data["recommended_products"][0]["price"] == "INR 29.99"
    assert "next step:" not in data["response_text"].lower()
    assert "you can continue by" not in data["response_text"].lower()
    assert "local catalog cache" not in data["response_text"].lower()
    assert "catalog items" not in data["response_text"].lower()


def test_product_search_stub_fallback_source_is_graceful(monkeypatch, client):
    monkeypatch.setattr("satmi_agent.nodes.classify_intent_with_llm", lambda **kwargs: ("shopping", 1.0))
    def fake_search_products(query: str):
        return {
            "query": query,
            "comparison_requested": False,
            "results": [
                {
                    "product_id": "P-1001",
                    "variant_id": "V-1001",
                    "sku": "MALA-KARUNGALI-001",
                    "name": "Karungali Mala",
                    "price": 29.99,
                    "currency": "INR",
                    "description": "Traditional karungali wood mala.",
                    "relevance": 8,
                }
            ],
            "source": "stub_fallback",
        }

    monkeypatch.setattr(tooling_service, "search_products", fake_search_products)

    payload = {
        "user_id": "test_user_2",
        "conversation_id": "test_conv_2",
        "message": "recommend a mala",
    }

    response = client.post("/chat", json=payload, headers=_auth_headers())
    assert response.status_code == 200
    data = response.json()
    assert data["response_text"]
    assert data["recommended_products"]
    assert data["recommended_products"][0]["price"] == "INR 29.99"
    assert "next step:" not in data["response_text"].lower()
    assert "you can continue by" not in data["response_text"].lower()
    assert "local catalog cache" not in data["response_text"].lower()
    assert "catalog items" not in data["response_text"].lower()


def test_policy_question_returns_no_recommended_products(monkeypatch, client):
    def fail_search_products(query: str):
        raise AssertionError(f"search_products should not be called for policy questions: {query}")

    monkeypatch.setattr(tooling_service, "search_products", fail_search_products)

    payload = {
        "user_id": "test_user_policy",
        "conversation_id": "test_conv_policy",
        "message": "What is your return policy?",
    }

    response = client.post("/chat", json=payload, headers=_auth_headers())
    assert response.status_code == 200
    data = response.json()

    assert data["recommended_products"] == []
    assert data["metadata"]["recommendation_count"] == 0
    assert data["response_text"].strip()
    assert "policy" in data["response_text"].lower()


def test_policy_question_with_show_me_phrase_returns_no_recommended_products(monkeypatch, client):
    def fail_search_products(query: str):
        raise AssertionError(f"search_products should not be called for policy questions: {query}")

    monkeypatch.setattr(tooling_service, "search_products", fail_search_products)

    payload = {
        "user_id": "test_user_policy_show_me",
        "conversation_id": "test_conv_policy_show_me",
        "message": "Show me your return policy",
    }

    response = client.post("/chat", json=payload, headers=_auth_headers())
    assert response.status_code == 200
    data = response.json()

    assert data["recommended_products"] == []
    assert data["metadata"]["recommendation_count"] == 0
    assert data["response_text"].strip()
    assert "policy" in data["response_text"].lower()
