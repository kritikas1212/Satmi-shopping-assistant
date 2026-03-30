from __future__ import annotations

import argparse
import concurrent.futures
import statistics
import time

import httpx


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simple concurrent smoke load test for /chat endpoint")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Base API URL")
    parser.add_argument("--requests", type=int, default=50, help="Total number of requests")
    parser.add_argument("--concurrency", type=int, default=10, help="Number of concurrent workers")
    parser.add_argument("--timeout", type=float, default=10.0, help="Request timeout in seconds")
    parser.add_argument("--api-key", default="", help="Optional X-API-Key header value")
    parser.add_argument("--message", default="track my order", help="Message payload sent to /chat")
    return parser.parse_args()


def run_single_request(base_url: str, timeout: float, index: int, message: str, api_key: str) -> tuple[int, float]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key

    payload = {
        "user_id": f"load-user-{index % 5}",
        "conversation_id": f"load-thread-{index}",
        "message": message,
    }

    start = time.perf_counter()
    with httpx.Client(timeout=timeout) as client:
        response = client.post(f"{base_url}/chat", headers=headers, json=payload)
    elapsed_ms = (time.perf_counter() - start) * 1000
    return response.status_code, elapsed_ms


def main() -> int:
    args = parse_args()

    latencies: list[float] = []
    status_counts: dict[int, int] = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [
            executor.submit(
                run_single_request,
                args.base_url,
                args.timeout,
                index,
                args.message,
                args.api_key,
            )
            for index in range(args.requests)
        ]

        for future in concurrent.futures.as_completed(futures):
            status_code, latency_ms = future.result()
            latencies.append(latency_ms)
            status_counts[status_code] = status_counts.get(status_code, 0) + 1

    success = sum(count for status, count in status_counts.items() if 200 <= status < 300)
    fail = args.requests - success
    p95 = statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else max(latencies, default=0.0)

    print("Load Test Summary")
    print(f"- Total requests: {args.requests}")
    print(f"- Concurrency: {args.concurrency}")
    print(f"- Success (2xx): {success}")
    print(f"- Failed: {fail}")
    print(f"- Mean latency: {statistics.mean(latencies) if latencies else 0.0:.2f} ms")
    print(f"- P95 latency: {p95:.2f} ms")
    print(f"- Status counts: {status_counts}")

    return 0 if success == args.requests else 1


if __name__ == "__main__":
    raise SystemExit(main())
