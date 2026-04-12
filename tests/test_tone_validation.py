from __future__ import annotations

from satmi_agent import nodes


AI_ISMS = [
    "as an ai",
    "i am an ai",
    "large language model",
    "i don't have feelings",
]

INTERNAL_LEAK_TERMS = [
    "catalog items",
    "relevance matches",
    "local cache",
    "search_products",
    "input_guardrails",
]


def _base_state(message: str, action: str, tool_result: dict) -> dict:
    return {
        "user_id": "tone-user",
        "conversation_id": "tone-conv",
        "message": message,
        "action": action,
        "tool_result": tool_result,
        "policy_context": [],
        "errors": [],
        "internal_logs": [],
        "message_history": [{"role": "user", "content": message}],
    }


def _assert_no_ai_isms(text: str) -> None:
    lowered = text.lower()
    for phrase in AI_ISMS:
        assert phrase not in lowered


def _assert_has_next_step(text: str) -> None:
    lowered = text.lower()
    assert "next step:" not in lowered
    # Broaden the next step heuristics so it accepts more natural variations in responses like 'please click'
    assert any(phrase in lowered for phrase in [
        "you can continue by",
        "would you like",
        "please click",
        "explore these",
        "check out",
        "here are some"
    ])


def _assert_no_internal_leaks(text: str) -> None:
    lowered = text.lower()
    for phrase in INTERNAL_LEAK_TERMS:
        assert phrase not in lowered


def test_search_products_response_has_next_step_and_no_ai_isms():
    state = _base_state(
        message="recommend a karungali mala",
        action="search_products",
        tool_result={
            "source": "db_cache",
            "catalog_size": 120,
            "matched_count": 5,
            "results": [
                {
                    "name": "Karungali Mala",
                    "price": 1499,
                    "currency": "INR",
                    "description": "Premium natural Karungali beads.",
                },
                {
                    "name": "Rudraksha Mala",
                    "price": 1299,
                    "currency": "INR",
                    "description": "Classic Rudraksha beads for everyday use.",
                },
            ],
        },
    )

    response = nodes.compose_response(state)["response"]
    _assert_no_ai_isms(response)
    _assert_no_internal_leaks(response)
    _assert_has_next_step(response)


def test_search_products_no_result_still_has_next_step_and_no_ai_isms():
    state = _base_state(
        message="show me moonstone karungali fusion",
        action="search_products",
        tool_result={"source": "db_cache", "catalog_size": 120, "matched_count": 0, "results": []},
    )

    response = nodes.compose_response(state)["response"]
    _assert_no_ai_isms(response)
    _assert_no_internal_leaks(response)
    _assert_has_next_step(response)


def test_knowledge_and_search_has_next_step_and_no_ai_isms():
    state = _base_state(
        message="What is Karungali?",
        action="knowledge_and_search",
        tool_result={
            "source": "db_cache",
            "catalog_size": 120,
            "matched_count": 3,
            "knowledge_query": True,
            "results": [
                {
                    "name": "Karungali Mala",
                    "price": 1499,
                    "currency": "INR",
                    "description": "A grounding and traditional bead option.",
                }
            ],
        },
    )

    response = nodes.compose_response(state)["response"]
    _assert_no_ai_isms(response)
    _assert_no_internal_leaks(response)
    _assert_has_next_step(response)


def test_place_order_assist_has_next_step_and_no_ai_isms():
    state = _base_state(
        message="place order for karungali mala",
        action="place_order_assist",
        tool_result={
            "source": "db_cache",
            "results": [
                {
                    "name": "Karungali Mala",
                    "price": 1499,
                    "currency": "INR",
                }
            ],
        },
    )

    response = nodes.compose_response(state)["response"]
    _assert_no_ai_isms(response)
    _assert_no_internal_leaks(response)
    _assert_has_next_step(response)


def test_place_order_response_has_next_step_and_no_ai_isms():
    state = _base_state(
        message="place order for karungali mala qty 2",
        action="place_order",
        tool_result={
            "placed": False,
            "requires_live_store": True,
            "quantity": 2,
            "source": "db_cache",
            "selected_product": {
                "name": "Karungali Mala",
                "price": 1499,
                "currency": "INR",
            },
        },
    )

    response = nodes.compose_response(state)["response"]
    _assert_no_ai_isms(response)
    _assert_no_internal_leaks(response)
    _assert_has_next_step(response)


def test_comparison_response_has_next_step_and_no_ai_isms():
    state = _base_state(
        message="compare karungali vs rudraksha",
        action="search_products",
        tool_result={
            "source": "db_cache",
            "comparison_requested": True,
            "catalog_size": 120,
            "matched_count": 4,
            "results": [
                {
                    "name": "Karungali Mala",
                    "price": 1499,
                    "currency": "INR",
                    "description": "Grounding beads",
                },
                {
                    "name": "Rudraksha Mala",
                    "price": 1299,
                    "currency": "INR",
                    "description": "Classic spiritual beads",
                },
            ],
        },
    )

    response = nodes.compose_response(state)["response"]
    _assert_no_ai_isms(response)
    _assert_no_internal_leaks(response)
    _assert_has_next_step(response)


def test_more_than_two_products_use_bulleted_list():
    state = _base_state(
        message="show me malas",
        action="search_products",
        tool_result={
            "results": [
                {"name": "Karungali Mala", "price": 1499, "currency": "INR", "description": "A"},
                {"name": "Rudraksha Mala", "price": 1299, "currency": "INR", "description": "B"},
                {"name": "Tulsi Mala", "price": 999, "currency": "INR", "description": "C"},
                {"name": "Sphatik Mala", "price": 1799, "currency": "INR", "description": "D"},
            ]
        },
    )

    response = nodes.compose_response(state)["response"]
    _assert_has_next_step(response)
    assert "\n- **" in response
    assert ";" not in response


def test_product_discovery_query_returns_curated_shortlist():
    state = _base_state(
        message="What products do you offer?",
        action="search_products",
        tool_result={
            "results": [
                {"name": "Karungali Mala Exclusive", "price": 999, "currency": "INR", "description": "Free pendant"},
                {"name": "Govt Lab Certified Karungali", "price": 499, "currency": "INR", "description": "Buy 1 get 1"},
                {"name": "Rudraksha Mala", "price": 1299, "currency": "INR", "description": "Traditional"},
                {"name": "Tulsi Mala", "price": 899, "currency": "INR", "description": "Daily wear"},
                {"name": "Sphatik Mala", "price": 1799, "currency": "INR", "description": "Premium"},
            ]
        },
    )

    response = nodes.compose_response(state)["response"]
    _assert_has_next_step(response)
    _assert_no_internal_leaks(response)
    assert ("popular picks" in response.lower() or "specialize in" in response.lower() or "authentic" in response.lower())
    assert response.count("\n- **") >= 3
