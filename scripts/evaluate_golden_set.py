from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from satmi_agent.main import app
from satmi_agent.persistence import persistence_service


def evaluate_case(client: TestClient, case: dict) -> tuple[bool, str]:
    payload = {
        "user_id": "eval-user",
        "conversation_id": f"eval-{case['id']}",
        "message": case["message"],
    }

    response = client.post("/chat", json=payload)
    if response.status_code != 200:
        return False, f"HTTP {response.status_code}"

    body = response.json()

    expected_status = case.get("expected_status")
    if expected_status and body.get("status") != expected_status:
        return False, f"expected status={expected_status}, got={body.get('status')}"

    expected_intent = case.get("expected_intent")
    if expected_intent and body.get("intent") != expected_intent:
        return False, f"expected intent={expected_intent}, got={body.get('intent')}"

    for snippet in case.get("must_include", []):
        if snippet.lower() not in body.get("response", "").lower():
            return False, f"response missing snippet: {snippet}"

    return True, "ok"


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate chatbot against golden query dataset")
    parser.add_argument(
        "--dataset",
        default=str(ROOT / "evaluations" / "golden_queries.json"),
        help="Path to golden query JSON file",
    )
    parser.add_argument("--min-pass-rate", type=float, default=0.8, help="Minimum acceptable pass rate")
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        print(f"Golden set file not found: {dataset_path}")
        return 1

    cases = json.loads(dataset_path.read_text(encoding="utf-8"))
    persistence_service.init_db()
    passed = 0

    with TestClient(app) as client:
        for case in cases:
            ok, reason = evaluate_case(client, case)
            status = "PASS" if ok else "FAIL"
            print(f"[{status}] {case['id']}: {reason}")
            if ok:
                passed += 1

    total = len(cases)
    pass_rate = (passed / total) if total else 0.0
    print(f"\nSummary: {passed}/{total} passed ({pass_rate:.1%})")

    if pass_rate < args.min_pass_rate:
        print(f"Pass rate below threshold {args.min_pass_rate:.1%}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
