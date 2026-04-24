from __future__ import annotations

from datetime import datetime, timezone
from collections import deque
import json
import threading
from typing import Any
from uuid import uuid4

from satmi_agent.config import settings
from satmi_agent.persistence import persistence_service


class CancellationQueueService:
    def __init__(self) -> None:
        self._redis_client = None
        self._memory_queue: deque[dict[str, Any]] = deque()
        self._memory_lock = threading.Lock()
        if settings.redis_url:
            try:
                import redis

                self._redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
            except Exception:
                self._redis_client = None

    @property
    def backend(self) -> str:
        return "redis" if self._redis_client is not None else "in_memory"

    def enqueue_cancel_order(self, *, conversation_id: str, user_id: str, order_id: str, reason: str) -> dict[str, Any]:
        task_id = f"CXL-{uuid4().hex[:10].upper()}"
        payload = {
            "task_id": task_id,
            "task_type": "cancel_order",
            "conversation_id": conversation_id,
            "user_id": user_id,
            "order_id": order_id,
            "reason": reason,
            "queued_at": datetime.now(timezone.utc).isoformat(),
        }

        persistence_service.create_async_task(
            task_id=task_id,
            task_type="cancel_order",
            conversation_id=conversation_id,
            user_id=user_id,
            payload=payload,
            status="queued",
        )

        if self._redis_client is not None:
            self._redis_client.rpush(settings.cancel_queue_key, json.dumps(payload))
        else:
            with self._memory_lock:
                self._memory_queue.append(payload)

        return {
            "task_id": task_id,
            "queued": True,
            "status": "queued",
            "backend": self.backend,
            "order_id": order_id,
            "reason": reason,
        }

    def pop_next_task(self, timeout_seconds: int = 2) -> dict[str, Any] | None:
        if self._redis_client is None:
            with self._memory_lock:
                if not self._memory_queue:
                    return None
                return self._memory_queue.popleft()

        item = self._redis_client.blpop(settings.cancel_queue_key, timeout=timeout_seconds)
        if not item:
            return None

        _, payload = item
        return json.loads(payload)

    def dependency_health(self) -> dict[str, Any]:
        if self._redis_client is None:
            return {
                "configured": bool(settings.redis_url),
                "reachable": False,
                "backend": self.backend,
            }
        try:
            reachable = bool(self._redis_client.ping())
            return {
                "configured": bool(settings.redis_url),
                "reachable": reachable,
                "backend": self.backend,
            }
        except Exception:
            return {
                "configured": bool(settings.redis_url),
                "reachable": False,
                "backend": self.backend,
            }


cancellation_queue_service = CancellationQueueService()


class ConversationIntentQueueService:
    def __init__(self) -> None:
        self._redis_client = None
        self._memory_queue: deque[dict[str, Any]] = deque()
        self._memory_dead_letter: deque[dict[str, Any]] = deque()
        self._memory_lock = threading.Lock()
        if settings.redis_url:
            try:
                import redis

                self._redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
            except Exception:
                self._redis_client = None

    @property
    def backend(self) -> str:
        return "redis" if self._redis_client is not None else "in_memory"

    def enqueue_classification(
        self,
        *,
        conversation_id: str,
        user_id: str,
        force: bool = False,
        transcript_checksum: str | None = None,
    ) -> dict[str, Any]:
        task_id = f"INT-{uuid4().hex[:10].upper()}"
        payload = {
            "task_id": task_id,
            "task_type": "classify_conversation_intent",
            "conversation_id": conversation_id,
            "user_id": user_id,
            "force": bool(force),
            "transcript_checksum": transcript_checksum,
            "attempts": 0,
            "queued_at": datetime.now(timezone.utc).isoformat(),
        }

        persistence_service.create_async_task(
            task_id=task_id,
            task_type="classify_conversation_intent",
            conversation_id=conversation_id,
            user_id=user_id,
            payload=payload,
            status="queued",
        )

        if self._redis_client is not None:
            self._redis_client.rpush(settings.conversation_intent_queue_key, json.dumps(payload))
        else:
            with self._memory_lock:
                self._memory_queue.append(payload)

        return {
            "task_id": task_id,
            "queued": True,
            "status": "queued",
            "backend": self.backend,
            "conversation_id": conversation_id,
        }

    def pop_next_task(self, timeout_seconds: int = 2) -> dict[str, Any] | None:
        if self._redis_client is None:
            with self._memory_lock:
                if not self._memory_queue:
                    return None
                return self._memory_queue.popleft()

        item = self._redis_client.blpop(settings.conversation_intent_queue_key, timeout=timeout_seconds)
        if not item:
            return None

        _, payload = item
        return json.loads(payload)

    def requeue_task(self, payload: dict[str, Any]) -> None:
        if self._redis_client is not None:
            self._redis_client.rpush(settings.conversation_intent_queue_key, json.dumps(payload))
            return

        with self._memory_lock:
            self._memory_queue.append(payload)

    def push_dead_letter(self, payload: dict[str, Any]) -> None:
        if self._redis_client is not None:
            self._redis_client.rpush(settings.conversation_intent_dead_letter_key, json.dumps(payload))
            return

        with self._memory_lock:
            self._memory_dead_letter.append(payload)


conversation_intent_queue_service = ConversationIntentQueueService()