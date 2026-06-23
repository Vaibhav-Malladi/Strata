from __future__ import annotations

from collections.abc import Mapping
import re
from urllib.parse import urlsplit


_ALLOWED_SCHEMES = {"http", "https"}
_SYSTEM_PROMPT = "Return only a unified diff patch. No prose, no markdown wrappers."
_DEFAULT_MODEL_PLACEHOLDER = "strata-configured-model"
_DEFAULT_PROMPT_PLACEHOLDER = "[prompt text from .aidc/agent_prompt.md]"
_RESPONSE_TEXT_PATH = "choices[0].message.content"


def normalize_base_url(base_url: str) -> str:
    if base_url is None or not isinstance(base_url, str):
        raise ValueError("base_url must be a non-empty string")

    normalized = base_url.strip().rstrip("/")
    if not normalized:
        raise ValueError("base_url must be a non-empty string")

    parsed = urlsplit(normalized)
    if parsed.scheme and parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise ValueError(f"Unsupported base_url scheme: {parsed.scheme}")

    return normalized


def build_openai_compatible_url(base_url: str) -> str:
    normalized_base_url = normalize_base_url(base_url)

    if normalized_base_url.endswith("/chat/completions"):
        return normalized_base_url

    if normalized_base_url.endswith("/v1"):
        return f"{normalized_base_url}/chat/completions"

    return f"{normalized_base_url}/v1/chat/completions"


def build_openai_compatible_payload(prompt_text: str, model: str | None = None) -> dict:
    resolved_model = model if isinstance(model, str) and model else _DEFAULT_MODEL_PLACEHOLDER
    resolved_prompt_text = "" if prompt_text is None else str(prompt_text)

    return {
        "model": resolved_model,
        "messages": [
            {
                "role": "system",
                "content": _SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": resolved_prompt_text,
            },
        ],
        "temperature": 0,
    }


def extract_text_from_openai_compatible_response(response_json: dict) -> dict:
    if not isinstance(response_json, Mapping):
        return _invalid_response("Response JSON must be a mapping.")

    choices = response_json.get("choices")
    if not isinstance(choices, list) or not choices:
        return _invalid_response("Response JSON is missing choices[0].")

    first_choice = choices[0]
    if not isinstance(first_choice, Mapping):
        return _invalid_response("Response JSON is missing choices[0].message.content.")

    message = first_choice.get("message")
    if not isinstance(message, Mapping):
        return _invalid_response("Response JSON is missing choices[0].message.content.")

    if "content" not in message:
        return _invalid_response("Response JSON is missing choices[0].message.content.")

    content = message.get("content")
    text = _coerce_content_to_text(content)
    if text == "":
        return _invalid_response("Response JSON is missing choices[0].message.content.")

    return {
        "status": "ok",
        "text": text,
        "errors": [],
        "message": "Response text extracted.",
    }


def extract_patch_from_text(text: str) -> dict:
    if not isinstance(text, str):
        raise ValueError("text must be a string")

    normalized_text = text.replace("\r\n", "\n").replace("\r", "\n")
    fenced_patch = _extract_fenced_diff_block(normalized_text)
    if fenced_patch is not None:
        patch_text = fenced_patch
    else:
        patch_text = _extract_diff_like_text(normalized_text)

    if not patch_text:
        return {
            "status": "invalid_response",
            "patch": "",
            "errors": ["Unified diff patch was not found in the provided text."],
            "message": "Unified diff patch was not found in the provided text.",
        }

    return {
        "status": "ok",
        "patch": patch_text,
        "errors": [],
        "message": "Unified diff patch extracted.",
    }


def build_http_contract_summary(config: dict, prompt_exists: bool = False) -> dict:
    config_mapping = config if isinstance(config, Mapping) else {}
    errors: list[str] = []

    base_url_value = config_mapping.get("base_url")
    model_value = config_mapping.get("model")
    api_key_env_value = config_mapping.get("api_key_env")
    timeout_value = config_mapping.get("http_timeout_seconds")
    adapter_value = config_mapping.get("adapter")

    base_url = None
    request_url = None

    if isinstance(base_url_value, str) and base_url_value.strip():
        try:
            base_url = normalize_base_url(base_url_value)
            request_url = build_openai_compatible_url(base_url)
        except ValueError as error:
            errors.append(str(error))
    else:
        errors.append("base_url is required for HTTP adapters.")

    model = model_value if isinstance(model_value, str) and model_value else _DEFAULT_MODEL_PLACEHOLDER
    api_key_env = api_key_env_value if isinstance(api_key_env_value, str) and api_key_env_value else None
    http_timeout_seconds = timeout_value if type(timeout_value) is int and timeout_value > 0 else None
    prompt_exists_flag = bool(prompt_exists)

    payload = build_openai_compatible_payload(_DEFAULT_PROMPT_PLACEHOLDER, model=model)

    status = "ok" if request_url else "not_ready"
    message = "HTTP request/response contract is available locally; network execution is not implemented yet."
    if not request_url:
        message = "HTTP request/response contract is not ready until base_url is configured."

    summary = {
        "status": status,
        "message": message,
        "adapter": adapter_value if isinstance(adapter_value, str) and adapter_value else None,
        "adapter_family": "http",
        "base_url": base_url,
        "request_url": request_url,
        "model": model,
        "api_key_env": api_key_env,
        "http_timeout_seconds": http_timeout_seconds,
        "prompt_exists": prompt_exists_flag,
        "request_payload": payload,
        "response_text_path": _RESPONSE_TEXT_PATH,
        "errors": list(errors),
    }

    return summary


def _invalid_response(message: str) -> dict:
    return {
        "status": "invalid_response",
        "text": "",
        "errors": [message],
        "message": message,
    }


def _coerce_content_to_text(content: object) -> str:
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue

            if isinstance(item, Mapping):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
                    continue

                nested_content = item.get("content")
                if isinstance(nested_content, str):
                    parts.append(nested_content)
                    continue

            parts.append(str(item))

        return "".join(parts)

    if content is None:
        return ""

    return str(content)


def _extract_fenced_diff_block(text: str) -> str | None:
    pattern = re.compile(r"```diff\s*\n(.*?)(?:\n```|```)", re.IGNORECASE | re.DOTALL)
    match = pattern.search(text)
    if not match:
        return None

    candidate = match.group(1).strip("\n")
    return candidate if candidate else None


def _extract_diff_like_text(text: str) -> str:
    lines = text.split("\n")
    start_index = None

    for index, line in enumerate(lines):
        if line.startswith("diff --git ") or line.startswith("--- ") or line.startswith("+++ "):
            start_index = index
            break

    if start_index is None:
        stripped = text.strip()
        if stripped.startswith("diff --git ") or stripped.startswith("--- ") or stripped.startswith("+++ "):
            return stripped
        return ""

    return "\n".join(lines[start_index:]).strip("\n")
