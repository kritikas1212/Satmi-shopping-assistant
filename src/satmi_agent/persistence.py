from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy import JSON, DateTime, Float, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from satmi_agent.config import settings
from satmi_agent.security import scrub_pii
from satmi_agent.schemas import HandoffStatus


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


engine = create_engine(settings.database_url, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False, future=True)


class PersistenceService:
    def init_db(self) -> None:
        Base.metadata.create_all(bind=engine)

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


persistence_service = PersistenceService()