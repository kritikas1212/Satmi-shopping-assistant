from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from satmi_agent.config import settings
from satmi_agent.security import rate_limiter


@pytest.fixture(autouse=True)
def reset_runtime_settings():
    original = {
        "auth_required": settings.auth_required,
        "api_key": settings.api_key,
        "gemini_api_key": settings.gemini_api_key,
        "rate_limit_enabled": settings.rate_limit_enabled,
        "rate_limit_requests": settings.rate_limit_requests,
        "rate_limit_window_seconds": settings.rate_limit_window_seconds,
        "tracing_enabled": settings.tracing_enabled,
        "hitl_interrupt_enabled": settings.hitl_interrupt_enabled,
        "async_cancel_enabled": settings.async_cancel_enabled,
        "catalog_cache_enabled": settings.catalog_cache_enabled,
        "gemini_intent_classifier_api_key": settings.gemini_intent_classifier_api_key,
        "conversation_intent_allow_heuristic_fallback": settings.conversation_intent_allow_heuristic_fallback,
        "conversation_intent_raw_mode": settings.conversation_intent_raw_mode,
        "conversation_intent_raw_disable_redaction": settings.conversation_intent_raw_disable_redaction,
    }

    settings.auth_required = False
    settings.api_key = None
    settings.gemini_api_key = None
    settings.rate_limit_enabled = False
    settings.rate_limit_requests = 30
    settings.rate_limit_window_seconds = 60
    settings.tracing_enabled = False
    settings.hitl_interrupt_enabled = False
    settings.async_cancel_enabled = False
    settings.catalog_cache_enabled = False
    settings.gemini_intent_classifier_api_key = None
    settings.conversation_intent_allow_heuristic_fallback = True
    settings.conversation_intent_raw_mode = False
    settings.conversation_intent_raw_disable_redaction = False
    rate_limiter._counters.clear()

    yield

    settings.auth_required = original["auth_required"]
    settings.api_key = original["api_key"]
    settings.gemini_api_key = original["gemini_api_key"]
    settings.rate_limit_enabled = original["rate_limit_enabled"]
    settings.rate_limit_requests = original["rate_limit_requests"]
    settings.rate_limit_window_seconds = original["rate_limit_window_seconds"]
    settings.tracing_enabled = original["tracing_enabled"]
    settings.hitl_interrupt_enabled = original["hitl_interrupt_enabled"]
    settings.async_cancel_enabled = original["async_cancel_enabled"]
    settings.catalog_cache_enabled = original["catalog_cache_enabled"]
    settings.gemini_intent_classifier_api_key = original["gemini_intent_classifier_api_key"]
    settings.conversation_intent_allow_heuristic_fallback = original["conversation_intent_allow_heuristic_fallback"]
    settings.conversation_intent_raw_mode = original["conversation_intent_raw_mode"]
    settings.conversation_intent_raw_disable_redaction = original["conversation_intent_raw_disable_redaction"]
    rate_limiter._counters.clear()
