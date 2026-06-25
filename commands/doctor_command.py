from __future__ import annotations

import importlib.util
import shutil
import sys
import sysconfig
from adapter_doctor import check_adapter
from cli_help import print_usage
from pathlib import Path
from secret_redaction import safe_env_status
from ui import (
    build_kv_table,
    build_section,
    format_error,
    format_path,
    format_success,
    format_warning,
    print_command_header,
    print_status_card,
)


def write_doctor_command(*args: str) -> int:
    if not args:
        _print_usage_hint()
        return 1

    target = args[0]

    if target == "adapter":
        if len(args) > 2:
            print_usage()
            return 1

        root = args[1] if len(args) == 2 else "."
        result = check_adapter(root)

        _print_adapter_result(result)
        return 0 if result.get("ready") else 1

    if target == "install":
        if len(args) > 1:
            print_usage()
            return 1

        _print_install_result()
        return 0

    if target != "adapter":
        print_usage()
        return 1


def _print_usage_hint() -> None:
    print_command_header("Doctor", "Adapter checks", mode="compact")
    print(format_warning("Supported usage is `strata doctor adapter` or `strata doctor install`."))


def _print_adapter_result(result: dict[str, object]) -> None:
    rows = [
        ("Mode", _format_value(result.get("mode"))),
        ("Agent", _format_value(result.get("agent"))),
        ("Adapter", _format_value(result.get("adapter"))),
        ("Adapter family", _format_value(result.get("adapter_family"))),
        ("Prompt", _format_path_value(result.get("prompt"))),
        ("Patch", _format_path_value(result.get("patch"))),
        ("Command", _format_value(result.get("command"))),
        ("Command timeout", _format_value(result.get("command_timeout_seconds"))),
        ("Base URL", _format_value(result.get("base_url"))),
        ("Model", _format_value(result.get("model"))),
        ("API key env", _format_value(result.get("api_key_env"))),
        ("API key", _format_value(safe_env_status(result.get("api_key_env")))),
        ("HTTP timeout seconds", _format_value(result.get("http_timeout_seconds"))),
        ("Message", _format_value(result.get("message"))),
    ]

    errors = result.get("errors") or []
    warnings = result.get("warnings") or []

    if errors:
        rows.append(("Errors", _format_notes(errors)))

    if warnings:
        rows.append(("Warnings", _format_notes(warnings)))

    print_command_header("Doctor", "Adapter health check", mode="compact")
    print_status_card(
        "Adapter doctor",
        rows,
        status=_format_status(str(result.get("status", "invalid"))),
    )

    checks = result.get("checks") or []
    if checks:
        print_status_card(
            "Checks",
            [
                (
                    str(check.get("name", "")).title(),
                    _format_check(check),
                )
                for check in checks
            ],
        )


def _print_install_result() -> None:
    which_strata = shutil.which("strata")
    strata_module = _module_status("strata")
    cli_module = _module_status("cli")
    run_module = _module_status("commands.run_command")
    scripts_dir = _scripts_dir()

    rows = [
        ("Current working directory", format_path(Path.cwd())),
        ("Python executable", sys.executable),
        ("Python version", sys.version.split()[0]),
        ("strata on PATH", _format_optional_path(which_strata)),
        ("Resolved strata path", _format_optional_text(which_strata, "not found")),
        ("Expected Scripts dir", _format_optional_text(scripts_dir, "unknown")),
        ("strata module", strata_module),
        ("cli module", cli_module),
        ("commands.run_command", run_module),
    ]

    path_ready = which_strata is not None
    status = format_success("ready") if path_ready and strata_module == "available" else format_warning("check PATH")

    print_command_header("Doctor", "Install diagnostics", mode="compact")
    print_status_card("Install doctor", rows, status=status)
    print()
    print(build_section("Windows tips"))
    print(
        build_kv_table(
            [
                ("Local dev", "Run `py -m pip install -e .` from the project root."),
                ("Installed CLI", "Run `strata help` after installation."),
                ("VS Code", "Restart the VS Code terminal after PATH changes."),
                (
                    "PowerShell vs VS Code",
                    "If it works in PowerShell but not VS Code, close and reopen VS Code.",
                ),
                (
                    "Fallback",
                    "If PATH still fails, run from the project environment or reinstall Strata.",
                ),
            ]
        )
    )


def _format_status(status: str) -> str:
    normalized = status.strip().lower()

    if normalized == "ready":
        return format_success("ready")

    if normalized == "not_ready":
        return format_error("not_ready")

    if normalized == "invalid":
        return format_error("invalid")

    return normalized


def _format_value(value: object) -> object:
    if value is None or value == "":
        return "-"

    return value


def _format_path_value(value: object) -> object:
    if value is None or value == "":
        return "-"

    return format_path(value)


def _format_notes(values: object) -> str:
    if not values:
        return "-"

    return "; ".join(str(value) for value in values)


def _format_check(check: dict[str, object]) -> str:
    status = str(check.get("status", "")).strip().lower()
    message = str(check.get("message", ""))

    if status == "pass":
        return f"{format_success('pass')} {message}"

    if status == "fail":
        return f"{format_error('fail')} {message}"

    if status == "info":
        return f"info {message}"

    return message


def _module_status(name: str) -> str:
    return "available" if importlib.util.find_spec(name) is not None else "missing"


def _format_optional_path(value: str | None) -> str:
    if value is None or value == "":
        return "not on PATH"

    return format_path(value)


def _format_optional_text(value: str | None, missing_text: str) -> str:
    if value is None or value == "":
        return missing_text

    return format_path(value)


def _scripts_dir() -> str | None:
    try:
        scripts_dir = sysconfig.get_path("scripts")
    except Exception:
        return None

    if not scripts_dir:
        return None

    return scripts_dir
