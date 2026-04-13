from __future__ import annotations

import argparse
import time

from satmi_agent.persistence import persistence_service
from satmi_agent.queueing import cancellation_queue_service
from satmi_agent.tools import tooling_service


def process_once() -> bool:
    payload = cancellation_queue_service.pop_next_task(timeout_seconds=2)
    if payload is None:
        return False

    task_id = str(payload.get("task_id", ""))
    if not task_id:
        return False

    persistence_service.update_async_task(task_id, status="in_progress")
    try:
        result = tooling_service.process_cancel_task(payload)
        persistence_service.update_async_task(task_id, status="completed", result=result)
    except Exception as exc:
        persistence_service.update_async_task(task_id, status="failed", error=str(exc))

    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Process SATMI queued cancellation tasks")
    parser.add_argument("--once", action="store_true", help="Process a single task and exit")
    parser.add_argument("--sleep", type=float, default=1.0, help="Idle sleep seconds between queue polls")
    args = parser.parse_args()

    persistence_service.init_db()

    if args.once:
        process_once()
        return

    while True:
        processed = process_once()
        if not processed:
            time.sleep(args.sleep)


if __name__ == "__main__":
    main()