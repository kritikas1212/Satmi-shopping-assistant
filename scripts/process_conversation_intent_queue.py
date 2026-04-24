from __future__ import annotations

import argparse
import time
from typing import Any

from satmi_agent.config import settings
from satmi_agent.llm import classify_batch_conversation_intents_with_llm
from satmi_agent.conversation_intent_classifier import classify_conversation_intent
from satmi_agent.persistence import persistence_service
from satmi_agent.queueing import conversation_intent_queue_service

class TokenBucket:
    def __init__(self, capacity: int, fill_rate_per_sec: float):
        self.capacity = capacity
        self.fill_rate = fill_rate_per_sec
        self.tokens = float(capacity)
        self.last_fill = time.time()

    def consume(self, tokens: int = 1) -> bool:
        now = time.time()
        self.tokens += (now - self.last_fill) * self.fill_rate
        self.tokens = min(self.capacity, self.tokens)
        self.last_fill = now

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

def process_batch(max_batch_size: int = 5) -> int:
    tasks: list[dict[str, Any]] = []
    
    # Try to build a batch
    first_task = conversation_intent_queue_service.pop_next_task(timeout_seconds=2)
    if first_task:
        tasks.append(first_task)
        # Aggressively pop more without waiting if they are queued
        while len(tasks) < max_batch_size:
            next_task = conversation_intent_queue_service.pop_next_task(timeout_seconds=0)
            if not next_task:
                break
            tasks.append(next_task)
            
    if not tasks:
        return 0

    if settings.conversation_intent_raw_mode:
        processed = 0
        for payload in tasks:
            task_id = str(payload.get("task_id", "")).strip()
            conversation_id = str(payload.get("conversation_id", "")).strip()
            if not task_id or not conversation_id:
                continue

            persistence_service.update_async_task(task_id, status="in_progress")
            try:
                classify_conversation_intent(conversation_id=conversation_id, force=bool(payload.get("force", False)))
                persistence_service.update_async_task(task_id, status="completed", result={"classified": True, "mode": "raw_single"})
                processed += 1
            except Exception as exc:
                attempts = int(payload.get("attempts", 0)) + 1
                payload["attempts"] = attempts
                payload["last_error"] = str(exc)
                if attempts <= max(0, int(settings.conversation_intent_max_retries)):
                    conversation_intent_queue_service.requeue_task(payload)
                    persistence_service.update_async_task(
                        task_id,
                        status="queued",
                        result={"retry_scheduled": True, "attempts": attempts},
                        error=str(exc),
                    )
                else:
                    conversation_intent_queue_service.push_dead_letter(payload)
                    persistence_service.update_async_task(task_id, status="failed", error=str(exc))
        return processed

    batch_transcripts: dict[str, list[dict[str, str]]] = {}
    task_map: dict[str, dict[str, Any]] = {}
    
    for payload in tasks:
        task_id = str(payload.get("task_id", "")).strip()
        conversation_id = str(payload.get("conversation_id", "")).strip()
        if not task_id or not conversation_id:
            continue
            
        persistence_service.update_async_task(task_id, status="in_progress")
        task_map[conversation_id] = payload
        
        # Check cache first for each item to avoid sending to LLM if unnecessary
        events = persistence_service.list_conversation_events_for_classification(conversation_id)
        checksum = persistence_service.compute_transcript_checksum(conversation_id)
        cached = persistence_service.get_cached_intent_by_checksum(checksum)
        
        if cached and not bool(payload.get("force", False)):
            # We can resolve this instantly via cache
            print(f"Task {task_id} (conv {conversation_id}): Semantic cache hit.")
            classify_conversation_intent(conversation_id=conversation_id, force=False)
            persistence_service.update_async_task(task_id, status="completed", result={"classified": True, "mode": "cache"})
            del task_map[conversation_id] # Remove from LLM batch
        else:
            # Prepare for LLM batch
            transcript = []
            for event in events:
                role = str(getattr(event, "role", "")).strip().lower()
                content = str(getattr(event, "message", "") or "")
                if role in {"user", "assistant", "system"}:
                    transcript.append({"role": role, "content": content})
            batch_transcripts[conversation_id] = transcript

    if not batch_transcripts:
        return len(tasks) # All were handled by cache

    print(f"Sending LLM batch of {len(batch_transcripts)} conversations...")
    try:
        results = classify_batch_conversation_intents_with_llm(
            batch=batch_transcripts,
            source_version=settings.conversation_intent_source_version,
        )
        
        for conversation_id, payload in task_map.items():
            task_id = payload["task_id"]
            if conversation_id in results:
                # Successfully classified in batch, persist it
                label_payload = results[conversation_id]
                checksum = persistence_service.compute_transcript_checksum(conversation_id)
                persistence_service.upsert_conversation_intent_label(
                    conversation_id=conversation_id,
                    intent_label=str(label_payload.get("intent_label") or "unknown"),
                    confidence=float(label_payload.get("confidence") or 0.0),
                    rationale_short=str(label_payload.get("rationale_short") or ""),
                    model_name=str(label_payload.get("model_name") or ""),
                    model_version=str(label_payload.get("model_version") or ""),
                    source_version=str(label_payload.get("source_version") or ""),
                    needs_review=bool(label_payload.get("needs_review", False)),
                    transcript_checksum=checksum,
                    intent_subcategory=str(label_payload.get("intent_subcategory") or ""),
                )
                persistence_service.create_conversation_intent_classification_run(
                    conversation_id=conversation_id,
                    intent_label=str(label_payload.get("intent_label") or "unknown"),
                    raw_intent_label=str(label_payload.get("raw_intent_label") or ""),
                    classifier_mode=str(label_payload.get("classifier_mode") or "guardrailed_batch"),
                    confidence=float(label_payload.get("confidence") or 0.0),
                    rationale_short=str(label_payload.get("rationale_short") or ""),
                    model_name=str(label_payload.get("model_name") or ""),
                    model_version=str(label_payload.get("model_version") or ""),
                    source_version=str(label_payload.get("source_version") or ""),
                    raw_output=str(label_payload.get("raw_output") or ""),
                    raw_error=str(label_payload.get("raw_error") or ""),
                    prompt_token_count=label_payload.get("prompt_token_count"),
                    completion_token_count=label_payload.get("completion_token_count"),
                    total_token_count=label_payload.get("total_token_count"),
                    prompt_char_count=label_payload.get("prompt_char_count"),
                    transcript_checksum=checksum,
                )
                persistence_service.update_async_task(task_id, status="completed", result={"classified": True, "mode": "batch"})
                print(f"Successfully processed task {task_id}.")
            else:
                # Fallback to single processing if batch failed for this specific ID
                print(f"Task {task_id} missing from batch result. Falling back to single processing...")
                classify_conversation_intent(conversation_id=conversation_id, force=True)
                persistence_service.update_async_task(task_id, status="completed", result={"classified": True, "mode": "single_fallback"})
                
    except Exception as exc:
        print(f"Batch LLM processing failed: {exc}")
        for payload in task_map.values():
            task_id = payload["task_id"]
            attempts = int(payload.get("attempts", 0)) + 1
            payload["attempts"] = attempts
            payload["last_error"] = str(exc)

            if attempts <= max(0, int(settings.conversation_intent_max_retries)):
                conversation_intent_queue_service.requeue_task(payload)
                persistence_service.update_async_task(
                    task_id,
                    status="queued",
                    result={"retry_scheduled": True, "attempts": attempts},
                    error=str(exc),
                )
            else:
                conversation_intent_queue_service.push_dead_letter(payload)
                persistence_service.update_async_task(task_id, status="failed", error=str(exc))

    return len(tasks)


