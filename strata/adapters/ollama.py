from __future__ import annotations

from collections.abc import Mapping
import json
import socket
from pathlib import Path
from typing import Any
from urllib import error, request
from urllib.parse import urlsplit

from strata.adapters.agent_adapters import prompt_path
from strata.adapters.http_contract import extract_patch_from_text
from patch_contract import inspect_patch, resolve_patch_path
from patch_validator import validate_patch_file
from strata.utils.config import load_config
from strata.utils.artifacts import write_artifact_text

DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "qwen2.5-coder"
_OLLAMA_DIFF_INSTRUCTION = (
    "Return only a unified diff patch. "
    "No explanations. "
    "No markdown fences unless necessary."
)
_DEFAULT_HTTP_TIMEOUT_SECONDS = 120


def normalize_ollama_base_url(base_url: str | None) -> str:
    if base_url is None:
        return DEFAULT_OLLAMA_BASE_URL

    if not isinstance(base_url, str):
        raise ValueError("base_url must be a string")

    normalized = base_url.strip().rstrip("/")
    if not normalized:
        return DEFAULT_OLLAMA_BASE_URL

    parsed = urlsplit(normalized)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise ValueError("Unsupported Ollama base_url scheme. Use http:// or https://.")

    return normalized


def build_ollama_generate_url(base_url: str | None) -> str:
    return f"{normalize_ollama_base_url(base_url)}/api/generate"


def build_ollama_tags_url(base_url: str | None) -> str:
    return f"{normalize_ollama_base_url(base_url)}/api/tags"


def build_ollama_payload(prompt_text: str, model: str | None = None) -> dict:
    resolved_model = model if isinstance(model, str) and model else DEFAULT_OLLAMA_MODEL
    resolved_prompt_text = "" if prompt_text is None else str(prompt_text)
    wrapped_prompt = f"{_OLLAMA_DIFF_INSTRUCTION}\n\n{resolved_prompt_text}"

    return {
        "model": resolved_model,
        "prompt": wrapped_prompt,
        "stream": False,
    }


def extract_text_from_ollama_response(response_json: dict) -> dict:
    if not isinstance(response_json, Mapping):
        return _invalid_response("Ollama response JSON must be a mapping.")

    response_text = response_json.get("response")
    if not isinstance(response_text, str) or not response_text.strip():
        return _invalid_response("Ollama response JSON is missing response text.")

    return {
        "status": "ok",
        "text": response_text,
        "errors": [],
        "message": "Ollama response text extracted.",
    }


def extract_ollama_models(tags_json: dict) -> list[str]:
    if not isinstance(tags_json, Mapping):
        return []

    models = tags_json.get("models")
    if not isinstance(models, list):
        return []

    names: list[str] = []
    for model in models:
        if not isinstance(model, Mapping):
            continue

        name = model.get("name")
        if isinstance(name, str) and name:
            names.append(name)

    return names


def check_ollama_health(config: dict, timeout_seconds: int | None = None) -> dict:
    config_mapping = config if isinstance(config, Mapping) else {}
    base_url_value = config_mapping.get("base_url")
    model = _display_model(config_mapping.get("model"))
    timeout = _resolve_timeout(timeout_seconds, config_mapping.get("http_timeout_seconds"))

    try:
        base_url = normalize_ollama_base_url(base_url_value)
    except ValueError as error_message:
        message = str(error_message)
        return _build_health_result(
            status="invalid_response",
            base_url=_display_raw_base_url(base_url_value),
            tags_url=None,
            models=[],
            model=model,
            model_available=False,
            errors=[message],
            warnings=[],
            message=message,
        )

    tags_url = build_ollama_tags_url(base_url)
    request_result = _request_json("GET", tags_url, timeout)
    if request_result["status"] != "ok":
        return _build_health_result(
            status=str(request_result["status"]),
            base_url=base_url,
            tags_url=tags_url,
            models=[],
            model=model,
            model_available=False,
            errors=list(request_result.get("errors", [])),
            warnings=[],
            message=str(request_result.get("message", "Ollama health check failed.")),
        )

    parsed_json = _parse_json_object(request_result["body_text"])
    if parsed_json["status"] != "ok":
        return _build_health_result(
            status="invalid_response",
            base_url=base_url,
            tags_url=tags_url,
            models=[],
            model=model,
            model_available=False,
            errors=list(parsed_json.get("errors", [])),
            warnings=[],
            message=str(parsed_json.get("message", "Ollama tags response was not valid JSON.")),
        )

    models = extract_ollama_models(parsed_json["json"])
    model_available = _model_is_available(model, models)
    warnings: list[str] = []
    if not model_available:
        warnings.append(f"Model '{model}' was not found in /api/tags.")

    status = "ok" if model_available else "unavailable"
    message = (
        "Ollama endpoint is healthy."
        if model_available
        else "Ollama endpoint responded, but the configured model is not available."
    )

    return _build_health_result(
        status=status,
        base_url=base_url,
        tags_url=tags_url,
        models=models,
        model=model,
        model_available=model_available,
        errors=[],
        warnings=warnings,
        message=message,
    )


