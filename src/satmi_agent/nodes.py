from __future__ import annotations

import re
from typing import Any
import logging
from pathlib import Path
import json
from datetime import datetime, timezone

from satmi_agent.config.persona import FINAL_SYSTEM_PROMPT as SATMI_SYSTEM_PROMPT
from satmi_agent.config import settings
from satmi_agent.llm import (
    classify_intent_with_llm,
    compose_structured_response_with_llm,
    extract_search_keywords_with_llm,
    generate_general_conversation_response,
)
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
BRAND_FAQ_KEYWORDS = {
    "satmi",
    "brand",
    "about",
    "who",
    "shipping",
    "delivery",
    "international",
    "policy",
    "policies",
    "exchange",
    "store",
}
POLICY_QUESTION_KEYWORDS = {
    "policy",
    "policies",
    "shipping",
    "delivery",
    "international",
    "privacy",
}
POLICY_QUESTION_PHRASES = {
    "return policy",
    "refund policy",
    "shipping policy",
    "cancellation policy",
    "privacy policy",
}
BRAND_FAQ_PHRASES = {
    "what is satmi",
    "who are you",
    "about satmi",
    "do you ship internationally",
    "shipping policy",
    "return policy",
    "refund policy",
}
GREETING_WORDS = {"hi", "hello", "hey", "namaste", "hii", "yo"}
CONVERSATIONAL_KEYWORDS = {
    "how",
    "why",
    "what",
    "thanks",
    "thank",
    "help",
    "guide",
    "tell",
    "explain",
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
SELECT_PRODUCT_INTENT_PATTERN = re.compile(
    r"\[SYSTEM_INTENT:\s*SELECT_PRODUCT\]\s*ID:\s*([^,\n]+),\s*Name:\s*(.+)",
    re.IGNORECASE,
)
AUTHENTICATION_INTENT_PATTERNS = (
    r"\bsign\s*in\b",
    r"\blog\s*in\b",
    r"\blogin\b",
    r"\bauthenticate(?:d|ion)?\b",
)
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
TEMP_AI_CORE_ISSUE_MESSAGE = (
    "I am currently experiencing a temporary connection issue to my AI core. "
    "Please try asking your question again in a moment."
)

SUPPORT_PORTAL_URL = "https://accounts.satmi.in"
SUPPORT_EMAIL = "support@satmi.in"
SUPPORT_PHONE = "+919403891731"
ORDER_TRACKING_URL = "https://satmi.in/pages/track-your-order"
SUPPORT_RESPONSE_TIME = "within 24 hours"

PORTAL_BOUND_PHRASES = {
    "update address",
    "change address",
    "address update",
    "add address",
    "update phone number",
    "change phone number",
    "update phone",
    "change phone",
    "phone number in order",
    "number in order",
    "replacement request",
    "replacement order",
    "replace my order",
    "cancel order",
    "order cancellation",
}
PORTAL_BOUND_KEYWORDS = {
    "cancel",
    "cancellation",
    "address",
    "replacement",
    "replace",
    "return",
    "modify",
}
SUPPORT_CONTACT_PHRASES = {
    "contact me",
    "contact us",
    "contact support",
    "send whatsapp",
    "whatsapp",
    "call me",
    "phone number",
    "mobile number",
    "reach me",
    "get in touch",
    "message me",
}
SUPPORT_CONTACT_KEYWORDS = {"whatsapp", "contact", "call", "phone", "mobile", "email", "support"}

SEARCH_STOPWORDS = {
    "i",
    "need",
    "want",
    "to",
    "buy",
    "please",
    "show",
    "me",
    "find",
    "for",
    "my",
    "a",
    "an",
    "the",
    "some",
    "with",
    "and",
    "of",
    "in",
    "on",
    "at",
    "order",
    "place",
    "checkout",
}

DEFAULT_DISCOVERY_QUERY = "Karungali Rudraksha Rose Quartz"

BEST_SELLER_HINTS = {"best", "seller", "sellers", "trending", "popular", "top"}
PRODUCT_FORCE_HINTS = {
    "recommend",
    "recommendation",
    "recommendations",
    "suggest",
    "suggestion",
    "product",
    "products",
    "item",
    "items",
    "catalog",
    "shop",
    "browse",
    "buy",
    "purchase",
    "checkout",
}


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


def _parse_selected_product_intent(message: str) -> tuple[str, str] | None:
    match = SELECT_PRODUCT_INTENT_PATTERN.search(message or "")
    if not match:
        return None
    product_id = str(match.group(1) or "").strip()
    product_name = str(match.group(2) or "").strip()
    if not product_id and not product_name:
        return None
    return product_id, product_name


def _state_logs(state: AgentState) -> list[dict[str, Any]]:
    return state.get("internal_logs") or state.get("audit_log", [])


def _ensure_system_message_first(history: list[dict[str, str]] | None) -> list[dict[str, str]]:
    """Return history with exactly one SATMI system prompt at index 0.

    We aggressively normalize to avoid stale, duplicated, or malformed
    system messages reaching the LLM call path.
    """
    normalized: list[dict[str, str]] = []
    for item in history or []:
        role = str(item.get("role", "")).strip().lower()
        content = str(item.get("content", "")).strip()
        if not role or not content:
            continue
        if role == "system":
            continue
        normalized.append({"role": role, "content": content})

    return [{"role": "system", "content": SATMI_SYSTEM_PROMPT}, *normalized]


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


def _contains_authentication_intent(message: str) -> bool:
    lowered = message.lower()
    return any(re.search(pattern, lowered) for pattern in AUTHENTICATION_INTENT_PATTERNS)


def _extract_search_query(message: str) -> str:
    """Extract a cleaned catalog query without over-compressing it."""
    llm_query = extract_search_keywords_with_llm(user_message=message)
    if llm_query:
        cleaned_llm_query = " ".join(llm_query.split()).strip()
        return cleaned_llm_query or DEFAULT_DISCOVERY_QUERY

    text = " ".join((message or "").split()).strip().lower()
    if not text:
        return DEFAULT_DISCOVERY_QUERY

    tokens = re.findall(r"[a-zA-Z0-9']+", text)
    filtered = [tok for tok in tokens if tok not in SEARCH_STOPWORDS and len(tok) > 1]

    if not filtered:
        filtered = [tok for tok in tokens if len(tok) > 1]
    if not filtered:
        return DEFAULT_DISCOVERY_QUERY

    preferred = [tok for tok in filtered if tok in PRODUCT_INFO_KEYWORDS or tok in {"karungali", "rudraksha", "crystal"}]
    query_tokens = preferred if preferred else filtered
    cleaned_query = " ".join(query_tokens).strip()
    return cleaned_query or DEFAULT_DISCOVERY_QUERY


def _is_comparison_request(message: str, words: set[str]) -> bool:
    lowered = message.lower()
    return bool(words.intersection(COMPARE_KEYWORDS)) or " vs " in lowered


def _is_best_sellers_query(message: str, words: set[str]) -> bool:
    lowered = message.lower()
    return ("best seller" in lowered) or ({"best", "sellers"}.issubset(words))


def _must_force_product_tool_usage(message: str, words: set[str]) -> bool:
    lowered = message.lower()
    if _is_brand_faq(message, words) or _is_policy_question(message, words):
        return False

    if not _is_store_related(message, words):
        return False

    return (
        _is_best_sellers_query(message, words)
        or bool(words.intersection(PRODUCT_FORCE_HINTS))
        or "recommend me" in lowered
        or "show me" in lowered
        or "faq best sellers" in lowered
    )


def _requested_human_assistance(message: str, words: set[str]) -> bool:
    lowered = message.lower()
    if any(phrase in lowered for phrase in EXPLICIT_HUMAN_PHRASES):
        return True
    return bool(words.intersection(HUMAN_REQUEST_KEYWORDS) and ("talk" in words or "transfer" in words))


def _is_portal_bound_support_request(message: str, words: set[str]) -> bool:
    lowered = message.lower()
    if any(phrase in lowered for phrase in PORTAL_BOUND_PHRASES):
        return True
    return bool(words.intersection(PORTAL_BOUND_KEYWORDS) and ("order" in words or "address" in words or "replacement" in words))


def _is_support_contact_request(message: str, words: set[str]) -> bool:
    lowered = message.lower()
    if any(phrase in lowered for phrase in SUPPORT_CONTACT_PHRASES):
        return True
    return bool(words.intersection(SUPPORT_CONTACT_KEYWORDS) and ("me" in words or "support" in words or "team" in words))


def _is_order_tracking_request(message: str, words: set[str]) -> bool:
    lowered = message.lower()
    if any(phrase in lowered for phrase in {"where is my order", "track my order", "order status", "status of order", "track order", "where is it"}):
        return True
    return bool(words.intersection({"track", "tracking", "status", "delivery"}) and "order" in words)


def _portal_redirect_response(*, include_contact_details: bool = True) -> str:
    response = (
        f"I'd be happy to help with your order! For cancellations, address or phone updates, and replacement requests, the fastest way is to manage it securely through our portal at {SUPPORT_PORTAL_URL}."
    )
    if include_contact_details:
        response += (
            f" If you need further assistance, our team is always ready to help at {SUPPORT_EMAIL} or {SUPPORT_PHONE} (we usually reply {SUPPORT_RESPONSE_TIME})."
        )
    return response


def _support_contact_response(*, mention_portal: bool = True) -> str:
    response = (
        f"I'm here to help! Feel free to contact our dedicated support team at {SUPPORT_EMAIL} or call us directly at {SUPPORT_PHONE}. We typically reply {SUPPORT_RESPONSE_TIME}."
    )
    if mention_portal:
        response += (
            f" Also, just a quick tip: you can instantly manage cancellations, address updates, and replacements yourself over at {SUPPORT_PORTAL_URL}."
        )
    return response


def _order_tracking_response(*, mention_portal: bool = True) -> str:
    return f"I can certainly help you keep an eye on your delivery! You can easily check the latest status of your order right here: {ORDER_TRACKING_URL}."


def _is_legal_or_financial_dispute(message: str, words: set[str]) -> bool:
    lowered = message.lower()
    if "financial dispute" in lowered:
        return True
    return bool(words.intersection(LEGAL_FINANCIAL_DISPUTE_KEYWORDS))


def _is_highly_frustrated(words: set[str]) -> bool:
    return bool(words.intersection(FRUSTRATION_KEYWORDS))


def _is_brand_faq(message: str, words: set[str]) -> bool:
    lowered = message.lower().strip()
    if lowered in GREETING_WORDS:
        return True
    if any(phrase in lowered for phrase in BRAND_FAQ_PHRASES):
        return True
    if lowered.startswith("what is satmi") or lowered.startswith("who are you"):
        return True
    return bool(words.intersection(BRAND_FAQ_KEYWORDS) and "order" not in words and "buy" not in words)


def _is_policy_question(message: str, words: set[str]) -> bool:
    lowered = message.lower().strip()
    if "order" in words and any(keyword in words for keyword in {"cancel", "track", "status"}):
        return False
    if any(phrase in lowered for phrase in POLICY_QUESTION_PHRASES):
        return True
    if lowered.startswith("what is your") and "policy" in lowered:
        return True
    return bool(words.intersection(POLICY_QUESTION_KEYWORDS))


def _is_conversational_query(message: str, words: set[str]) -> bool:
    lowered = message.lower().strip()
    if lowered in GREETING_WORDS:
        return True
    if lowered.endswith("?") and len(words) <= 16:
        return True
    return bool(words.intersection(CONVERSATIONAL_KEYWORDS))


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


def _extract_user_preferences(*, messages: list[str]) -> dict[str, Any]:
    joined = " ".join(messages).lower()
    prefs: dict[str, Any] = {}

    budget_match = re.search(r"(?:under|below|budget)\s*(?:inr|rs\.?|₹)?\s*(\d{2,6})", joined)
    if budget_match:
        prefs["budget_inr"] = int(budget_match.group(1))

    categories = ["bracelet", "mala", "necklace", "ring", "crystal", "pendant"]
    preferred_categories = [cat for cat in categories if re.search(rf"\b{cat}s?\b", joined)]
    if preferred_categories:
        prefs["preferred_categories"] = sorted(set(preferred_categories))

    materials = ["karungali", "rudraksha", "crystal", "silver", "wood"]
    preferred_materials = [mat for mat in materials if re.search(rf"\b{mat}\b", joined)]
    if preferred_materials:
        prefs["preferred_materials"] = sorted(set(preferred_materials))

    return prefs


def _conversation_summary(state: AgentState, limit: int = 10) -> str:
    turns: list[str] = []
    for item in state.get("message_history", [])[-limit:]:
        role = str(item.get("role", "user")).strip()
        content = str(item.get("content", "")).strip()
        if content:
            turns.append(f"{role}: {content}")
    return "\n".join(turns)


def _build_product_snippets(tool_result: dict[str, Any], max_items: int = 3) -> list[dict[str, Any]]:
    snippets: list[dict[str, Any]] = []
    for item in (tool_result.get("results") or [])[:max_items]:
        title = str(item.get("title") or item.get("name") or "").strip()
        if not title:
            continue
        snippets.append(
            {
                "title": title,
                "price": item.get("price"),
                "currency": item.get("currency"),
                "material": item.get("material") or item.get("product_type"),
                "benefits": str(item.get("description", "")).strip()[:180],
                "product_url": item.get("product_url"),
                "image_url": item.get("image_url"),
            }
        )
    return snippets


def _is_store_related(message: str, words: set[str]) -> bool:
    return bool(
        words.intersection(BRAND_FAQ_KEYWORDS)
        or words.intersection(POLICY_QUESTION_KEYWORDS)
        or words.intersection(SHOPPING_KEYWORDS)
        or words.intersection(PRODUCT_INFO_KEYWORDS)
        or any(token in message.lower() for token in ["satmi", "shipping", "refund", "return", "karungali", "rudraksha"])
    )


def _comparison_requested(state: AgentState, tool_result: dict[str, Any]) -> bool:
    words = _tokenize(str(state.get("message", "")))
    message = str(state.get("message", ""))
    lowered = message.lower()
    explicit_compare_phrase = "compare" in lowered or " vs " in lowered or " versus " in lowered
    return bool(tool_result.get("comparison_requested")) or _is_comparison_request(message, words) or explicit_compare_phrase


def _has_markdown_table(text: str) -> bool:
    return "|" in text and "|---" in text


def _deterministic_grounded_fallback(*, state: AgentState, policy_context: list[dict[str, str]], product_snippets: list[dict[str, Any]], next_step_guidance: str) -> str:
    user_message = str(state.get("message", "")).strip()
    if product_snippets:
        first_title = str(product_snippets[0].get("title") or "these options").strip()
        return (
            f"I found grounded options that match \"{user_message}\". "
            f"Start with {first_title}, and I can narrow by budget, material, or purpose in the next step. Would you like to explore these options?"
        )

    if policy_context:
        first_topic = str(policy_context[0].get("title") or "policy guidance").strip()
        return (
            f"Based on available SATMI guidance, this maps to {first_topic}. "
            "If you want, I can provide a concise checklist for what to do next. You can continue by asking for the checklist."
        )

    return (
        f"I can help with \"{user_message}\" right away. "
        f"{next_step_guidance} Would you like to proceed?"
    )


def _evidence_gap_response(*, state: AgentState, policy_missing: bool, products_missing: bool) -> str:
    user_message = str(state.get("message", "")).strip()
    if policy_missing and products_missing:
        return (
            f"I want to answer \"{user_message}\" accurately, but I do not have enough grounded policy or catalog context yet. "
            "Could you share one specific detail: are you asking about policy terms or product recommendations?"
        )
    if policy_missing:
        return (
            f"I want to answer \"{user_message}\" accurately, but I do not have matching policy context yet. "
            "Could you specify which policy you need: shipping, return, refund, or cancellation?"
        )
    if products_missing:
        return (
            f"I cannot find a grounded catalog match for \"{user_message}\" yet. "
            "Please share your preferred category or budget, and I will narrow it precisely."
        )
    return (
        f"I want to answer \"{user_message}\" accurately, but I need one more detail to ground the response. "
        "Could you clarify your primary goal?"
    )


def _comparison_table_from_products(products: list[dict[str, Any]]) -> str:
    rows = ["| Product | Price | Product Link |", "|---|---|---|"]
    for item in products[:3]:
        title = str(item.get("title", "Product")).replace("|", "/")
        price = str(item.get("price", "NA")).replace("|", "/")
        link = str(item.get("product_url") or "NA").replace("|", "/")
        rows.append(f"| {title} | {price} | {link} |")
    return "\n".join(rows)


def _record_feedback_event(*, state: AgentState, reason: str, response_text: str) -> None:
    try:
        root = Path(__file__).resolve().parents[2]
        out = root / "evaluations" / "response_feedback_log.jsonl"
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "conversation_id": state.get("conversation_id"),
            "user_id": state.get("user_id"),
            "message": state.get("message"),
            "intent": state.get("intent"),
            "action": state.get("action"),
            "reason": reason,
            "response": response_text,
        }
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(payload, ensure_ascii=True) + "\n")
    except Exception:
        pass


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

    # 1. Check system/auth overrides first
    if _parse_selected_product_intent(message):
        intent = "shopping"
        confidence = 1.0
        classification_source = "system_intent_select_product"
    elif _contains_authentication_intent(message):
        intent = "authentication"
        confidence = 1.0
        classification_source = "keyword_authentication"
    else:
        # 2. Delegate everything else directly to the Semantic LLM Supervisor
        llm_intent = classify_intent_with_llm(
            user_message=message,
            message_history=state.get("message_history", []),
        )
        if llm_intent is not None:
            intent, confidence = llm_intent
            classification_source = "llm"
        else:
            intent = "general"
            confidence = 0.5
            classification_source = "fallback"

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
                "classification_source": classification_source,
                "requested_human": requested_human,
                "out_of_scope": out_of_scope,
                "highly_frustrated": highly_frustrated,
            },
        ],
    }


