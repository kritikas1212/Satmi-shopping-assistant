from __future__ import annotations

import json
import logging
import random
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

from satmi_agent.config import settings
from satmi_agent.config.persona import (
    FINAL_SYSTEM_PROMPT as SATMI_SYSTEM_PROMPT,
    GENERAL_CONVERSATION_SYSTEM_PROMPT,
)


MAX_OUTPUT_TOKENS = 4096

_DEFAULT_GEMINI_FALLBACK_MODELS = (
    "gemini-2.5-flash",
    "gemini-2.0-flash",
)


_INTERNAL_LABEL_PATTERN = re.compile(
    r"(?im)^\s*(next step|internal note|reasoning|tool output|metadata)\s*:\s*"
)
llm_logger = logging.getLogger("satmi_agent.llm")


_RAW_INTENT_ALIASES: dict[str, str] = {
    # --- order_tracking ---
    "track_order": "order_tracking",
    "tracking": "order_tracking",
    "order_status": "order_tracking",
    "order-status": "order_tracking",
    "delivery_tracking": "order_tracking",
    "shipment_tracking": "order_tracking",
    "order_tracking_inquiry": "order_tracking",
    "check_order_status": "order_tracking",
    "order_update": "order_tracking",
    "delivery_status": "order_tracking",
    "shipment_status": "order_tracking",
    "track_my_package": "order_tracking",
    "where_is_my_order": "order_tracking",

    # --- shopping ---
    "product_discovery": "shopping",
    "shopping_query": "shopping",
    "browse_products": "shopping",
    "product_suggestion": "shopping",
    "product_recommendation": "shopping",
    "product_recommendation_request": "shopping",
    "product_inquiry": "shopping",
    "product_information_inquiry": "shopping",
    "product_information_and_inquiry": "shopping",
    "product_inquiry_recommendation_spiritual_items_for_prosperity": "shopping",
    "product_inquiry_and_recommendation": "shopping",
    "product_discovery_sales_inquiry": "shopping",
    "sales_inquiry": "shopping",
    "shopping_assistance": "shopping",
    "purchase_inquiry": "shopping",
    "item_lookup": "shopping",
    "search_products": "shopping",

    # --- policy_brand_faq ---
    "returns_policy_query": "policy_brand_faq",
    "returns_policy": "policy_brand_faq",
    "refund_policy": "policy_brand_faq",
    "return_policy": "policy_brand_faq",
    "inquire_about_return_policy": "policy_brand_faq",
    "return_order": "policy_brand_faq",
    "return_request": "policy_brand_faq",
    "order_cancellation": "policy_brand_faq",
    "cancel_order": "policy_brand_faq",
    "request_human_for_cancellation": "policy_brand_faq",
    "information_about_satmi": "policy_brand_faq",
    "brand_inquiry": "policy_brand_faq",
    "faq": "policy_brand_faq",
    "product_complaint": "policy_brand_faq",
    "shipping_policy": "policy_brand_faq",
    "delivery_policy": "policy_brand_faq",
    "warranty_inquiry": "policy_brand_faq",
    "contact_support": "policy_brand_faq",

    # --- authentication ---
    "account_login": "authentication",
    "account_support": "authentication",
    "provide_update_contact_and_payment_information": "authentication",
    "provide_contact_and_payment_information": "authentication",
    "update_contact_information": "authentication",
    "payment_information": "authentication",
    "user_registration": "authentication",
    "login_issues": "authentication",

    # --- general ---
    "general_inquiry": "general",
    "general_query": "general",
    "small_talk": "general",
    "general_support": "general",
    "greetings": "general",
    "greeting": "general",
    "chit_chat": "general",
    "other": "general",
    "human_agent_request": "general",
}


def _retry_delay_seconds(response: httpx.Response | None, attempt: int) -> float:
    """Compute delay for retries, honoring Retry-After when present."""
    if response is not None:

        retry_after = str(response.headers.get("Retry-After", "")).strip()
        if retry_after:
            if retry_after.isdigit():
                return max(0.0, float(retry_after))
            try:
                target = parsedate_to_datetime(retry_after)
                if target.tzinfo is None:
                    target = target.replace(tzinfo=timezone.utc)
                wait = (target - datetime.now(timezone.utc)).total_seconds()
                return max(0.0, wait)
            except Exception:
                pass

    base = settings.gemini_retry_base_delay_seconds * (2**attempt)
    jitter = random.uniform(0.0, max(0.0, settings.gemini_retry_jitter_seconds))
    return min(max(0.0, settings.gemini_retry_max_delay_seconds), base + jitter)


