from __future__ import annotations

from typing import Any, Literal, TypedDict


Intent = Literal["support", "shopping", "mixed", "unknown"]
Status = Literal["active", "awaiting_human", "resolved"]


class AgentState(TypedDict, total=False):
    user_id: str
    message: str
    conversation_id: str
    intent: Intent
    confidence: float
    requested_human: bool
    out_of_scope: bool
    highly_frustrated: bool
    status: Status
    action: str
    policy_ok: bool
    tool_result: dict[str, Any]
    errors: list[str]
    response: str
    handoff_id: str
    handoff_reason: str
    audit_log: list[dict[str, Any]]
    internal_logs: list[dict[str, Any]]
    message_history: list[dict[str, str]]
    guardrail_issues: list[str]
    requires_manual_review: bool
    policy_context: list[dict[str, str]]
    grounded: bool
    async_task_id: str
    async_task_status: str
    resumed_by_human: bool
    human_resolution_message: str
    user_authenticated: bool
    authenticated_user: dict[str, Any]
    order_context: list[dict[str, Any]]
