from __future__ import annotations

from pathlib import Path

from satmi_agent import nodes, prompt_loader
from satmi_agent.config import settings


def _base_state(message: str) -> dict:
    return {
        "user_id": "test-user",
        "conversation_id": "test-conversation",
        "message": message,
        "errors": [],
        "internal_logs": [],
        "message_history": [{"role": "user", "content": message}],
    }


def test_system_prompt_loading_from_file(tmp_path, monkeypatch):
    prompt_text = "SYSTEM PROMPT: test prompt file content"
    prompt_file = tmp_path / "system_prompt.md"
    prompt_file.write_text(prompt_text, encoding="utf-8")

    monkeypatch.setattr(settings, "system_prompt_path", str(prompt_file))

    loaded_prompt = prompt_loader.reload_system_prompt()
    assert loaded_prompt == prompt_text


def test_system_prompt_loading_fallback_when_missing(tmp_path, monkeypatch):
    missing_file = tmp_path / "missing_prompt.md"
    monkeypatch.setattr(settings, "system_prompt_path", str(missing_file))

    loaded_prompt = prompt_loader.reload_system_prompt()
    assert loaded_prompt == prompt_loader.DEFAULT_SYSTEM_PROMPT


def test_general_inquiry_routes_to_general_conversation(monkeypatch):
    monkeypatch.setattr(
        nodes,
        "generate_general_conversation_response",
        lambda **_: "Warm SATMI response",
    )

    state = _base_state("blorb zyx")
    state = nodes.classify_intent(state)
    assert state["intent"] == "general_inquiry"

    state = nodes.policy_guard(state)
    assert state["policy_ok"] is True

    assert nodes.route_post_policy(state) == "general_conversation"

    state = nodes.retrieve_policy_node(state)
    state = nodes.general_conversation(state)
    assert state["action"] == "general_conversation"
    assert "Warm SATMI response" in state["response"]


def test_knowledge_query_routes_to_knowledge_and_search(monkeypatch):
    def fake_search_products(query: str):
        return {
            "query": query,
            "results": [
                {
                    "name": "Karungali Mala",
                    "price": 999,
                    "currency": "INR",
                    "description": "Traditional karungali wood mala.",
                }
            ],
            "source": "stub",
        }

    monkeypatch.setattr(nodes.tooling_service, "search_products", fake_search_products)

    state = _base_state("What is Karungali?")
    state = nodes.classify_intent(state)
    state = nodes.policy_guard(state)
    state = nodes.execute_action(state)

    assert state["action"] == "knowledge_and_search"


def test_general_conversation_normalizes_system_message_to_front(monkeypatch):
    monkeypatch.setattr(
        nodes,
        "generate_general_conversation_response",
        lambda **_: "Warm SATMI response",
    )

    state = _base_state("hi there")
    state["message_history"] = [
        {"role": "user", "content": "hello"},
        {"role": "system", "content": "stale system prompt"},
        {"role": "assistant", "content": "how can I help?"},
        {"role": "system", "content": "another stale prompt"},
    ]

    state = nodes.retrieve_policy_node(state)
    state = nodes.general_conversation(state)

    history = state["message_history"]
    assert history[0]["role"] == "system"
    assert "SATMI Concierge" in history[0]["content"]
    assert sum(1 for item in history if item.get("role") == "system") == 1


def test_ambiguous_query_yields_clarification_response():
    state = _base_state("refund")
    state = nodes.classify_intent(state)
    state = nodes.policy_guard(state)
    state = nodes.execute_action(state)

    assert state["action"] == "clarification"

    state = nodes.compose_response(state)
    response = state["response"].lower()
    assert response
    assert "next step:" not in response
    assert "you can continue by" not in response