def _post_gemini_json(
    *,
    endpoint: str,
    payload: dict[str, object],
    timeout_seconds: float,
    retry_count: int,
    op_name: str,
) -> dict[str, object] | None:
    model_mark = "/models/"
    suffix = ":generateContent"
    model_name = settings.model_name
    if model_mark in endpoint and suffix in endpoint:
        try:
            model_name = endpoint.split(model_mark, 1)[1].split(suffix, 1)[0]
        except Exception:
            model_name = settings.model_name

    candidate_models: list[str] = [model_name]
    for fallback_name in _DEFAULT_GEMINI_FALLBACK_MODELS:
        if fallback_name and fallback_name not in candidate_models:
            candidate_models.append(fallback_name)

    for model_idx, active_model in enumerate(candidate_models):
        active_endpoint = endpoint.replace(f"/models/{model_name}:generateContent", f"/models/{active_model}:generateContent")
        for attempt in range(retry_count + 1):
            response: httpx.Response | None = None
            try:
                with httpx.Client(timeout=timeout_seconds) as client:
                    response = client.post(active_endpoint, json=payload)

                if settings.gemini_retry_on_429 and response.status_code == 429 and attempt < retry_count:
                    if "GenerateRequestsPerDay" in (response.text or ""):
                        llm_logger.error("%s daily quota exhausted (model=%s). Failing fast.", op_name, active_model)
                        break
                    
                    llm_logger.warning(
                        "%s rate-limited (model=%s attempt=%s). status=%s body=%s. Failing fast without sleep.",
                        op_name,
                        active_model,
                        attempt,
                        response.status_code,
                        (response.text or "")[:1200],
                    )
                    break

                if settings.gemini_retry_on_5xx and response.status_code >= 500 and attempt < retry_count:
                    delay = _retry_delay_seconds(response, attempt)
                    llm_logger.warning(
                        "%s transient server error (model=%s attempt=%s). status=%s body=%s Retrying in %.2fs",
                        op_name,
                        active_model,
                        attempt,
                        response.status_code,
                        (response.text or "")[:1200],
                        delay,
                    )
                    time.sleep(delay)
                    continue

                response.raise_for_status()
                if model_idx > 0:
                    llm_logger.info("%s recovered via fallback model=%s", op_name, active_model)
                return response.json()
            except httpx.RequestError as exc:
                if attempt < retry_count:
                    delay = _retry_delay_seconds(response, attempt)
                    llm_logger.warning(
                        "%s request error (model=%s attempt=%s): %s. Retrying in %.2fs",
                        op_name,
                        active_model,
                        attempt,
                        exc,
                        delay,
                    )
                    time.sleep(delay)
                    continue
                llm_logger.warning("%s failed after retries for model=%s: %s", op_name, active_model, exc)
                break
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                retryable = (settings.gemini_retry_on_5xx and status_code >= 500) or (settings.gemini_retry_on_429 and status_code == 429)
                if retryable and model_idx < len(candidate_models) - 1:
                    llm_logger.warning(
                        "%s switching model after HTTP error. from=%s status=%s body=%s",
                        op_name,
                        active_model,
                        status_code,
                        (exc.response.text or "")[:1200],
                    )
                    break
                llm_logger.error(
                    "%s failed with HTTP error. model=%s status=%s body=%s error=%s",
                    op_name,
                    active_model,
                    status_code,
                    (exc.response.text or "")[:2000],
                    exc,
                )
                return None
            except Exception as exc:
                llm_logger.exception("%s failed unexpectedly for model=%s: %s", op_name, active_model, exc)
                return None

    return None


def _sanitize_user_facing_text(text: str) -> str:
    cleaned = _INTERNAL_LABEL_PATTERN.sub("", text or "")
    # Remove leaked internal tool snippets if model emits pseudo-code.
    cleaned = re.sub(r"```(?:json|python)?\s*\{\s*\"tool_code\".*?\}\s*```", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"\{\s*\"tool_code\"\s*:\s*\".*?\"\s*\}", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"(?im)^.*search_products\(query=.*$", "", cleaned)
    cleaned = re.sub(r"(?im)^.*tool_code.*$", "", cleaned)
    
    # Strip bare JSON objects that slip through
    if re.search(r"^\s*\{[\s\S]*\}\s*$", cleaned):
        cleaned = re.sub(r"^\s*\{[\s\S]*\}\s*$", "", cleaned)

    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = cleaned.strip()
    if not cleaned or (cleaned.startswith("{") and cleaned.endswith("}")):
        return "I can help with that. Tell me what outcome you want, and I will guide you step by step."
    return cleaned


def _parse_intent_json(raw: str) -> tuple[str, float] | None:
    import re
    # Use regex to find the JSON block {...} anywhere in the output.
    # This naturally ignores markdown backticks or "json" labels.
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    clean_str = match.group(0) if match else raw.strip()

    if clean_str.startswith("```json"):
        clean_str = clean_str[7:]
    elif clean_str.startswith("```"):
        clean_str = clean_str[3:]
    if clean_str.endswith("```"):
        clean_str = clean_str[:-3]
    clean_str = clean_str.strip()

    payload: dict[str, object] | None = None
    try:
        payload = json.loads(clean_str)
    except Exception:
        # Tolerate partially malformed output by extracting intent/confidence directly.
        lowered = raw.lower()
        intent_match = re.search(r'"?intent"?\s*[:=]\s*"?([a-z_]+)', lowered)
        conf_match = re.search(r'"?confidence"?\s*[:=]\s*([0-9]*\.?[0-9]+)', lowered)
        if not intent_match:
            return None
        payload = {
            "intent": intent_match.group(1),
            "confidence": conf_match.group(1) if conf_match else 0.0,
        }

    intent = str(payload.get("intent", "")).strip().lower()
    if intent not in {"shopping", "order_tracking", "policy_brand_faq", "general"}:
        return None

    try:
        confidence = float(payload.get("confidence", 0.0))
    except Exception:
        confidence = 0.0

    confidence = max(0.0, min(1.0, confidence))
    return intent, confidence


