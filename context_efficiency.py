from __future__ import annotations

import math
from pathlib import Path


def estimate_tokens(text: str) -> int:
    text = text or ""

    if not text:
        return 0

    return _estimate_tokens_from_chars(len(text))


def estimate_graph_source_chars(graph: dict) -> int:
    root = str(graph.get("root", "") or "").strip()
    total = 0

    for file_info in graph.get("files", []):
        if not isinstance(file_info, dict):
            continue

        raw_path = str(file_info.get("path", "") or "").strip()

        if not raw_path:
            continue

        file_path = Path(raw_path)
        if not file_path.is_absolute() and root:
            file_path = Path(root) / file_path

        try:
            total += len(file_path.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue

    return total


def compute_context_efficiency(full_source_chars: int, focused_context_chars: int) -> dict[str, int]:
    full_source_chars = max(0, int(full_source_chars))
    focused_context_chars = max(0, int(focused_context_chars))

    full_source_tokens = _estimate_tokens_from_chars(full_source_chars)
    focused_context_tokens = _estimate_tokens_from_chars(focused_context_chars)

    if full_source_chars <= 0 or focused_context_chars > full_source_chars:
        reduction_percent = 0
    elif full_source_tokens <= 0:
        reduction_percent = 0
    else:
        reduction_percent = max(
            0,
            ((full_source_tokens - focused_context_tokens) * 100) // full_source_tokens,
        )

    return {
        "full_source_tokens": full_source_tokens,
        "focused_context_tokens": focused_context_tokens,
        "reduction_percent": reduction_percent,
    }


def _estimate_tokens_from_chars(char_count: int) -> int:
    if char_count <= 0:
        return 0

    return math.ceil(char_count / 3.3)
