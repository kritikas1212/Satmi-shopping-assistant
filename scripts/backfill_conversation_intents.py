from __future__ import annotations

import argparse

from satmi_agent.config import settings
from satmi_agent.persistence import persistence_service
from satmi_agent.queueing import conversation_intent_queue_service


def enqueue_backfill_batch(*, limit: int, inactive_minutes: int) -> int:
    candidates = persistence_service.list_inactive_conversations_needing_intent_classification(
        inactive_minutes=inactive_minutes,
        limit=limit,
    )

    queued = 0
    for item in candidates:
        conversation_intent_queue_service.enqueue_classification(
            conversation_id=str(item.get("conversation_id") or ""),
            user_id=str(item.get("user_id") or "unknown"),
            force=False,
            transcript_checksum=str(item.get("transcript_checksum") or ""),
        )
        queued += 1

    return queued


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill conversation-level intent classifications")
    parser.add_argument("--limit", type=int, default=settings.conversation_intent_backfill_batch_size)
    parser.add_argument("--inactive-minutes", type=int, default=settings.conversation_intent_inactive_minutes)
    args = parser.parse_args()

    persistence_service.init_db()
    queued = enqueue_backfill_batch(limit=max(args.limit, 1), inactive_minutes=max(args.inactive_minutes, 1))
    print(f"Queued {queued} conversation intent classification tasks")


if __name__ == "__main__":
    main()