def extract_search_keywords_with_llm(*, user_message: str, policy_context: list[dict[str, str]] | None = None) -> str | None:
    """Extract a concise product search query from conversational text."""
    if settings.llm_provider.lower() != "gemini":
        return None
    if not settings.gemini_api_key:
        return None

    # Spiritual benefit → product name mapping (offline fast-path)
    # Avoids extra LLM call for common need-based queries
    _BENEFIT_TO_PRODUCT: list[tuple[re.Pattern, str]] = [
        (re.compile(r"\b(best.sell|bestsell|trending|popular|top.product|most.popular|most.sought)\b", re.I), "Karungali Rudraksha Rose Quartz"),
        (re.compile(r"\b(anxiety|stress|calm|nervous|worry|panic)\b", re.I), "Rudraksha Amethyst"),
        (re.compile(r"\b(wealth|money|prosperity|abundance|financial|rich|luck)\b", re.I), "Pyrite"),
        (re.compile(r"\b(love|relationship|marriage|heart|romantic)\b", re.I), "Rose Quartz"),
        (re.compile(r"\b(protection|negativ|evil|bad energy)\b", re.I), "Karungali Rudraksha"),
        (re.compile(r"\b(spiritual|meditation|growth|awareness|divine)\b", re.I), "Rudraksha Karungali"),
        (re.compile(r"\b(healing|wellness|well.being)\b", re.I), "Rudraksha Crystal"),
        (re.compile(r"\b(confidence|courage|strength|power)\b", re.I), "Pyrite Tiger Eye"),
        (re.compile(r"\b(chakra|energy|balance)\b", re.I), "Crystal Rudraksha"),
        (re.compile(r"\b(karungali)\b", re.I), "Karungali"),
        (re.compile(r"\b(rudraksha)\b", re.I), "Rudraksha"),
        (re.compile(r"\b(mala|bracelet|crystal|pyrite|quartz)\b", re.I), "Karungali Rudraksha mala"),
    ]
    for pattern, product in _BENEFIT_TO_PRODUCT:
        if pattern.search(user_message):
            return product

    context_str = ""
    if policy_context:
        lines = [f"{item.get('title', '')}: {item.get('content', '')}" for item in policy_context]
        context_str = "Knowledge Base Context:\n" + "\n".join(lines) + "\n\n"

    prompt = (
        "Extract a concise product search query from the user's message.\n"
        "CRITICAL RULES:\n"
        "- If the user specifies a known product (e.g., 'Karungali', '5 Mukhi Rudraksha'), output that product name.\n"
        "- If the user expresses a need (e.g., 'attracting money', 'anxiety relief'), output the relevant product name from SATMI catalog (e.g., 'Pyrite', 'Rudraksha Amethyst').\n"
        "- Output ONLY the product search term, no JSON, no labels, no punctuation.\n"
        "- Query can be 1 to 5 words. Longer is fine if it adds specificity.\n\n"
        f"{context_str}"
        f"User message: {user_message}"
    )

    endpoint = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{settings.model_name}:generateContent"
        f"?key={settings.gemini_api_key}"
    )
    payload = {
        "system_instruction": {"parts": [{"text": SATMI_SYSTEM_PROMPT}]},
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 128},
    }

    body = _post_gemini_json(
        endpoint=endpoint,
        payload=payload,
        timeout_seconds=8.0,
        retry_count=max(0, settings.gemini_retry_count),
        op_name="extract_search_keywords",
    )
    if not body:
        return None

    candidates = body.get("candidates", [])
    if not candidates:
        return None
    parts = candidates[0].get("content", {}).get("parts", [])
    if not parts:
        return None

    raw = str(parts[0].get("text", "")).strip().strip("`")
    raw = raw.replace("\n", " ").strip()
    if not raw:
        return None

    # Strip common LLM preamble patterns before extracting tokens
    # e.g. "Namaste! The product is: Karungali" → "Karungali"
    for preamble in ["namaste", "sure", "the product is", "search for", "query:", "answer:", "for", "here"]:
        if raw.lower().startswith(preamble):
            raw = raw[len(preamble):].strip().lstrip("!:,.- ").strip()
            break

    # Clean up but allow up to 6 words
    tokens = re.findall(r"[a-zA-Z0-9']+", raw)
    if not tokens:
        return None
    # Reject garbage: filter tokens shorter than 2 chars
    valid_tokens = [t for t in tokens if len(t) >= 2]
    if not valid_tokens:
        return None
    result = " ".join(valid_tokens[:6])
    # Final sanity check - must be at least 3 chars total
    return result if len(result) >= 3 else None


def classify_intent_with_llm(*, user_message: str, message_history: list[dict[str, str]] | None = None) -> tuple[str, float] | None:
    if settings.llm_provider.lower() != "gemini":
        return None

    if not settings.gemini_api_key:
        return None

    normalized_history = _ensure_system_prompt_first(message_history, SATMI_SYSTEM_PROMPT)
    history_lines: list[str] = []
    for item in normalized_history[-8:]:
        role = str(item.get("role", "user")).strip().lower()
        content = str(item.get("content", "")).strip()
        if role == "system" or not content:
            continue
        history_lines.append(f"{role}: {content}")

    user_prompt = (
        "Classify the user's latest message into exactly one intent from this closed set:\n"
        "- shopping\n"
        "- order_tracking\n"
        "- policy_brand_faq\n"
        "- general\n\n"
        "CRITICAL ROUTING RULES:\n"
        "- Map to 'shopping' if the user asks for recommendations, specific items (e.g., 'Karungali', 'Rudraksha'), OR asks broad discovery questions like 'What do you offer?', 'What products do you sell?', 'Show me your collection', or 'I need a gift.'\n"
        "- Map to 'policy_brand_faq' ONLY if they ask about shipping, returns, refunds, guarantees (2X assurance), or contact info.\n"
        "- Map to 'order_tracking' for tracking orders, delivery status, shipment info, or cancellations.\n"
        "- Map to 'general' for simple greetings or non-commerce chit-chat.\n\n"
        "Return ONLY compact JSON with keys intent and confidence.\n"
        "Example: {\"intent\":\"shopping\",\"confidence\":0.92}\n\n"
        f"Conversation history:\n{chr(10).join(history_lines) if history_lines else '- none'}\n\n"
        f"Latest user message: {user_message}"
    )

    system_prompt = (
        f"{SATMI_SYSTEM_PROMPT}\n\n"
        "ABSOLUTE RULE: You must respond with ONLY a valid, raw JSON object. Do not include markdown backticks. "
        "Do not include conversational text like 'Here is the JSON'. Your output must be instantly parsable by json.loads()."
    )

    endpoint = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{settings.model_name}:generateContent"
        f"?key={settings.gemini_api_key}"
    )
    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"parts": [{"text": user_prompt}]}],
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 200,
            "responseMimeType": "application/json",
        },
    }

    body = _post_gemini_json(
        endpoint=endpoint,
        payload=payload,
        timeout_seconds=10.0,
        retry_count=max(0, settings.gemini_retry_count),
        op_name="classify_intent",
    )
    if not body:
        llm_logger.error("classify_intent_with_llm: empty body from Gemini")
        return None

    candidates = body.get("candidates", [])
    if not candidates:
        llm_logger.error("classify_intent_with_llm: missing candidates body=%s", json.dumps(body, ensure_ascii=True)[:2000])
        return None
    parts = candidates[0].get("content", {}).get("parts", [])
    if not parts:
        llm_logger.error("classify_intent_with_llm: missing parts body=%s", json.dumps(body, ensure_ascii=True)[:2000])
        return None

    text = str(parts[0].get("text", "")).strip()
    if not text:
        llm_logger.error("classify_intent_with_llm: empty text body=%s", json.dumps(body, ensure_ascii=True)[:2000])
        return None

    # --- STRIP MARKDOWN FORMATTING ---
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    # ---------------------------------

    try:
        parsed = json.loads(text)
    except Exception:
        llm_logger.error("classify_intent_with_llm: invalid JSON output text=%s", text[:1200])
        return None

    intent = str(parsed.get("intent", "")).strip().lower()
    if intent not in {"shopping", "order_tracking", "policy_brand_faq", "general"}:
        return None

    try:
        confidence = float(parsed.get("confidence", 0.0))
    except Exception:
        confidence = 0.0

    confidence = max(0.0, min(1.0, confidence))
    return intent, confidence


