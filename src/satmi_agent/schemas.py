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
    intent: Literal["shopping", "order_tracking", "policy_brand_faq", "general", "authentication", "unknown"]
    confidence: float
    handoff_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class HandoffTicket(BaseModel):
    user_id: str
    conversation_id: str
    summary: str
    reason: str
    intent: Literal["shopping", "order_tracking", "policy_brand_faq", "general", "authentication", "unknown"]
    attempted_action: str | None = None
    tool_result: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)


HandoffStatus = Literal["open", "in_progress", "resolved"]


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
