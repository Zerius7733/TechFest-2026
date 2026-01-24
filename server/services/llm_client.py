import os
import json
import requests
from typing import Any, Dict


class LLMError(RuntimeError):
    pass


def chat_json(system_prompt: str, user_prompt: str) -> Dict[str, Any]:
    base_url = os.getenv("LLM_BASE_URL", "").rstrip("/")
    api_key = os.getenv("LLM_API_KEY", "")
    model = os.getenv("LLM_MODEL", "")

    if not base_url or not api_key or not model:
        raise LLMError("Missing LLM_BASE_URL / LLM_API_KEY / LLM_MODEL in environment.")

    url = f"{base_url}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {"type": "json_object"},
    }

    try:
        r = requests.post(url, headers=headers, json=payload, timeout=60)
    except requests.RequestException as e:
        raise LLMError(f"LLM request failed: {e}") from e

    if r.status_code >= 400:
        raise LLMError(f"LLM HTTP {r.status_code}: {r.text[:800]}")

    data = r.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except Exception as e:
        raise LLMError(f"Unexpected LLM response shape: {json.dumps(data)[:800]}") from e

    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        raise LLMError(f"LLM did not return valid JSON. Raw: {content[:800]}") from e
