from __future__ import annotations

import json

import httpx

from satmi_agent.config import settings
from satmi_agent.prompt_loader import get_system_prompt


def refine_response_with_llm(*, user_message: str, base_response: str, policy_context: list[dict[str, str]] | None = None) -> str:
    if not settings.llm_response_refinement_enabled:
        return base_response

    if settings.llm_provider.lower() != "gemini":
        return base_response

    if not settings.gemini_api_key:
        return base_response

    system_prompt = get_system_prompt()

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
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 240},
    }

    try:
        with httpx.Client(timeout=12.0) as client:
            response = client.post(endpoint, json=payload)
            response.raise_for_status()
            body = response.json()
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
            return text
    except Exception:
        return base_response


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