def policy_guard(state: AgentState) -> AgentState:
    confidence = state.get("confidence", 0.0)
    policy_ok = confidence >= 0.40

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
    intent = state.get("intent", "unknown")
    if intent in {"policy_brand_faq", "general"}:
        return {
            **state,
            "policy_context": [],
            "grounded": True,
            "internal_logs": [
                *_state_logs(state),
                {"event": "policy_retrieval_bypassed", "intent": intent},
            ],
        }

    retrieval_intent = "shopping" if intent == "general" else intent
    context = retrieve_policy_context(state.get("message", ""), retrieval_intent)
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


def route_post_policy(state: AgentState) -> str:
    return "execute_action"


def route_after_policy_guard(state: AgentState) -> str:
    message = str(state.get("message", ""))
    words = _tokenize(message)
    if not state.get("policy_ok", True):
        return "handoff_to_human"
    if _is_portal_bound_support_request(message, words) or _is_support_contact_request(message, words) or _is_order_tracking_request(message, words):
        return "retrieve_policy"
    if _must_force_product_tool_usage(message, words):
        return "retrieve_policy"
    if state.get("intent") in {"policy_brand_faq", "general"}:
        return "general_conversation"
    return "retrieve_policy"


def _fallback_general_conversation_response(message: str, policy_context: list[dict[str, str]]) -> str:
    cleaned = str(message or "").strip()
    if policy_context:
        topic = str(policy_context[0].get("title") or "SATMI policy").strip()
        detail = str(policy_context[0].get("content") or "").strip()
        concise_detail = detail[:180] + ("..." if len(detail) > 180 else "")
        if concise_detail:
            return f"Here is what I can confirm right now about {topic}: {concise_detail}"
        return f"Here is what I can confirm right now about {topic}. Tell me what specific detail you need next."

    if cleaned:
        return (
            f"I am having a brief delay from the AI service, but I can still help with \"{cleaned}\". "
            "Share whether you want policy guidance, order help, or product recommendations, and I will continue."
        )

    return TEMP_AI_CORE_ISSUE_MESSAGE


