from __future__ import annotations

from collections.abc import Mapping
import json
import os
import socket
from pathlib import Path
from typing import Any
from urllib import error, request

from strata.adapters.agent_adapters import prompt_path
from strata.adapters.http_contract import (
    build_openai_compatible_payload,
    build_openai_compatible_url,
    extract_patch_from_text,
    extract_text_from_openai_compatible_response,
    normalize_base_url,
)
from patch_contract import inspect_patch, resolve_patch_path
from patch_validator import validate_patch_file
from strata.utils.secrets import redact_text
from strata.utils.config import load_config
from strata.utils.artifacts import write_artifact_text

_DEFAULT_HTTP_TIMEOUT_SECONDS = 120


def build_http_headers(config: dict[str, Any]) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
    }

    api_key_env = config.get("api_key_env")
    if isinstance(api_key_env, str) and api_key_env:
        api_key = os.environ.get(api_key_env)
        if api_key is None or not str(api_key):
            raise ValueError(redact_text(f"Environment variable '{api_key_env}' is not set."))

        headers["Authorization"] = f"Bearer {api_key}"

    return headers


def write_patch_text(root: str | Path, patch_text: str) -> Path:
    return write_artifact_text(root, "agent_patch.diff", patch_text)


def post_json(url: str, payload: dict, headers: dict[str, str], timeout_seconds: int) -> dict[str, Any]:
    request_body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    http_request = request.Request(url, data=request_body, headers=dict(headers), method="POST")

    try:
        with request.urlopen(http_request, timeout=timeout_seconds) as response:
            http_status = _coerce_http_status(response.getcode())
            response_text = _decode_response_bytes(response.read(), response.headers.get_content_charset())
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
            "errors": [redact_text(f"HTTP request failed with status {exc.code}.")],
            "message": redact_text(f"HTTP request failed with status {exc.code}."),
        }
    except (socket.timeout, TimeoutError):
        return {
            "status": "timeout",
            "http_status": None,
            "body_text": "",
            "timed_out": True,
            "errors": [redact_text(f"HTTP request timed out after {timeout_seconds} seconds.")],
            "message": redact_text("HTTP request timed out."),
        }
    except error.URLError as exc:
        reason = exc.reason
        message = redact_text(f"HTTP request failed: {reason}")
        return {
            "status": "http_error",
            "http_status": None,
            "body_text": "",
            "timed_out": False,
            "errors": [message],
            "message": message,
        }


