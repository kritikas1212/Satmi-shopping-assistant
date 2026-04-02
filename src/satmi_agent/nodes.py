from __future__ import annotations

import re
from typing import Any
import logging

from satmi_agent.config import settings
from satmi_agent.llm import refine_response_with_llm
from satmi_agent.persistence import persistence_service
from satmi_agent.policy import detect_guardrail_issues, retrieve_policy_context
from satmi_agent.queueing import cancellation_queue_service
from satmi_agent.schemas import HandoffTicket
from satmi_agent.state import AgentState
from satmi_agent.tools import tooling_service

try:
    from langgraph.types import interrupt
except Exception:  # pragma: no cover
    interrupt = None


SUPPORT_KEYWORDS = {
    "cancel",
    "refund",
    "return",
    "order",
    "track",
    "shipment",
    "delivery",
    "issue",
    "problem",
}
SHOPPING_KEYWORDS = {
    "buy",
    "purchase",
    "recommend",
    "suggest",
    "product",
    "catalog",
    "cart",
    "checkout",
    "place",
    "shop",
    "browse",
}
HUMAN_REQUEST_KEYWORDS = {"human", "agent", "representative", "person", "manual"}
EXPLICIT_HUMAN_PHRASES = {
    "talk to a human",
    "transfer me",
    "human support",
    "connect me to support",
    "speak to an agent",
}
LEGAL_FINANCIAL_DISPUTE_KEYWORDS = {
    "legal",
    "lawsuit",
    "litigation",
    "chargeback",
    "fraud",
    "financial dispute",
    "consumer court",
}
FRUSTRATION_KEYWORDS = {
    "useless",
    "worst",
    "ridiculous",
    "frustrated",
    "angry",
    "damn",
    "shit",
    "fuck",
}
ORDER_TRACKING_HINTS = {"track", "shipment", "delivery", "status", "where", "latest", "my"}
SATMI_ACCOUNTS_URL = "https://accounts.satmi.in"
PRODUCT_INFO_KEYWORDS = {
    "mala",
    "bead",
    "beads",
    "bracelet",
    "necklace",
    "ring",
    "material",
    "price",
    "cost",
    "available",
    "stock",
    "details",
    "catalog",
    "product",
}
COMPARE_KEYWORDS = {"compare", "comparison", "versus", "vs", "difference", "better"}
DISCOVERY_KEYWORDS = {"list", "show", "find", "tell", "about", "options"}


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z']+", text.lower()))


react_logger = logging.getLogger("satmi_agent.react")


def _extract_order_reference(message: str) -> str:
    match = re.search(r"#?\d{3,}", message)
    if match:
        return match.group(0)
    return "#1001"