def _ensure_system_prompt_first(message_history: list[dict[str, str]] | None, system_prompt: str) -> list[dict[str, str]]:
    """Normalize chat history to guarantee a single system prompt at index 0."""
    normalized: list[dict[str, str]] = []
    for item in message_history or []:
        role = str(item.get("role", "")).strip().lower()
        content = str(item.get("content", "")).strip()
        if not role or not content:
            continue
        if role == "system":
            continue
        normalized.append({"role": role, "content": content})
    return [{"role": "system", "content": system_prompt}, *normalized]


def refine_response_with_llm(*, user_message: str, base_response: str, policy_context: list[dict[str, str]] | None = None) -> str:
    if not settings.llm_response_refinement_enabled:
        return base_response

    if settings.llm_provider.lower() != "gemini":
        return base_response

    if not settings.gemini_api_key:
        return base_response

    system_prompt = SATMI_SYSTEM_PROMPT

    context_lines = []
    for item in policy_context or []:
        title = str(item.get("title", "Policy"))
        content = str(item.get("content", ""))
        context_lines.append(f"- {title}: {content}")

    user_prompt = (
        f"User message: {user_message}\n"
        f"Draft response: {base_response}\n"
        f"Policy context:\n{chr(10).join(context_lines) if context_lines else '- none'}\n\n"
        "Rewrite the draft response following your system instructions. "
        "Do not add new facts. Preserve order IDs, statuses, and key actions exactly."
    )

    endpoint = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{settings.model_name}:generateContent"
        f"?key={settings.gemini_api_key}"
    )
    payload = {
        "system_instruction": {
            "parts": [{"text": system_prompt}]
        },
        "contents": [{"parts": [{"text": user_prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": MAX_OUTPUT_TOKENS},
    }

    body = _post_gemini_json(
        endpoint=endpoint,
        payload=payload,
        timeout_seconds=12.0,
        retry_count=max(0, settings.gemini_retry_count),
        op_name="refine_response",
    )
    if not body:
        return base_response

    candidates = body.get("candidates", [])
    if not candidates:
        return base_response
    content = candidates[0].get("content", {})
    parts = content.get("parts", [])
    if not parts:
        return base_response
    text = str(parts[0].get("text", "")).strip()
    if not text:
        return base_response
    return _sanitize_user_facing_text(text)


def _prepare_transcript_for_classification(transcript_lines: list[str], *, char_limit: int) -> str:
    joined = "\n".join(transcript_lines).strip()
    if len(joined) <= char_limit:
        return joined

    # Keep both ends of the transcript and summarize omitted middle turns.
    half = max(char_limit // 2, 2000)
    head = joined[:half]
    tail = joined[-half:]
    omitted_chars = max(len(joined) - (len(head) + len(tail)), 0)
    return (
        f"{head}\n"
        f"[... transcript truncated: omitted approximately {omitted_chars} characters from middle ...]\n"
        f"{tail}"
    )


def _intent_classifier_api_key() -> str | None:
    key = settings.gemini_intent_classifier_api_key
    if key:
        return key
    if settings.gemini_api_key:
        llm_logger.warning("Intent classifier API key missing, falling back to main Gemini API key.")
        return settings.gemini_api_key
    return None


def _extract_usage_metadata(body: dict[str, object]) -> dict[str, int | None]:
    usage = body.get("usageMetadata") if isinstance(body, dict) else None
    if not isinstance(usage, dict):
        return {
            "prompt_token_count": None,
            "candidates_token_count": None,
            "total_token_count": None,
        }

    def _to_int(value: object) -> int | None:
        try:
            if value is None:
                return None
            return int(value)
        except Exception:
            return None

    return {
        "prompt_token_count": _to_int(usage.get("promptTokenCount")),
        "candidates_token_count": _to_int(usage.get("candidatesTokenCount")),
        "total_token_count": _to_int(usage.get("totalTokenCount")),
    }


def _extract_json_object_text(raw_text: str) -> str:
    text = (raw_text or "").strip()
    if not text:
        return text

    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()

    if not text.startswith("{"):
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            text = match.group(0).strip()

    return text


def _normalize_raw_intent_label(value: str) -> str:
    # Lower-case, collapse whitespace → underscore, strip stray punctuation
    # but keep underscore and hyphen so snake_case aliases still match.
    normalized = str(value or "").strip().lower()
    normalized = re.sub(r"[/&()]", " ", normalized)  # replace punctuation with space so they get collapsed to _
    normalized = re.sub(r"\s+", "_", normalized)       # spaces → _
    normalized = re.sub(r"_+", "_", normalized)        # collapse multiple __
    normalized = normalized.strip("_")
    normalized = _RAW_INTENT_ALIASES.get(normalized, normalized)
    return normalized


def classify_conversation_intent_with_llm(
    *,
    transcript: list[dict[str, str]],
    source_version: str,
) -> dict[str, object] | None:
    if settings.llm_provider.lower() != "gemini":
        return None
    classifier_api_key = _intent_classifier_api_key()
    if not classifier_api_key:
        return None

    # Respect runtime setting so admins can switch between strict guardrailed
    # classification and raw/unfiltered dynamic intent labels.
    raw_mode = bool(settings.conversation_intent_raw_mode)

    if not transcript:
        return {
            "intent_label": "unknown",
            "raw_intent_label": "",
            "confidence": 0.0,
            "rationale_short": "No transcript available.",
            "needs_review": True,
            "model_name": settings.model_name,
            "model_version": settings.model_name,
            "source_version": source_version,
            "classifier_mode": "raw" if raw_mode else "guardrailed",
            "raw_output": "",
            "raw_error": "no_transcript",
            "prompt_token_count": None,
            "completion_token_count": None,
            "total_token_count": None,
            "prompt_char_count": 0,
        }

    transcript_lines: list[str] = []
    for turn in transcript:
        role = str(turn.get("role", "")).strip().lower()
        content = str(turn.get("content", "")).strip()
        if role not in {"user", "assistant", "system"} or not content:
            continue
        transcript_lines.append(f"{role}: {content}")

    prepared_transcript = _prepare_transcript_for_classification(
        transcript_lines,
        char_limit=max(int(settings.conversation_intent_transcript_char_limit), 2000),
    )

    enum_choices = ["Shopping & Products", "Order Tracking", "Returns & Support", "General/Spiritual"]
    try:
        from pathlib import Path
        import json
        cat_path = Path("data/categories.json")
        if cat_path.exists():
            loaded = json.loads(cat_path.read_text("utf-8"))
            if loaded:
                enum_choices = loaded
    except Exception:
        pass

    cat_str = ", ".join(f"'{c}'" for c in enum_choices)

    if raw_mode:
        prompt = (
            f"Read the full conversation transcript and reply with the exact intent phrase in 1 to 3 simple words, followed by a pipe '|', followed by the broad category (MUST be exactly one of: {cat_str}).\n"
            f"Example format: track order | {enum_choices[0]}\n"
            "Do not output JSON, labels, explanations, punctuation, or any extra text. If unsure, pick the most relevant category.\n\n"
            f"Transcript:\n{prepared_transcript}"
        )
    else:
        prompt = (
            "You are an elite NLP intent classification engine for SATMI. Your job is to read a sanitized chat transcript and determine the user's exact intent without being restricted to predefined categories. \n"
            "CRITICAL RULES: \n"
            "1. You must invent the most accurate label possible. \n"
            "2. The dynamic_intent_label MUST be formatted in lowercase snake_case. \n"
            "3. Use an [action]_[subject] format whenever possible. \n"
            "4. Be specific but concise (max 4 words). \n"
            "5. Base your confidence score purely on how explicit the user was.\n\n"
            f"Transcript:\n{prepared_transcript}"
        )

    endpoint = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{settings.model_name}:generateContent"
        f"?key={classifier_api_key}"
    )

    generation_config: dict[str, object] = {
        "temperature": 0.0,
        "maxOutputTokens": 1024 if raw_mode else 512,
    }

    if not raw_mode:
        generation_config["responseMimeType"] = "application/json"
        generation_config["responseSchema"] = {
            "type": "OBJECT",
            "required": ["step_1_user_goal_analysis", "step_2_dynamic_intent_label", "step_3_confidence_score", "step_4_broad_category", "needs_human_review"],
            "properties": {
                "step_1_user_goal_analysis": {
                    "type": "STRING",
                    "description": "Briefly analyze the conversation. What is the user's root objective?"
                },
                "step_2_dynamic_intent_label": {
                    "type": "STRING",
                    "description": "Generate a concise, snake_case label representing the core action (e.g., request_refund, ask_product_sizing, check_shipping_time)."
                },
                "step_3_confidence_score": {
                    "type": "INTEGER",
                    "description": "Rate your confidence in this label from 1 to 100 based on the clarity of the user's phrasing."
                },
                "step_4_broad_category": {
                    "type": "STRING",
                    "description": f"Classify the overall conversation into EXACTLY one of these broad categories. You MUST choose one of: {cat_str}.",
                    "enum": enum_choices
                },
                "needs_human_review": {
                    "type": "BOOLEAN",
                    "description": "True if the user's intent is highly ambiguous, contradictory, or emotionally escalated."
                },
            },
        }

    payload = {
        "system_instruction": {
            "parts": [
                {
                    "text": (
                        "You are an elite NLP intent classification engine for SATMI. "
                        "Your job is to read a sanitized chat transcript and determine the user's exact intent without being restricted to predefined categories. "
                        "CRITICAL RULES: "
                        "1. You must invent the most accurate label possible. "
                        "2. The dynamic_intent_label MUST be formatted in lowercase snake_case. "
                        "3. Use an [action]_[subject] format whenever possible. "
                        "4. Be specific but concise (max 4 words). "
                        "5. Base your confidence score purely on how explicit the user was."
                    )
                }
            ]
        },
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": generation_config,
    }

    # Use a higher retry count for intent classification since it runs in
    # the background worker and can afford to wait out 429 rate-limit delays.
    _classifier_retry_count = max(5, settings.gemini_strict_retry_count)

    body = _post_gemini_json(
        endpoint=endpoint,
        payload=payload,
        timeout_seconds=30.0,
        retry_count=_classifier_retry_count,
        op_name="classify_conversation_intent",
    )
    
    if not body and classifier_api_key != settings.gemini_api_key and settings.gemini_api_key:
        llm_logger.warning("classify_conversation_intent: primary classifier key failed, falling back to gemini_api_key.")
        endpoint = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{settings.model_name}:generateContent"
            f"?key={settings.gemini_api_key}"
        )
        body = _post_gemini_json(
            endpoint=endpoint,
            payload=payload,
            timeout_seconds=15.0,
            retry_count=_classifier_retry_count,
            op_name="classify_conversation_intent_fallback",
        )

    if not body:
        return None

    token_usage = _extract_usage_metadata(body)

    candidates = body.get("candidates", [])
    if not candidates:
        return None
    parts = candidates[0].get("content", {}).get("parts", [])
    if not parts:
        return None

    text = str(parts[0].get("text", "")).strip()
    if not text:
        return None

    if raw_mode:
        raw_completion = text.strip()
        intent_phrase = raw_completion
        category = ""
        if "|" in raw_completion:
            parts = raw_completion.split("|", 1)
            intent_phrase = parts[0].strip()
            category = parts[1].strip()

        return {
            "intent_label": intent_phrase or "unknown",
            "raw_intent_label": raw_completion,
            "intent_subcategory": category,
            "confidence": 0.0,
            "rationale_short": "",
            "needs_review": False,
            "model_name": settings.model_name,
            "model_version": settings.model_name,
            "source_version": source_version,
            "classifier_mode": "raw",
            "raw_output": raw_completion,
            "raw_error": "",
            "prompt_token_count": token_usage["prompt_token_count"],
            "completion_token_count": token_usage["candidates_token_count"],
            "total_token_count": token_usage["total_token_count"],
            "prompt_char_count": len(prepared_transcript),
        }

    try:
        parsed = json.loads(text)
    except Exception:
        return None

    raw_intent_label = str(parsed.get("step_2_dynamic_intent_label", "unknown")).strip()
    intent_label = raw_intent_label or "unknown"

    try:
        conf_val = float(parsed.get("step_3_confidence_score", 0.0))
        confidence = conf_val / 100.0 if conf_val > 1.0 else conf_val
    except Exception:
        confidence = 0.0
    confidence = max(0.0, min(confidence, 1.0))

    rationale_short = str(parsed.get("step_1_user_goal_analysis", "")).strip()
    if len(rationale_short) > 240:
        rationale_short = rationale_short[:240].rstrip()

    needs_review = bool(parsed.get("needs_human_review", False))
    if intent_label == "unknown":
        needs_review = True

    intent_subcategory = str(parsed.get("step_4_broad_category", "")).strip()

    return {
        "intent_label": intent_label,
        "raw_intent_label": raw_intent_label,
        "confidence": confidence,
        "rationale_short": rationale_short,
        "needs_review": needs_review,
        "model_name": settings.model_name,
        "model_version": settings.model_name,
        "source_version": source_version,
        "classifier_mode": "guardrailed",
        "raw_output": text[:12000],
        "raw_error": "",
        "prompt_token_count": token_usage["prompt_token_count"],
        "completion_token_count": token_usage["candidates_token_count"],
        "total_token_count": token_usage["total_token_count"],
        "prompt_char_count": len(prepared_transcript),
        "intent_subcategory": intent_subcategory,
    }

def classify_batch_conversation_intents_with_llm(
    *,
    batch: dict[str, list[dict[str, str]]],
    source_version: str,
) -> dict[str, dict[str, object]]:
    """Classify multiple conversations in a single LLM prompt (Micro-batching)."""
    if settings.llm_provider.lower() != "gemini":
        return {}
    classifier_api_key = _intent_classifier_api_key()
    if not classifier_api_key:
        return {}

    if not batch:
        return {}

    batch_payload_text = ""
    for idx, (conv_id, transcript) in enumerate(batch.items()):
        transcript_lines: list[str] = []
        for turn in transcript:
            role = str(turn.get("role", "")).strip().lower()
            content = str(turn.get("content", "")).strip()
            if role not in {"user", "assistant", "system"} or not content:
                continue
            transcript_lines.append(f"{role}: {content}")

        prepared_transcript = _prepare_transcript_for_classification(
            transcript_lines,
            char_limit=1500,  # Slightly shorter for batching
        )
        batch_payload_text += f"--- CONVERSATION {idx + 1} (ID: {conv_id}) ---\n{prepared_transcript}\n\n"

    prompt = (
        "You are an elite NLP intent classification engine for SATMI. You will be provided with a batch of multiple distinct chat transcripts.\n"
        "Your job is to read each sanitized chat transcript and determine the user's exact intent without being restricted to predefined categories.\n"
        "CRITICAL RULES:\n"
        "1. You must invent the most accurate label possible for each conversation.\n"
        "2. The dynamic_intent_label MUST be formatted in lowercase snake_case.\n"
        "3. Use an [action]_[subject] format whenever possible.\n"
        "4. Be specific but concise (max 4 words).\n"
        "5. Base your confidence score purely on how explicit the user was.\n"
        "6. Return an array of objects. You MUST include exactly one object for every conversation provided.\n\n"
        f"{batch_payload_text}"
    )

    endpoint = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{settings.model_name}:generateContent"
        f"?key={classifier_api_key}"
    )

    enum_choices = ["Shopping & Products", "Order Tracking", "Returns & Support", "General/Spiritual"]
    cat_str = ", ".join(f"'{c}'" for c in enum_choices)

    generation_config: dict[str, object] = {
        "temperature": 0.0,
        "maxOutputTokens": 2048,
        "responseMimeType": "application/json",
        "responseSchema": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "required": ["conversation_id", "step_1_user_goal_analysis", "step_2_dynamic_intent_label", "step_3_confidence_score", "step_4_broad_category", "needs_human_review"],
                "properties": {
                    "conversation_id": {
                        "type": "STRING",
                        "description": "The exact ID provided in the prompt delimiter (e.g. 1234-abcd)"
                    },
                    "step_1_user_goal_analysis": {
                        "type": "STRING",
                        "description": "Briefly analyze the conversation. What is the user's root objective?"
                    },
                    "step_2_dynamic_intent_label": {
                        "type": "STRING",
                        "description": "Generate a concise, snake_case label representing the core action."
                    },
                    "step_3_confidence_score": {
                        "type": "INTEGER",
                        "description": "Rate your confidence in this label from 1 to 100 based on clarity."
                    },
                    "step_4_broad_category": {
                        "type": "STRING",
                        "description": f"Classify the overall conversation into EXACTLY one of these broad categories. You MUST choose one of: {cat_str}.",
                        "enum": enum_choices
                    },
                    "needs_human_review": {
                        "type": "BOOLEAN",
                        "description": "True if the user's intent is highly ambiguous or escalated."
                    },
                },
            }
        }
    }

    payload = {
        "system_instruction": {"parts": [{"text": "You are an elite NLP intent classification engine for SATMI. Read a sanitized chat transcript and determine the user's exact intent without being restricted to predefined categories. CRITICAL RULES: 1. You must invent the most accurate label possible. 2. The dynamic_intent_label MUST be formatted in lowercase snake_case. 3. Use an [action]_[subject] format whenever possible. 4. Be specific but concise (max 4 words). 5. Base your confidence score purely on how explicit the user was. Return a valid JSON array."}]},
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": generation_config,
    }

    body = _post_gemini_json(
        endpoint=endpoint,
        payload=payload,
        timeout_seconds=45.0,
        retry_count=max(5, settings.gemini_strict_retry_count),
        op_name="classify_batch_conversation_intents",
    )

    if not body:
        return {}

    try:
        candidates = body.get("candidates")
        if not candidates or not isinstance(candidates, list):
            return {}
        first_candidate = candidates[0]
        content_obj = first_candidate.get("content")
        if not content_obj or not isinstance(content_obj, dict):
            return {}
        parts = content_obj.get("parts")
        if not parts or not isinstance(parts, list):
            return {}
        text = str(parts[0].get("text", "")).strip()

        parsed_array = json.loads(text)
        if not isinstance(parsed_array, list):
            return {}

        results: dict[str, dict[str, object]] = {}
        token_usage = _extract_usage_metadata(body)

        for parsed in parsed_array:
            conv_id = str(parsed.get("conversation_id", "")).strip()
            if not conv_id:
                continue

            raw_intent_label = str(parsed.get("step_2_dynamic_intent_label", "unknown")).strip()
            intent_label = raw_intent_label or "unknown"

            try:
                conf_val = float(parsed.get("step_3_confidence_score", 0.0))
                confidence = conf_val / 100.0 if conf_val > 1.0 else conf_val
            except Exception:
                confidence = 0.0
            confidence = max(0.0, min(confidence, 1.0))

            rationale_short = str(parsed.get("step_1_user_goal_analysis", "")).strip()
            if len(rationale_short) > 240:
                rationale_short = rationale_short[:240].rstrip()

            needs_review = bool(parsed.get("needs_human_review", False))
            if intent_label == "unknown":
                needs_review = True

            results[conv_id] = {
                "intent_label": intent_label,
                "raw_intent_label": raw_intent_label,
                "confidence": confidence,
                "rationale_short": rationale_short,
                "needs_review": needs_review,
                "model_name": settings.model_name,
                "model_version": settings.model_name,
                "source_version": source_version,
                "classifier_mode": "guardrailed_batch",
                "raw_output": text[:2000],  # Truncate raw output per item to save space
                "raw_error": "",
                "prompt_token_count": token_usage["prompt_token_count"],
                "completion_token_count": token_usage["candidates_token_count"],
                "total_token_count": token_usage["total_token_count"],
                "prompt_char_count": len(batch_payload_text),
                "intent_subcategory": str(parsed.get("step_4_broad_category", "")).strip(),
            }
        return results
    except Exception as e:
        llm_logger.error(f"Failed to parse batch response: {e}")
        return {}