def execute_ollama_adapter(root: str | Path = ".", config: Mapping[str, Any] | None = None) -> dict:
    root_path = Path(root)

    if config is None:
        try:
            loaded_config = load_config(root_path)
        except ValueError as error_message:
            message = str(error_message)
            return _build_result(
                status="not_ready",
                executed=False,
                adapter="ollama",
                adapter_family="http",
                base_url=None,
                url=None,
                model=DEFAULT_OLLAMA_MODEL,
                http_timeout_seconds=None,
                prompt_path=str(prompt_path(root_path)),
                patch_path=str(resolve_patch_path(root_path)),
                http_status=None,
                timed_out=False,
                patch_status="missing",
                patch_valid=False,
                targets=[],
                errors=[message],
                warnings=[],
                message="Ollama adapter is not ready.",
            )
        config_mapping = loaded_config
    else:
        config_mapping = dict(config)

    prompt_config = config_mapping.get("prompt_path")
    resolved_prompt_path = prompt_path(root_path, prompt_config)
    resolved_patch_path = resolve_patch_path(root_path)
    prompt_display = str(resolved_prompt_path)
    patch_display = str(resolved_patch_path)

    if not resolved_prompt_path.is_file():
        return _build_result(
            status="missing_prompt",
            executed=False,
            adapter="ollama",
            adapter_family="http",
            base_url=_display_base_url(config_mapping.get("base_url")),
            url=None,
            model=_display_model(config_mapping.get("model")),
            http_timeout_seconds=_resolve_timeout(
                config_mapping.get("http_timeout_seconds"),
                None,
            ),
            prompt_path=prompt_display,
            patch_path=patch_display,
            http_status=None,
            timed_out=False,
            patch_status="missing",
            patch_valid=False,
            targets=[],
            errors=[f"Prompt file not found: {prompt_display}"],
            warnings=[],
            message="Ollama adapter is not ready.",
        )

    try:
        base_url = normalize_ollama_base_url(config_mapping.get("base_url"))
        url = build_ollama_generate_url(base_url)
    except ValueError as error_message:
        message = str(error_message)
        return _build_result(
            status="not_ready",
            executed=False,
            adapter="ollama",
            adapter_family="http",
            base_url=_display_raw_base_url(config_mapping.get("base_url")),
            url=None,
            model=_display_model(config_mapping.get("model")),
            http_timeout_seconds=_resolve_timeout(
                config_mapping.get("http_timeout_seconds"),
                None,
            ),
            prompt_path=prompt_display,
            patch_path=patch_display,
            http_status=None,
            timed_out=False,
            patch_status="missing",
            patch_valid=False,
            targets=[],
            errors=[message],
            warnings=[],
            message="Ollama adapter is not ready.",
        )

    timeout_seconds = _resolve_timeout(config_mapping.get("http_timeout_seconds"), None)
    headers = {"Content-Type": "application/json"}
    prompt_text = resolved_prompt_path.read_text(encoding="utf-8")
    model = _display_model(config_mapping.get("model"))
    payload = build_ollama_payload(prompt_text, model=model)
    request_result = _request_json("POST", url, timeout_seconds, payload=payload, headers=headers)

    if request_result["status"] != "ok":
        return _build_result(
            status=str(request_result["status"]),
            executed=True,
            adapter="ollama",
            adapter_family="http",
            base_url=base_url,
            url=url,
            model=model,
            http_timeout_seconds=timeout_seconds,
            prompt_path=prompt_display,
            patch_path=patch_display,
            http_status=request_result.get("http_status"),
            timed_out=bool(request_result.get("timed_out")),
            patch_status="missing",
            patch_valid=False,
            targets=[],
            errors=list(request_result.get("errors", [])),
            warnings=[],
            message=str(request_result.get("message", "Ollama request failed.")),
        )

    parsed_json = _parse_json_object(request_result["body_text"])
    if parsed_json["status"] != "ok":
        return _build_result(
            status="invalid_json",
            executed=True,
            adapter="ollama",
            adapter_family="http",
            base_url=base_url,
            url=url,
            model=model,
            http_timeout_seconds=timeout_seconds,
            prompt_path=prompt_display,
            patch_path=patch_display,
            http_status=request_result.get("http_status"),
            timed_out=False,
            patch_status="missing",
            patch_valid=False,
            targets=[],
            errors=list(parsed_json.get("errors", [])),
            warnings=[],
            message=str(parsed_json.get("message", "Ollama response body was not valid JSON.")),
        )

    extracted_text = extract_text_from_ollama_response(parsed_json["json"])
    if extracted_text["status"] != "ok":
        return _build_result(
            status="invalid_response",
            executed=True,
            adapter="ollama",
            adapter_family="http",
            base_url=base_url,
            url=url,
            model=model,
            http_timeout_seconds=timeout_seconds,
            prompt_path=prompt_display,
            patch_path=patch_display,
            http_status=request_result.get("http_status"),
            timed_out=False,
            patch_status="missing",
            patch_valid=False,
            targets=[],
            errors=list(extracted_text.get("errors", [])),
            warnings=[],
            message=str(extracted_text.get("message", "Ollama response text could not be extracted.")),
        )

    patch_result = extract_patch_from_text(extracted_text["text"])
    if patch_result["status"] != "ok":
        return _build_result(
            status="missing_patch",
            executed=True,
            adapter="ollama",
            adapter_family="http",
            base_url=base_url,
            url=url,
            model=model,
            http_timeout_seconds=timeout_seconds,
            prompt_path=prompt_display,
            patch_path=patch_display,
            http_status=request_result.get("http_status"),
            timed_out=False,
            patch_status="missing",
            patch_valid=False,
            targets=[],
            errors=list(patch_result.get("errors", [])),
            warnings=[],
            message=str(patch_result.get("message", "Unified diff patch was not found in the provided text.")),
        )

    try:
        write_patch_text(root_path, patch_result["patch"])
    except OSError as error_message:
        message = f"Failed to write patch file: {error_message}"
        return _build_result(
            status="invalid_patch",
            executed=True,
            adapter="ollama",
            adapter_family="http",
            base_url=base_url,
            url=url,
            model=model,
            http_timeout_seconds=timeout_seconds,
            prompt_path=prompt_display,
            patch_path=patch_display,
            http_status=request_result.get("http_status"),
            timed_out=False,
            patch_status="missing",
            patch_valid=False,
            targets=[],
            errors=[message],
            warnings=[],
            message="Ollama adapter executed but produced an invalid patch.",
        )

    patch_summary = inspect_patch(root_path)
    validation = validate_patch_file(root_path)

    if validation.get("valid"):
        return _build_result(
            status="patch_ready",
            executed=True,
            adapter="ollama",
            adapter_family="http",
            base_url=base_url,
            url=url,
            model=model,
            http_timeout_seconds=timeout_seconds,
            prompt_path=prompt_display,
            patch_path=patch_display,
            http_status=request_result.get("http_status"),
            timed_out=False,
            patch_status=patch_summary.get("status", "ready"),
            patch_valid=True,
            targets=list(validation.get("targets", [])),
            errors=[],
            warnings=list(validation.get("warnings", [])),
            message="Ollama adapter executed and produced a valid patch.",
        )

    return _build_result(
        status="invalid_patch",
        executed=True,
        adapter="ollama",
        adapter_family="http",
        base_url=base_url,
        url=url,
        model=model,
        http_timeout_seconds=timeout_seconds,
        prompt_path=prompt_display,
        patch_path=patch_display,
        http_status=request_result.get("http_status"),
        timed_out=False,
        patch_status=patch_summary.get("status", "ready"),
        patch_valid=False,
        targets=[],
        errors=list(validation.get("errors", ["Patch failed validation."])),
        warnings=list(validation.get("warnings", [])),
        message="Ollama adapter executed but produced an invalid patch.",
    )


