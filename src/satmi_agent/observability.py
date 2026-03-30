from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest


REQUEST_COUNT = Counter(
    "satmi_http_requests_total",
    "Total number of HTTP requests",
    ["method", "path", "status_code"],
)

REQUEST_DURATION = Histogram(
    "satmi_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
)

INFLIGHT_REQUESTS = Gauge(
    "satmi_http_inflight_requests",
    "Current number of in-flight HTTP requests",
)

CHAT_OUTCOME_COUNT = Counter(
    "satmi_chat_outcomes_total",
    "Total number of chat outcomes",
    ["status", "intent"],
)

HANDOFF_CREATED_COUNT = Counter(
    "satmi_handoffs_created_total",
    "Total number of handoffs created",
    ["reason"],
)

HANDOFF_STATUS_COUNT = Counter(
    "satmi_handoff_status_updates_total",
    "Total handoff status updates",
    ["status"],
)

SHOPIFY_ERROR_COUNT = Counter(
    "satmi_shopify_errors_total",
    "Total Shopify API errors grouped by class",
    ["error_class"],
)

RATE_LIMIT_HIT_COUNT = Counter(
    "satmi_rate_limit_hits_total",
    "Total number of rate limit rejections",
    ["scope"],
)

AUTH_FAILURE_COUNT = Counter(
    "satmi_auth_failures_total",
    "Total authentication and authorization failures",
    ["reason", "path"],
)


def record_request(method: str, path: str, status_code: int, duration_seconds: float) -> None:
    REQUEST_COUNT.labels(method=method, path=path, status_code=str(status_code)).inc()
    REQUEST_DURATION.labels(method=method, path=path).observe(duration_seconds)


def record_chat_outcome(status: str, intent: str) -> None:
    CHAT_OUTCOME_COUNT.labels(status=status, intent=intent).inc()


def record_handoff_created(reason: str) -> None:
    HANDOFF_CREATED_COUNT.labels(reason=reason).inc()


def record_handoff_status(status: str) -> None:
    HANDOFF_STATUS_COUNT.labels(status=status).inc()


def record_shopify_error(error_class: str) -> None:
    SHOPIFY_ERROR_COUNT.labels(error_class=error_class).inc()


def record_rate_limit_hit(scope: str) -> None:
    RATE_LIMIT_HIT_COUNT.labels(scope=scope).inc()


def record_auth_failure(reason: str, path: str) -> None:
    AUTH_FAILURE_COUNT.labels(reason=reason, path=path).inc()


def metrics_payload() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST