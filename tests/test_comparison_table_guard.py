from __future__ import annotations

from satmi_agent import nodes


def _base_state(message: str) -> dict:
    return {
        "user_id": "test-user",
        "conversation_id": "test-comparison",
        "message": message,
        "errors": [],
        "internal_logs": [],
        "message_history": [{"role": "user", "content": message}],
        "action": "search_products",
        "intent": "shopping",
        "tool_result": {
            "comparison_requested": True,
            "results": [
                {
                    "title": "Karungali Bracelet",
                    "name": "Karungali Bracelet",
                    "price": 799,
                    "currency": "INR",
                    "description": "Grounded product one",
                    "product_url": "https://satmi.in/products/karungali-bracelet",
                    "image_url": "https://satmi.in/img/karungali.jpg",
                },
                {
                    "title": "Rudraksha Bracelet",
                    "name": "Rudraksha Bracelet",
                    "price": 899,
                    "currency": "INR",
                    "description": "Grounded product two",
                    "product_url": "https://satmi.in/products/rudraksha-bracelet",
                    "image_url": "https://satmi.in/img/rudraksha.jpg",
                },
            ],
        },
        "policy_context": [],
    }


def test_comparison_guard_forces_markdown_table(monkeypatch):
    # Simulate LLM returning non-table output for a comparison request.
    monkeypatch.setattr(
        nodes,
        "compose_structured_response_with_llm",
        lambda **_: "Here are two great options for you.",
    )

    state = _base_state("Compare karungali bracelet and rudraksha bracelet")
    out = nodes.compose_response(state)

    response = out["response_text"]
    assert "| Product | Price | Product Link |" in response
    assert "|---|---|---|" in response
    assert "Karungali Bracelet" in response
    assert "Rudraksha Bracelet" in response
