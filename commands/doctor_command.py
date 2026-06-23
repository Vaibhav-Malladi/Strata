from __future__ import annotations

from adapter_doctor import check_adapter
from cli_help import print_usage
from ui import build_banner, build_kv_table, build_section, format_error, format_path, format_success, format_warning


def write_doctor_command(*args: str) -> int:
    if not args:
        _print_usage_hint()
        return 1

    target = args[0]

    if target != "adapter":
        print_usage()
        return 1

    if len(args) > 2:
        print_usage()
        return 1

    root = args[1] if len(args) == 2 else "."
    result = check_adapter(root)

    _print_adapter_result(result)
    return 0 if result.get("ready") else 1


def _print_usage_hint() -> None:
    print(build_banner())
    print()
    print(build_section("Doctor"))
    print(format_warning("Supported usage is `strata doctor adapter`."))


def _print_adapter_result(result: dict[str, object]) -> None:
    rows = [
        ("Status", _format_status(str(result.get("status", "invalid")))),
        ("Mode", _format_value(result.get("mode"))),
        ("Agent", _format_value(result.get("agent"))),
        ("Adapter", _format_value(result.get("adapter"))),
        ("Prompt", _format_path_value(result.get("prompt"))),
        ("Patch", _format_path_value(result.get("patch"))),
        ("Command", _format_value(result.get("command"))),
        ("Message", _format_value(result.get("message"))),
    ]

    errors = result.get("errors") or []
    warnings = result.get("warnings") or []

    if errors:
        rows.append(("Errors", _format_notes(errors)))

    if warnings:
        rows.append(("Warnings", _format_notes(warnings)))

    print(build_banner())
    print()
    print(build_section("Adapter doctor"))
    print(build_kv_table(rows))

    checks = result.get("checks") or []
    if checks:
        print()
        print(build_section("Checks"))
        print(
            build_kv_table(
                [
                    (
                        str(check.get("name", "")).title(),
                        _format_check(check),
                    )
                    for check in checks
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