def _extract_quantity(message: str) -> int:
    patterns = [
        r"(?:qty|quantity|x)\s*[:=]?\s*(\d+)",
        r"(\d+)\s*(?:pcs|pieces|units?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, message.lower())
        if match:
            try:
                return max(1, int(match.group(1)))
            except Exception:
                return 1
    return 1


def _state_logs(state: AgentState) -> list[dict[str, Any]]:
    return state.get("internal_logs") or state.get("audit_log", [])


def _looks_like_product_query(message: str, words: set[str]) -> bool:
    lowered = message.lower().strip()
    if words.intersection(PRODUCT_INFO_KEYWORDS):
        return True
    if lowered.startswith("what is ") and len(words) >= 3:
        return True
    if lowered.startswith("tell me about ") and len(words) >= 3:
        return True
    if words.intersection(COMPARE_KEYWORDS):
        return True
    if words.intersection(DISCOVERY_KEYWORDS) and words.intersection(PRODUCT_INFO_KEYWORDS):
        return True
    return False


def _is_knowledge_query(message: str) -> bool:
    """G3: Detect general knowledge questions like 'What is Karungali?'
    that need educational context alongside catalog results."""
    lowered = message.lower().strip()
    return (
        lowered.startswith("what is ")
        or lowered.startswith("what are ")
        or lowered.startswith("tell me about ")
        or lowered.startswith("explain ")
        or lowered.startswith("describe ")
    )


def _is_comparison_request(message: str, words: set[str]) -> bool:
    lowered = message.lower()
    return bool(words.intersection(COMPARE_KEYWORDS)) or " vs " in lowered


def _requested_human_assistance(message: str, words: set[str]) -> bool:
    lowered = message.lower()
    if any(phrase in lowered for phrase in EXPLICIT_HUMAN_PHRASES):
        return True
    return bool(words.intersection(HUMAN_REQUEST_KEYWORDS) and ("talk" in words or "transfer" in words))


def _is_legal_or_financial_dispute(message: str, words: set[str]) -> bool:
    lowered = message.lower()
    if "financial dispute" in lowered:
        return True
    return bool(words.intersection(LEGAL_FINANCIAL_DISPUTE_KEYWORDS))


def _is_highly_frustrated(words: set[str]) -> bool:
    return bool(words.intersection(FRUSTRATION_KEYWORDS))


def _comparison_history_hint(state: AgentState) -> str:
    conversation_id = state.get("conversation_id", "")
    history_parts: list[str] = []

    for item in state.get("message_history", []):
        content = str(item.get("content", "")).strip()
        if content:
            history_parts.append(content)

    if conversation_id:
        try:
            events = persistence_service.list_conversation_events(conversation_id, limit=8)
            for event in events:
                text = str(event.message or "").strip()
                if text:
                    history_parts.append(text)
        except Exception:
            # Comparison can still proceed using current user message only.
            pass

    merged = " ".join(history_parts)
    return " ".join(merged.split())[:400]


def input_guardrails(state: AgentState) -> AgentState:
    message = state.get("message", "")
    issues = detect_guardrail_issues(message)
    requires_manual_review = "possible_card_number_detected" in issues

    return {
        **state,
        "guardrail_issues": issues,
        "requires_manual_review": requires_manual_review,
        "internal_logs": [
            *_state_logs(state),
            {
                "event": "input_guardrails",
                "issue_count": len(issues),
                "requires_manual_review": requires_manual_review,
            },
        ],
    }


def classify_intent(state: AgentState) -> AgentState:
    message = state.get("message", "")
    words = _tokenize(message)

    support_hits = len(words.intersection(SUPPORT_KEYWORDS))
    shopping_hits = len(words.intersection(SHOPPING_KEYWORDS))
    product_query = _looks_like_product_query(message, words)

    intent = "unknown"
    confidence = 0.4

    if support_hits > 0 and shopping_hits > 0:
        intent = "mixed"
        confidence = 0.75
    elif support_hits > 0:
        intent = "support"
        confidence = 0.80
    elif shopping_hits > 0 or product_query:
        intent = "shopping"
        confidence = 0.80 if shopping_hits > 0 else 0.72

    requested_human = _requested_human_assistance(message, words)
    out_of_scope = _is_legal_or_financial_dispute(message, words)
    highly_frustrated = _is_highly_frustrated(words)

    return {
        **state,
        "intent": intent,
        "confidence": confidence,
        "requested_human": requested_human,
        "out_of_scope": out_of_scope,
        "highly_frustrated": highly_frustrated,
        "internal_logs": [
            *_state_logs(state),
            {
                "event": "intent_classified",
                "intent": intent,
                "confidence": confidence,
                "requested_human": requested_human,
                "out_of_scope": out_of_scope,
                "highly_frustrated": highly_frustrated,
            },
        ],
    }


def policy_guard(state: AgentState) -> AgentState:
    intent = state.get("intent", "unknown")
    confidence = state.get("confidence", 0.0)

    # G6 fix: Allow "unknown" intents at the lower 0.4 confidence floor.
    # The system prompt says: "use search_products even if only 40% sure."
    if intent in {"support", "shopping", "mixed"}:
        policy_ok = confidence >= 0.65
    elif intent == "unknown":
        policy_ok = confidence >= 0.4
    else:
        policy_ok = False

    if state.get("out_of_scope"):
        policy_ok = False
    if state.get("requires_manual_review"):
        policy_ok = False

    return {
        **state,
        "policy_ok": policy_ok,
        "internal_logs": [
            *_state_logs(state),
            {"event": "policy_guard", "policy_ok": policy_ok},
        ],
    }


def retrieve_policy_node(state: AgentState) -> AgentState:
    context = retrieve_policy_context(state.get("message", ""), state.get("intent", "unknown"))
    grounded = len(context) > 0

    return {
        **state,
        "policy_context": context,
        "grounded": grounded,
        "internal_logs": [
            *_state_logs(state),
            {"event": "policy_retrieval", "grounded": grounded, "snippet_count": len(context)},
        ],
    }


def execute_action(state: AgentState) -> AgentState:
    message = state.get("message", "")
    user_id = state.get("user_id", "unknown")
    words = _tokenize(message)
    requires_auth = settings.firebase_auth_enabled and settings.firebase_require_for_sensitive_actions
    user_authenticated = bool(state.get("user_authenticated", False))
    placing_order = "place" in words and "order" in words
    comparison_request = _is_comparison_request(message, words)
    tracking_order = any(keyword in words for keyword in {"track", "shipment", "delivery"}) or (
        "order" in words and bool(words.intersection(ORDER_TRACKING_HINTS))
    )

    action = "none"
    tool_result: dict[str, Any] = {}
    errors = state.get("errors", [])
    logs = [*_state_logs(state)]

    def _react(phase: str, thought: str, detail: dict[str, Any] | None = None) -> None:
        payload = detail or {}
        logs.append(
            {
                "event": "react",
                "phase": phase,
                "thought": thought,
                "detail": payload,
            }
        )
        react_logger.info("REACT phase=%s thought=%s detail=%s", phase, thought, payload)
        print(f"[REACT] phase={phase} thought={thought} detail={payload}")

    try:
        if requires_auth and not user_authenticated and (placing_order or tracking_order or ("cancel" in words and "order" in words)):
            action = "auth_required"
            _react("think", "This is a sensitive order action and requires verified identity.")
            tool_result = {
                "required_for": "place_or_manage_order",
                "auth_provider": "firebase",
                "instruction": "Sign in and send Firebase ID token in Authorization: Bearer <token> or X-Firebase-Token header.",
            }
            _react("answer", "Prompting user to authenticate before action execution.")
        elif "cancel" in words and "order" in words:
            action = "cancel_redirect"
            order_id = _extract_order_reference(message)
            _react("think", "Cancellation is policy-restricted and must be handled in accounts portal.", {"order_id": order_id})
            _react("act", "Redirecting user to accounts portal for cancellation.")
            tool_result = {
                "order_id": order_id,
                "redirect_url": SATMI_ACCOUNTS_URL,
                "reason": "No-cancel policy in chatbot channel",
            }
            _react("observe", "Generated cancellation redirect response.", tool_result)
        elif placing_order:
            quantity = _extract_quantity(message)
            action = "place_order"
            _react("think", "I need to place an order using the best product match.", {"quantity": quantity})
            _react("act", "Calling place_order tool.")
            tool_result = tooling_service.place_order(
                product_query=message,
                quantity=quantity,
                user_id=user_id,
                authenticated_user=state.get("authenticated_user"),
            )
            if tool_result.get("needs_input"):
                action = "place_order_assist"
            _react("observe", "Order placement tool completed.", {"placed": tool_result.get("placed")})
        elif (
            comparison_request
            or any(keyword in words for keyword in {"recommend", "buy", "purchase", "product", "suggest", "shop", "browse", "list", "show", "find"})
            or _looks_like_product_query(message, words)
            or state.get("intent") == "unknown"
        ):
            # G3: Tag knowledge queries so compose_response can add educational context.
            is_knowledge = _is_knowledge_query(message)
            action = "knowledge_and_search" if is_knowledge else "search_products"
            query = message
            if comparison_request and len(words) <= 5:
                history_hint = _comparison_history_hint(state)
                if history_hint:
                    query = f"{message} {history_hint}"
            _react("think", "I should search product catalog context for this request.", {"knowledge_query": is_knowledge})
            _react("act", "Calling search_products tool.")
            tool_result = tooling_service.search_products(query)
            tool_result["comparison_requested"] = comparison_request
            tool_result["effective_query"] = query
            tool_result["knowledge_query"] = is_knowledge
            _react("observe", "Catalog search returned product candidates.", {"result_count": len(tool_result.get("results", []))})
        elif tracking_order:
            action = "get_customer_orders"
            if state.get("order_context"):
                _react("think", "Authenticated order context is already available in state; reuse it.")
                tool_result = {
                    "customer_id": user_id,
                    "orders": state.get("order_context", []),
                    "source": "firebase_context",
                }
            else:
                _react("think", "I need latest order status for this user.")
                _react("act", "Calling get_customer_orders tool.")
                tool_result = tooling_service.get_customer_orders(user_id)
            _react("observe", "Order status lookup completed.", {"order_count": len(tool_result.get("orders", []))})
        else:
            # G4: Instead of generic capabilities, ask a targeted clarification question.
            action = "clarification"
            _react("think", "Query is ambiguous; asking a targeted follow-up question instead of quitting.")
    except Exception as exc:  # pragma: no cover
        errors = [*errors, f"Tool execution failed: {exc}"]
        _react("observe", "Tool execution raised an exception.", {"error": str(exc)})

    return {
        **state,
        "action": action,
        "tool_result": tool_result,
        "errors": errors,
        "internal_logs": [
            *logs,
            {"event": "action_executed", "action": action, "error_count": len(errors)},
        ],
    }


def should_handoff(state: AgentState) -> str:
    if state.get("requested_human"):
        return "handoff"
    if state.get("highly_frustrated"):
        return "handoff"
    if state.get("out_of_scope"):
        return "handoff"
    return "respond"


def handoff_to_human_node(state: AgentState) -> AgentState:
    reason = "Out of scope or requires manual agent"
    if state.get("requested_human"):
        reason = "Customer requested human agent"
    elif state.get("highly_frustrated"):
        reason = "Customer appears highly frustrated and requested escalation-grade support"
    elif state.get("out_of_scope"):
        reason = "Request involves legal or high-stakes financial dispute"
    elif state.get("errors"):
        reason = "Automated flow failed to resolve request"

    ticket = HandoffTicket(
        user_id=state.get("user_id", "unknown"),
        conversation_id=state.get("conversation_id", "unknown"),
        summary=state.get("message", ""),
        reason=reason,
        intent=state.get("intent", "unknown"),
        attempted_action=state.get("action"),
        tool_result=state.get("tool_result", {}),
        errors=state.get("errors", []),
    )
    handoff = tooling_service.handoff_to_human(ticket)

    if settings.hitl_interrupt_enabled and interrupt is not None:
        resume_payload = interrupt(
            {
                "handoff_id": handoff["handoff_id"],
                "conversation_id": state.get("conversation_id", "unknown"),
                "reason": reason,
                "instruction": "Resume this thread with {'agent_message': '<final resolution message>'}",
            }
        )
        if isinstance(resume_payload, dict):
            agent_message = str(resume_payload.get("agent_message", "")).strip()
            if agent_message:
                return {
                    **state,
                    "status": "resolved",
                    "handoff_id": handoff["handoff_id"],
                    "handoff_reason": reason,
                    "resumed_by_human": True,
                    "human_resolution_message": agent_message,
                    "response": agent_message,
                    "internal_logs": [
                        *_state_logs(state),
                        {
                            "event": "handoff_resumed_native",
                            "handoff_id": handoff["handoff_id"],
                            "reason": reason,
                        },
                    ],
                }

    response = (
        "I am handing this over to a SATMI support specialist now. "
        f"Your handoff reference is {handoff['handoff_id']}. "
        f"Estimated response time is about {handoff['eta_minutes']} minutes."
    )

    return {
        **state,
        "status": "awaiting_human",
        "handoff_id": handoff["handoff_id"],
        "handoff_reason": reason,
        "response": response,
        "internal_logs": [
            *_state_logs(state),
            {"event": "handoff_created", "handoff_id": handoff["handoff_id"], "reason": reason},
        ],
    }


def compose_response(state: AgentState) -> AgentState:
    action = state.get("action", "none")
    tool_result = state.get("tool_result", {})

    def _format_price(value: Any, currency: str | None = None) -> str:
        code = (currency or settings.display_currency_code or "INR").upper()
        amount = float(value or 0.0)
        if code == "USD" and settings.display_currency_code.upper() == "INR":
            inr_value = amount * settings.usd_to_inr_rate
            return f"INR {inr_value:.2f}"
        if code == "INR":
            return f"INR {amount:.2f}"
        return f"{code} {amount:.2f}"

    def _with_next_step(text: str, next_step: str) -> str:
        if "next step:" in text.lower():
            return text
        return f"{text}\n\nNext Step: {next_step}"

    def _safe_cell(value: str) -> str:
        return value.replace("|", "/").strip()

    def _comparison_table(results: list[dict[str, Any]]) -> str:
        rows = ["| Product | Price | Key Details |", "|---|---:|---|"]
        for item in results[:3]:
            name = f"**{_safe_cell(str(item.get('name', 'Unknown Product')))}**"
            price = f"**{_safe_cell(_format_price(item.get('price'), item.get('currency')))}**"
            details = _safe_cell(str(item.get("description", "")).strip()[:120] or "Catalog-matched product")
            rows.append(f"| {name} | {price} | {details} |")
        return "\n".join(rows)

    def _display_product_name(name: str) -> str:
        # Keep user-facing wording natural by avoiding catalog jargon labels.
        cleaned = re.sub(r"\bcombo\b", "set", name, flags=re.IGNORECASE)
        return " ".join(cleaned.split())

    def _display_description(text: str, limit: int = 100) -> str:
        cleaned = re.sub(r"\bcombo\b", "set", text, flags=re.IGNORECASE)
        normalized = " ".join(cleaned.split())
        if len(normalized) <= limit:
            return normalized
        short = normalized[:limit].rsplit(" ", 1)[0].strip()
        return f"{short}..." if short else normalized[:limit]

    def _product_bullets(results: list[dict[str, Any]], limit: int = 4) -> str:
        lines: list[str] = []
        for item in results[:limit]:
            name = _display_product_name(str(item.get("name", "Product")))
            price = _format_price(item.get("price"), item.get("currency"))
            description = _display_description(str(item.get("description", "")), limit=100)
            if description:
                lines.append(f"- **{name}** - **{price}** ({description})")
            else:
                lines.append(f"- **{name}** - **{price}**")
        return "\n".join(lines)

    def _is_catalog_discovery_query(message: str) -> bool:
        lowered = message.lower()
        return (
            "what products" in lowered
            or "what do you offer" in lowered
            or "show products" in lowered
            or "show me products" in lowered
            or "what can i buy" in lowered
        )

    if action == "cancel_redirect":
        response = (
            f"For your security, cancellation requests are handled only via {SATMI_ACCOUNTS_URL}. "
            "Please sign in there to manage or cancel your order."
        )
        response = _with_next_step(response, "Open accounts.satmi.in, sign in, and cancel from your order details page.")
    elif action == "place_order":
        selected = tool_result.get("selected_product", {})
        product_name = selected.get("name", "the selected product")
        price_text = _format_price(tool_result.get("total_price") or selected.get("price"), tool_result.get("currency") or selected.get("currency"))
        quantity = int(tool_result.get("quantity") or 1)
        source = str(tool_result.get("source", "unknown"))
        if tool_result.get("placed"):
            draft_name = tool_result.get("draft_order_name") or tool_result.get("draft_order_id")
            invoice_url = tool_result.get("invoice_url")
            response = (
                f"Your order request is created as draft order {draft_name} for {quantity} x {product_name} at {price_text}."
            )
            if invoice_url:
                response = f"{response} Complete payment here: {invoice_url}"
            if source == "shopify":
                response = f"{response} This draft is created in your live Shopify store."
        else:
            response = (
                f"I found {product_name} at {price_text}, but I could not create a live order yet. "
                "Please confirm product variant, quantity, and delivery pincode to continue."
            )
            if tool_result.get("requires_live_store"):
                response = f"{response} Live Shopify order placement is currently unavailable."
        response = _with_next_step(response, "Reply with quantity and delivery pincode to continue.")
    elif action == "get_customer_orders":
        orders = tool_result.get("orders", [])
        if not orders:
            response = "I could not find any orders on your account yet."
        else:
            latest = orders[0]
            response = (
                f"Your latest order is {latest['order_id']} and its status is {latest['status']}. "
                "Would you like help with tracking, cancellation, or reordering?"
            )
        response = _with_next_step(response, "Tell me if you want tracking details, re-order help, or cancellation steps.")
    elif action in {"search_products", "knowledge_and_search"}:
        results = tool_result.get("results", [])
        comparison_requested = bool(tool_result.get("comparison_requested"))
        is_knowledge = bool(tool_result.get("knowledge_query"))
        user_message = str(state.get("message", ""))
        discovery_query = _is_catalog_discovery_query(user_message)
        if not results:
            response = (
                "I've got you covered. That's a unique request, and while we don't have that exact item right now, "
                "I can suggest close alternatives based on your material and budget preference."
            )
            response = _with_next_step(response, "Tell me your preferred material and budget in INR, and I will suggest the best options.")
        elif comparison_requested:
            if len(results) < 2:
                top = results[0]
                response = (
                    f"Great choice. I found one strong match: **{_display_product_name(top.get('name', 'Product'))}** at **{_format_price(top.get('price'), top.get('currency'))}**. "
                    "Share one more option and I'll compare them clearly for you."
                )
                response = _with_next_step(response, "Share one more product name or use-case to compare side-by-side.")
            else:
                table = _comparison_table(results)
                response = f"I'd be happy to help you compare. Here is a clean side-by-side view:\n\n{table}"
                response = _with_next_step(response, "Tell me which product you want, and I can help you place the order.")
        elif discovery_query:
            curated = _product_bullets(results, limit=4)
            response = (
                "I'd be happy to show you what we have. Here are some popular picks from our collection:\n\n"
                f"{curated}"
            )
            response = _with_next_step(response, "Which one catches your eye, or should I narrow this by budget and purpose?")
        else:
            top = results[0]
            description = _display_description(str(top.get("description", "")), limit=180)
            # G3: For knowledge queries, prepend a hint so LLM adds educational context.
            if is_knowledge:
                response = (
                    f"Great question. **{_display_product_name(top['name'])}** is available for **{_format_price(top.get('price'), top.get('currency'))}**. "
                    f"{description} "
                    "Use your internal knowledge to provide a brief educational explanation of this item, "
                    "then present the catalog details."
                )
            else:
                response = f"Great choice. **{_display_product_name(top['name'])}** is available for **{_format_price(top.get('price'), top.get('currency'))}**."
                if description:
                    response = f"{response} {description}"
            if len(results) > 2:
                response = f"{response}\n\nHere are a few more options you might like:\n{_product_bullets(results[1:5], limit=4)}"
            elif len(results) == 2:
                second = results[1]
                response = (
                    f"{response} You may also like **{_display_product_name(second.get('name', 'Product'))}** "
                    f"at **{_format_price(second.get('price'), second.get('currency'))}**."
                )
            response = f"{response} I can also help you compare options based on your purpose and budget."
            response = _with_next_step(response, "Would you like a side-by-side comparison or should I help place an order?")
    elif action == "place_order_assist":
        results = tool_result.get("results", [])
        source = str(tool_result.get("source", "unknown"))
        if not results:
            response = "I could not find a close match to place an order right now. Tell me the product name, material, and your budget in INR."
        else:
            top = results[0]
            response = (
                f"Great choice. I found {top.get('name')} at {_format_price(top.get('price'), top.get('currency'))}. "
                "To place the order, confirm quantity and delivery pincode."
            )
            if source == "shopify":
                response = f"{response} This offer is pulled from your live Shopify catalog."
            elif source.startswith("stub"):
                response = f"{response} Note: Shopify is currently unavailable, so this quote is from fallback data."
        response = _with_next_step(response, "Reply with quantity and delivery pincode to proceed.")
    elif action == "auth_required":
        response = (
            "Before I place, cancel, or fetch order details, please sign in. "
            "Send Firebase ID token using Authorization: Bearer <token> or X-Firebase-Token header."
        )
        response = _with_next_step(response, "Sign in and send your Firebase token, then repeat your request.")
    elif action == "clarification":
        # G4: Targeted clarification instead of generic capabilities message.
        user_message = state.get("message", "")
        response = (
            f"I want to help you with \"{user_message}\" but I need a bit more context. "
            "Could you tell me if you are looking for a product recommendation, want to track an order, "
            "or have a specific question about our catalog?"
        )
        response = _with_next_step(response, "Try asking something like: 'Show me Karungali malas' or 'Track my order #1001'.")
    else:
        response = (
            "I can help with order tracking, order cancellation, and shopping recommendations. "
            "Please share what you want to do."
        )
        response = _with_next_step(response, "Ask for a product recommendation, comparison, or order support action.")

    policy_context = state.get("policy_context", [])
    if policy_context and action not in {"auth_required", "place_order_assist"}:
        primary = policy_context[0]
        response = f"{response} Quick note: {primary['content']}"

    response = refine_response_with_llm(
        user_message=state.get("message", ""),
        base_response=response,
        policy_context=policy_context,
    )

    return {
        **state,
        "status": "active",
        "response": response,
        "async_task_id": tool_result.get("task_id"),
        "async_task_status": tool_result.get("status"),
        "internal_logs": [
            *_state_logs(state),
            {"event": "response_composed", "status": "active"},
        ],
    }