def validate_gemini_key() -> tuple[bool, str]:
    if not settings.gemini_api_key:
        return False, "GEMINI_API_KEY is not configured"

    endpoint = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{settings.model_name}:generateContent"
        f"?key={settings.gemini_api_key}"
    )
    payload = {
        "contents": [{"parts": [{"text": "Reply exactly with: ok"}]}],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 8},
    }

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(endpoint, json=payload)
            response.raise_for_status()
        return True, "Gemini API key is valid"
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text
        return False, f"Gemini API validation failed: {detail}"
    except Exception as exc:
        return False, f"Gemini API validation failed: {exc}"


def generate_general_conversation_response(
    *,
    user_message: str,
    message_history: list[dict[str, str]] | None = None,
    policy_context: list[dict[str, str]] | None = None,
) -> str | None:
    """Generate an open-ended conversational response for non-tool queries."""
    if settings.llm_provider.lower() != "gemini":
        return None

    if not settings.gemini_api_key:
        return None

    system_prompt = GENERAL_CONVERSATION_SYSTEM_PROMPT

    normalized_history = _ensure_system_prompt_first(message_history, system_prompt)

    history_lines: list[str] = []
    for item in normalized_history:
        role = str(item.get("role", "user")).strip() or "user"
        if role == "system":
            continue
        content = str(item.get("content", "")).strip()
        if content:
            history_lines.append(f"{role}: {content}")

    context_lines: list[str] = []
    for item in policy_context or []:
        title = str(item.get("title", "Policy")).strip()
        content = str(item.get("content", "")).strip()
        if content:
            context_lines.append(f"- {title}: {content}")

    user_prompt = (
        "Conversation so far:\n"
        f"{chr(10).join(history_lines) if history_lines else 'user: ' + user_message}\n\n"
        "Policy or knowledge context:\n"
        f"{chr(10).join(context_lines) if context_lines else '- none'}\n\n"
        f"Current user message: {user_message}\n\n"
        "Respond naturally and helpfully in 1-2 sentences. "
        "For greetings or small talk, acknowledge warmly then offer useful help. "
        "For store-related questions, give direct guidance and next steps. "
        "Use markdown only when it improves clarity."
    )

    endpoint = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{settings.model_name}:generateContent"
        f"?key={settings.gemini_api_key}"
    )
    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"parts": [{"text": user_prompt}]}],
        "generationConfig": {"temperature": 0.65, "maxOutputTokens": MAX_OUTPUT_TOKENS},
    }

    body = _post_gemini_json(
        endpoint=endpoint,
        payload=payload,
        timeout_seconds=15.0,
        retry_count=max(0, settings.gemini_retry_count),
        op_name="general_conversation",
    )
    if not body:
        llm_logger.error("generate_general_conversation_response: empty body from Gemini")
        return None

    candidates = body.get("candidates", [])
    if not candidates:
        llm_logger.error("generate_general_conversation_response: missing candidates body=%s", json.dumps(body, ensure_ascii=True)[:2000])
        return None
    parts = candidates[0].get("content", {}).get("parts", [])
    if not parts:
        llm_logger.error("generate_general_conversation_response: missing parts body=%s", json.dumps(body, ensure_ascii=True)[:2000])
        return None
    text = str(parts[0].get("text", "")).strip()
    if not text:
        llm_logger.error("generate_general_conversation_response: empty text body=%s", json.dumps(body, ensure_ascii=True)[:2000])
        return None
    return _sanitize_user_facing_text(text)


