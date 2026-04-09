#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv


def fail(message: str, exit_code: int = 1) -> None:
    print("\n" + "=" * 72)
    print("GEMINI DIAGNOSTIC ERROR")
    print("=" * 72)
    print(message)
    print("=" * 72 + "\n")
    raise SystemExit(exit_code)


def main() -> None:
    repo_root = Path(__file__).resolve().parent
    env_path = repo_root / ".env"

    load_dotenv(dotenv_path=env_path)

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model_name = os.getenv("MODEL_NAME", "").strip()

    if not api_key:
        fail(
            "GEMINI_API_KEY is missing. Add it to your .env file, for example:\n"
            "GEMINI_API_KEY=your_key_here"
        )

    if not model_name:
        model_name = "gemini-1.5-flash"
        print("[warn] MODEL_NAME not set. Falling back to: gemini-1.5-flash")

    endpoint = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
        f"?key={api_key}"
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": "Reply with exactly: Hello World"
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 32,
        },
    }

    print(f"[info] Testing model: {model_name}")
    print(f"[info] Endpoint: https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent")

    try:
        response = requests.post(endpoint, json=payload, timeout=30)
        response.raise_for_status()
    except requests.exceptions.HTTPError:
        status_code = response.status_code if 'response' in locals() and response is not None else "unknown"
        raw_error = response.text if 'response' in locals() and response is not None else "<no response body>"

        print("\n" + "=" * 72)
        print("GEMINI HTTP ERROR")
        print("=" * 72)
        print(f"Status Code: {status_code}")
        print("Raw Error Body:")
        print(raw_error)
        print("=" * 72 + "\n")
        raise SystemExit(2)
    except requests.exceptions.RequestException as exc:
        fail(f"Network/request failure while calling Gemini: {exc}", exit_code=3)

    try:
        data = response.json()
    except json.JSONDecodeError:
        fail(f"Gemini returned non-JSON response:\n{response.text}", exit_code=4)

    candidates = data.get("candidates", [])
    if not candidates:
        print("\n" + "=" * 72)
        print("GEMINI RESPONSE ISSUE")
        print("=" * 72)
        print("Request succeeded but no candidates were returned.")
        print("Raw JSON:")
        print(json.dumps(data, indent=2, ensure_ascii=False))
        print("=" * 72 + "\n")
        raise SystemExit(5)

    parts = candidates[0].get("content", {}).get("parts", [])
    text = ""
    if parts:
        text = str(parts[0].get("text", "")).strip()

    if not text:
        print("\n" + "=" * 72)
        print("GEMINI RESPONSE ISSUE")
        print("=" * 72)
        print("Request succeeded but response text was empty.")
        print("Raw JSON:")
        print(json.dumps(data, indent=2, ensure_ascii=False))
        print("=" * 72 + "\n")
        raise SystemExit(6)

    print("\n" + "=" * 72)
    print("GEMINI TEST SUCCESS")
    print("=" * 72)
    print("AI Response:")
    print(text)
    print("=" * 72 + "\n")


if __name__ == "__main__":
    main()
