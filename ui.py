from __future__ import annotations

from pathlib import Path
from typing import Sequence

APP_NAME = "Strata"
TAGLINE = "Local-first repository intelligence for AI-assisted coding"

_SUCCESS_SYMBOL = "✓"
_WARNING_SYMBOL = "⚠"
_ERROR_SYMBOL = "✕"
_SEPARATOR = "─"


def build_banner() -> str:
    width = max(len(APP_NAME), len(TAGLINE))
    divider = _SEPARATOR * width

    return "\n".join(
        [
            divider,
            APP_NAME,
            TAGLINE,
            divider,
        ]
    )


def build_section(title: str) -> str:
    separator = _SEPARATOR * max(len(title), 1)
    return f"{title}\n{separator}"


def build_kv_table(rows: Sequence[tuple[str, object]]) -> str:
    if not rows:
        return ""

    label_width = max(len(label) for label, _ in rows)
    lines = [
        f"{label.ljust(label_width)}  {value}"
        for label, value in rows
    ]
    return "\n".join(lines)


def format_status(status: str) -> str:
    normalized = status.strip().upper()

    if normalized == "PASS":
        return f"{_SUCCESS_SYMBOL} PASS"

    if normalized in {"WARN", "WARNING"}:
        return f"{_WARNING_SYMBOL} WARN"

    if normalized in {"FAIL", "ERROR"}:
        return f"{_ERROR_SYMBOL} FAIL"

    return normalized


def format_success(message: str) -> str:
    return f"{_SUCCESS_SYMBOL} {message}"


def format_warning(message: str) -> str:
    return f"{_WARNING_SYMBOL} {message}"


def format_error(message: str) -> str:
    return f"{_ERROR_SYMBOL} {message}"


def format_path(path: str | Path) -> str:
    return str(path)
