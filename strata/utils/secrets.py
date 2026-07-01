from __future__ import annotations

import os
import re

_ENV_VAR_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_AUTH_HEADER_RE = re.compile(r"(?i)\b(Authorization\s*[:=]\s*)(?:Bearer|Token)\s+[^\s,;\"']+")
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)(?<![-A-Za-z0-9_.])((?:API_KEY|TOKEN|SECRET|PASSWORD|AUTHORIZATION)|[A-Za-z0-9_.][A-Za-z0-9_.-]*(?:API_KEY|TOKEN|SECRET|PASSWORD|AUTHORIZATION))\s*([:=])\s*([^\s,;\"']+)"
)
_SECRET_CLI_OPTION_RE = re.compile(
    r"(?i)(--[A-Za-z0-9_-]*(?:api[-_]?key|token|secret|password|authorization)[A-Za-z0-9_-]*)(=|\s+)([^\s,;\"']+)"
)
_OPENAI_KEY_RE = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b")
_ANTHROPIC_KEY_RE = re.compile(r"\bsk-ant-[A-Za-z0-9_-]{8,}\b")
_GITHUB_TOKEN_RE = re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{8,}|github_pat_[A-Za-z0-9_]{8,})\b")
_JWT_RE = re.compile(r"\b[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")
_GENERIC_SECRET_RE = re.compile(r"\b[A-Za-z0-9+/=_-]{40,}\b")


def looks_like_secret(value: str) -> bool:
    if not isinstance(value, str):
        value = str(value)

    candidate = value.strip()
    if not candidate:
        return False

    if _OPENAI_KEY_RE.search(candidate):
        return True

    if _ANTHROPIC_KEY_RE.search(candidate):
        return True

    if _GITHUB_TOKEN_RE.search(candidate):
        return True

    if _JWT_RE.search(candidate):
        return True

    if _looks_like_generic_secret(candidate):
        return True

    return False


def redact_secret(value: str) -> str:
    if not isinstance(value, str):
        value = str(value)

    return "<redacted>" if looks_like_secret(value) else value


def redact_text(text: object) -> str:
    if text is None:
        return ""

    redacted = str(text)
    redacted = _AUTH_HEADER_RE.sub(r"\1<redacted>", redacted)
    redacted = _SECRET_CLI_OPTION_RE.sub(r"\1\2<redacted>", redacted)
    redacted = _SECRET_ASSIGNMENT_RE.sub(r"\1\2 <redacted>", redacted)
    redacted = _OPENAI_KEY_RE.sub("<redacted>", redacted)
    redacted = _ANTHROPIC_KEY_RE.sub("<redacted>", redacted)
    redacted = _GITHUB_TOKEN_RE.sub("<redacted>", redacted)
    redacted = _JWT_RE.sub("<redacted>", redacted)
    redacted = _GENERIC_SECRET_RE.sub(_redact_generic_match, redacted)
    return redacted


def safe_env_status(env_name: str | None) -> str:
    if not validate_env_var_name(env_name):
        return "missing"

    value = os.environ.get(env_name or "")
    if value is None or not str(value).strip():
        return "missing"

    return "found"


def validate_env_var_name(name: str | None) -> bool:
    if not isinstance(name, str):
        return False

    candidate = name.strip()
    if not candidate:
        return False

    return bool(_ENV_VAR_NAME_RE.fullmatch(candidate))


def _looks_like_generic_secret(candidate: str) -> bool:
    if len(candidate) < 40:
        return False

    if not _GENERIC_SECRET_RE.fullmatch(candidate):
        return False

    if "/" in candidate and "+" not in candidate and "=" not in candidate:
        return False

    has_lower = any(char.islower() for char in candidate)
    has_upper = any(char.isupper() for char in candidate)
    has_digit = any(char.isdigit() for char in candidate)
    has_symbol = any(char in "+/=_-" for char in candidate)

    return sum((has_lower, has_upper, has_digit, has_symbol)) >= 3


def _redact_generic_match(match: re.Match[str]) -> str:
    candidate = match.group(0)
    before = match.string[match.start() - 1] if match.start() else ""
    after = match.string[match.end()] if match.end() < len(match.string) else ""
    following = match.string[match.end():]
    has_file_extension = bool(re.match(r"^\.[A-Za-z0-9]{1,10}(?:\b|$)", following))
    if before in "/\\" or after in "/\\" or has_file_extension:
        return candidate
    return "<redacted>" if _looks_like_generic_secret(candidate) else candidate
