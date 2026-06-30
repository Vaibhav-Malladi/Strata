from __future__ import annotations

from pathlib import Path

from strata.adapters.agent_adapters import DEFAULT_PATCH_PATH, DEFAULT_PROMPT_PATH

_PRESET_ALIASES = {
    "aider": "aider",
    "codex": "codex_cli",
    "codex-cli": "codex_cli",
    "codex_cli": "codex_cli",
}

_SUPPORTED_PRESETS = ("aider", "codex_cli")


def supported_presets() -> list[str]:
    return list(_SUPPORTED_PRESETS)


def get_adapter_preset(name: str) -> dict[str, object]:
    normalized = _normalize_preset_name(name)

    if normalized == "aider":
        return _build_preset(
            adapter="aider",
            display_name="Aider",
            command=build_aider_command(),
        )

    if normalized == "codex_cli":
        return _build_preset(
            adapter="codex_cli",
            display_name="Codex CLI",
            command=build_codex_cli_command(),
        )

    supported = ", ".join(_SUPPORTED_PRESETS)
    raise ValueError(f"Unknown adapter preset '{name}'. Supported presets: {supported}.")


def build_aider_command(
    prompt_path: str = str(DEFAULT_PROMPT_PATH),
    patch_path: str = str(DEFAULT_PATCH_PATH),
) -> str:
    _ = patch_path
    return f"aider --message-file {_normalize_path_text(prompt_path)}"


def build_codex_cli_command(
    prompt_path: str = str(DEFAULT_PROMPT_PATH),
    patch_path: str = str(DEFAULT_PATCH_PATH),
) -> str:
    _ = patch_path
    return f"codex --prompt-file {_normalize_path_text(prompt_path)}"


def _normalize_preset_name(name: str) -> str:
    normalized = str(name).strip().lower()
    if not normalized:
        return ""

    return _PRESET_ALIASES.get(normalized, normalized)


def _build_preset(*, adapter: str, display_name: str, command: str) -> dict[str, object]:
    patch_path = _normalize_path_text(DEFAULT_PATCH_PATH)
    return {
        "adapter": adapter,
        "adapter_family": "command",
        "display_name": display_name,
        "command": command,
        "warning": (
            f"{display_name} may edit files directly depending on how it is configured. "
            f"Verify this command for your installed CLI before running execute. "
            f"Strata expects {patch_path}."
        ),
        "message": f"{display_name} preset is configured.",
        "requires_confirmation": True,
    }


def _normalize_path_text(value: str | Path) -> str:
    return Path(value).as_posix()
