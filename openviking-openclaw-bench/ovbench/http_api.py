from __future__ import annotations

import json
import time
from typing import Any

import requests


class OpenClawAPIError(RuntimeError):
    """Raised when the gateway call fails."""


DEFAULT_USAGE = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}


def extract_response_text(response_json: dict[str, Any]) -> str:
    try:
        for item in response_json.get("output", []):
            if item.get("type") == "message":
                for content in item.get("content", []):
                    if content.get("type") == "output_text":
                        return str(content.get("text", ""))
        for item in response_json.get("output", []):
            if "text" in item:
                return str(item["text"])
            for content in item.get("content", []):
                if "text" in content:
                    return str(content["text"])
    except Exception:
        pass
    return f"[ERROR: could not extract text from response: {json.dumps(response_json, ensure_ascii=False)}]"


def send_response(
    *,
    base_url: str,
    token: str,
    user: str,
    message: str,
    timeout: int = 300,
    retries: int = 2,
    sleep_seconds: float = 1.0,
) -> tuple[str, dict[str, int], dict[str, Any]]:
    url = f"{base_url.rstrip('/')}/v1/responses"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "openclaw",
        "input": message,
        "stream": False,
        "user": user,
    }
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=timeout)
            response.raise_for_status()
            body = response.json()
            usage = body.get("usage", DEFAULT_USAGE)
            normalized = {
                "input_tokens": int(usage.get("input_tokens", 0)),
                "output_tokens": int(usage.get("output_tokens", 0)),
                "total_tokens": int(usage.get("total_tokens", 0)),
            }
            return extract_response_text(body), normalized, body
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(sleep_seconds)
    raise OpenClawAPIError(str(last_error))