def general_conversation(state: AgentState) -> AgentState:
    user_message = state.get("message", "")
    policy_context = state.get("policy_context", [])
    history = _ensure_system_message_first(state.get("message_history", []))
    llm_history = _ensure_system_message_first(
        [{"role": "system", "content": SATMI_SYSTEM_PROMPT}, *history]
    )

    words = _tokenize(user_message)
    if _is_portal_bound_support_request(user_message, words):
        response = _portal_redirect_response(include_contact_details=True)
        return {
            **state,
            "action": "portal_redirect",
            "status": "active",
            "response": response,
            "response_text": response,
            "recommended_products": [],
            "tool_result": {
                "redirect_url": SUPPORT_PORTAL_URL,
                "support_email": SUPPORT_EMAIL,
                "support_response_time": SUPPORT_RESPONSE_TIME,
            },
            "message_history": history,
            "user_preferences": {},
            "conversation_summary": _conversation_summary({**state, "message_history": history}),
            "context_packet": {
                "policy_snippets": policy_context,
                "product_snippets": [],
                "recent_conversation_summary": _conversation_summary({**state, "message_history": history}),
                "user_state": {
                    "authenticated": bool(state.get("user_authenticated", False)),
                    "order_intent": False,
                    "preferences": {},
                },
            },
            "internal_logs": [
                *_state_logs(state),
                {
                    "event": "general_conversation_portal_redirect",
                    "support_portal_url": SUPPORT_PORTAL_URL,
                },
            ],
        }
    if _is_support_contact_request(user_message, words):
        response = _support_contact_response(mention_portal=True)
        return {
            **state,
            "action": "support_contact",
            "status": "active",
            "response": response,
            "response_text": response,
            "recommended_products": [],
            "tool_result": {
                "support_email": SUPPORT_EMAIL,
                "support_response_time": SUPPORT_RESPONSE_TIME,
                "support_portal_url": SUPPORT_PORTAL_URL,
            },
            "message_history": history,
            "user_preferences": {},
            "conversation_summary": _conversation_summary({**state, "message_history": history}),
            "context_packet": {
                "policy_snippets": policy_context,
                "product_snippets": [],
                "recent_conversation_summary": _conversation_summary({**state, "message_history": history}),
                "user_state": {
                    "authenticated": bool(state.get("user_authenticated", False)),
                    "order_intent": False,
                    "preferences": {},
                },
            },
            "internal_logs": [
                *_state_logs(state),
                {
                    "event": "general_conversation_support_contact",
                    "support_email": SUPPORT_EMAIL,
                },
            ],
        }
    if _is_order_tracking_request(user_message, words):
        response = _order_tracking_response(mention_portal=False)
        return {
            **state,
            "action": "order_tracking_redirect",
            "status": "active",
            "response": response,
            "response_text": response,
            "recommended_products": [],
            "tool_result": {
                "redirect_url": ORDER_TRACKING_URL,
            },
            "message_history": history,
            "user_preferences": {},
            "conversation_summary": _conversation_summary({**state, "message_history": history}),
            "context_packet": {
                "policy_snippets": policy_context,
                "product_snippets": [],
                "recent_conversation_summary": _conversation_summary({**state, "message_history": history}),
                "user_state": {
                    "authenticated": bool(state.get("user_authenticated", False)),
                    "order_intent": False,
                    "preferences": {},
                },
            },
            "internal_logs": [
                *_state_logs(state),
                {
                    "event": "general_conversation_order_tracking_redirect",
                    "redirect_url": ORDER_TRACKING_URL,
                },
            ],
        }
    history_text = [str(item.get("content", "")).strip() for item in history if str(item.get("content", "")).strip()]
    try:
        recent_user_messages = persistence_service.list_recent_user_messages(state.get("user_id", "unknown"), limit=20)
    except Exception:
        recent_user_messages = []
    user_preferences = _extract_user_preferences(messages=[*history_text, *recent_user_messages])
    summary = _conversation_summary({**state, "message_history": history})
    context_packet = {
        "policy_snippets": policy_context,
        "product_snippets": [],
        "recent_conversation_summary": summary,
        "user_state": {
            "authenticated": bool(state.get("user_authenticated", False)),
            "order_intent": bool(any(token in words for token in {"order", "buy", "checkout", "place"})),
            "preferences": user_preferences,
        },
    }

    response_source = "llm"
    response = generate_general_conversation_response(
        user_message=user_message,
        message_history=llm_history,
        policy_context=policy_context,
    )

    if not response:
        response = _fallback_general_conversation_response(user_message, policy_context)
        response_source = "deterministic_fallback"

    return {
        **state,
        "action": "general_conversation",
        "status": "active",
        "response": response,
        "response_text": response,
        "recommended_products": [],
        "tool_result": {},
        "message_history": history,
        "user_preferences": user_preferences,
        "conversation_summary": summary,
        "context_packet": context_packet,
        "internal_logs": [
            *_state_logs(state),
            {
                "event": "general_conversation",
                "policy_snippet_count": len(policy_context),
                "product_snippet_count": 0,
                "history_turns": len(history),
                "response_source": response_source,
            },
        ],
    }


