from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import hashlib
import logging
from pathlib import Path
import re
import threading
import time
from typing import Any
from uuid import uuid4

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from sqlalchemy import text

from satmi_agent.graph import compiled_graph
from satmi_agent.config import settings
from satmi_agent.observability import (
    INFLIGHT_REQUESTS,
    metrics_payload,
    record_chat_outcome,
    record_handoff_created,
    record_handoff_status,
    record_request,
)
from satmi_agent.persistence import engine, persistence_service
from satmi_agent.queueing import cancellation_queue_service, conversation_intent_queue_service
from satmi_agent.schemas import (
    ChatTranscriptResponse,
    AdminChatHistoryEvent,
    AsyncTaskResponse,
    ChatRequest,
    ChatResponse,
    ConversationEventResponse,
    ConversationIntentOverrideRequest,
    DashboardAnalyticsSummary,
    DashboardCategorySlice,
    DashboardChatMessage,
    DashboardChatSession,
    DashboardDailyActivity,
    DashboardExportRow,
    DashboardIntentSlice,
    DashboardIntentSubcategorySlice,
    DashboardSnapshotResponse,
    DashboardTopTrend,
    HandoffStatusUpdateRequest,
    IntentTrendPoint,
    HandoffTicketResponse,
    ResumeHandoffRequest,
    SearchTermCount,
    SearchTermTrendPoint,
    WeeklyInsightCard,
    AdminCommentRequest,
)
from satmi_agent.security import (
    enforce_chat_rate_limit,
    ensure_firebase_ready_or_raise,
    firebase_auth_health,
    require_api_key,
    require_support_role,
    preserve_support_email_text,
    scrub_pii,
    verify_firebase_token,
)
from satmi_agent.tools import tooling_service
from satmi_agent.tracing import get_tracer, setup_tracing

try:
    from langgraph.types import Command
except Exception:  # pragma: no cover
    Command = None


logger = logging.getLogger("satmi_agent.analytics")


async def _warm_catalog_cache() -> None:
    if not settings.catalog_cache_enabled:
        return

    try:
        fetch_products = (
            tooling_service._fetch_all_shopify_products
            if tooling_service.shopify_enabled
            else tooling_service._fetch_public_storefront_products
        )
        products = await asyncio.to_thread(fetch_products)
        if not products:
            return
        await asyncio.to_thread(persistence_service.upsert_product_catalog, products)
    except Exception:
        return


def _run_intent_worker_loop(stop_event: threading.Event):
    import time
    import sys
    import os
    # Ensure scripts dir is importable
    scripts_dir = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, os.path.abspath(scripts_dir))
    from process_conversation_intent_queue import TokenBucket, process_batch

    bucket = TokenBucket(capacity=15, fill_rate_per_sec=15.0 / 60.0)
    while not stop_event.is_set():
        if bucket.tokens < 2.0:
            stop_event.wait(timeout=5.0)
            continue
        try:
            processed_count = process_batch(max_batch_size=5)
            if processed_count > 0:
                bucket.consume(1)
            else:
                stop_event.wait(timeout=1.0)
        except Exception as e:
            stop_event.wait(timeout=5.0)


@asynccontextmanager
async def lifespan(_: FastAPI):
    persistence_service.init_db()
    await _warm_catalog_cache()
    ensure_firebase_ready_or_raise()
    setup_tracing()

    # Run the background intent classifier worker inline
    stop_event = threading.Event()
    worker_task = asyncio.create_task(
        asyncio.to_thread(_run_intent_worker_loop, stop_event)
    )

    yield

    # Teardown
    stop_event.set()
    worker_task.cancel()



app = FastAPI(title="SATMI Agent API", version="0.1.0", lifespan=lifespan)


def _cors_allow_origins() -> list[str]:
    origins = {
        "https://satmi.in",
        "https://www.satmi.in",
        "https://accounts.satmi.in",
        "https://satmi.myshopify.com",
        "https://satmi-shopping-assistant.vercel.app",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    }
    domain = (settings.shopify_store_domain or "").strip().strip('"').strip("'")
    if domain:
        if domain.startswith("http://") or domain.startswith("https://"):
            domain = domain.split("://", 1)[1]
        domain = domain.strip("/")
        if domain:
            origins.add(f"https://{domain}")
            origins.add(f"http://{domain}")
    return sorted(origins)


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allow_origins(),
    allow_origin_regex=r"https?://(([a-zA-Z0-9-]+\.)*(myshopify\.com|shopify\.com|vercel\.app)|localhost|127\.0\.0\.1|192\.168\.\d+\.\d+)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    if not settings.observability_enabled:
        return await call_next(request)

    tracer = get_tracer("satmi_agent.http")
    INFLIGHT_REQUESTS.inc()
    start = time.perf_counter()
    response = None
    try:
        with tracer.start_as_current_span("http.request") as span:
            span.set_attribute("http.method", request.method)
            span.set_attribute("http.route", request.url.path)
            response = await call_next(request)
            span.set_attribute("http.status_code", response.status_code)
        return response
    finally:
        elapsed = time.perf_counter() - start
        status_code = response.status_code if response is not None else 500
        record_request(request.method, request.url.path, status_code, elapsed)
        INFLIGHT_REQUESTS.dec()