def execute_openai_compatible_http_adapter(root: str | Path = ".", config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    root_path = Path(root)

    if config is None:
        try:
            loaded_config = load_config(root_path)
        except ValueError as error:
            message = redact_text(str(error))
            return _build_result(
                status="not_ready",
                executed=False,
                adapter="openai_compatible_http",
                adapter_family="http",
                base_url=None,
                url=None,
                model=None,
                api_key_env=None,
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
                message="HTTP adapter is not ready.",
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
            adapter="openai_compatible_http",
            adapter_family="http",
            base_url=None,
            url=None,
            model=_display_model(config_mapping.get("model")),
            api_key_env=_display_optional_string(config_mapping.get("api_key_env")),
            http_timeout_seconds=_display_timeout(config_mapping.get("http_timeout_seconds")),
            prompt_path=prompt_display,
            patch_path=patch_display,
            http_status=None,
            timed_out=False,
            patch_status="missing",
            patch_valid=False,
            targets=[],
            errors=[redact_text(f"Prompt file not found: {prompt_display}")],
            warnings=[],
            message="HTTP adapter is not ready.",
        )

    base_url_value = config_mapping.get("base_url")
    if not isinstance(base_url_value, str) or not base_url_value.strip():
        return _build_result(
            status="missing_base_url",
            executed=False,
            adapter="openai_compatible_http",
            adapter_family="http",
            base_url=None,
            url=None,
            model=_display_model(config_mapping.get("model")),
            api_key_env=_display_optional_string(config_mapping.get("api_key_env")),
            http_timeout_seconds=_display_timeout(config_mapping.get("http_timeout_seconds")),
            prompt_path=prompt_display,
            patch_path=patch_display,
            http_status=None,
            timed_out=False,
            patch_status="missing",
            patch_valid=False,
            targets=[],
            errors=[redact_text("base_url is required for HTTP adapters.")],
            warnings=[],
            message="HTTP adapter is not ready.",
        )

    try:
        base_url = normalize_base_url(base_url_value)
        url = build_openai_compatible_url(base_url)
    except ValueError as error:
        message = redact_text(str(error))
        return _build_result(
            status="missing_base_url",
            executed=False,
            adapter="openai_compatible_http",
            adapter_family="http",
            base_url=base_url_value,
            url=None,
            model=_display_model(config_mapping.get("model")),
            api_key_env=_display_optional_string(config_mapping.get("api_key_env")),
            http_timeout_seconds=_display_timeout(config_mapping.get("http_timeout_seconds")),
            prompt_path=prompt_display,
            patch_path=patch_display,
            http_status=None,
            timed_out=False,
            patch_status="missing",
            patch_valid=False,
            targets=[],
            errors=[message],
            warnings=[],
            message="HTTP adapter is not ready.",
        )

    timeout_seconds = _display_timeout(config_mapping.get("http_timeout_seconds"))
    if timeout_seconds is None:
        timeout_seconds = _DEFAULT_HTTP_TIMEOUT_SECONDS

    try:
        headers = build_http_headers(config_mapping)
    except ValueError as error:
        return _build_result(
            status="missing_api_key",
            executed=False,
            adapter="openai_compatible_http",
            adapter_family="http",
            base_url=base_url,
            url=url,
            model=_display_model(config_mapping.get("model")),
            api_key_env=_display_optional_string(config_mapping.get("api_key_env")),
            http_timeout_seconds=timeout_seconds,
            prompt_path=prompt_display,
            patch_path=patch_display,
            http_status=None,
            timed_out=False,
            patch_status="missing",
            patch_valid=False,
            targets=[],
            errors=[redact_text(str(error))],
            warnings=[],
            message="HTTP adapter is not ready.",
        )

    prompt_text = resolved_prompt_path.read_text(encoding="utf-8")
    model = _display_model(config_mapping.get("model"))
    payload = build_openai_compatible_payload(prompt_text, model=model)
    http_result = post_json(url, payload, headers, timeout_seconds)

    if http_result["status"] != "ok":
        return _build_result(
            status=str(http_result["status"]),
            executed=True,
            adapter="openai_compatible_http",
            adapter_family="http",
            base_url=base_url,
            url=url,
            model=model,
            api_key_env=_display_optional_string(config_mapping.get("api_key_env")),
            http_timeout_seconds=timeout_seconds,
            prompt_path=prompt_display,
            patch_path=patch_display,
            http_status=http_result.get("http_status"),
            timed_out=bool(http_result.get("timed_out")),
            patch_status="missing",
            patch_valid=False,
            targets=[],
            errors=list(http_result.get("errors", [])),
            warnings=[],
            message=str(http_result.get("message", "HTTP request failed.")),
        )

    response_json = _parse_json_response(http_result["body_text"])
    if response_json["status"] != "ok":
        return _build_result(
            status="invalid_json",
            executed=True,
            adapter="openai_compatible_http",
            adapter_family="http",
            base_url=base_url,
            url=url,
            model=model,
            api_key_env=_display_optional_string(config_mapping.get("api_key_env")),
            http_timeout_seconds=timeout_seconds,
            prompt_path=prompt_display,
            patch_path=patch_display,
            http_status=http_result.get("http_status"),
            timed_out=False,
            patch_status="missing",
            patch_valid=False,
            targets=[],
            errors=list(response_json.get("errors", [])),
            warnings=[],
            message=str(response_json.get("message", "HTTP response body was not valid JSON.")),
        )

    extracted_text = extract_text_from_openai_compatible_response(response_json["json"])
    if extracted_text["status"] != "ok":
        return _build_result(
            status="invalid_response",
            executed=True,
            adapter="openai_compatible_http",
            adapter_family="http",
            base_url=base_url,
            url=url,
            model=model,
            api_key_env=_display_optional_string(config_mapping.get("api_key_env")),
            http_timeout_seconds=timeout_seconds,
            prompt_path=prompt_display,
            patch_path=patch_display,
            http_status=http_result.get("http_status"),
            timed_out=False,
            patch_status="missing",
            patch_valid=False,
            targets=[],
            errors=list(extracted_text.get("errors", [])),
            warnings=[],
            message=str(extracted_text.get("message", "HTTP response text could not be extracted.")),
        )

    patch_result = extract_patch_from_text(extracted_text["text"])
    if patch_result["status"] != "ok":
        return _build_result(
            status="missing_patch",
            executed=True,
            adapter="openai_compatible_http",
            adapter_family="http",
            base_url=base_url,
            url=url,
            model=model,
            api_key_env=_display_optional_string(config_mapping.get("api_key_env")),
            http_timeout_seconds=timeout_seconds,
            prompt_path=prompt_display,
            patch_path=patch_display,
            http_status=http_result.get("http_status"),
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
    except OSError as error:
        message = redact_text(f"Failed to write patch file: {error}")
        return _build_result(
            status="invalid_patch",
            executed=True,
            adapter="openai_compatible_http",
            adapter_family="http",
            base_url=base_url,
            url=url,
            model=model,
            api_key_env=_display_optional_string(config_mapping.get("api_key_env")),
            http_timeout_seconds=timeout_seconds,
            prompt_path=prompt_display,
            patch_path=patch_display,
            http_status=http_result.get("http_status"),
            timed_out=False,
            patch_status="missing",
            patch_valid=False,
            targets=[],
            errors=[message],
            warnings=[],
            message="HTTP adapter executed but produced an invalid patch.",
        )

    patch_summary = inspect_patch(root_path)
    validation = validate_patch_file(root_path)

    if validation.get("valid"):
        return _build_result(
            status="patch_ready",
            executed=True,
            adapter="openai_compatible_http",
            adapter_family="http",
            base_url=base_url,
            url=url,
            model=model,
            api_key_env=_display_optional_string(config_mapping.get("api_key_env")),
            http_timeout_seconds=timeout_seconds,
            prompt_path=prompt_display,
            patch_path=patch_display,
            http_status=http_result.get("http_status"),
            timed_out=False,
            patch_status=patch_summary.get("status", "ready"),
            patch_valid=True,
            targets=list(validation.get("targets", [])),
            errors=[],
            warnings=list(validation.get("warnings", [])),
            message="HTTP adapter executed and produced a valid patch.",
        )

    return _build_result(
        status="invalid_patch",
        executed=True,
        adapter="openai_compatible_http",
        adapter_family="http",
        base_url=base_url,
        url=url,
        model=model,
        api_key_env=_display_optional_string(config_mapping.get("api_key_env")),
        http_timeout_seconds=timeout_seconds,
        prompt_path=prompt_display,
        patch_path=patch_display,
        http_status=http_result.get("http_status"),
        timed_out=False,
        patch_status=patch_summary.get("status", "ready"),
        patch_valid=False,
        targets=[],
        errors=list(validation.get("errors", ["Patch failed validation."])),
        warnings=list(validation.get("warnings", [])),
        message="HTTP adapter executed but produced an invalid patch.",
    )


def _parse_json_response(body_text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(body_text)
    except json.JSONDecodeError as error:
        return {
            "status": "invalid_json",
            "json": None,
            "errors": [redact_text(f"HTTP response body was not valid JSON: {error}")],
            "message": redact_text("HTTP response body was not valid JSON."),
        }

    if not isinstance(parsed, Mapping):
        return {
            "status": "invalid_json",
            "json": None,
            "errors": [redact_text("HTTP response body was not a JSON object.")],
            "message": redact_text("HTTP response body was not valid JSON."),
        }

    return {
        "status": "ok",
        "json": dict(parsed),
        "errors": [],
        "message": "HTTP response parsed.",
    }


def _display_model(value: object) -> str:
    if isinstance(value, str) and value:
        return value

    return "strata-configured-model"


def _display_optional_string(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value

    return None


def _display_timeout(value: object) -> int | None:
    if type(value) is int and value > 0:
        return value

    return None


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


def _build_result(
    *,
    status: str,
    executed: bool,
    adapter: str,
    adapter_family: str,
    base_url: str | None,
    url: str | None,
    model: str | None,
    api_key_env: str | None,
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
        "api_key_env": api_key_env,
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
