from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import AliasChoices, BaseModel, Field


class ChatRequest(BaseModel):
    user_id: str = Field(..., description="Unique customer id")
    conversation_id: str = Field(..., description="Conversation/thread id")
    message: str = Field(default="", min_length=0)
    action: Optional[str] = None
    product_id: Optional[str] = None
    customer_name: Optional[str] = None
    shipping_address: Optional[str] = None


class ChatResponse(BaseModel):
    conversation_id: str
    status: Literal["active", "awaiting_human", "resolved"]
    response_text: str
    recommended_products: list[dict[str, Any]] = Field(default_factory=list)
    auth_required: bool = False
    intent: str
    confidence: float
    handoff_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class HandoffTicket(BaseModel):
    user_id: str
    conversation_id: str
    summary: str
    reason: str
    intent: str
    attempted_action: str | None = None
    tool_result: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)


HandoffStatus = Literal["open", "in_progress", "resolved"]


class ConversationIntentOverrideRequest(BaseModel):
    intent_label: str
    category: str


class HandoffStatusUpdateRequest(BaseModel):
    status: HandoffStatus
    note: str | None = None


class HandoffTicketResponse(BaseModel):
    handoff_id: str
    conversation_id: str
    user_id: str
    status: HandoffStatus
    reason: str
    summary: str
    intent: str
    attempted_action: str | None = None
    tool_result: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    queue: str
    eta_minutes: int
    resolution_note: str | None = None
    created_at: str
    updated_at: str
    resolved_at: str | None = None


class ConversationEventResponse(BaseModel):
    role: str
    message: str
    status: str
    intent: str | None = None
    confidence: float | None = None
    action: str | None = None
    handoff_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class ResumeHandoffRequest(BaseModel):
    agent_message: str = Field(..., min_length=1)


class AsyncTaskResponse(BaseModel):
    task_id: str
    task_type: str
    status: str
    conversation_id: str
    user_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    created_at: str
    updated_at: str
    completed_at: str | None = None


class SendOtpRequest(BaseModel):
    phone_number: str = Field(..., min_length=10, max_length=20, validation_alias=AliasChoices("phone_number", "phone"))


class SendOtpResponse(BaseModel):
    success: bool
    message: str


class VerifyOtpRequest(BaseModel):
    phone_number: str = Field(..., min_length=10, max_length=20, validation_alias=AliasChoices("phone_number", "phone"))
    otp: str = Field(..., min_length=6, max_length=6)


class VerifyOtpResponse(BaseModel):
    success: bool
    token: str | None = None
    message: str


class SearchTermCount(BaseModel):
    normalized_term: str
    query_count: int


class SearchTermTrendPoint(BaseModel):
    stat_date: str
    normalized_term: str
    query_count: int


class IntentTrendPoint(BaseModel):
    stat_date: str
    intent: str
    query_count: int


class WeeklyInsightCard(BaseModel):
    key: str
    title: str
    value: str
    delta_percent: float | None = None
    direction: Literal["up", "down", "flat"]
    summary: str


class AdminChatHistoryEvent(BaseModel):
    conversation_id: str
    user_id_hash: str
    role: str
    message: str
    status: str
    intent: str | None = None
    created_at: str
    event_metadata: dict[str, Any] | None = None


class DashboardChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    message: str
    created_at: str
    intent: str | None = None
    event_metadata: dict[str, Any] | None = None


class DashboardChatSession(BaseModel):
    conversation_id: str
    user_id_hash: str
    is_frustrated: bool
    status: Literal["Resolved", "Abandoned"]
    dominant_category: str
    dominant_intent: str
    intent_confidence: float | None = None
    intent_model_name: str | None = None
    intent_model_version: str | None = None
    intent_source_version: str | None = None
    intent_needs_review: bool | None = None
    intent_is_overridden: bool = False
    intent_override_reason: str | None = None
    intent_raw_label: str | None = None
    intent_classifier_mode: str | None = None
    intent_classifier_error: str | None = None
    intent_classifier_total_tokens: int | None = None
    started_at: str
    last_activity_at: str


class ChatTranscriptResponse(BaseModel):
    conversation_id: str
    transcript: list[DashboardChatMessage] = Field(default_factory=list)


class DashboardCategorySlice(BaseModel):
    category: str
    count: int
    percentage: float


class DashboardIntentSlice(BaseModel):
    intent: str
    count: int
    percentage: float


class DashboardTopTrend(BaseModel):
    term: str
    count: int


class DashboardIntentSubcategorySlice(BaseModel):
    parent_intent: str
    subcategory: str
    count: int


class DashboardDailyActivity(BaseModel):
    date: str
    sessions: int


class DashboardAnalyticsSummary(BaseModel):
    resolution_rate: float
    recommendation_conversions: int = 0
    category_divide: list[DashboardCategorySlice] = Field(default_factory=list)
    intent_breakdown: list[DashboardIntentSlice] = Field(default_factory=list)
    intent_subcategory_breakdown: list[DashboardIntentSubcategorySlice] = Field(default_factory=list)
    top_trending_terms: list[DashboardTopTrend] = Field(default_factory=list)
    daily_activity: list[DashboardDailyActivity] = Field(default_factory=list)


class DashboardSnapshotResponse(BaseModel):
    total_sessions: int = 0
    chats: list[DashboardChatSession] = Field(default_factory=list)
    analytics: DashboardAnalyticsSummary


class DashboardExportRow(BaseModel):
    conversation_id: str
    user_id_hash: str
    session_status: str
    dominant_category: str
    dominant_intent: str
    role: str
    intent: str | None = None
    intent_confidence: float | None = None
    intent_model_version: str | None = None
    intent_raw_label: str | None = None
    intent_classifier_mode: str | None = None
    message: str
    created_at: str


class ConversationIntentOverrideRequest(BaseModel):
    intent_label: str = Field(..., min_length=3, max_length=64)
    override_reason: str = Field(..., min_length=3, max_length=500)
    overridden_by: str | None = Field(default="admin", max_length=128)

class AdminCommentRequest(BaseModel):
    message: str = Field(..., min_length=1)