def _to_iso(value) -> str | None:
    return value.isoformat() if value else None


def _normalize_chat_intent(value: Any) -> str:
    allowed = {"shopping", "order_tracking", "policy_brand_faq", "general", "authentication", "unknown"}
    normalized = str(value or "unknown").strip().lower()
    return normalized if normalized in allowed else "general"


def _normalize_user_visible_text(text: str, *, preserve_support_email: bool = False) -> str:
    masked = scrub_pii(text)
    if preserve_support_email:
        return preserve_support_email_text(masked)
    return masked


def _mask_secret(value: str | None, *, visible_prefix: int = 4) -> str | None:
    if not value:
        return None
    prefix = value[:visible_prefix]
    return f"{prefix}..."


def _mask_database_url(value: str) -> str:
    if not value:
        return "unset"
    # Keep dialect and target host:port while masking credentials.
    if "://" not in value:
        return "configured"

    scheme, remainder = value.split("://", 1)
    host_part = remainder
    if "@" in remainder:
        host_part = remainder.split("@", 1)[1]
    host_port = host_part.split("/", 1)[0]
    return f"{scheme}://***@{host_port}"


def _mask_path(value: str | None) -> str | None:
    if not value:
        return None
    name = Path(value).name
    return f".../{name}"


_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "for",
    "from",
    "how",
    "i",
    "in",
    "is",
    "me",
    "my",
    "of",
    "on",
    "or",
    "please",
    "show",
    "the",
    "to",
    "want",
    "with",
}


def _normalize_search_term(text: str) -> str:
    lowered = re.sub(r"[^a-z0-9\s]", " ", (text or "").lower())
    tokens = [token for token in lowered.split() if token and token not in _STOPWORDS]
    phrase = " ".join(tokens[:8]).strip()
    return phrase or "general_query"


def _hash_user_id(user_id: str) -> str:
    return hashlib.sha256((user_id or "unknown").encode("utf-8")).hexdigest()[:32]


def _latency_bucket(seconds: float) -> str:
    ms = max(seconds * 1000.0, 0.0)
    if ms < 300:
        return "lt_300ms"
    if ms < 1000:
        return "300ms_1s"
    if ms < 3000:
        return "1s_3s"
    return "gte_3s"


