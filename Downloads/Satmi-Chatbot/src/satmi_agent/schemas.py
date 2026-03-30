from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    user_id: str = Field(..., description="Unique customer id")
    conversation_id: str = Field(..., description="Conversation/thread id")
    message: str = Field(..., min_length=1)


class ChatResponse(BaseModel):
    conversation_id: str
    status: Literal["active", "awaiting_human", "resolved"]
    response: str
    intent: Literal["support", "shopping", "mixed", "unknown"]
    confidence: float
    handoff_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class HandoffTicket(BaseModel):
    user_id: str
    conversation_id: str
    summary: str
    reason: str
    intent: Literal["support", "shopping", "mixed", "unknown"]
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
