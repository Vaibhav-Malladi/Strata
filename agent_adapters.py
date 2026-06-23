"""Adapter helpers for Strata's model-agnostic agent foundation."""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

DEFAULT_PROMPT_PATH = Path(".aidc") / "agent_prompt.md"
DEFAULT_PATCH_PATH = Path(".aidc") / "agent_patch.diff"

SUPPORTED_ADAPTERS = frozenset(
    {
        "prompt_file",
        "command",
        "ollama",
        "openai_compatible_http",
        "aider",
        "codex_cli",
    }
)

IMPLEMENTED_ADAPTERS = frozenset({"prompt_file"})

_ADAPTER_ALIASES = {
    "prompt": "prompt_file",
    "file": "prompt_file",
    "manual": "prompt_file",
    "openai-http": "openai_compatible_http",
    "http": "openai_compatible_http",
    "codex": "codex_cli",
}


def supported_adapters() -> set[str]:
    """Return a fresh set of all supported adapter names."""

    return set(SUPPORTED_ADAPTERS)


def implemented_adapters() -> set[str]:
    """Return a fresh set of adapters that are implemented today."""

    return set(IMPLEMENTED_ADAPTERS)


def normalize_adapter_name(name: str | None) -> str:
    """Normalize adapter names and map known aliases to canonical names."""

    if name is None:
        return "prompt_file"

    normalized = name.strip().lower()
    if not normalized:
        return "prompt_file"

    return _ADAPTER_ALIASES.get(normalized, normalized)


def validate_adapter_name(name: str | None) -> str:
    """Normalize and validate an adapter name."""

    normalized = normalize_adapter_name(name)
    if normalized not in SUPPORTED_ADAPTERS:
        supported = ", ".join(sorted(SUPPORTED_ADAPTERS))
        raise ValueError(f"Unknown adapter '{name}'. Supported adapters: {supported}.")
    return normalized


def is_adapter_implemented(name: str | None) -> bool:
    """Return whether a validated adapter is implemented."""

    normalized = validate_adapter_name(name)
    return normalized in IMPLEMENTED_ADAPTERS


def prompt_path(root: str | Path = ".", configured_path: str | Path | None = None) -> Path:
    """Resolve the prompt path without creating anything on disk."""

    root_path = Path(root)
    if configured_path is None:
        return root_path / DEFAULT_PROMPT_PATH

    configured = Path(configured_path)
    if configured.is_absolute():
        return configured
    return root_path / configured


def patch_path(root: str | Path = ".", configured_path: str | Path | None = None) -> Path:
    """Resolve the patch path without creating anything on disk."""

    root_path = Path(root)
    if configured_path is None:
        return root_path / DEFAULT_PATCH_PATH

    configured = Path(configured_path)
    if configured.is_absolute():
        return configured
    return root_path / configured


def build_prompt_file_result(
    root: str | Path = ".",
    configured_prompt_path: str | Path | None = None,
) -> dict[str, Any]:
    """Build the deterministic result for the safe prompt-file adapter."""

    resolved_prompt_path = prompt_path(root, configured_prompt_path)

    if resolved_prompt_path.exists():
        status = "ready"
        message = (
            "Prompt ready. Paste it into your AI coding tool, then run `strata review`."
        )
    else:
        status = "missing_prompt"
        message = "Prompt file not found. Run `strata prepare \"task\"` first."

    return {
        "adapter": "prompt_file",
        "status": status,
        "executed": False,
        "prompt_path": str(resolved_prompt_path),
        "patch_path": None,
        "message": message,
    }


def run_adapter(
    adapter: str | None,
    root: str | Path = ".",
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run an adapter in a deterministic, non-executing way."""

    normalized = validate_adapter_name(adapter)

    if normalized == "prompt_file":
        configured_prompt_path = None
        if config is not None:
            configured_prompt_path = config.get("prompt_path")
        return build_prompt_file_result(root, configured_prompt_path)

    return {
        "adapter": normalized,
        "status": "not_implemented",
        "executed": False,
        "prompt_path": str(DEFAULT_PROMPT_PATH),
        "patch_path": None,
        "message": (
            f"Adapter '{normalized}' is planned but not implemented yet. "
            "Use adapter 'prompt_file' for now."
        ),
    }
