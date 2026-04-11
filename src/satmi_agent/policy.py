from __future__ import annotations

import re
from functools import lru_cache
import json
from pathlib import Path

from satmi_agent.config import settings


DEFAULT_POLICY_KNOWLEDGE_BASE = [
    {
        "id": "cancel_window",
        "intent": "support",
        "tags": {"cancel", "order", "refund"},
        "title": "Cancellation window",
        "content": "Orders can be cancelled before fulfillment. After shipment, cancellation is unavailable and return policy applies.",
    },
    {
        "id": "refund_timeline",
        "intent": "support",
        "tags": {"refund", "return", "order"},
        "title": "Refund timeline",
        "content": "Approved refunds are typically processed to the original payment method within 5-7 business days.",
    },
    {
        "id": "portal_actions",
        "intent": "support",
        "tags": {"cancel", "cancellation", "address", "replacement", "replace", "update", "order"},
        "title": "Account portal actions",
        "content": "Order cancellation, address updates, and replacement requests must be completed through https://accounts.satmi.in.",
    },
    {
        "id": "support_contact",
        "intent": "support",
        "tags": {"contact", "whatsapp", "call", "phone", "email", "support"},
        "title": "Support contact details",
        "content": "Please contact support@satmi.in. The support team responds within 24 hours.",
    },
    {
        "id": "shipping_updates",
        "intent": "support",
        "tags": {"track", "shipment", "delivery"},
        "title": "Tracking updates",
        "content": "Tracking events can take up to 24 hours to refresh after carrier scans.",
    },
    {
        "id": "product_reco",
        "intent": "shopping",
        "tags": {"recommend", "buy", "product"},
        "title": "Recommendations policy",
        "content": "Product recommendations are based on current catalog availability and may change as inventory updates.",
    },
]


TOXIC_TERMS = {"kill", "hate", "idiot", "stupid"}


def tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z']+", text.lower()))


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _resolve_policy_kb_path() -> Path:
    configured = Path(settings.policy_kb_path)
    if configured.is_absolute():
        return configured
    return _project_root() / configured


@lru_cache(maxsize=1)
def _load_policy_kb() -> list[dict]:
    path = _resolve_policy_kb_path()
    if not path.exists():
        return DEFAULT_POLICY_KNOWLEDGE_BASE

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list) and all(isinstance(item, dict) for item in data):
            normalized: list[dict] = []
            for item in data:
                normalized.append(
                    {
                        "id": str(item.get("id", "policy_item")),
                        "intent": str(item.get("intent", "support")),
                        "tags": set(item.get("tags", [])),
                        "title": str(item.get("title", "Policy")),
                        "content": str(item.get("content", "")),
                    }
                )
            return normalized
    except Exception:
        return DEFAULT_POLICY_KNOWLEDGE_BASE

    return DEFAULT_POLICY_KNOWLEDGE_BASE


def detect_guardrail_issues(message: str) -> list[str]:
    issues: list[str] = []
    words = tokenize(message)

    if words.intersection(TOXIC_TERMS):
        issues.append("toxic_language_detected")

    if re.search(r"\b\d{13,19}\b", message):
        issues.append("possible_card_number_detected")
    if re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", message):
        issues.append("email_detected")
    if re.search(r"\b\+?\d[\d\s\-()]{8,}\b", message):
        issues.append("phone_number_detected")

    return issues


def retrieve_policy_context(message: str, intent: str, max_items: int = 2) -> list[dict[str, str]]:
    words = tokenize(message)
    scored: list[tuple[int, dict[str, str]]] = []
    effective_max_items = max_items or settings.policy_retrieval_max_items
    knowledge_base = _load_policy_kb()

    for item in knowledge_base:
        if item["intent"] not in {intent, "support", "shopping" if intent == "mixed" else intent} and intent != "unknown":
            continue
        score = len(words.intersection(item["tags"]))
        if score > 0:
            scored.append((score, item))

    scored.sort(key=lambda value: value[0], reverse=True)
    return [
        {
            "id": item["id"],
            "title": item["title"],
            "content": item["content"],
        }
        for _, item in scored[:effective_max_items]
    ]
