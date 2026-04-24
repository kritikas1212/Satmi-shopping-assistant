from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import re
from typing import Any, Literal

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, Integer, String, Text, create_engine, func, select, text, or_
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from satmi_agent.config import settings
from satmi_agent.security import scrub_pii
from satmi_agent.schemas import HandoffStatus


# Safety caps for admin dashboard queries so a single very large conversation
# cannot exhaust worker memory during snapshot/transcript/export rendering.
DASHBOARD_SESSION_EVENT_LIMIT = 250
DASHBOARD_TRANSCRIPT_EVENT_LIMIT = 500
DASHBOARD_EXPORT_EVENT_LIMIT = 500


class Base(DeclarativeBase):
    pass


class ConversationEventRecord(Base):
    __tablename__ = "conversation_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(String(128), index=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    role: Mapped[str] = mapped_column(String(32))
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="active")
    intent: Mapped[str | None] = mapped_column(String(32), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    action: Mapped[str | None] = mapped_column(String(128), nullable=True)
    handoff_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    event_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class HandoffTicketRecord(Base):
    __tablename__ = "handoff_tickets"

    handoff_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(128), index=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    reason: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    intent: Mapped[str] = mapped_column(String(32), default="unknown")
    attempted_action: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tool_result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    errors: Mapped[list[str]] = mapped_column(JSON, default=list)
    queue: Mapped[str] = mapped_column(String(128), default="satmi-tier-1-manual-support")
    eta_minutes: Mapped[int] = mapped_column(default=15)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AsyncTaskRecord(Base):
    __tablename__ = "async_tasks"

    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True, default="queued")
    conversation_id: Mapped[str] = mapped_column(String(128), index=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProductCatalogRecord(Base):
    __tablename__ = "product_catalog"

    product_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(512), index=True)
    body_html: Mapped[str] = mapped_column(Text, default="")
    product_type: Mapped[str] = mapped_column(String(128), default="")
    tags: Mapped[str] = mapped_column(Text, default="")
    vendor: Mapped[str] = mapped_column(String(256), default="")
    status: Mapped[str] = mapped_column(String(32), index=True, default="active")
    variants: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    searchable_text: Mapped[str] = mapped_column(Text, default="", index=True)
    shopify_updated_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


class ChatQueryEventRecord(Base):
    __tablename__ = "chat_query_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(String(128), index=True)
    user_id_hash: Mapped[str] = mapped_column(String(128), index=True)
    masked_query: Mapped[str] = mapped_column(Text)
    normalized_term: Mapped[str] = mapped_column(String(256), index=True)
    intent: Mapped[str] = mapped_column(String(32), index=True, default="unknown")
    had_recommendations: Mapped[bool] = mapped_column(Boolean, default=False)
    recommendation_count: Mapped[int] = mapped_column(Integer, default=0)
    latency_bucket: Mapped[str] = mapped_column(String(32), default="unknown", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


class SearchTermDailyStatRecord(Base):
    __tablename__ = "search_term_daily_stats"

    stat_date: Mapped[date] = mapped_column(Date, primary_key=True)
    normalized_term: Mapped[str] = mapped_column(String(256), primary_key=True)
    query_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class QueryIntentDailyStatRecord(Base):
    __tablename__ = "query_intent_daily_stats"

    stat_date: Mapped[date] = mapped_column(Date, primary_key=True)
    intent: Mapped[str] = mapped_column(String(32), primary_key=True)
    query_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class ConversationIntentLabelRecord(Base):
    __tablename__ = "conversation_intent_labels"

    conversation_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    intent_label: Mapped[str] = mapped_column(String(64), default="unknown", index=True)
    intent_subcategory: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    rationale_short: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    classified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    source_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    transcript_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)


class ConversationIntentOverrideRecord(Base):
    __tablename__ = "conversation_intent_overrides"

    conversation_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    intent_label: Mapped[str] = mapped_column(String(64), default="unknown", index=True)
    override_reason: Mapped[str] = mapped_column(Text)
    overridden_by: Mapped[str] = mapped_column(String(128), default="admin")
    overridden_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


class ConversationIntentClassificationRunRecord(Base):
    __tablename__ = "conversation_intent_classification_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(String(128), index=True)
    intent_label: Mapped[str] = mapped_column(String(64), default="unknown", index=True)
    raw_intent_label: Mapped[str | None] = mapped_column(String(256), nullable=True)
    classifier_mode: Mapped[str] = mapped_column(String(32), default="guardrailed", index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    rationale_short: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    raw_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt_char_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    transcript_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


def _normalize_database_url(url: str) -> str:
    normalized = (url or "").strip()
    if normalized.startswith("postgres://"):
        normalized = "postgresql://" + normalized[len("postgres://"):]
    if normalized.startswith("postgresql://") and "+" not in normalized.split("://", 1)[0]:
        normalized = "postgresql+psycopg://" + normalized[len("postgresql://"):]
    return normalized


_db_url = _normalize_database_url(settings.database_url)
_engine_kwargs = {"future": True}
if _db_url.startswith("postgresql"):
    _engine_kwargs["pool_pre_ping"] = True
    _engine_kwargs["pool_recycle"] = 300
engine = create_engine(_db_url, **_engine_kwargs)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False, future=True)


_FRUSTRATION_KEYWORDS = {"human", "agent", "wrong", "frustrated"}
_ORDER_TRACKING_KEYWORDS = {"track", "tracking", "shipment", "shipping", "delivery", "order", "awb"}
_PRODUCT_SEARCH_KEYWORDS = {
    "buy",
    "shop",
    "product",
    "products",
    "recommend",
    "price",
    "bracelet",
    "mala",
    "ring",
    "necklace",
    "rudraksha",
    "karungali",
    "crystal",
}
_RETURNS_KEYWORDS = {"return", "returns", "refund", "exchange", "cancel", "replacement"}
_POLICY_KEYWORDS = {
    "policy",
    "policies",
    "warranty",
    "guarantee",
    "certified",
    "lab",
    "certificate",
    "authentic",
    "money-back",
    "moneyback",
}
_TREND_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "can",
    "for",
    "from",
    "i",
    "is",
    "it",
    "my",
    "of",
    "on",
    "or",
    "please",
    "the",
    "to",
    "what",
    "where",
    "with",
}


def _tokenize_words(text: str) -> set[str]:
    cleaned = re.sub(r"[^a-z0-9\s]", " ", (text or "").lower())
    return {token for token in cleaned.split() if token}


def _extract_trend_term(text: str) -> str | None:
    words = [token for token in _tokenize_words(text) if token not in _TREND_STOPWORDS]
    if not words:
        return None
    return " ".join(words[:4])


def _classify_message_category(text: str) -> str:
    words = _tokenize_words(text)
    if words.intersection(_ORDER_TRACKING_KEYWORDS):
        return "Order Tracking"
    if words.intersection(_RETURNS_KEYWORDS):
        return "Returns"
    if words.intersection(_PRODUCT_SEARCH_KEYWORDS):
        return "Product Search"
    if words.intersection(_POLICY_KEYWORDS):
        return "Policy & FAQ"
    return "General"


def _normalize_intent(intent: str | None) -> str:
    normalized = str(intent or "unknown").strip().lower()
    if normalized in {"shopping", "order_tracking", "policy_brand_faq", "authentication", "general", "unknown"}:
        return normalized
    return "unknown"


def _normalize_conversation_intent_label(intent: str | None) -> str:
    return str(intent or "unknown").strip()


def _conversation_intent_to_label(intent: str | None) -> str:
    return str(intent or "unknown").strip() or "unknown"


def _intent_to_label(intent: str | None) -> str:
    return str(intent or "unknown").strip() or "unknown"


