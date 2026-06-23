from pathlib import Path

from ui import (
    build_banner,
    build_kv_table,
    build_section,
    format_error,
    format_path,
    format_success,
)
from workflow_config import config_path, ensure_config, load_config


def write_config_command(root: str = ".") -> int:
    path = config_path(root)

    try:
        config = load_config(root)
    except ValueError as error:
        print(build_banner())
        print()
        print(build_section("Workflow config error"))
        print(format_error(str(error)))
        return 1

    exists = path.exists()

    print(build_banner())
    print()
    print(build_section("Workflow config"))
    print(
        build_kv_table(
            _config_rows(
                path=path,
                config=config,
                exists=exists,
            )
        )
    )

    return 0


def write_config_init_command(root: str = ".") -> int:
    path = config_path(root)

    try:
        ensure_config(root)
        config = load_config(root)
    except ValueError as error:
        print(build_banner())
        print()
        print(build_section("Workflow config error"))
        print(format_error(str(error)))
        return 1

    print(build_banner())
    print()
    print(build_section("Workflow config initialized"))
    print(
        build_kv_table(
            _config_rows(
                path=path,
                config=config,
                exists=True,
                include_exists=False,
                include_status=True,
            )
        )
    )

    return 0


def _config_rows(
    *,
    path: Path,
    config: dict,
    exists: bool,
    include_exists: bool = True,
    include_status: bool = False,
) -> list[tuple[str, object]]:
    rows: list[tuple[str, object]] = [("Path", format_path(path))]

    if include_status:
        rows.append(("Status", format_success("initialized")))

    if include_exists:
        rows.append(("Exists", format_success("yes") if exists else format_error("no")))

    rows.extend(
        [
            ("Mode", config["mode"]),
            ("Agent", config["agent"]),
            ("Auto snapshot", _bool_text(config["auto_snapshot"])),
            ("Auto verify", _bool_text(config["auto_verify"])),
            (
                "Require gate before commit",
                _bool_text(config["require_gate_pass_before_commit"]),
            ),
        ]
    )
    return rows


def _bool_text(value: object) -> str:
    return "true" if value is True else "false"