def _record_chat_analytics_safe(
    *,
    conversation_id: str,
    user_id: str,
    user_message_masked: str,
    intent: str,
    recommendation_count: int,
    latency_seconds: float,
) -> None:
    try:
        persistence_service.create_chat_query_event(
            conversation_id=conversation_id,
            user_id_hash=_hash_user_id(user_id),
            masked_query=user_message_masked,
            normalized_term=_normalize_search_term(user_message_masked),
            intent=_normalize_chat_intent(intent),
            had_recommendations=recommendation_count > 0,
            recommendation_count=recommendation_count,
            latency_bucket=_latency_bucket(latency_seconds),
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("Analytics capture failed: %s", exc)


def _ensure_admin_analytics_enabled() -> None:
    if not settings.analytics_admin_panel_enabled:
        raise HTTPException(status_code=404, detail="Analytics admin endpoints disabled")


def _queue_conversation_intent_classification_safe(
    *,
    conversation_id: str,
    user_id: str,
    force: bool,
    transcript_checksum: str | None = None,
) -> None:
    if not settings.conversation_intent_classifier_enabled:
        return
    try:
        conversation_intent_queue_service.enqueue_classification(
            conversation_id=conversation_id,
            user_id=user_id,
            force=force,
            transcript_checksum=transcript_checksum,
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("Unable to enqueue conversation intent classification: %s", exc)


def _enqueue_inactive_conversation_intents(*, limit: int, inactive_minutes: int) -> int:
    candidates = persistence_service.list_inactive_conversations_needing_intent_classification(
        inactive_minutes=inactive_minutes,
        limit=limit,
    )
    queued = 0
    for item in candidates:
        _queue_conversation_intent_classification_safe(
            conversation_id=str(item.get("conversation_id") or ""),
            user_id=str(item.get("user_id") or "unknown"),
            force=False,
            transcript_checksum=str(item.get("transcript_checksum") or ""),
        )
        queued += 1
    return queued


def _load_recent_message_history(conversation_id: str, limit: int = 12) -> list[dict[str, str]]:
    """Load recent chat turns so each graph invocation has conversational memory."""
    try:
        events = persistence_service.list_conversation_events(conversation_id, limit=limit)
    except Exception:
        return []

    history: list[dict[str, str]] = []
    for event in events:
        role = str(event.role or "").strip().lower()
        if role not in {"user", "assistant", "system"}:
            continue
        content = str(event.message or "").strip()
        if not content:
            continue
        history.append({"role": role, "content": content})
    return history


def _invoke_chat_graph(
    *,
    request: ChatRequest,
    firebase_user: dict[str, Any] | None,
    order_context: list[dict[str, Any]],
    masked_user_message: str,
    message_history: list[dict[str, str]],
) -> dict[str, Any]:
    try:
        return compiled_graph.invoke(
            {
                "user_id": request.user_id,
                "conversation_id": request.conversation_id,
                "message": masked_user_message,
                "status": "active",
                "user_authenticated": bool(firebase_user),
                "authenticated_user": firebase_user,
                "order_context": order_context,
                "errors": [],
                "internal_logs": [],
                "message_history": message_history,
            },
            config={"configurable": {"thread_id": request.conversation_id}, "recursion_limit": 50},
        )
    except Exception as exc:
        fallback_handoff_id = f"HND-{uuid4().hex[:8].upper()}"
        return {
            "status": "awaiting_human",
            "intent": "unknown",
            "confidence": 0.0,
            "handoff_id": fallback_handoff_id,
            "handoff_reason": "Graph execution failed",
            "action": "none",
            "tool_result": {},
            "errors": [f"Graph execution failed: {exc}"],
            "internal_logs": [{"event": "graph_invoke_failed"}],
            "response": (
                "I am handing this over to a SATMI support specialist now. "
                f"Your handoff reference is {fallback_handoff_id}. "
                "Estimated response time is about 15 minutes."
            ),
            "message_history": message_history,
        }


def _coerce_recommended_products(final_state: dict[str, Any]) -> list[dict[str, Any]]:
    intent = str(final_state.get("intent", "")).strip().lower()
    if intent not in {"shopping", "order_tracking"}:
        return []

    products = final_state.get("recommended_products")
    if isinstance(products, list) and products:
        return products

    fallback_results = (final_state.get("tool_result") or {}).get("results")
    if not isinstance(fallback_results, list):
        return []

    normalized: list[dict[str, Any]] = []
    for item in fallback_results[:8]:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "product_id": str(item.get("product_id") or item.get("id") or "") or None,
                "variant_id": str(item.get("variant_id") or "") or None,
                "handle": str(item.get("handle") or "") or None,
                "url": item.get("url") or item.get("product_url"),
                "title": str(item.get("title") or item.get("name") or "SATMI Product"),
                "price": str(item.get("price") or ""),
                "image_url": item.get("image_url") or item.get("image"),
                "product_url": item.get("product_url") or item.get("url"),
            }
        )
    return normalized


