from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import time
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Request
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
from satmi_agent.queueing import cancellation_queue_service
from satmi_agent.schemas import (
    AsyncTaskResponse,
    ChatRequest,
    ChatResponse,
    ConversationEventResponse,
    HandoffStatusUpdateRequest,
    HandoffTicketResponse,
    ResumeHandoffRequest,
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


@asynccontextmanager
async def lifespan(_: FastAPI):
    persistence_service.init_db()
    await _warm_catalog_cache()
    ensure_firebase_ready_or_raise()
    setup_tracing()
    yield


app = FastAPI(title="SATMI Agent API", version="0.1.0", lifespan=lifespan)


def _cors_allow_origins() -> list[str]:
    origins = {
        "https://satmi.in",
        "https://www.satmi.in",
        "https://accounts.satmi.in",
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
    allow_origin_regex=r"https?://(([a-zA-Z0-9-]+\.)?(myshopify\.com|shopify\.com)|localhost|127\.0\.0\.1|192\.168\.\d+\.\d+)(:\d+)?$",
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
    http_request: Request,
    _: None = Depends(require_api_key),
) -> ChatResponse | dict[str, Any]:
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
        event_metadata={
            "handoff_reason": final_state.get("handoff_reason"),
            "errors": scrub_pii(final_state.get("errors", [])),
            "internal_logs": scrub_pii(final_state.get("internal_logs", [])),
        },
    )

    status_value = final_state.get("status", "active")
    intent_value = _normalize_chat_intent(final_state.get("intent", "unknown"))
    recommended_products = _safe_recommended_products(_coerce_recommended_products(final_state))
    recommendation_source = (final_state.get("tool_result") or {}).get("source")

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
