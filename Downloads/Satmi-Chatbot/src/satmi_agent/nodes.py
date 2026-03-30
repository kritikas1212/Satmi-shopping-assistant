from __future__ import annotations

import re
from typing import Any

from satmi_agent.config import settings
from satmi_agent.llm import refine_response_with_llm
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
}
HUMAN_REQUEST_KEYWORDS = {"human", "agent", "representative", "person", "manual"}
OUT_OF_SCOPE_KEYWORDS = {"legal", "lawsuit", "hack", "exploit", "medical", "investment"}


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z']+", text.lower()))


def _extract_order_reference(message: str) -> str:
    match = re.search(r"#?\d{3,}", message)
    if match:
        return match.group(0)
    return "#1001"


def _state_logs(state: AgentState) -> list[dict[str, Any]]:
    return state.get("internal_logs") or state.get("audit_log", [])


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

    intent = "unknown"
    confidence = 0.4

    if support_hits > 0 and shopping_hits > 0:
        intent = "mixed"
        confidence = 0.75
    elif support_hits > 0:
        intent = "support"
        confidence = 0.80
    elif shopping_hits > 0:
        intent = "shopping"
        confidence = 0.80

    requested_human = bool(words.intersection(HUMAN_REQUEST_KEYWORDS))
    out_of_scope = bool(words.intersection(OUT_OF_SCOPE_KEYWORDS))

    return {
        **state,
        "intent": intent,
        "confidence": confidence,
        "requested_human": requested_human,
        "out_of_scope": out_of_scope,
        "internal_logs": [
            *_state_logs(state),
            {
                "event": "intent_classified",
                "intent": intent,
                "confidence": confidence,
                "requested_human": requested_human,
                "out_of_scope": out_of_scope,
            },
        ],
    }


def policy_guard(state: AgentState) -> AgentState:
    intent = state.get("intent", "unknown")
    confidence = state.get("confidence", 0.0)

    policy_ok = intent in {"support", "shopping", "mixed"} and confidence >= 0.65
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

    action = "none"
    tool_result: dict[str, Any] = {}
    errors = state.get("errors", [])

    try:
        if "cancel" in words and "order" in words:
            action = "cancel_order"
            order_id = _extract_order_reference(message)
            if settings.async_cancel_enabled:
                tool_result = cancellation_queue_service.enqueue_cancel_order(
                    conversation_id=state.get("conversation_id", "unknown"),
                    user_id=user_id,
                    order_id=order_id,
                    reason="Requested by customer",
                )
            else:
                tool_result = tooling_service.cancel_order(order_id, reason="Requested by customer")
            if not tool_result.get("order_id") and not tool_result.get("queued"):
                errors = [*errors, "Cancellation result missing order reference."]
        elif any(keyword in words for keyword in {"track", "shipment", "delivery", "order"}):
            action = "get_customer_orders"
            tool_result = tooling_service.get_customer_orders(user_id)
        elif any(keyword in words for keyword in {"recommend", "buy", "product", "suggest"}):
            action = "search_products"
            tool_result = tooling_service.search_products(message)
        else:
            action = "none"
            errors = [*errors, "No supported action found in request."]
    except Exception as exc:  # pragma: no cover
        errors = [*errors, f"Tool execution failed: {exc}"]

    return {
        **state,
        "action": action,
        "tool_result": tool_result,
        "errors": errors,
        "internal_logs": [
            *_state_logs(state),
            {"event": "action_executed", "action": action, "error_count": len(errors)},
        ],
    }


def should_handoff(state: AgentState) -> str:
    if state.get("requested_human"):
        return "handoff"
    if state.get("out_of_scope"):
        return "handoff"
    if not state.get("policy_ok", False):
        return "handoff"
    if not state.get("grounded", False):
        return "handoff"
    if state.get("errors"):
        return "handoff"
    return "respond"


def handoff_to_human_node(state: AgentState) -> AgentState:
    reason = "Out of scope or requires manual agent"
    if state.get("requested_human"):
        reason = "Customer requested human agent"
    elif state.get("out_of_scope"):
        reason = "Request is out of supported scope"
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

    if action == "cancel_order":
        if tool_result.get("queued"):
            response = (
                f"Your cancellation request for order {tool_result.get('order_id')} is queued. "
                f"Task reference: {tool_result.get('task_id')}. "
                "I will keep this conversation updated once processing completes."
            )
        else:
            response = (
                f"Your order {tool_result.get('order_id')} has been cancelled successfully. "
                "If needed, I can also help you place a new order."
            )
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
    elif action == "search_products":
        results = tool_result.get("results", [])
        if not results:
            response = "I could not find matching products. Please refine your preference."
        else:
            top = results[0]
            response = (
                f"I found {top['name']} for ${top['price']}. "
                "I can shortlist more options or help add one to your cart."
            )
    else:
        response = (
            "I can help with order tracking, order cancellation, and shopping recommendations. "
            "Please share what you want to do."
        )

    policy_context = state.get("policy_context", [])
    if policy_context:
        primary = policy_context[0]
        response = f"{response} Policy note: {primary['content']}"

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
