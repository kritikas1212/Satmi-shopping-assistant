from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import re
from typing import Any, Literal

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, Integer, String, Text, create_engine, func, select
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


def _normalize_database_url(url: str) -> str:
    normalized = (url or "").strip()
    if normalized.startswith("postgres://"):
        normalized = "postgresql://" + normalized[len("postgres://"):]
    if normalized.startswith("postgresql://") and "+" not in normalized.split("://", 1)[0]:
        normalized = "postgresql+psycopg://" + normalized[len("postgresql://"):]
    return normalized


engine = create_engine(_normalize_database_url(settings.database_url), future=True)
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


def _intent_to_label(intent: str | None) -> str:
    mapping = {
        "shopping": "Product Discovery",
        "order_tracking": "Order Tracking",
        "policy_brand_faq": "Policy & FAQ",
        "authentication": "Account & Login",
        "general": "General Inquiry",
        "unknown": "General Inquiry",
    }
    return mapping[_normalize_intent(intent)]


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

    def list_dashboard_chat_sessions(self, *, limit: int = 150, offset: int = 0) -> dict[str, Any]:
        target_limit = max(min(limit, 150), 1)
        target_offset = max(offset, 0)
        session_event_limit = DASHBOARD_SESSION_EVENT_LIMIT
        category_labels = ["Order Tracking", "Product Search", "Returns", "Policy & FAQ", "General"]
        intent_labels = ["Product Discovery", "Order Tracking", "Policy & FAQ", "Account & Login", "General Inquiry"]

        with self._session() as session:
            # Get total number of sessions
            total_sessions = session.scalar(
                select(func.count(func.distinct(ConversationEventRecord.conversation_id)))
            ) or 0

            # Get overall intent breakdowns
            global_intents = session.execute(
                select(ConversationEventRecord.intent, func.count())
                .where(ConversationEventRecord.role == "assistant")
                .where(ConversationEventRecord.intent.is_not(None))
                .group_by(ConversationEventRecord.intent)
            ).all()

            global_intent_counts = {label: 0 for label in intent_labels}
            global_intent_total = 0
            for db_intent, count in global_intents:
                label = _intent_to_label(db_intent)
                global_intent_counts[label] += count
                global_intent_total += count

            # Add defaults if nothing exists
            if global_intent_total == 0:
                global_intent_counts["General Inquiry"] += 1
                global_intent_total += 1

            recent_sessions_subquery = (
                select(
                    ConversationEventRecord.conversation_id.label("conversation_id"),
                    func.max(ConversationEventRecord.created_at).label("last_activity_at"),
                )
                .group_by(ConversationEventRecord.conversation_id)
                .order_by(func.max(ConversationEventRecord.created_at).desc())
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
                        {"intent": "Product Discovery", "count": 0, "percentage": 0.0},
                        {"intent": "Order Tracking", "count": 0, "percentage": 0.0},
                        {"intent": "Policy & FAQ", "count": 0, "percentage": 0.0},
                        {"intent": "Account & Login", "count": 0, "percentage": 0.0},
                        {"intent": "General Inquiry", "count": 0, "percentage": 0.0},
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

        last_activity_lookup = {
            str(row.conversation_id): row.last_activity_at for row in session_rows if row.last_activity_at is not None
        }

        sessions: list[dict[str, Any]] = []
        resolved_count = 0
        category_totals = {
            "Order Tracking": 0,
            "Product Search": 0,
            "Returns": 0,
            "Policy & FAQ": 0,
            "General": 0,
        }
        intent_totals = {label: 0 for label in intent_labels}
        trend_counts: dict[str, int] = {}

        for conversation_id in conversation_ids:
            events = by_conversation.get(conversation_id, [])
            if not events:
                continue

            user_messages = [str(event.message or "") for event in events if event.role == "user"]
            user_id = next((str(event.user_id or "") for event in events if event.user_id), "unknown")
            user_id_hash = hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:32]

            category_counts = {
                "Order Tracking": 0,
                "Product Search": 0,
                "Returns": 0,
                "Policy & FAQ": 0,
                "General": 0,
            }
            session_intent_counts = {label: 0 for label in intent_labels}
            for message in user_messages:
                category = _classify_message_category(message)
                category_counts[category] += 1
                category_totals[category] += 1

                trend_term = _extract_trend_term(message)
                if trend_term:
                    trend_counts[trend_term] = trend_counts.get(trend_term, 0) + 1

            for event in events:
                if event.role != "assistant":
                    continue
                label = _intent_to_label(event.intent)
                session_intent_counts[label] += 1
                intent_totals[label] += 1

            dominant_category = max(category_counts.items(), key=lambda item: item[1])[0]
            if all(count == 0 for count in category_counts.values()):
                dominant_category = "General"

            if sum(session_intent_counts.values()) == 0:
                inferred_label = _intent_to_label(
                    "policy_brand_faq"
                    if dominant_category == "Policy & FAQ"
                    else "shopping"
                    if dominant_category == "Product Search"
                    else "order_tracking"
                    if dominant_category == "Order Tracking"
                    else "general"
                )
                session_intent_counts[inferred_label] += 1
                intent_totals[inferred_label] += 1

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
                    "started_at": started_at,
                    "last_activity_at": last_activity_at,
                }
            )

        sessions.sort(key=lambda row: row["last_activity_at"], reverse=True)
        # Using real global count instead of just the paginated session count
        
        total_categorized_messages = sum(category_totals.values())

        category_divide = []
        for category in category_labels:
            count = category_totals[category]
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

        intent_breakdown = []
        for intent in intent_labels:
            count = global_intent_counts[intent]
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
            "category_divide": category_divide,
            "intent_breakdown": intent_breakdown,
            "top_trending_terms": top_trending_terms,
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
                "intent": _intent_to_label(event.intent) if event.intent else None,
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
                    "role": event.role,
                    "intent": _intent_to_label(event.intent) if event.intent else None,
                    "message": scrub_pii(event.message),
                    "created_at": event.created_at.isoformat(),
                }
            )

        return rows


persistence_service = PersistenceService()
