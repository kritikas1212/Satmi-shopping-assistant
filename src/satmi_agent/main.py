from __future__ import annotations

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
    extract_bearer_token,
    ensure_firebase_ready_or_raise,
    firebase_auth_health,
    require_api_key,
    require_support_role,
    scrub_pii,
    verify_firebase_user,
)
from satmi_agent.tools import tooling_service
from satmi_agent.tracing import get_tracer, setup_tracing

try:
    from langgraph.types import Command
except Exception:  # pragma: no cover
    Command = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    persistence_service.init_db()
    ensure_firebase_ready_or_raise()
    setup_tracing()
    yield


app = FastAPI(title="SATMI Agent API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://satmi.in",
        "https://www.satmi.in",
        "https://accounts.satmi.in",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
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


@app.post("/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    http_request: Request,
    authorization: str | None = Header(default=None),
    x_firebase_token: str | None = Header(default=None),
    _: None = Depends(require_api_key),
) -> ChatResponse:
    enforce_chat_rate_limit(http_request, request.user_id)
    masked_user_message = scrub_pii(request.message)
    firebase_token = x_firebase_token or extract_bearer_token(authorization)
    firebase_user = verify_firebase_user(firebase_token)
    order_context: list[dict[str, Any]] = []

    if firebase_user:
        # Load recent order context for this authenticated user to avoid repeat prompts.
        order_data = tooling_service.get_customer_orders(request.user_id)
        order_context = order_data.get("orders", [])

    persistence_service.create_conversation_event(
        conversation_id=request.conversation_id,
        user_id=request.user_id,
        role="user",
        message=masked_user_message,
        status="active",
        event_metadata={"event": "user_message"},
    )

    try:
        final_state = compiled_graph.invoke(
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
                "message_history": [
                    {"role": "user", "content": masked_user_message},
                ],
            },
            config={"configurable": {"thread_id": request.conversation_id}},
        )
    except Exception as exc:
        fallback_handoff_id = f"HND-{uuid4().hex[:8].upper()}"
        final_state = {
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
            "message_history": [{"role": "user", "content": masked_user_message}],
        }

    message_history = final_state.get("message_history", [])
    if final_state.get("response"):
        message_history = [
            *message_history,
            {"role": "assistant", "content": scrub_pii(final_state.get("response", ""))},
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
    intent_value = final_state.get("intent", "unknown")
    record_chat_outcome(status=status_value, intent=intent_value)
    if final_state.get("handoff_id"):
        record_handoff_created(final_state.get("handoff_reason", "unspecified"))

    return ChatResponse(
        conversation_id=request.conversation_id,
        status=final_state.get("status", "active"),
        response=scrub_pii(final_state.get("response", "I am here to help.")),
        intent=final_state.get("intent", "unknown"),
        confidence=final_state.get("confidence", 0.0),
        handoff_id=final_state.get("handoff_id"),
        metadata={
            "action": final_state.get("action"),
            "handoff_reason": final_state.get("handoff_reason"),
            "async_task_id": final_state.get("async_task_id"),
            "async_task_status": final_state.get("async_task_status"),
            "user_authenticated": bool(firebase_user),
            "auth_user_uid": firebase_user.get("uid") if firebase_user else None,
            "order_context_count": len(order_context),
            "catalog_source": (final_state.get("tool_result") or {}).get("source"),
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
    resumed_intent = "support"
    resumed_confidence = 1.0

    if settings.hitl_interrupt_enabled and Command is not None:
        try:
            resumed_state = compiled_graph.invoke(
                Command(resume={"agent_message": resumed_response}),
                config={"configurable": {"thread_id": record.conversation_id}},
            )
            resumed_response = scrub_pii(resumed_state.get("response", resumed_response))
            resumed_intent = resumed_state.get("intent", "support")
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
        response=resumed_response,
        intent=resumed_intent,
        confidence=resumed_confidence,
        handoff_id=handoff_id,
        metadata={"handoff_status": "resolved", "resolution_note": scrub_pii(updated.resolution_note)},
    )