def _is_frustrated_session(user_messages: list[str]) -> bool:
    for message in user_messages:
        lowered = (message or "").lower()
        if any(keyword in lowered for keyword in _FRUSTRATION_KEYWORDS):
            return True
    return False


def _is_resolved_session(events: list[ConversationEventRecord]) -> bool:
    for event in events:
        if event.role not in {"assistant", "system"}:
            continue
        action = str(event.action or "").lower()
        message = str(event.message or "").lower()

        # Mark resolved if assistant completed tracking flow or presented Select & Buy product CTA.
        if action in {"order_tracking_redirect", "portal_redirect"}:
            return True
        if "select & buy" in message or "select and buy" in message:
            return True
    return False


class PersistenceService:
    def init_db(self) -> None:
        Base.metadata.create_all(bind=engine)
        # Safe migration: add intent_subcategory column if it doesn't exist (for existing databases)
        try:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE conversation_intent_labels ADD COLUMN intent_subcategory VARCHAR(128)"))
                conn.commit()
        except Exception:
            pass  # Column already exists

    def _session(self) -> Session:
        return SessionLocal()

    def create_conversation_event(
        self,
        *,
        conversation_id: str,
        user_id: str,
        role: Literal["user", "assistant", "system"],
        message: str,
        status: str,
        intent: str | None = None,
        confidence: float | None = None,
        action: str | None = None,
        handoff_id: str | None = None,
        event_metadata: dict[str, Any] | None = None,
    ) -> None:
        record = ConversationEventRecord(
            conversation_id=conversation_id,
            user_id=user_id,
            role=role,
            message=message,
            status=status,
            intent=intent,
            confidence=confidence,
            action=action,
            handoff_id=handoff_id,
            event_metadata=event_metadata or {},
        )
        with self._session() as session:
            session.add(record)
            session.commit()

    def upsert_handoff_from_state(self, state: dict[str, Any]) -> None:
        handoff_id = state.get("handoff_id")
        if not handoff_id:
            return

        with self._session() as session:
            record = session.get(HandoffTicketRecord, handoff_id)
            if record is None:
                record = HandoffTicketRecord(
                    handoff_id=handoff_id,
                    conversation_id=state.get("conversation_id", "unknown"),
                    user_id=state.get("user_id", "unknown"),
                    status="open",
                    reason=scrub_pii(state.get("handoff_reason") or "Manual support required"),
                    summary=scrub_pii(state.get("message", "")),
                    intent=state.get("intent", "unknown"),
                    attempted_action=state.get("action"),
                    tool_result=scrub_pii(state.get("tool_result", {})),
                    errors=scrub_pii(state.get("errors", [])),
                )
                session.add(record)
            else:
                record.reason = scrub_pii(state.get("handoff_reason") or record.reason)
                record.summary = scrub_pii(state.get("message", record.summary))
                record.intent = state.get("intent", record.intent)
                record.attempted_action = state.get("action", record.attempted_action)
                record.tool_result = scrub_pii(state.get("tool_result", record.tool_result))
                record.errors = scrub_pii(state.get("errors", record.errors))
                record.updated_at = datetime.now(timezone.utc)

            session.commit()

    def get_handoff(self, handoff_id: str) -> HandoffTicketRecord | None:
        with self._session() as session:
            return session.get(HandoffTicketRecord, handoff_id)

    def update_handoff_status(self, handoff_id: str, status: HandoffStatus, note: str | None = None) -> HandoffTicketRecord | None:
        with self._session() as session:
            record = session.get(HandoffTicketRecord, handoff_id)
            if record is None:
                return None

            record.status = status
            record.updated_at = datetime.now(timezone.utc)
            if note:
                record.resolution_note = note
            if status == "resolved":
                record.resolved_at = datetime.now(timezone.utc)

            session.commit()
            session.refresh(record)
            return record

    def list_conversation_events(self, conversation_id: str, limit: int = 50) -> list[ConversationEventRecord]:
        with self._session() as session:
            stmt = (
                select(ConversationEventRecord)
                .where(ConversationEventRecord.conversation_id == conversation_id)
                .order_by(ConversationEventRecord.created_at.asc())
                .limit(limit)
            )
            return list(session.scalars(stmt).all())

    def list_recent_user_messages(self, user_id: str, limit: int = 20) -> list[str]:
        with self._session() as session:
            stmt = (
                select(ConversationEventRecord)
                .where(ConversationEventRecord.user_id == user_id)
                .where(ConversationEventRecord.role == "user")
                .order_by(ConversationEventRecord.created_at.desc())
                .limit(limit)
            )
            rows = list(session.scalars(stmt).all())
            return [str(row.message or "").strip() for row in rows if str(row.message or "").strip()]

    def list_conversation_events_for_classification(self, conversation_id: str, limit: int | None = None) -> list[ConversationEventRecord]:
        max_limit = max(int(limit or settings.conversation_intent_transcript_event_limit), 1)
        with self._session() as session:
            stmt = (
                select(ConversationEventRecord)
                .where(ConversationEventRecord.conversation_id == conversation_id)
                .where(ConversationEventRecord.role.in_(["user", "assistant", "system"]))
                .order_by(ConversationEventRecord.created_at.asc())
                .limit(max_limit)
            )
            return list(session.scalars(stmt).all())

    def compute_transcript_checksum(self, conversation_id: str, *, limit: int | None = None) -> str:
        events = self.list_conversation_events_for_classification(conversation_id, limit=limit)
        digest = hashlib.sha256()
        for event in events:
            digest.update(f"{event.created_at.isoformat()}|{event.role}|{event.message}\n".encode("utf-8"))
        return digest.hexdigest()

    def upsert_conversation_intent_label(
        self,
        *,
        conversation_id: str,
        intent_label: str,
        confidence: float,
        rationale_short: str | None,
        model_name: str | None,
        model_version: str | None,
        source_version: str | None,
        needs_review: bool,
        transcript_checksum: str | None,
        classified_at: datetime | None = None,
        intent_subcategory: str | None = None,
    ) -> None:
        exact_intent = str(intent_label or "unknown").strip() or "unknown"
        now = classified_at or datetime.now(timezone.utc)
        with self._session() as session:
            row = session.get(ConversationIntentLabelRecord, conversation_id)
            if row is None:
                row = ConversationIntentLabelRecord(
                    conversation_id=conversation_id,
                    intent_label=exact_intent,
                    intent_subcategory=str(intent_subcategory or "")[:128] or None,
                    confidence=max(0.0, min(float(confidence), 1.0)),
                    rationale_short=scrub_pii(rationale_short or ""),
                    model_name=model_name,
                    model_version=model_version,
                    classified_at=now,
                    source_version=source_version,
                    needs_review=bool(needs_review),
                    transcript_checksum=transcript_checksum,
                )
                session.add(row)
            else:
                row.intent_label = exact_intent
                row.intent_subcategory = str(intent_subcategory or "")[:128] or None
                row.confidence = max(0.0, min(float(confidence), 1.0))
                row.rationale_short = scrub_pii(rationale_short or "")
                row.model_name = model_name
                row.model_version = model_version
                row.classified_at = now
                row.source_version = source_version
                row.needs_review = bool(needs_review)
                row.transcript_checksum = transcript_checksum
            session.commit()

    def create_conversation_intent_classification_run(
        self,
        *,
        conversation_id: str,
        intent_label: str,
        raw_intent_label: str | None,
        classifier_mode: str,
        confidence: float,
        rationale_short: str | None,
        model_name: str | None,
        model_version: str | None,
        source_version: str | None,
        raw_output: str | None,
        raw_error: str | None,
        prompt_token_count: int | None,
        completion_token_count: int | None,
        total_token_count: int | None,
        prompt_char_count: int | None,
        transcript_checksum: str | None,
        created_at: datetime | None = None,
    ) -> None:
        exact_intent = str(intent_label or "unknown").strip() or "unknown"
        exact_raw_intent = str(raw_intent_label or exact_intent).strip() or exact_intent
        now = created_at or datetime.now(timezone.utc)
        with self._session() as session:
            session.add(
                ConversationIntentClassificationRunRecord(
                    conversation_id=conversation_id,
                    intent_label=exact_intent,
                    raw_intent_label=exact_raw_intent[:256] or None,
                    classifier_mode=str(classifier_mode or "guardrailed")[:32],
                    confidence=max(0.0, min(float(confidence), 1.0)),
                    rationale_short=scrub_pii(rationale_short or ""),
                    model_name=model_name,
                    model_version=model_version,
                    source_version=source_version,
                    raw_output=scrub_pii(str(raw_output or "")[:12000]),
                    raw_error=scrub_pii(str(raw_error or "")[:2000]),
                    prompt_token_count=prompt_token_count,
                    completion_token_count=completion_token_count,
                    total_token_count=total_token_count,
                    prompt_char_count=prompt_char_count,
                    transcript_checksum=transcript_checksum,
                    created_at=now,
                )
            )
            session.commit()

    def get_conversation_intent_label(self, conversation_id: str) -> dict[str, Any] | None:
        with self._session() as session:
            label_row = session.get(ConversationIntentLabelRecord, conversation_id)
            override_row = session.get(ConversationIntentOverrideRecord, conversation_id)
            latest_run = session.scalars(
                select(ConversationIntentClassificationRunRecord)
                .where(ConversationIntentClassificationRunRecord.conversation_id == conversation_id)
                .order_by(
                    ConversationIntentClassificationRunRecord.created_at.desc(),
                    ConversationIntentClassificationRunRecord.id.desc(),
                )
                .limit(1)
            ).first()
            if label_row is None and override_row is None:
                return None

            label_value = override_row.intent_label if override_row is not None else (label_row.intent_label if label_row is not None else "unknown")
            return {
                "conversation_id": conversation_id,
                "intent_label": str(label_value or "unknown").strip() or "unknown",
                "intent_display": str(label_value or "unknown").strip() or "unknown",
                "confidence": float(label_row.confidence) if label_row is not None else None,
                "rationale_short": str(label_row.rationale_short or "") if label_row is not None else "",
                "model_name": str(label_row.model_name or "") if label_row is not None else "",
                "model_version": str(label_row.model_version or "") if label_row is not None else "",
                "classified_at": label_row.classified_at.isoformat() if label_row is not None else None,
                "source_version": str(label_row.source_version or "") if label_row is not None else "",
                "needs_review": bool(label_row.needs_review) if label_row is not None else True,
                "transcript_checksum": str(label_row.transcript_checksum or "") if label_row is not None else "",
                "is_overridden": override_row is not None,
                "override_reason": str(override_row.override_reason or "") if override_row is not None else None,
                "overridden_by": str(override_row.overridden_by or "") if override_row is not None else None,
                "overridden_at": override_row.overridden_at.isoformat() if override_row is not None else None,
                "raw_intent_label": str(latest_run.raw_intent_label or "") if latest_run is not None else "",
                "classifier_mode": str(latest_run.classifier_mode or "") if latest_run is not None else "",
                "classifier_raw_error": str(latest_run.raw_error or "") if latest_run is not None else "",
                "classifier_raw_output": str(latest_run.raw_output or "") if latest_run is not None else "",
                "classifier_prompt_token_count": int(latest_run.prompt_token_count)
                if latest_run is not None and latest_run.prompt_token_count is not None
                else None,
                "classifier_completion_token_count": int(latest_run.completion_token_count)
                if latest_run is not None and latest_run.completion_token_count is not None
                else None,
                "classifier_total_token_count": int(latest_run.total_token_count)
                if latest_run is not None and latest_run.total_token_count is not None
                else None,
                "classifier_prompt_char_count": int(latest_run.prompt_char_count)
                if latest_run is not None and latest_run.prompt_char_count is not None
                else None,
            }

    def get_cached_intent_by_checksum(self, checksum: str) -> dict[str, Any] | None:
        """Find an existing classification with the same exact transcript checksum and high confidence."""
        if not checksum:
            return None
            
        with self._session() as session:
            # Look for any row with this exact checksum and confidence >= 0.95
            stmt = (
                select(ConversationIntentLabelRecord)
                .where(ConversationIntentLabelRecord.transcript_checksum == checksum)
                .where(ConversationIntentLabelRecord.confidence >= 0.95)
                .where(ConversationIntentLabelRecord.intent_label != "unknown")
                .order_by(ConversationIntentLabelRecord.classified_at.desc())
                .limit(1)
            )
            row = session.scalars(stmt).first()
            if not row:
                return None
                
            return {
                "intent_label": row.intent_label,
                "confidence": float(row.confidence),
                "rationale_short": str(row.rationale_short or ""),
                "model_name": str(row.model_name or ""),
                "model_version": str(row.model_version or ""),
                "source_version": str(row.source_version or ""),
                "needs_review": bool(row.needs_review),
                "transcript_checksum": str(row.transcript_checksum or ""),
                "classified_at": row.classified_at.isoformat(),
            }

    def list_conversation_intent_labels(self, conversation_ids: list[str]) -> dict[str, dict[str, Any]]:
        ids = [str(item) for item in conversation_ids if str(item).strip()]
        if not ids:
            return {}

        with self._session() as session:
            label_rows = list(
                session.scalars(
                    select(ConversationIntentLabelRecord).where(ConversationIntentLabelRecord.conversation_id.in_(ids))
                ).all()
            )
            override_rows = list(
                session.scalars(
                    select(ConversationIntentOverrideRecord).where(ConversationIntentOverrideRecord.conversation_id.in_(ids))
                ).all()
            )
            ranked_runs_subquery = (
                select(
                    ConversationIntentClassificationRunRecord.id.label("run_id"),
                    func.row_number()
                    .over(
                        partition_by=ConversationIntentClassificationRunRecord.conversation_id,
                        order_by=(
                            ConversationIntentClassificationRunRecord.created_at.desc(),
                            ConversationIntentClassificationRunRecord.id.desc(),
                        ),
                    )
                    .label("row_num"),
                )
                .where(ConversationIntentClassificationRunRecord.conversation_id.in_(ids))
                .subquery()
            )
            latest_runs = list(
                session.scalars(
                    select(ConversationIntentClassificationRunRecord)
                    .join(
                        ranked_runs_subquery,
                        ConversationIntentClassificationRunRecord.id == ranked_runs_subquery.c.run_id,
                    )
                    .where(ranked_runs_subquery.c.row_num == 1)
                ).all()
            )

        label_map = {row.conversation_id: row for row in label_rows}
        override_map = {row.conversation_id: row for row in override_rows}
        latest_run_map = {row.conversation_id: row for row in latest_runs}
        result: dict[str, dict[str, Any]] = {}

        for conversation_id in ids:
            label_row = label_map.get(conversation_id)
            override_row = override_map.get(conversation_id)
            run_row = latest_run_map.get(conversation_id)
            if label_row is None and override_row is None:
                continue

            effective_label = override_row.intent_label if override_row is not None else (label_row.intent_label if label_row is not None else "unknown")
            result[conversation_id] = {
                "intent_label": str(effective_label or "unknown").strip() or "unknown",
                "intent_display": str(effective_label or "unknown").strip() or "unknown",
                "intent_subcategory": str(getattr(label_row, "intent_subcategory", "")) if label_row is not None else "",
                "confidence": float(label_row.confidence) if label_row is not None else None,
                "model_name": str(label_row.model_name or "") if label_row is not None else "",
                "model_version": str(label_row.model_version or "") if label_row is not None else "",
                "classified_at": label_row.classified_at.isoformat() if label_row is not None else None,
                "source_version": str(label_row.source_version or "") if label_row is not None else "",
                "needs_review": bool(label_row.needs_review) if label_row is not None else True,
                "transcript_checksum": str(label_row.transcript_checksum or "") if label_row is not None else "",
                "rationale_short": str(label_row.rationale_short or "") if label_row is not None else "",
                "is_overridden": override_row is not None,
                "override_reason": str(override_row.override_reason or "") if override_row is not None else None,
                "overridden_by": str(override_row.overridden_by or "") if override_row is not None else None,
                "overridden_at": override_row.overridden_at.isoformat() if override_row is not None else None,
                "raw_intent_label": str(run_row.raw_intent_label or "") if run_row is not None else "",
                "classifier_mode": str(run_row.classifier_mode or "") if run_row is not None else "",
                "classifier_raw_error": str(run_row.raw_error or "") if run_row is not None else "",
                "classifier_total_token_count": int(run_row.total_token_count)
                if run_row is not None and run_row.total_token_count is not None
                else None,
            }

        return result

    def upsert_conversation_intent_override(
        self,
        *,
        conversation_id: str,
        intent_label: str,
        override_reason: str,
        overridden_by: str,
    ) -> None:
        exact_intent = str(intent_label or "unknown").strip() or "unknown"
        now = datetime.now(timezone.utc)
        with self._session() as session:
            row = session.get(ConversationIntentOverrideRecord, conversation_id)
            if row is None:
                row = ConversationIntentOverrideRecord(
                    conversation_id=conversation_id,
                    intent_label=exact_intent,
                    override_reason=scrub_pii(override_reason),
                    overridden_by=str(overridden_by or "admin"),
                    overridden_at=now,
                )
                session.add(row)
            else:
                row.intent_label = exact_intent
                row.override_reason = scrub_pii(override_reason)
                row.overridden_by = str(overridden_by or "admin")
                row.overridden_at = now
            session.commit()

    def clear_conversation_intent_override(self, conversation_id: str) -> None:
        with self._session() as session:
            row = session.get(ConversationIntentOverrideRecord, conversation_id)
            if row is None:
                return
            session.delete(row)
            session.commit()

    def list_inactive_conversations_needing_intent_classification(self, *, inactive_minutes: int, limit: int) -> list[dict[str, Any]]:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=max(inactive_minutes, 1))
        max_limit = max(limit, 1)
        candidates: list[dict[str, Any]] = []

        with self._session() as session:
            subquery = (
                select(
                    ConversationEventRecord.conversation_id.label("conversation_id"),
                    func.max(ConversationEventRecord.created_at).label("last_activity_at"),
                )
                .where(ConversationEventRecord.role.in_(["user", "assistant", "system"]))
                .group_by(ConversationEventRecord.conversation_id)
                .having(func.max(ConversationEventRecord.created_at) <= cutoff)
                .order_by(func.max(ConversationEventRecord.created_at).desc())
                .limit(max_limit)
            )
            rows = session.execute(subquery).all()

            for item in rows:
                conversation_id = str(item.conversation_id)
                events = self.list_conversation_events_for_classification(conversation_id)
                if not events:
                    continue

                checksum = hashlib.sha256(
                    "".join(f"{event.created_at.isoformat()}|{event.role}|{event.message}\n" for event in events).encode("utf-8")
                ).hexdigest()
                label_row = session.get(ConversationIntentLabelRecord, conversation_id)

                if label_row is not None and str(label_row.transcript_checksum or "") == checksum:
                    continue

                user_id = next((str(event.user_id or "") for event in events if str(event.user_id or "").strip()), "unknown")
                candidates.append(
                    {
                        "conversation_id": conversation_id,
                        "user_id": user_id,
                        "last_activity_at": item.last_activity_at.isoformat() if item.last_activity_at is not None else None,
                        "transcript_checksum": checksum,
                    }
                )

        return candidates

    def create_async_task(
        self,
        *,
        task_id: str,
        task_type: str,
        conversation_id: str,
        user_id: str,
        payload: dict[str, Any],
        status: str = "queued",
    ) -> None:
        record = AsyncTaskRecord(
            task_id=task_id,
            task_type=task_type,
            status=status,
            conversation_id=conversation_id,
            user_id=user_id,
            payload=scrub_pii(payload),
            result={},
            error=None,
        )
        with self._session() as session:
            session.add(record)
            session.commit()

    def update_async_task(
        self,
        task_id: str,
        *,
        status: str,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> AsyncTaskRecord | None:
        with self._session() as session:
            record = session.get(AsyncTaskRecord, task_id)
            if record is None:
                return None

            record.status = status
            record.updated_at = datetime.now(timezone.utc)
            if result is not None:
                record.result = scrub_pii(result)
            if error is not None:
                record.error = scrub_pii(error)
            if status in {"completed", "failed"}:
                record.completed_at = datetime.now(timezone.utc)

            session.commit()
            session.refresh(record)
            return record

    def get_async_task(self, task_id: str) -> AsyncTaskRecord | None:
        with self._session() as session:
            return session.get(AsyncTaskRecord, task_id)

    def upsert_product_catalog(self, products: list[dict[str, Any]]) -> int:
        if not products:
            return 0

        upserted = 0
        now = datetime.now(timezone.utc)

        with self._session() as session:
            for item in products:
                product_id = str(item.get("product_id") or item.get("id") or "").strip()
                if not product_id:
                    continue

                record = session.get(ProductCatalogRecord, product_id)
                if record is None:
                    record = ProductCatalogRecord(product_id=product_id, title="Unknown Product")
                    session.add(record)

                record.title = str(item.get("title") or item.get("name") or record.title)
                record.body_html = str(item.get("body_html") or "")
                record.product_type = str(item.get("product_type") or "")
                record.tags = str(item.get("tags") or "")
                record.vendor = str(item.get("vendor") or "")
                record.status = str(item.get("status") or "active")
                variants = item.get("variants") or []
                record.variants = variants if isinstance(variants, list) else []
                record.searchable_text = str(item.get("searchable_text") or "")
                record.shopify_updated_at = str(item.get("updated_at") or item.get("shopify_updated_at") or "") or None
                record.synced_at = now
                upserted += 1

            session.commit()

        return upserted

    def list_product_catalog(self, limit: int | None = None) -> list[dict[str, Any]]:
        with self._session() as session:
            stmt = select(ProductCatalogRecord).where(ProductCatalogRecord.status == "active").order_by(ProductCatalogRecord.title.asc())
            if limit and limit > 0:
                stmt = stmt.limit(limit)
            records = list(session.scalars(stmt).all())

        return [
            {
                "id": record.product_id,
                "title": record.title,
                "body_html": record.body_html,
                "product_type": record.product_type,
                "tags": record.tags,
                "vendor": record.vendor,
                "status": record.status,
                "variants": record.variants,
                "updated_at": record.shopify_updated_at,
            }
            for record in records
        ]

    def get_catalog_cache_snapshot(self) -> dict[str, Any]:
        with self._session() as session:
            count_stmt = select(func.count(ProductCatalogRecord.product_id)).where(ProductCatalogRecord.status == "active")
            max_sync_stmt = select(func.max(ProductCatalogRecord.synced_at))
            product_count = int(session.scalar(count_stmt) or 0)
            latest_sync_at = session.scalar(max_sync_stmt)

        return {
            "product_count": product_count,
            "latest_sync_at": latest_sync_at,
        }

    def create_chat_query_event(
        self,
        *,
        conversation_id: str,
        user_id_hash: str,
        masked_query: str,
        normalized_term: str,
        intent: str,
        had_recommendations: bool,
        recommendation_count: int,
        latency_bucket: str,
    ) -> None:
        now = datetime.now(timezone.utc)
        stat_day = now.date()

        with self._session() as session:
            event = ChatQueryEventRecord(
                conversation_id=conversation_id,
                user_id_hash=user_id_hash,
                masked_query=masked_query,
                normalized_term=normalized_term,
                intent=intent,
                had_recommendations=had_recommendations,
                recommendation_count=max(int(recommendation_count), 0),
                latency_bucket=latency_bucket,
                created_at=now,
            )
            session.add(event)

            term_row = session.get(
                SearchTermDailyStatRecord,
                {"stat_date": stat_day, "normalized_term": normalized_term},
            )
            if term_row is None:
                term_row = SearchTermDailyStatRecord(
                    stat_date=stat_day,
                    normalized_term=normalized_term,
                    query_count=1,
                    updated_at=now,
                )
                session.add(term_row)
            else:
                term_row.query_count += 1
                term_row.updated_at = now

            intent_row = session.get(
                QueryIntentDailyStatRecord,
                {"stat_date": stat_day, "intent": intent},
            )
            if intent_row is None:
                intent_row = QueryIntentDailyStatRecord(
                    stat_date=stat_day,
                    intent=intent,
                    query_count=1,
                    updated_at=now,
                )
                session.add(intent_row)
            else:
                intent_row.query_count += 1
                intent_row.updated_at = now

            session.commit()

    def list_top_search_terms(self, *, days: int = 7, limit: int = 20) -> list[dict[str, Any]]:
        cutoff_day = datetime.now(timezone.utc).date() - timedelta(days=max(days, 1) - 1)
        with self._session() as session:
            stmt = (
                select(
                    SearchTermDailyStatRecord.normalized_term,
                    func.sum(SearchTermDailyStatRecord.query_count).label("query_count"),
                )
                .where(SearchTermDailyStatRecord.stat_date >= cutoff_day)
                .group_by(SearchTermDailyStatRecord.normalized_term)
                .order_by(func.sum(SearchTermDailyStatRecord.query_count).desc())
                .limit(max(limit, 1))
            )
            rows = session.execute(stmt).all()

        return [
            {
                "normalized_term": str(row.normalized_term),
                "query_count": int(row.query_count or 0),
            }
            for row in rows
        ]

    def list_search_term_trends(self, *, days: int = 30, limit_terms: int = 8) -> list[dict[str, Any]]:
        cutoff_day = datetime.now(timezone.utc).date() - timedelta(days=max(days, 1) - 1)
        with self._session() as session:
            top_stmt = (
                select(
                    SearchTermDailyStatRecord.normalized_term,
                    func.sum(SearchTermDailyStatRecord.query_count).label("query_count"),
                )
                .where(SearchTermDailyStatRecord.stat_date >= cutoff_day)
                .group_by(SearchTermDailyStatRecord.normalized_term)
                .order_by(func.sum(SearchTermDailyStatRecord.query_count).desc())
                .limit(max(limit_terms, 1))
            )
            top_terms = [str(row.normalized_term) for row in session.execute(top_stmt).all()]
            if not top_terms:
                return []

            trend_stmt = (
                select(
                    SearchTermDailyStatRecord.stat_date,
                    SearchTermDailyStatRecord.normalized_term,
                    SearchTermDailyStatRecord.query_count,
                )
                .where(SearchTermDailyStatRecord.stat_date >= cutoff_day)
                .where(SearchTermDailyStatRecord.normalized_term.in_(top_terms))
                .order_by(SearchTermDailyStatRecord.stat_date.asc(), SearchTermDailyStatRecord.normalized_term.asc())
            )
            rows = session.execute(trend_stmt).all()

        return [
            {
                "stat_date": row.stat_date.isoformat(),
                "normalized_term": str(row.normalized_term),
                "query_count": int(row.query_count or 0),
            }
            for row in rows
        ]

    def list_intent_daily_trends(self, *, days: int = 30) -> list[dict[str, Any]]:
        cutoff_day = datetime.now(timezone.utc).date() - timedelta(days=max(days, 1) - 1)
        with self._session() as session:
            stmt = (
                select(
                    QueryIntentDailyStatRecord.stat_date,
                    QueryIntentDailyStatRecord.intent,
                    QueryIntentDailyStatRecord.query_count,
                )
                .where(QueryIntentDailyStatRecord.stat_date >= cutoff_day)
                .order_by(QueryIntentDailyStatRecord.stat_date.asc(), QueryIntentDailyStatRecord.intent.asc())
            )
            rows = session.execute(stmt).all()

        return [
            {
                "stat_date": row.stat_date.isoformat(),
                "intent": str(row.intent),
                "query_count": int(row.query_count or 0),
            }
            for row in rows
        ]

    def get_weekly_insights(self) -> list[dict[str, Any]]:
        today = datetime.now(timezone.utc).date()
        current_start = today - timedelta(days=6)
        previous_end = current_start - timedelta(days=1)
        previous_start = previous_end - timedelta(days=6)

        with self._session() as session:
            total_current_stmt = (
                select(func.count(ChatQueryEventRecord.id))
                .where(func.date(ChatQueryEventRecord.created_at) >= current_start)
                .where(func.date(ChatQueryEventRecord.created_at) <= today)
            )
            total_previous_stmt = (
                select(func.count(ChatQueryEventRecord.id))
                .where(func.date(ChatQueryEventRecord.created_at) >= previous_start)
                .where(func.date(ChatQueryEventRecord.created_at) <= previous_end)
            )
            total_current = int(session.scalar(total_current_stmt) or 0)
            total_previous = int(session.scalar(total_previous_stmt) or 0)

            recommend_current_stmt = (
                select(func.count(ChatQueryEventRecord.id))
                .where(func.date(ChatQueryEventRecord.created_at) >= current_start)
                .where(func.date(ChatQueryEventRecord.created_at) <= today)
                .where(ChatQueryEventRecord.had_recommendations.is_(True))
            )
            recommend_previous_stmt = (
                select(func.count(ChatQueryEventRecord.id))
                .where(func.date(ChatQueryEventRecord.created_at) >= previous_start)
                .where(func.date(ChatQueryEventRecord.created_at) <= previous_end)
                .where(ChatQueryEventRecord.had_recommendations.is_(True))
            )
            recommend_current = int(session.scalar(recommend_current_stmt) or 0)
            recommend_previous = int(session.scalar(recommend_previous_stmt) or 0)

            top_term_current_stmt = (
                select(
                    SearchTermDailyStatRecord.normalized_term,
                    func.sum(SearchTermDailyStatRecord.query_count).label("query_count"),
                )
                .where(SearchTermDailyStatRecord.stat_date >= current_start)
                .where(SearchTermDailyStatRecord.stat_date <= today)
                .group_by(SearchTermDailyStatRecord.normalized_term)
                .order_by(func.sum(SearchTermDailyStatRecord.query_count).desc())
                .limit(1)
            )
            top_term_previous_stmt = (
                select(
                    SearchTermDailyStatRecord.normalized_term,
                    func.sum(SearchTermDailyStatRecord.query_count).label("query_count"),
                )
                .where(SearchTermDailyStatRecord.stat_date >= previous_start)
                .where(SearchTermDailyStatRecord.stat_date <= previous_end)
                .group_by(SearchTermDailyStatRecord.normalized_term)
                .order_by(func.sum(SearchTermDailyStatRecord.query_count).desc())
                .limit(1)
            )
            top_term_current = session.execute(top_term_current_stmt).first()
            top_term_previous = session.execute(top_term_previous_stmt).first()

            top_intent_current_stmt = (
                select(
                    QueryIntentDailyStatRecord.intent,
                    func.sum(QueryIntentDailyStatRecord.query_count).label("query_count"),
                )
                .where(QueryIntentDailyStatRecord.stat_date >= current_start)
                .where(QueryIntentDailyStatRecord.stat_date <= today)
                .group_by(QueryIntentDailyStatRecord.intent)
                .order_by(func.sum(QueryIntentDailyStatRecord.query_count).desc())
                .limit(1)
            )
            top_intent_current = session.execute(top_intent_current_stmt).first()

        def pct_delta(current: int, previous: int) -> float | None:
            if previous <= 0:
                return None
            return round(((current - previous) / previous) * 100.0, 2)

        def direction(current: int, previous: int) -> str:
            if current > previous:
                return "up"
            if current < previous:
                return "down"
            return "flat"

        top_term_text = str(top_term_current.normalized_term) if top_term_current else "n/a"
        top_term_count = int(top_term_current.query_count or 0) if top_term_current else 0
        previous_top_term = str(top_term_previous.normalized_term) if top_term_previous else "n/a"

        insights = [
            {
                "key": "weekly_volume",
                "title": "Weekly Query Volume",
                "value": f"{total_current}",
                "delta_percent": pct_delta(total_current, total_previous),
                "direction": direction(total_current, total_previous),
                "summary": f"Current 7 days vs previous 7 days ({total_previous}).",
            },
            {
                "key": "recommendation_coverage",
                "title": "Queries With Recommendations",
                "value": f"{recommend_current}",
                "delta_percent": pct_delta(recommend_current, recommend_previous),
                "direction": direction(recommend_current, recommend_previous),
                "summary": "Tracks how often users receive product recommendations.",
            },
            {
                "key": "top_term",
                "title": "Top Weekly Search Term",
                "value": f"{top_term_text} ({top_term_count})",
                "delta_percent": None,
                "direction": "flat",
                "summary": f"Previous week top term: {previous_top_term}.",
            },
            {
                "key": "top_intent",
                "title": "Top Weekly Intent",
                "value": str(top_intent_current.intent) if top_intent_current else "unknown",
                "delta_percent": None,
                "direction": "flat",
                "summary": f"Count: {int(top_intent_current.query_count or 0) if top_intent_current else 0}.",
            },
        ]
        return insights

    def list_admin_chat_history(
        self,
        *,
        days: int = 30,
        limit: int = 100,
        offset: int = 0,
        user_id_hash: str | None = None,
    ) -> list[dict[str, Any]]:
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=max(days, 1))
        raw_limit = max(limit + offset, 1)
        raw_limit = min(raw_limit * 5, 5000)

        with self._session() as session:
            stmt = (
                select(ConversationEventRecord)
                .where(ConversationEventRecord.created_at >= cutoff_time)
                .where(ConversationEventRecord.role.in_(["user", "assistant", "system"]))
                .order_by(ConversationEventRecord.created_at.desc())
                .limit(raw_limit)
            )
            rows = list(session.scalars(stmt).all())

        normalized: list[dict[str, Any]] = []
        for row in rows:
            uid_hash = hashlib.sha256((row.user_id or "unknown").encode("utf-8")).hexdigest()[:32]
            if user_id_hash and uid_hash != user_id_hash:
                continue
            normalized.append(
                {
                    "conversation_id": row.conversation_id,
                    "user_id_hash": uid_hash,
                    "role": row.role,
                    "message": row.message,
                    "status": row.status,
                    "intent": row.intent,
                    "created_at": row.created_at.isoformat(),
                }
            )

        paged = normalized[offset : offset + max(limit, 1)]
        return paged

    def list_dashboard_chat_sessions(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> dict[str, Any]:
        from pathlib import Path
        import json
        target_limit = min(max(int(limit), 1), 500)
        target_offset = max(int(offset), 0)
        session_event_limit = DASHBOARD_SESSION_EVENT_LIMIT
        category_labels = ["Order Tracking", "Product Search", "Returns", "Policy & FAQ", "General"]
        cat_path = Path("data/categories.json")
        if cat_path.exists():
            try:
                category_labels = json.loads(cat_path.read_text("utf-8"))
            except Exception:
                pass
        apply_llm_primary = (
            settings.conversation_intent_classifier_enabled
            and not settings.conversation_intent_shadow_mode
        )

        with self._session() as session:
            # Get total number of sessions
            total_sessions_q = select(func.count(func.distinct(ConversationEventRecord.conversation_id)))
            if start_date:
                total_sessions_q = total_sessions_q.where(ConversationEventRecord.created_at >= start_date)
            if end_date:
                total_sessions_q = total_sessions_q.where(ConversationEventRecord.created_at <= end_date)
            total_sessions = session.scalar(total_sessions_q) or 0

            # Get recommendation conversions
            rec_conv_q = (
                select(func.count(func.distinct(ConversationEventRecord.conversation_id)))
                .where(
                    or_(
                        ConversationEventRecord.action == "portal_redirect",
                        ConversationEventRecord.message.ilike("%select & buy%"),
                        ConversationEventRecord.message.ilike("%select and buy%")
                    )
                )
            )
            if start_date:
                rec_conv_q = rec_conv_q.where(ConversationEventRecord.created_at >= start_date)
            if end_date:
                rec_conv_q = rec_conv_q.where(ConversationEventRecord.created_at <= end_date)
            
            recommendation_conversions = session.scalar(rec_conv_q) or 0

            # Get overall intent breakdowns
            global_intent_counts: dict[str, int] = {}
            global_intent_total = 0
            global_subcategory_counts: dict[tuple[str, str], int] = {}

            if apply_llm_primary:
                label_q = select(ConversationIntentLabelRecord, ConversationIntentOverrideRecord).outerjoin(
                    ConversationIntentOverrideRecord,
                    ConversationIntentOverrideRecord.conversation_id == ConversationIntentLabelRecord.conversation_id,
                )
                if start_date:
                    label_q = label_q.where(ConversationIntentLabelRecord.classified_at >= start_date)
                if end_date:
                    label_q = label_q.where(ConversationIntentLabelRecord.classified_at <= end_date)
                    
                label_rows = session.execute(label_q).all()
                for label_row, override_row in label_rows:
                    raw_intent = override_row.intent_label if override_row is not None else label_row.intent_label
                    display_label = str(raw_intent or "unknown").strip() or "unknown"
                    if display_label not in global_intent_counts:
                        global_intent_counts[display_label] = 0
                    global_intent_counts[display_label] += 1
                    global_intent_total += 1
                    # Track subcategories
                    subcategory = getattr(label_row, "intent_subcategory", None)
                    if subcategory:
                        subcat_display = subcategory.replace("_", " ").title()
                        sub_key = (display_label, subcat_display)
                        global_subcategory_counts[sub_key] = global_subcategory_counts.get(sub_key, 0) + 1
            else:
                global_intents_q = select(ConversationEventRecord.intent, func.count()).where(ConversationEventRecord.role == "assistant").where(ConversationEventRecord.intent.is_not(None))
                if start_date:
                    global_intents_q = global_intents_q.where(ConversationEventRecord.created_at >= start_date)
                if end_date:
                    global_intents_q = global_intents_q.where(ConversationEventRecord.created_at <= end_date)
                global_intents_q = global_intents_q.group_by(ConversationEventRecord.intent)
                
                global_intents = session.execute(global_intents_q).all()
                for db_intent, count in global_intents:
                    label = str(db_intent or "unknown").strip() or "unknown"
                    global_intent_counts[label] = global_intent_counts.get(label, 0) + count
                    global_intent_total += count

            # Add defaults if nothing exists
            if global_intent_total == 0:
                global_intent_counts["unknown"] = global_intent_counts.get("unknown", 0) + 1
                global_intent_total += 1

            # --- Daily Activity ---
            daily_activity_q = select(
                func.date(ConversationEventRecord.created_at).label("date"),
                func.count(func.distinct(ConversationEventRecord.conversation_id)).label("sessions")
            ).group_by(func.date(ConversationEventRecord.created_at))
            
            if start_date:
                daily_activity_q = daily_activity_q.where(ConversationEventRecord.created_at >= start_date)
            if end_date:
                daily_activity_q = daily_activity_q.where(ConversationEventRecord.created_at <= end_date)
            daily_activity_q = daily_activity_q.order_by(func.date(ConversationEventRecord.created_at).asc())

            daily_activity_rows = session.execute(daily_activity_q).all()
            daily_activity_list = [{"date": str(row.date), "sessions": row.sessions} for row in daily_activity_rows]


            recent_sessions_q = select(
                ConversationEventRecord.conversation_id.label("conversation_id"),
                func.max(ConversationEventRecord.created_at).label("last_activity_at"),
            ).group_by(ConversationEventRecord.conversation_id)
            
            if start_date:
                recent_sessions_q = recent_sessions_q.having(func.max(ConversationEventRecord.created_at) >= start_date)
            if end_date:
                recent_sessions_q = recent_sessions_q.having(func.max(ConversationEventRecord.created_at) <= end_date)
                
            recent_sessions_subquery = (
                recent_sessions_q.order_by(func.max(ConversationEventRecord.created_at).desc())
                .limit(target_limit)
                .offset(target_offset)
                .subquery()
            )

            session_rows = session.execute(
                select(
                    recent_sessions_subquery.c.conversation_id,
                    recent_sessions_subquery.c.last_activity_at,
                )
                .order_by(recent_sessions_subquery.c.last_activity_at.desc())
            ).all()

            if not session_rows:
                return {
                    "total_sessions": 0,
                    "sessions": [],
                    "resolution_rate": 0.0,
                    "category_divide": [
                        {"category": "Order Tracking", "count": 0, "percentage": 0.0},
                        {"category": "Product Search", "count": 0, "percentage": 0.0},
                        {"category": "Returns", "count": 0, "percentage": 0.0},
                        {"category": "Policy & FAQ", "count": 0, "percentage": 0.0},
                        {"category": "General", "count": 0, "percentage": 0.0},
                    ],
                    "intent_breakdown": [
                        {"intent": "unknown", "count": 0, "percentage": 0.0},
                    ],
                    "top_trending_terms": [],
                }

            conversation_ids = [str(row.conversation_id) for row in session_rows]
            ranked_events_subquery = (
                select(
                    ConversationEventRecord.id.label("event_id"),
                    func.row_number()
                    .over(
                        partition_by=ConversationEventRecord.conversation_id,
                        order_by=ConversationEventRecord.created_at.desc(),
                    )
                    .label("row_num"),
                )
                .where(ConversationEventRecord.conversation_id.in_(conversation_ids))
                .where(ConversationEventRecord.role.in_(["user", "assistant", "system"]))
                .subquery()
            )

            rows = list(
                session.scalars(
                    select(ConversationEventRecord)
                    .join(ranked_events_subquery, ConversationEventRecord.id == ranked_events_subquery.c.event_id)
                    .where(ranked_events_subquery.c.row_num <= session_event_limit)
                    .order_by(ConversationEventRecord.created_at.asc())
                ).all()
            )

        by_conversation: dict[str, list[ConversationEventRecord]] = {cid: [] for cid in conversation_ids}
        for row in rows:
            by_conversation.setdefault(row.conversation_id, []).append(row)

        label_map = self.list_conversation_intent_labels(conversation_ids)

        last_activity_lookup = {
            str(row.conversation_id): row.last_activity_at for row in session_rows if row.last_activity_at is not None
        }

        sessions: list[dict[str, Any]] = []
        resolved_count = 0
        category_totals: dict[str, int] = {}
        trend_counts: dict[str, int] = {}

        for conversation_id in conversation_ids:
            events = by_conversation.get(conversation_id, [])
            if not events:
                continue

            user_messages = [str(event.message or "") for event in events if event.role == "user"]
            user_id = next((str(event.user_id or "") for event in events if event.user_id), "unknown")
            user_id_hash = hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:32]

            session_intent_counts: dict[str, int] = {}
            for message in user_messages:
                trend_term = _extract_trend_term(message)
                if trend_term:
                    trend_counts[trend_term] = trend_counts.get(trend_term, 0) + 1

            for event in events:
                if event.role != "assistant":
                    continue
                label = str(event.intent or "unknown").strip() or "unknown"
                session_intent_counts[label] = session_intent_counts.get(label, 0) + 1

            label_meta = label_map.get(conversation_id)
            if label_meta is not None:
                cat = label_meta.get("intent_subcategory", "General")
                dominant_category = cat if cat else "General"
                
                # Robust normalization against predefined dynamic categories
                matched = False
                for cl in category_labels:
                    if cl.lower().strip() == dominant_category.lower().strip():
                        dominant_category = cl
                        matched = True
                        break
                if not matched:
                    for cl in category_labels:
                        if cl.lower().strip() in dominant_category.lower().strip() or dominant_category.lower().strip() in cl.lower().strip():
                            dominant_category = cl
                            matched = True
                            break
                if not matched:
                    dominant_category = category_labels[-1] if category_labels else "General"
            else:
                dominant_category = "General"
            
            category_totals[dominant_category] = category_totals.get(dominant_category, 0) + 1

            if sum(session_intent_counts.values()) == 0:
                inferred_label = "unknown"
                session_intent_counts[inferred_label] += 1

            label_meta = label_map.get(conversation_id)
            if label_meta is not None and bool(label_meta.get("is_overridden")):
                dominant_intent = str(label_meta.get("intent_display") or "unknown")
            elif apply_llm_primary and label_meta is not None:
                dominant_intent = str(label_meta.get("intent_display") or "unknown")
            else:
                dominant_intent = max(session_intent_counts.items(), key=lambda item: item[1])[0]

            is_frustrated = _is_frustrated_session(user_messages)
            is_resolved = _is_resolved_session(events)
            session_status = "Resolved" if is_resolved else "Abandoned"
            if is_resolved:
                resolved_count += 1

            started_at = events[0].created_at.isoformat()
            last_activity = last_activity_lookup.get(conversation_id)
            last_activity_at = last_activity.isoformat() if last_activity else events[-1].created_at.isoformat()

            sessions.append(
                {
                    "conversation_id": conversation_id,
                    "user_id_hash": user_id_hash,
                    "is_frustrated": is_frustrated,
                    "status": session_status,
                    "dominant_category": dominant_category,
                    "dominant_intent": dominant_intent,
                    "intent_confidence": (
                        None
                        if label_meta is None
                        or bool(label_meta.get("is_overridden"))
                        or label_meta.get("confidence") is None
                        else float(label_meta.get("confidence"))
                    ),
                    "intent_model_version": str(label_meta.get("model_version") or "") if label_meta is not None else None,
                    "intent_model_name": str(label_meta.get("model_name") or "") if label_meta is not None else None,
                    "intent_source_version": str(label_meta.get("source_version") or "") if label_meta is not None else None,
                    "intent_needs_review": bool(label_meta.get("needs_review")) if label_meta is not None else None,
                    "intent_is_overridden": bool(label_meta.get("is_overridden")) if label_meta is not None else False,
                    "intent_override_reason": str(label_meta.get("override_reason") or "") if label_meta is not None else None,
                    "intent_raw_label": str(label_meta.get("raw_intent_label") or "") if label_meta is not None else None,
                    "intent_classifier_mode": str(label_meta.get("classifier_mode") or "") if label_meta is not None else None,
                    "intent_classifier_error": str(label_meta.get("classifier_raw_error") or "") if label_meta is not None else None,
                    "intent_classifier_total_tokens": label_meta.get("classifier_total_token_count") if label_meta is not None else None,
                    "started_at": started_at,
                    "last_activity_at": last_activity_at,
                }
            )

        sessions.sort(key=lambda row: row["last_activity_at"], reverse=True)
        # Using real global count instead of just the paginated session count
        
        total_categorized_messages = sum(category_totals.values())

        category_divide = []
        for category in category_labels:
            count = category_totals.get(category, 0)
            percentage = 0.0
            if total_categorized_messages > 0:
                percentage = round((count / total_categorized_messages) * 100.0, 2)
            category_divide.append(
                {
                    "category": category,
                    "count": count,
                    "percentage": percentage,
                }
            )

        # Build dynamic top-20 intent breakdown sorted by count
        all_intents_sorted = sorted(global_intent_counts.items(), key=lambda item: item[1], reverse=True)
        # Take top 20 intents
        top_intents = all_intents_sorted[:20]

        intent_breakdown = []
        for intent, count in top_intents:
            percentage = 0.0
            if global_intent_total > 0:
                percentage = round((count / global_intent_total) * 100.0, 2)
            intent_breakdown.append(
                {
                    "intent": intent,
                    "count": count,
                    "percentage": percentage,
                }
            )

        # Build subcategory breakdown
        intent_subcategory_breakdown = []
        for (parent_intent, subcategory), sub_count in sorted(
            global_subcategory_counts.items(), key=lambda x: x[1], reverse=True
        ):
            intent_subcategory_breakdown.append(
                {
                    "parent_intent": parent_intent,
                    "subcategory": subcategory,
                    "count": sub_count,
                }
            )

        top_trending_terms = [
            {"term": term, "count": count}
            for term, count in sorted(trend_counts.items(), key=lambda item: item[1], reverse=True)[:10]
        ]

        resolution_rate = 0.0
        if len(sessions) > 0:
            resolution_rate = round((resolved_count / len(sessions)) * 100.0, 2)

        return {
            "total_sessions": total_sessions,
            "sessions": sessions,
            "resolution_rate": resolution_rate,
            "recommendation_conversions": recommendation_conversions,
            "category_divide": category_divide,
            "intent_breakdown": intent_breakdown,
            "intent_subcategory_breakdown": intent_subcategory_breakdown,
            "top_trending_terms": top_trending_terms,
            "daily_activity": daily_activity_list,
        }

    def delete_conversation(self, conversation_id: str) -> dict[str, int]:
        with self._session() as session:
            deleted_events = session.query(ConversationEventRecord).filter(
                ConversationEventRecord.conversation_id == conversation_id
            ).delete(synchronize_session=False)
            deleted_tasks = session.query(AsyncTaskRecord).filter(
                AsyncTaskRecord.conversation_id == conversation_id
            ).delete(synchronize_session=False)
            deleted_handoffs = session.query(HandoffTicketRecord).filter(
                HandoffTicketRecord.conversation_id == conversation_id
            ).delete(synchronize_session=False)
            deleted_query_events = session.query(ChatQueryEventRecord).filter(
                ChatQueryEventRecord.conversation_id == conversation_id
            ).delete(synchronize_session=False)
            deleted_labels = session.query(ConversationIntentLabelRecord).filter(
                ConversationIntentLabelRecord.conversation_id == conversation_id
            ).delete(synchronize_session=False)
            deleted_overrides = session.query(ConversationIntentOverrideRecord).filter(
                ConversationIntentOverrideRecord.conversation_id == conversation_id
            ).delete(synchronize_session=False)
            deleted_runs = session.query(ConversationIntentClassificationRunRecord).filter(
                ConversationIntentClassificationRunRecord.conversation_id == conversation_id
            ).delete(synchronize_session=False)

            session.commit()

        return {
            "conversation_events": int(deleted_events or 0),
            "async_tasks": int(deleted_tasks or 0),
            "handoff_tickets": int(deleted_handoffs or 0),
            "chat_query_events": int(deleted_query_events or 0),
            "intent_labels": int(deleted_labels or 0),
            "intent_overrides": int(deleted_overrides or 0),
            "intent_runs": int(deleted_runs or 0),
        }


    def get_chat_transcript(self, conversation_id: str) -> list[dict[str, Any]]:
        with self._session() as session:
            rows = session.scalars(
                select(ConversationEventRecord)
                .where(ConversationEventRecord.conversation_id == conversation_id)
                .where(ConversationEventRecord.role.in_(["user", "assistant", "system"]))
                .order_by(ConversationEventRecord.created_at.desc())
                .limit(DASHBOARD_TRANSCRIPT_EVENT_LIMIT)
            ).all()

        rows = list(reversed(rows))

        return [
            {
                "role": event.role,
                "message": event.message,
                "created_at": event.created_at.isoformat(),
                "intent": str(event.intent or "unknown").strip() or "unknown",
                "event_metadata": dict(event.event_metadata or {}),
            }
            for event in rows
        ]

    def list_dashboard_export_rows(self, *, limit: int = 150, offset: int = 0) -> list[dict[str, Any]]:
        snapshot = self.list_dashboard_chat_sessions(limit=limit, offset=offset)
        sessions = snapshot.get("sessions", [])
        if not sessions:
            return []

        session_lookup = {item["conversation_id"]: item for item in sessions}
        conversation_ids = list(session_lookup.keys())
        export_event_limit = DASHBOARD_EXPORT_EVENT_LIMIT

        with self._session() as session:
            ranked_events_subquery = (
                select(
                    ConversationEventRecord.id.label("event_id"),
                    func.row_number()
                    .over(
                        partition_by=ConversationEventRecord.conversation_id,
                        order_by=ConversationEventRecord.created_at.desc(),
                    )
                    .label("row_num"),
                )
                .where(ConversationEventRecord.conversation_id.in_(conversation_ids))
                .where(ConversationEventRecord.role.in_(["user", "assistant", "system"]))
                .subquery()
            )

            events = list(
                session.scalars(
                    select(ConversationEventRecord)
                    .join(ranked_events_subquery, ConversationEventRecord.id == ranked_events_subquery.c.event_id)
                    .where(ranked_events_subquery.c.row_num <= export_event_limit)
                    .order_by(ConversationEventRecord.conversation_id.asc(), ConversationEventRecord.created_at.asc())
                ).all()
            )

        rows: list[dict[str, Any]] = []
        for event in events:
            session_info = session_lookup.get(event.conversation_id)
            if not session_info:
                continue

            rows.append(
                {
                    "conversation_id": event.conversation_id,
                    "user_id_hash": session_info["user_id_hash"],
                    "session_status": session_info["status"],
                    "dominant_category": session_info["dominant_category"],
                    "dominant_intent": session_info["dominant_intent"],
                    "intent_confidence": session_info.get("intent_confidence"),
                    "intent_model_version": session_info.get("intent_model_version"),
                    "intent_raw_label": session_info.get("intent_raw_label"),
                    "intent_classifier_mode": session_info.get("intent_classifier_mode"),
                    "role": event.role,
                    "intent": str(event.intent or "unknown").strip() or "unknown",
                    "message": scrub_pii(event.message),
                    "created_at": event.created_at.isoformat(),
                }
            )

        return rows


persistence_service = PersistenceService()