def main() -> None:
    parser = argparse.ArgumentParser(description="Process SATMI queued conversation intent classification tasks")
    parser.add_argument("--once", action="store_true", help="Process a single task and exit")
    parser.add_argument("--sleep", type=float, default=1.0, help="Idle sleep seconds between queue polls")
    args = parser.parse_args()

    persistence_service.init_db()

    if args.once:
        print("Processing a single batch...")
        process_batch()
        print("Done.")
        return

    # 15 RPM = 15 requests per 60 seconds = 0.25 requests per second fill rate.
    bucket = TokenBucket(capacity=15, fill_rate_per_sec=15.0 / 60.0)
    
    print(f"Started intent queue worker with Micro-Batching and Token-Bucket Rate Limiting. Polling every {args.sleep}s...")
    while True:
        # Check bucket token levels before popping to proactively prevent HTTP 429
        if bucket.tokens < 2.0:
            print(f"Token bucket near empty ({bucket.tokens:.1f} tokens). Proactively sleeping for 5s to replenish...")
            time.sleep(5.0)
            continue
            
        processed_count = process_batch(max_batch_size=5)
        if processed_count > 0:
            bucket.consume(1) # We consumed 1 LLM request token for the batch
        else:
            time.sleep(args.sleep)

if __name__ == "__main__":
    main()