def execute_action(state: AgentState) -> AgentState:
    intent = str(state.get("intent", "")).strip().lower()
    message = state.get("message", "")
    words = _tokenize(message)

    if intent in {"policy_brand_faq", "general"} and not (_is_portal_bound_support_request(message, words) or _is_support_contact_request(message, words) or _is_order_tracking_request(message, words)):
        return {
            **state,
            "action": "general_conversation",
            "tool_result": {}
        }

    user_id = state.get("user_id", "unknown")
    intent = intent or "unknown"

    # Strict routing by classified intent: only shopping can trigger product search.
    if intent != "shopping":
        if intent in {"policy_brand_faq", "general"} and not (_is_portal_bound_support_request(message, words) or _is_support_contact_request(message, words) or _is_order_tracking_request(message, words)):
            return {
                **state,
                "action": "general_conversation",
                "tool_result": {},
                "internal_logs": [*_state_logs(state), {"event": "action_bypassed_by_intent", "intent": intent}],
            }

        # Rule-based overrides take priority over LLM intent (e.g. portal requests)
        if _is_portal_bound_support_request(message, words):
            order_id = _extract_order_reference(message)
            tool_result = {
                "order_id": order_id,
                "redirect_url": SUPPORT_PORTAL_URL,
                "support_email": SUPPORT_EMAIL,
                "support_response_time": SUPPORT_RESPONSE_TIME,
                "reason": "Managed through account portal",
            }
            return {
                **state,
                "action": "portal_redirect",
                "tool_result": tool_result,
                "internal_logs": [
                    *_state_logs(state),
                    {"event": "action_executed", "action": "portal_redirect", "order_id": order_id, "error_count": 0},
                ],
            }

        if _is_order_tracking_request(message, words) or intent == "order_tracking":
            tool_result = {
                "redirect_url": ORDER_TRACKING_URL,
                "reason": "Tracking redirects to global track-your-order page",
            }
            return {
                **state,
                "action": "order_tracking_redirect",
                "tool_result": tool_result,
                "internal_logs": [
                    *_state_logs(state),
                    {"event": "action_executed", "action": "order_tracking_redirect", "error_count": 0},
                ],
            }

        if _is_support_contact_request(message, words):
            tool_result = {
                "support_email": SUPPORT_EMAIL,
                "support_response_time": SUPPORT_RESPONSE_TIME,
                "support_portal_url": SUPPORT_PORTAL_URL,
                "reason": "Customer requested contact details",
            }
            return {
                **state,
                "action": "support_contact",
                "tool_result": tool_result,
                "internal_logs": [
                    *_state_logs(state),
                    {"event": "action_executed", "action": "support_contact", "error_count": 0},
                ],
            }

        # Cancellation requests go to portal.
        if "cancel" in words and "order" in words:
            order_id = _extract_order_reference(message)
            tool_result = {
                "order_id": order_id,
                "redirect_url": SUPPORT_PORTAL_URL,
                "support_email": SUPPORT_EMAIL,
                "support_response_time": SUPPORT_RESPONSE_TIME,
                "reason": "No-cancel policy in chatbot channel",
            }
            return {
                **state,
                "action": "cancel_redirect",
                "tool_result": tool_result,
                "internal_logs": [
                    *_state_logs(state),
                    {"event": "action_executed", "action": "cancel_redirect", "order_id": order_id, "error_count": 0},
                ],
            }

        # Ambiguous non-shopping intent — ask clarification.
        return {
            **state,
            "action": "clarification",
            "tool_result": {},
            "internal_logs": [
                *_state_logs(state),
                {"event": "action_executed", "action": "clarification", "error_count": 0},
            ],
        }

    action = "knowledge_and_search" if _is_knowledge_query(message) else "search_products"
    clean_query = "Karungali Rudraksha Rose Quartz" if _is_best_sellers_query(message, _tokenize(message)) else _extract_search_query(message)

    # Comparison queries need results from both sides (e.g. "rose quartz" and "pyrite").
    if _is_comparison_request(message, words):
        query_parts: list[str] = []
        lowered = message.lower()
        split_parts = re.split(r"\b(?:vs|versus|and)\b", lowered)
        for part in split_parts:
            extracted = _extract_search_query(part)
            if extracted:
                query_parts.append(extracted)
        query_parts = [q for q in dict.fromkeys(query_parts) if q]

        merged_results: list[dict[str, Any]] = []
        seen_keys: set[str] = set()
        for query_part in (query_parts[:3] or [clean_query]):
            partial = tooling_service.search_products(query_part)
            for item in (partial.get("results") or []):
                key = str(item.get("product_id") or item.get("id") or item.get("handle") or item.get("title") or item.get("name"))
                if not key or key in seen_keys:
                    continue
                seen_keys.add(key)
                merged_results.append(item)

        tool_result = {
            "query": clean_query,
            "effective_query": clean_query,
            "results": merged_results,
            "source": "comparison_merged",
            "comparison_requested": True,
        }
    else:
        tool_result = tooling_service.search_products(clean_query)
        tool_result["effective_query"] = clean_query

    return {
        **state,
        "action": action,
        "tool_result": tool_result,
        "internal_logs": [
            *_state_logs(state),
            {"event": "action_executed", "action": action, "query": clean_query, "error_count": 0},
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
    intent = str(state.get("intent", "")).strip().lower() or "unknown"

    if state.get("intent") != "shopping":
        recommended_products = []
        tool_result = {}
        state = {**state, "tool_result": tool_result, "recommended_products": recommended_products}

    tool_result = state.get("tool_result", {})
    auth_required = False

    def _format_price(value: Any, currency: str | None = None) -> str:
        code = (currency or settings.display_currency_code or "INR").upper()
        amount = float(value or 0.0)
        if code == "USD" and settings.display_currency_code.upper() == "INR":
            inr_value = amount * settings.usd_to_inr_rate
            return f"INR {inr_value:.2f}"
        if code == "INR":
            return f"INR {amount:.2f}"
        return f"{code} {amount:.2f}"

    policy_context = state.get("policy_context", [])

    recommended_products: list[dict[str, Any]] = []
    intent = str(state.get("intent", "")).strip().lower()

    if intent == "shopping" and action in {"search_products", "knowledge_and_search"}:
        for item in (tool_result.get("results") or [])[:8]:
            title = str(item.get("title") or item.get("name") or "").strip()
            price_value = item.get("price")
            if not title:
                continue

            raw_img = item.get("image_url") or item.get("image")
            if isinstance(raw_img, dict):
                img_str = str(raw_img.get("src") or raw_img.get("url") or "")
            else:
                img_str = str(raw_img or "")
            if img_str.startswith("{") or not img_str:
                img_str = "https://placehold.co/640x400/F9F6F2/7A1E1E?text=SATMI"

            recommended_products.append(
                {
                    "product_id": str(item.get("product_id") or "") or None,
                    "variant_id": str(item.get("variant_id") or "") or None,
                    "handle": str(item.get("handle") or "") or None,
                    "url": str(item.get("url") or item.get("product_url") or "") or None,
                    "title": title,
                    "price": _format_price(price_value, item.get("currency")),
                    "image_url": img_str,
                    "product_url": item.get("product_url"),
                }
            )

    # Strict wipe: only shopping intent gets product cards.
    if intent != "shopping":
        recommended_products = []

    history_text = [str(item.get("content", "")).strip() for item in state.get("message_history", []) if str(item.get("content", "")).strip()]
    try:
        recent_user_messages = persistence_service.list_recent_user_messages(state.get("user_id", "unknown"), limit=20)
    except Exception:
        recent_user_messages = []
    user_preferences = _extract_user_preferences(messages=[*history_text, *recent_user_messages])
    summary = _conversation_summary(state)
    product_snippets = _build_product_snippets(tool_result)

    context_packet = {
        "policy_snippets": policy_context,
        "product_snippets": product_snippets,
        "recent_conversation_summary": summary,
        "user_state": {
            "authenticated": bool(state.get("user_authenticated", False)),
            "order_intent": action in {"place_order", "place_order_assist"},
            "preferences": user_preferences,
        },
    }

    next_step_guidance_map = {
        "cancel_redirect": "Ask the customer to sign in at accounts.satmi.in and manage cancellation from order details.",
        "portal_redirect": "Ask the customer to sign in at accounts.satmi.in for cancellation, address updates, or replacement requests.",
        "support_contact": "Ask the customer to contact support@satmi.in and mention the support response window.",
        "place_order": "Confirm quantity and delivery pincode, then guide payment completion if invoice URL exists.",
        "get_customer_orders": "Offer tracking, cancellation guidance, or reorder assistance for the latest order.",
        "search_products": "Offer shortlist refinement by intent, budget, or comparison preference.",
        "knowledge_and_search": "Blend brief educational context with catalog-backed product guidance.",
        "place_order_assist": "Ask for missing quantity or delivery details required to place order.",
        "clarification": "Ask one focused follow-up question to clarify the user objective.",
    }
    next_step_guidance = next_step_guidance_map.get(action, "Offer the most relevant next help option for the user.")

    compact_tool_result = {
        "source": tool_result.get("source"),
        "error": tool_result.get("error"),
        "placed": tool_result.get("placed"),
        "draft_order_id": tool_result.get("draft_order_id"),
        "draft_order_name": tool_result.get("draft_order_name"),
        "invoice_url": tool_result.get("invoice_url"),
        "orders": (tool_result.get("orders") or [])[:3],
        "comparison_requested": tool_result.get("comparison_requested"),
        "result_count": len(tool_result.get("results") or []),
        "results": product_snippets,
        "redirect_url": tool_result.get("redirect_url"),
        "support_email": tool_result.get("support_email"),
        "support_response_time": tool_result.get("support_response_time"),
    }

    response_source = "llm"
    if auth_required:
        selected_name = str(
            tool_result.get("selected_product_name")
            or state.get("selected_product_name")
            or ""
        ).strip()
        if selected_name:
            response = (
                f"Perfect choice. Here are some excellent options including {selected_name}. "
                "Click the Select & Buy button on any product to proceed to our website for checkout."
            )
        else:
            response = "Here are some excellent choices. Click the Select & Buy button on any product to proceed to our website for checkout."
        response_source = "auth_intercept"
    elif action == "portal_redirect":
        response = _portal_redirect_response(include_contact_details=True)
        response_source = "portal_redirect"
    elif action == "support_contact":
        response = _support_contact_response(mention_portal=True)
        response_source = "support_contact"
    elif action == "order_tracking_redirect":
        response = _order_tracking_response(mention_portal=False)
        response_source = "order_tracking_redirect"
    elif str(tool_result.get("error", "")).strip().lower() == "catalog unavailable":
        response = (
            "I am having trouble loading the live catalog right now. "
            "Please share the product type you want (for example Karungali mala, Rudraksha bracelet, or crystal), "
            "and I will refine recommendations and show available choices with Select & Buy links."
        )
        response_source = "catalog_unavailable"
    else:
        response = compose_structured_response_with_llm(
            user_message=str(state.get("message", "")),
            intent=str(intent),
            action=str(action),
            policy_context=policy_context,
            tool_result=compact_tool_result,
            recommended_products=recommended_products,
            next_step_guidance=next_step_guidance,
            retry_count=max(0, settings.gemini_retry_count),
            message_history=state.get("message_history", []),
        )

    comparison_required = _comparison_requested(state, tool_result) and len(recommended_products) >= 2
    if response and comparison_required and not _has_markdown_table(response):
        if recommended_products:
            response = (
                "Here is a grounded comparison from the current SATMI catalog context:\n\n"
                f"{_comparison_table_from_products(recommended_products)}"
            )
            response_source = "comparison_enforcer"
        _record_feedback_event(state=state, reason="comparison_missing_table", response_text=response or "")

    if not response:
        response = _deterministic_grounded_fallback(
            state=state,
            policy_context=policy_context,
            product_snippets=product_snippets,
            next_step_guidance=next_step_guidance,
        )
        response_source = "deterministic_fallback"
        _record_feedback_event(state=state, reason="llm_compose_fallback_used", response_text=response)

    if comparison_required and not _has_markdown_table(response) and recommended_products:
        response = (
            "Here is a grounded comparison from the current SATMI catalog context:\n\n"
            f"{_comparison_table_from_products(recommended_products)}"
        )
        response_source = "comparison_enforcer"
        _record_feedback_event(state=state, reason="comparison_table_enforced_post_fallback", response_text=response)

    # THE ABSOLUTE KILL SWITCH: Wipe cards for non-shopping intents
    final_intent = str(state.get("intent", "")).strip().lower()
    if final_intent not in ["shopping", "order_tracking"]:
        recommended_products = []

    return {
        **state,
        "status": "active",
        "response": response,
        "response_text": response,
        "recommended_products": recommended_products,
        "auth_required": auth_required,
        "context_packet": context_packet,
        "conversation_summary": summary,
        "user_preferences": user_preferences,
        "async_task_id": tool_result.get("task_id"),
        "async_task_status": tool_result.get("status"),
        "internal_logs": [
            *_state_logs(state),
            {
                "event": "response_composed",
                "status": "active",
                "policy_snippet_count": len(policy_context),
                "product_snippet_count": len(product_snippets),
                "has_summary": bool(summary),
                "has_preferences": bool(user_preferences),
                "response_source": response_source,
                "retrieval_source": tool_result.get("source"),
            },
        ],
    }