def compose_structured_response_with_llm(
    *,
    user_message: str,
    intent: str,
    action: str,
    policy_context: list[dict[str, str]] | None,
    tool_result: dict[str, object] | None,
    recommended_products: list[dict[str, object]] | None,
    next_step_guidance: str,
    retry_count: int = 2,
    strict_mode: bool = False,
    message_history: list[dict[str, str]] | None = None,
) -> str | None:
    """Compose user-facing response from structured state instead of hardcoded templates."""
    if settings.llm_provider.lower() != "gemini":
        return None

    if not settings.gemini_api_key:
        return None

    context_payload = {
        "intent": intent,
        "action": action,
        "policy_context": policy_context or [],
        # DO NOT pass the actual product arrays to the LLM to prevent text duplication
        "products_found": len(recommended_products or []),
        "next_step_guidance": (
            "Guide the user to click 'Select & Buy' on their favorite piece below."
            if next_step_guidance
            else next_step_guidance
        ),
    }

    system_prompt = (
        f"{SATMI_SYSTEM_PROMPT}\n\n"
        "The UI will automatically display the product cards below your text. "
        "NEVER list products, prices, or links. Instead, use the exact RESPONSE TEMPLATE from your instructions to introduce the visual catalog. "
        "CRITICAL RULE: Never output raw query parameters, search JSON, or internal tool-calls to the user. DO NOT output JSON. Always formulate a natural conversational response."
    )

    user_prompt = (
        f"User message: {user_message}\n"
        "Structured context (JSON):\n"
        f"{json.dumps(context_payload, ensure_ascii=True, indent=2)}\n\n"
        "Write one natural SATMI assistant response in Markdown. "
        "Get straight to the expert advice without fluff phrases. Use the requested RESPONSE TEMPLATE."
    )

    if strict_mode:
        user_prompt = (
            f"{user_prompt}\n\n"
            "STRICT REGENERATION MODE:\n"
            "- Preserve grounding only to provided context.\n"
            "- Do not use generic fallback text."
        )

    endpoint = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{settings.model_name}:generateContent"
        f"?key={settings.gemini_api_key}"
    )
    normalized_history = _ensure_system_prompt_first(message_history, SATMI_SYSTEM_PROMPT)
    history_lines: list[str] = []
    for item in normalized_history:
        role = str(item.get("role", "user")).strip().lower() or "user"
        content = str(item.get("content", "")).strip()
        if content:
            history_lines.append(f"{role}: {content}")

    context_message = (
        "Conversation context (prepended persona included):\n"
        f"{chr(10).join(history_lines) if history_lines else 'system: ' + SATMI_SYSTEM_PROMPT}"
    )

    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [
            {"role": "user", "parts": [{"text": context_message}]},
            {"role": "user", "parts": [{"text": user_prompt}]},
        ],
        "generationConfig": {"temperature": 0.55, "maxOutputTokens": MAX_OUTPUT_TOKENS},
    }

    body = _post_gemini_json(
        endpoint=endpoint,
        payload=payload,
        timeout_seconds=18.0,
        retry_count=retry_count,
        op_name="compose_structured_response",
    )
    if not body:
        llm_logger.error("compose_structured_response_with_llm: empty body from Gemini")
        return None

    candidates = body.get("candidates", [])
    if not candidates:
        llm_logger.warning("compose_structured_response: empty candidates")
        return None
    parts = candidates[0].get("content", {}).get("parts", [])
    if not parts:
        llm_logger.warning("compose_structured_response: empty parts")
        return None
    text = str(parts[0].get("text", "")).strip()
    if not text:
        llm_logger.warning("compose_structured_response: empty text")
        return None
    return _sanitize_user_facing_text(text)
