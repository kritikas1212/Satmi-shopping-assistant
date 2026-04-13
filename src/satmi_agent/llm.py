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
    "gemini-2.0-flash",
    "gemini-1.5-flash",
)


_INTERNAL_LABEL_PATTERN = re.compile(
    r"(?im)^\s*(next step|internal note|reasoning|tool output|metadata)\s*:\s*"
)
llm_logger = logging.getLogger("satmi_agent.llm")


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
                    delay = _retry_delay_seconds(response, attempt)
                    llm_logger.warning(
                        "%s rate-limited (model=%s attempt=%s). status=%s body=%s Retrying in %.2fs",
                        op_name,
                        active_model,
                        attempt,
                        response.status_code,
                        (response.text or "")[:1200],
                        delay,
                    )
                    time.sleep(delay)
                    continue

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
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = cleaned.strip()
    if cleaned.startswith("{") and cleaned.endswith("}"):
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


def extract_search_keywords_with_llm(*, user_message: str) -> str | None:
    """Extract a concise 1-3 word product search query from conversational text."""
    if settings.llm_provider.lower() != "gemini":
        return None
    if not settings.gemini_api_key:
        return None

    prompt = (
        "Extract a concise product search query from the user's message.\n"
        "Rules:\n"
        "- Output ONLY the query text, no JSON, no labels, no punctuation wrapper.\n"
        "- Query must be 1 to 3 words.\n"
        "- Keep only product/material/category keywords.\n"
        "- Remove conversational filler and ordering language.\n\n"
        f"User message: {user_message}"
    )

    endpoint = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{settings.model_name}:generateContent"
        f"?key={settings.gemini_api_key}"
    )
    payload = {
        "system_instruction": {"parts": [{"text": SATMI_SYSTEM_PROMPT}]},
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 24},
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

    tokens = re.findall(r"[a-zA-Z0-9']+", raw.lower())
    if not tokens:
        return None
    return " ".join(tokens[:3])


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
        "You are the SATMI Luxury Spiritual Concierge. The UI will automatically display the product cards below your text. "
        "NEVER list products, prices, or links. Instead, write a highly elegant, luxurious 1-2 sentence introduction to the visual catalog. "
        "Emphasize that our pieces are authentic, handcrafted, and Govt. Lab Certified."
    )

    user_prompt = (
        f"User message: {user_message}\n"
        "Structured context (JSON):\n"
        f"{json.dumps(context_payload, ensure_ascii=True, indent=2)}\n\n"
        "Write one natural SATMI assistant response in Markdown. "
        "Keep it warm, elegant, and conversational. "
        "If products were found, provide a brief inviting introduction to the visual catalog below."
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