def _safe_recommended_products(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return frontend-safe product payload without applying generic PII masking to URLs.

    URL/image fields can contain long numeric segments that are incorrectly redacted by
    phone-number masking, which breaks thumbnails and product links.
    """
    safe_products: list[dict[str, Any]] = []
    for item in products[:8]:
        if not isinstance(item, dict):
            continue
        safe_products.append(
            {
                "product_id": item.get("product_id"),
                "variant_id": item.get("variant_id"),
                "handle": item.get("handle"),
                "url": item.get("url"),
                "title": item.get("title"),
                "price": item.get("price"),
                "image_url": item.get("image_url"),
                "product_url": item.get("product_url"),
            }
        )
    return safe_products


def _is_product_related_query(message: str) -> bool:
    lowered = (message or "").lower()
    product_hints = {
        "recommend",
        "product",
        "products",
        "buy",
        "purchase",
        "shop",
        "show",
        "find",
        "suggest",
        "rudraksha",
        "karungali",
        "crystal",
        "bracelet",
        "mala",
        "ring",
        "necklace",
        "pendant",
    }
    return any(token in lowered for token in product_hints)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/system/config")
def system_config(_: None = Depends(require_support_role)) -> dict[str, object]:
    return {
        "app_env": settings.app_env,
        "api_port": settings.api_port,
        "database_url": _mask_database_url(settings.database_url),
        "redis_enabled": bool(settings.redis_url),
        "redis_url": _mask_database_url(settings.redis_url) if settings.redis_url else None,
        "llm_provider": settings.llm_provider,
        "model_name": settings.model_name,
        "gemini_api_key": _mask_secret(settings.gemini_api_key),
        "gemini_intent_classifier_api_key": _mask_secret(settings.gemini_intent_classifier_api_key),
        "conversation_intent_raw_mode": settings.conversation_intent_raw_mode,
        "conversation_intent_allow_heuristic_fallback": settings.conversation_intent_allow_heuristic_fallback,
        "shopify_store_domain": settings.shopify_store_domain,
        "shopify_admin_api_token": _mask_secret(settings.shopify_admin_api_token),
        "display_currency_code": settings.display_currency_code,
        "firebase_auth_enabled": settings.firebase_auth_enabled,
        "firebase_project_id": settings.firebase_project_id,
        "firebase_credentials_path": _mask_path(settings.firebase_credentials_path),
        "firebase_require_for_sensitive_actions": settings.firebase_require_for_sensitive_actions,
    }


@app.get("/system/healthz/deps")
def system_healthz_deps(_: None = Depends(require_support_role)) -> dict[str, object]:
    postgres = {"configured": bool(settings.database_url), "reachable": False}
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            postgres["reachable"] = True
    except Exception as exc:
        postgres["error"] = str(exc)

    redis = cancellation_queue_service.dependency_health()
    firebase = firebase_auth_health()
    shopify = tooling_service.shopify_health()

    all_healthy = bool(postgres.get("reachable")) and bool(redis.get("reachable")) and bool(shopify.get("reachable"))

    return {
        "overall": "healthy" if all_healthy else "degraded",
        "dependencies": {
            "firebase": firebase,
            "postgres": postgres,
            "redis": redis,
            "shopify": shopify,
        },
    }


@app.get(settings.metrics_endpoint_path)
def metrics(_: None = Depends(require_support_role)) -> Response:
    if not settings.metrics_endpoint_enabled:
        raise HTTPException(status_code=404, detail="Metrics endpoint disabled")

    payload, content_type = metrics_payload()
    return Response(content=payload, media_type=content_type)


@app.post("/chat")
def chat(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    http_request: Request,
    _: None = Depends(require_api_key),
) -> ChatResponse | dict[str, Any]:
    chat_started_at = time.perf_counter()
    enforce_chat_rate_limit(http_request, request.user_id)
    masked_user_message = scrub_pii(request.message or "")
    order_context: list[dict[str, Any]] = []

    persistence_service.create_conversation_event(
        conversation_id=request.conversation_id,
        user_id=request.user_id,
        role="user",
        message=masked_user_message,
        status="active",
        event_metadata={"event": "user_message"},
    )

    message_history = _load_recent_message_history(request.conversation_id, limit=14)
    if not message_history or message_history[-1].get("content") != masked_user_message:
        message_history = [
            *message_history,
            {"role": "user", "content": masked_user_message},
        ]

    final_state = _invoke_chat_graph(
        request=request,
        firebase_user=None,
        order_context=order_context,
        masked_user_message=masked_user_message,
        message_history=message_history,
    )

    message_history = final_state.get("message_history", message_history)
    if final_state.get("response"):
        preserve_support_email = final_state.get("action") in {"portal_redirect", "support_contact"}
        message_history = [
            *message_history,
            {
                "role": "assistant",
                "content": _normalize_user_visible_text(
                    final_state.get("response", ""),
                    preserve_support_email=preserve_support_email,
                ),
            },
        ]

    persistence_service.upsert_handoff_from_state(final_state)
    
    recommended_products = _safe_recommended_products(_coerce_recommended_products(final_state))
    
    event_meta = {
        "handoff_reason": final_state.get("handoff_reason"),
        "errors": scrub_pii(final_state.get("errors", [])),
        "internal_logs": scrub_pii(final_state.get("internal_logs", [])),
    }
    
    if final_state.get("action") in ("search_products", "knowledge_and_search") and recommended_products:
        event_meta["tool_action"] = "search_products"
        event_meta["tool_result"] = {"results": recommended_products}

    persistence_service.create_conversation_event(
        conversation_id=request.conversation_id,
        user_id=request.user_id,
        role="assistant",
        message=scrub_pii(final_state.get("response", "I am here to help.")),
        status=final_state.get("status", "active"),
        intent=final_state.get("intent"),
        confidence=final_state.get("confidence"),
        action=final_state.get("action"),
        handoff_id=final_state.get("handoff_id"),
        event_metadata=event_meta,
    )

    status_value = final_state.get("status", "active")
    intent_value = _normalize_chat_intent(final_state.get("intent", "unknown"))
    recommendation_source = (final_state.get("tool_result") or {}).get("source")

    if settings.analytics_enabled:
        background_tasks.add_task(
            _record_chat_analytics_safe,
            conversation_id=request.conversation_id,
            user_id=request.user_id,
            user_message_masked=masked_user_message,
            intent=intent_value,
            recommendation_count=len(recommended_products),
            latency_seconds=time.perf_counter() - chat_started_at,
        )

    # Queue conversation-level classification asynchronously after every assistant turn.
    # This keeps chat latency unaffected while making dashboard intent labels update continuously.
    background_tasks.add_task(
        _queue_conversation_intent_classification_safe,
        conversation_id=request.conversation_id,
        user_id=request.user_id,
        force=False,
    )

    record_chat_outcome(status=status_value, intent=intent_value)
    if final_state.get("handoff_id"):
        record_handoff_created(final_state.get("handoff_reason", "unspecified"))

    return ChatResponse(
        conversation_id=request.conversation_id,
        status=final_state.get("status", "active"),
        response_text=_normalize_user_visible_text(
            final_state.get("response_text") or final_state.get("response", "I am here to help."),
            preserve_support_email=final_state.get("action") in {"portal_redirect", "support_contact"},
        ),
        recommended_products=recommended_products,
        auth_required=False,
        intent=intent_value,
        confidence=final_state.get("confidence", 0.0),
        handoff_id=final_state.get("handoff_id"),
        metadata={
            "action": final_state.get("action") or (request.action or "chat"),
            "handoff_reason": final_state.get("handoff_reason"),
            "async_task_id": final_state.get("async_task_id"),
            "async_task_status": final_state.get("async_task_status"),
            "user_authenticated": False,
            "auth_user_uid": None,
            "order_context_count": len(order_context),
            "catalog_source": recommendation_source,
            "recommendation_count": len(recommended_products),
            "errors": scrub_pii(final_state.get("errors", [])),
            "internal_logs": scrub_pii(final_state.get("internal_logs", [])),
            "message_history": scrub_pii(message_history),
        },
    )


@app.get("/admin/analytics/top-search-terms", response_model=list[SearchTermCount])
def admin_top_search_terms(
    days: int = Query(default=7, ge=1, le=90),
    limit: int = Query(default=20, ge=1, le=100),
    _: None = Depends(require_support_role),
) -> list[SearchTermCount]:
    _ensure_admin_analytics_enabled()
    rows = persistence_service.list_top_search_terms(days=days, limit=limit)
    return [SearchTermCount(**row) for row in rows]


@app.get("/admin/analytics/search-term-trends", response_model=list[SearchTermTrendPoint])
def admin_search_term_trends(
    days: int = Query(default=30, ge=1, le=180),
    limit_terms: int = Query(default=8, ge=1, le=30),
    _: None = Depends(require_support_role),
) -> list[SearchTermTrendPoint]:
    _ensure_admin_analytics_enabled()
    rows = persistence_service.list_search_term_trends(days=days, limit_terms=limit_terms)
    return [SearchTermTrendPoint(**row) for row in rows]


@app.get("/admin/analytics/intent-trends", response_model=list[IntentTrendPoint])
def admin_intent_trends(
    days: int = Query(default=30, ge=1, le=180),
    _: None = Depends(require_support_role),
) -> list[IntentTrendPoint]:
    _ensure_admin_analytics_enabled()
    rows = persistence_service.list_intent_daily_trends(days=days)
    return [IntentTrendPoint(**row) for row in rows]


@app.get("/admin/analytics/weekly-insights", response_model=list[WeeklyInsightCard])
def admin_weekly_insights(_: None = Depends(require_support_role)) -> list[WeeklyInsightCard]:
    _ensure_admin_analytics_enabled()
    rows = persistence_service.get_weekly_insights()
    return [WeeklyInsightCard(**row) for row in rows]


@app.get("/admin/analytics/chat-history", response_model=list[AdminChatHistoryEvent])
def admin_chat_history(
    days: int = Query(default=30, ge=1, le=180),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0, le=5000),
    user_id_hash: str | None = Query(default=None, min_length=8, max_length=64),
    _: None = Depends(require_support_role),
) -> list[AdminChatHistoryEvent]:
    _ensure_admin_analytics_enabled()
    rows = persistence_service.list_admin_chat_history(
        days=days,
        limit=limit,
        offset=offset,
        user_id_hash=user_id_hash,
    )
    return [
        AdminChatHistoryEvent(
            conversation_id=row["conversation_id"],
            user_id_hash=row["user_id_hash"],
            role=row["role"],
            message=scrub_pii(row["message"]),
            status=row["status"],
            intent=row.get("intent"),
            created_at=row["created_at"],
            event_metadata=row.get("event_metadata") if isinstance(row.get("event_metadata"), dict) else None,
        )
        for row in rows
    ]


@app.get("/admin/dashboard/snapshot", response_model=DashboardSnapshotResponse)
def admin_dashboard_snapshot(
    limit: int = Query(default=10, ge=1, le=150),
    offset: int = Query(default=0, ge=0),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    _: None = Depends(require_support_role),
) -> DashboardSnapshotResponse:
    from datetime import datetime
    _ensure_admin_analytics_enabled()
    
    dt_start = None
    dt_end = None
    if start_date:
        try:
            dt_start = datetime.fromisoformat(start_date)
        except ValueError:
            pass
    if end_date:
        try:
            dt_end = datetime.fromisoformat(end_date)
        except ValueError:
            pass

    snapshot = persistence_service.list_dashboard_chat_sessions(
        limit=limit, 
        offset=offset,
        start_date=dt_start,
        end_date=dt_end
    )

    chats = [
        DashboardChatSession(
            conversation_id=row["conversation_id"],
            user_id_hash=row["user_id_hash"],
            is_frustrated=bool(row["is_frustrated"]),
            status=row["status"],
            dominant_category=row["dominant_category"],
            dominant_intent=row.get("dominant_intent", "Unclassified"),
            intent_confidence=row.get("intent_confidence"),
            intent_model_name=row.get("intent_model_name"),
            intent_model_version=row.get("intent_model_version"),
            intent_source_version=row.get("intent_source_version"),
            intent_needs_review=row.get("intent_needs_review"),
            intent_is_overridden=bool(row.get("intent_is_overridden", False)),
            intent_override_reason=row.get("intent_override_reason"),
            intent_raw_label=row.get("intent_raw_label"),
            intent_classifier_mode=row.get("intent_classifier_mode"),
            intent_classifier_error=row.get("intent_classifier_error"),
            intent_classifier_total_tokens=row.get("intent_classifier_total_tokens"),
            started_at=row["started_at"],
            last_activity_at=row["last_activity_at"],
        )
        for row in snapshot.get("sessions", [])
    ]

    analytics = DashboardAnalyticsSummary(
        resolution_rate=float(snapshot.get("resolution_rate", 0.0)),
        recommendation_conversions=int(snapshot.get("recommendation_conversions", 0)),
        category_divide=[DashboardCategorySlice(**item) for item in snapshot.get("category_divide", [])],
        intent_breakdown=[DashboardIntentSlice(**item) for item in snapshot.get("intent_breakdown", [])],
        intent_subcategory_breakdown=[DashboardIntentSubcategorySlice(**item) for item in snapshot.get("intent_subcategory_breakdown", [])],
        top_trending_terms=[DashboardTopTrend(**item) for item in snapshot.get("top_trending_terms", [])],
        daily_activity=[DashboardDailyActivity(**item) for item in snapshot.get("daily_activity", [])],
    )

    return DashboardSnapshotResponse(
        total_sessions=snapshot.get("total_sessions", 0),
        chats=chats,
        analytics=analytics
    )


@app.post("/admin/dashboard/chat/{conversation_id}/intent-override")
def admin_set_intent_override(
    conversation_id: str,
    request: ConversationIntentOverrideRequest,
    x_support_email: str | None = Header(default=None, alias="X-Support-Email"),
    _: None = Depends(require_support_role),
) -> dict[str, Any]:
    _ensure_admin_analytics_enabled()
    persistence_service.upsert_conversation_intent_override(
        conversation_id=conversation_id,
        intent_label=request.intent_label,
        override_reason=request.override_reason,
        overridden_by=request.overridden_by or x_support_email or "admin",
    )
    label = persistence_service.get_conversation_intent_label(conversation_id)
    return {
        "conversation_id": conversation_id,
        "saved": True,
        "label": label,
    }


@app.delete("/admin/dashboard/chat/{conversation_id}/intent-override")
def admin_clear_intent_override(
    conversation_id: str,
    _: None = Depends(require_support_role),
) -> dict[str, Any]:
    _ensure_admin_analytics_enabled()
    persistence_service.clear_conversation_intent_override(conversation_id)
    label = persistence_service.get_conversation_intent_label(conversation_id)
    return {
        "conversation_id": conversation_id,
        "cleared": True,
        "label": label,
    }


@app.post("/admin/dashboard/intent-classifier/backfill")
def admin_enqueue_intent_backfill(
    limit: int = Query(default=settings.conversation_intent_backfill_batch_size, ge=1, le=2000),
    inactive_minutes: int = Query(default=settings.conversation_intent_inactive_minutes, ge=1, le=1440),
    _: None = Depends(require_support_role),
) -> dict[str, Any]:
    _ensure_admin_analytics_enabled()
    queued = _enqueue_inactive_conversation_intents(limit=limit, inactive_minutes=inactive_minutes)
    return {
        "queued": queued,
        "limit": limit,
        "inactive_minutes": inactive_minutes,
    }


@app.post("/admin/dashboard/chat/{conversation_id}/intent-classifier/backfill")
def admin_run_conversation_intent_classification(
    conversation_id: str,
    _: None = Depends(require_support_role),
) -> dict[str, Any]:
    _ensure_admin_analytics_enabled()
    source_limit = max(int(getattr(settings, "conversation_intent_source_event_limit", 120) or 120), 1)

    events = persistence_service.list_conversation_events_for_classification(
        conversation_id,
        limit=source_limit,
    )
    if not events:
        raise HTTPException(status_code=404, detail="Conversation not found")

    from satmi_agent.conversation_intent_classifier import classify_conversation_intent
    result = classify_conversation_intent(conversation_id=conversation_id, force=True)

    return {
        "status": "completed",
        "conversation_id": conversation_id,
        "result": result,
    }


@app.post("/admin/dashboard/chat/{conversation_id}/comment")
def admin_add_chat_comment(
    conversation_id: str,
    request: AdminCommentRequest,
    x_support_email: str | None = Header(default=None, alias="X-Support-Email"),
    _: None = Depends(require_support_role),
) -> dict[str, Any]:
    _ensure_admin_analytics_enabled()
    
    # We use user_id="admin" and role="system" with special metadata
    event_meta = {"is_admin_comment": True}
    if x_support_email:
        event_meta["admin_email"] = x_support_email

    persistence_service.create_conversation_event(
        conversation_id=conversation_id,
        user_id="admin",
        role="system",
        message=request.message,
        status="active",
        intent=None,
        confidence=None,
        action="admin_comment",
        handoff_id=None,
        event_metadata=event_meta,
    )
    
    return {
        "status": "completed",
        "conversation_id": conversation_id,
    }


@app.delete("/admin/dashboard/chat/{conversation_id}")
def admin_delete_chat_conversation(
    conversation_id: str,
    _: None = Depends(require_support_role),
) -> dict[str, Any]:
    _ensure_admin_analytics_enabled()
    deleted = persistence_service.delete_conversation(conversation_id)
    if sum(deleted.values()) == 0:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return {
        "conversation_id": conversation_id,
        "deleted": deleted,
    }


@app.get("/admin/dashboard/export", response_model=list[DashboardExportRow])
def admin_dashboard_export(
    limit: int = Query(default=10, ge=1, le=150),
    offset: int = Query(default=0, ge=0),
    _: None = Depends(require_support_role),
) -> list[DashboardExportRow]:
    _ensure_admin_analytics_enabled()
    rows = persistence_service.list_dashboard_export_rows(limit=limit, offset=offset)
    return [DashboardExportRow(**row) for row in rows]


@app.get("/tasks/{task_id}", response_model=AsyncTaskResponse)
def get_async_task(task_id: str, _: None = Depends(require_support_role)) -> AsyncTaskResponse:
    task = persistence_service.get_async_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Async task not found")

    return AsyncTaskResponse(
        task_id=task.task_id,
        task_type=task.task_type,
        status=task.status,
        conversation_id=task.conversation_id,
        user_id=task.user_id,
        payload=scrub_pii(task.payload),
        result=scrub_pii(task.result),
        error=scrub_pii(task.error),
        created_at=task.created_at.isoformat(),
        updated_at=task.updated_at.isoformat(),
        completed_at=_to_iso(task.completed_at),
    )


@app.get("/conversations/{conversation_id}/events", response_model=list[ConversationEventResponse])
def get_conversation_events(
    conversation_id: str,
    limit: int = 50,
    _: None = Depends(require_support_role),
) -> list[ConversationEventResponse]:
    records = persistence_service.list_conversation_events(conversation_id, limit=limit)
    return [
        ConversationEventResponse(
            role=record.role,
            message=scrub_pii(record.message),
            status=record.status,
            intent=record.intent,
            confidence=record.confidence,
            action=record.action,
            handoff_id=record.handoff_id,
            metadata=scrub_pii(record.event_metadata),
            created_at=record.created_at.isoformat(),
        )
        for record in records
    ]


@app.get("/handoffs/{handoff_id}", response_model=HandoffTicketResponse)
def get_handoff(handoff_id: str, _: None = Depends(require_support_role)) -> HandoffTicketResponse:
    record = persistence_service.get_handoff(handoff_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Handoff ticket not found")

    return HandoffTicketResponse(
        handoff_id=record.handoff_id,
        conversation_id=record.conversation_id,
        user_id=record.user_id,
        status=record.status,
        reason=record.reason,
        summary=scrub_pii(record.summary),
        intent=record.intent,
        attempted_action=record.attempted_action,
        tool_result=scrub_pii(record.tool_result),
        errors=scrub_pii(record.errors),
        queue=record.queue,
        eta_minutes=record.eta_minutes,
        resolution_note=scrub_pii(record.resolution_note),
        created_at=record.created_at.isoformat(),
        updated_at=record.updated_at.isoformat(),
        resolved_at=_to_iso(record.resolved_at),
    )


@app.post("/handoffs/{handoff_id}/status", response_model=HandoffTicketResponse)
def update_handoff_status(
    handoff_id: str,
    request: HandoffStatusUpdateRequest,
    _: None = Depends(require_support_role),
) -> HandoffTicketResponse:
    record = persistence_service.update_handoff_status(handoff_id, request.status, request.note)
    if record is None:
        raise HTTPException(status_code=404, detail="Handoff ticket not found")

    record_handoff_status(request.status)

    return HandoffTicketResponse(
        handoff_id=record.handoff_id,
        conversation_id=record.conversation_id,
        user_id=record.user_id,
        status=record.status,
        reason=record.reason,
        summary=scrub_pii(record.summary),
        intent=record.intent,
        attempted_action=record.attempted_action,
        tool_result=scrub_pii(record.tool_result),
        errors=scrub_pii(record.errors),
        queue=record.queue,
        eta_minutes=record.eta_minutes,
        resolution_note=scrub_pii(record.resolution_note),
        created_at=record.created_at.isoformat(),
        updated_at=record.updated_at.isoformat(),
        resolved_at=_to_iso(record.resolved_at),
    )


@app.post("/handoffs/{handoff_id}/resume", response_model=ChatResponse)
def resume_handoff(
    handoff_id: str,
    request: ResumeHandoffRequest,
    _: None = Depends(require_support_role),
) -> ChatResponse:
    record = persistence_service.get_handoff(handoff_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Handoff ticket not found")

    updated = persistence_service.update_handoff_status(handoff_id, "resolved", "Conversation resumed by manual agent")
    if updated is None:
        raise HTTPException(status_code=404, detail="Handoff ticket not found")

    record_handoff_status("resolved")

    resumed_response = scrub_pii(request.agent_message)
    resumed_intent = "general"
    resumed_confidence = 1.0

    if settings.hitl_interrupt_enabled and Command is not None:
        try:
            resumed_state = compiled_graph.invoke(
                Command(resume={"agent_message": resumed_response}),
                config={"configurable": {"thread_id": record.conversation_id}},
            )
            resumed_response = scrub_pii(resumed_state.get("response", resumed_response))
            resumed_intent = _normalize_chat_intent(resumed_state.get("intent", "general"))
            resumed_confidence = resumed_state.get("confidence", 1.0)
        except Exception:
            resumed_response = scrub_pii(request.agent_message)

    persistence_service.create_conversation_event(
        conversation_id=record.conversation_id,
        user_id=record.user_id,
        role="system",
        message=resumed_response,
        status="resolved",
        handoff_id=handoff_id,
        event_metadata={"event": "human_agent_resume"},
    )

    return ChatResponse(
        conversation_id=record.conversation_id,
        status="resolved",
        response_text=_normalize_user_visible_text(resumed_response, preserve_support_email=True),
        recommended_products=[],
        auth_required=False,
        intent=_normalize_chat_intent(resumed_intent),
        confidence=resumed_confidence,
        handoff_id=handoff_id,
        metadata={"handoff_status": "resolved", "resolution_note": scrub_pii(updated.resolution_note)},
    )


@app.get("/admin/dashboard/chat/{conversation_id}/transcript", response_model=ChatTranscriptResponse)
def admin_chat_transcript(
    conversation_id: str,
    _: None = Depends(require_support_role),
) -> ChatTranscriptResponse:
    _ensure_admin_analytics_enabled()
    transcript = persistence_service.get_chat_transcript(conversation_id)

    return ChatTranscriptResponse(
        conversation_id=conversation_id,
        transcript=[
            DashboardChatMessage(
                role=item["role"],
                message=scrub_pii(item["message"]),
                created_at=item["created_at"],
                intent=item.get("intent"),
                event_metadata=item.get("event_metadata") or {},
            )
            for item in transcript
        ]
    )

import json

@app.get("/admin/categories")
def get_admin_categories(_: None = Depends(require_support_role)) -> list[str]:
    path = Path("data/categories.json")
    if not path.exists():
        return ["Other"]
    try:
        return json.loads(path.read_text("utf-8"))
    except Exception:
        return ["Other"]

@app.put("/admin/categories")
def update_admin_categories(categories: list[str], _: None = Depends(require_support_role)) -> list[str]:
    path = Path("data/categories.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(categories, indent=2), "utf-8")
    return categories

@app.post("/admin/conversations/{conversation_id}/intent")
def override_conversation_intent(
    conversation_id: str,
    request: ConversationIntentOverrideRequest,
    _: None = Depends(require_support_role),
):
    persistence_service.upsert_conversation_intent_label(
        conversation_id=conversation_id,
        intent_label=request.intent_label,
        confidence=1.0,
        rationale_short="Manual override via dashboard.",
        model_name="human",
        model_version="human",
        source_version="manual",
        needs_review=False,
        transcript_checksum="manual",
        intent_subcategory=request.category,
    )
    return {"status": "ok"}

@app.post("/admin/conversations/{conversation_id}/reclassify")
def reclassify_conversation_intent(
    conversation_id: str,
    _: None = Depends(require_support_role),
):
    result = conversation_intent_queue_service.enqueue_classification(
        conversation_id=conversation_id,
        user_id="admin",
        force=True,
    )
    return {"status": "ok", "task_id": result["task_id"]}
