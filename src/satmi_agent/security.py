from __future__ import annotations

import re
import threading
import time
from collections import defaultdict
from typing import Any

from fastapi import Header, HTTPException, Request

from satmi_agent.config import settings
from satmi_agent.observability import record_auth_failure, record_rate_limit_hit


EMAIL_PATTERN = re.compile(r"([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
PHONE_PATTERN = re.compile(r"\b\+?\d[\d\s\-()]{8,}\b")
CARD_PATTERN = re.compile(r"\b\d{13,19}\b")


def mask_pii_text(value: str) -> str:
    masked = EMAIL_PATTERN.sub("[masked-email]", value)
    masked = PHONE_PATTERN.sub("[masked-phone]", masked)
    masked = CARD_PATTERN.sub("[masked-card]", masked)
    return masked


def scrub_pii(value: Any) -> Any:
    if isinstance(value, str):
        return mask_pii_text(value)
    if isinstance(value, list):
        return [scrub_pii(item) for item in value]
    if isinstance(value, dict):
        return {key: scrub_pii(item) for key, item in value.items()}
    return value


def require_api_key(request: Request, x_api_key: str | None = Header(default=None)) -> None:
    if not settings.auth_required:
        return
    if not settings.api_key:
        record_auth_failure("missing_server_key", request.url.path)
        raise HTTPException(status_code=500, detail="Auth is enabled but API key is not configured")
    if x_api_key != settings.api_key:
        record_auth_failure("invalid_api_key", request.url.path)
        raise HTTPException(status_code=401, detail="Invalid API key")


def require_support_role(
    request: Request,
    x_role: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> None:
    require_api_key(request, x_api_key)
    if not settings.auth_required:
        return
    allowed_roles = {"support_agent", "admin"}
    if x_role not in allowed_roles:
        record_auth_failure("missing_support_role", request.url.path)
        raise HTTPException(status_code=403, detail="Support role required")


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, tuple[int, float]] = defaultdict(lambda: (0, 0.0))

    def check(self, identity: str) -> None:
        if not settings.rate_limit_enabled:
            return

        now = time.time()
        with self._lock:
            current_count, window_start = self._counters[identity]
            if now - window_start >= settings.rate_limit_window_seconds:
                self._counters[identity] = (1, now)
                return

            if current_count >= settings.rate_limit_requests:
                record_rate_limit_hit("chat")
                raise HTTPException(status_code=429, detail="Rate limit exceeded")

            self._counters[identity] = (current_count + 1, window_start)


rate_limiter = InMemoryRateLimiter()


def enforce_chat_rate_limit(request: Request, user_id: str) -> None:
    client_host = request.client.host if request.client else "unknown"
    identity = f"{user_id}:{client_host}"
    rate_limiter.check(identity)