def write_patch_text(root: str | Path, patch_text: str) -> Path:
    return write_artifact_text(root, "agent_patch.diff", patch_text)


def _request_json(
    method: str,
    url: str,
    timeout_seconds: int,
    payload: dict | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    request_body = None
    request_headers = dict(headers or {})
    if payload is not None:
        request_body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")

    http_request = request.Request(url, data=request_body, headers=request_headers, method=method)

    try:
        with request.urlopen(http_request, timeout=timeout_seconds) as response:
            http_status = _coerce_http_status(response.getcode())
            response_text = _decode_response_bytes(
                response.read(),
                response.headers.get_content_charset(),
            )
            return {
                "status": "ok",
                "http_status": http_status,
                "body_text": response_text,
                "timed_out": False,
                "errors": [],
                "message": "HTTP request completed.",
            }
    except error.HTTPError as exc:
        body_text = _read_error_body(exc)
        return {
            "status": "http_error",
            "http_status": _coerce_http_status(exc.code),
            "body_text": body_text,
            "timed_out": False,
            "errors": [f"HTTP request failed with status {exc.code}."],
            "message": f"HTTP request failed with status {exc.code}.",
        }
    except (socket.timeout, TimeoutError):
        return {
            "status": "timeout",
            "http_status": None,
            "body_text": "",
            "timed_out": True,
            "errors": [f"HTTP request timed out after {timeout_seconds} seconds."],
            "message": "HTTP request timed out.",
        }
    except error.URLError as exc:
        reason = exc.reason
        message = f"HTTP request failed: {reason}"
        return {
            "status": "http_error",
            "http_status": None,
            "body_text": "",
            "timed_out": False,
            "errors": [message],
            "message": message,
        }


def _parse_json_object(body_text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(body_text)
    except json.JSONDecodeError as error_message:
        return {
            "status": "invalid_json",
            "json": None,
            "errors": [f"Response body was not valid JSON: {error_message}"],
            "message": "Response body was not valid JSON.",
        }

    if not isinstance(parsed, Mapping):
        return {
            "status": "invalid_json",
            "json": None,
            "errors": ["Response body was not a JSON object."],
            "message": "Response body was not valid JSON.",
        }

    return {
        "status": "ok",
        "json": dict(parsed),
        "errors": [],
        "message": "Response parsed.",
    }


def _resolve_timeout(preferred_timeout: object, fallback_timeout: object) -> int:
    if type(preferred_timeout) is int and preferred_timeout > 0:
        return preferred_timeout

    if type(fallback_timeout) is int and fallback_timeout > 0:
        return fallback_timeout

    return _DEFAULT_HTTP_TIMEOUT_SECONDS


def _display_model(value: object) -> str:
    if isinstance(value, str) and value:
        return value

    return DEFAULT_OLLAMA_MODEL


def _display_base_url(value: object) -> str:
    if isinstance(value, str) and value.strip():
        try:
            return normalize_ollama_base_url(value)
        except ValueError:
            return value.strip().rstrip("/")

    return DEFAULT_OLLAMA_BASE_URL


def _display_raw_base_url(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip().rstrip("/")

    return None


def _model_is_available(requested_model: str, available_models: list[str]) -> bool:
    requested_base = requested_model.split(":", 1)[0]

    for available_model in available_models:
        if requested_model == available_model:
            return True

        available_base = available_model.split(":", 1)[0]
        if requested_base == available_base:
            return True

    return False


def _build_health_result(
    *,
    status: str,
    base_url: str | None,
    tags_url: str | None,
    models: list[str] | None,
    model: str,
    model_available: bool,
    errors: list[str] | None,
    warnings: list[str] | None,
    message: str,
) -> dict[str, Any]:
    return {
        "status": status,
        "base_url": base_url,
        "tags_url": tags_url,
        "models": list(models or []),
        "model": model,
        "model_available": model_available,
        "errors": list(errors or []),
        "warnings": list(warnings or []),
        "message": message,
    }


def _build_result(
    *,
    status: str,
    executed: bool,
    adapter: str,
    adapter_family: str,
    base_url: str | None,
    url: str | None,
    model: str | None,
    http_timeout_seconds: int | None,
    prompt_path: str,
    patch_path: str,
    http_status: int | None,
    timed_out: bool,
    patch_status: str,
    patch_valid: bool,
    targets: list[str] | None,
    errors: list[str] | None,
    warnings: list[str] | None,
    message: str,
) -> dict[str, Any]:
    return {
        "status": status,
        "executed": executed,
        "adapter": adapter,
        "adapter_family": adapter_family,
        "base_url": base_url,
        "url": url,
        "model": model,
        "http_timeout_seconds": http_timeout_seconds,
        "prompt_path": prompt_path,
        "patch_path": patch_path,
        "http_status": http_status,
        "timed_out": timed_out,
        "patch_status": patch_status,
        "patch_valid": patch_valid,
        "targets": list(targets or []),
        "errors": list(errors or []),
        "warnings": list(warnings or []),
        "message": message,
    }


def _coerce_http_status(value: object) -> int | None:
    if type(value) is int:
        return value

    return None


def _decode_response_bytes(data: bytes, charset: str | None) -> str:
    if not data:
        return ""

    encoding = charset or "utf-8"
    return data.decode(encoding, errors="replace")


def _read_error_body(exc: error.HTTPError) -> str:
    try:
        body = exc.read()
    except OSError:
        body = b""

    charset = None
    headers = getattr(exc, "headers", None)
    if headers is not None and hasattr(headers, "get_content_charset"):
        charset = headers.get_content_charset()

    return _decode_response_bytes(body, charset)


def _invalid_response(message: str) -> dict[str, Any]:
    return {
        "status": "invalid_response",
        "text": "",
        "errors": [message],
        "message": message,
    }
