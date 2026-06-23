from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

from patch_contract import inspect_patch
from patch_validator import validate_patch_file

DEFAULT_TIMEOUT_SECONDS = 120


def parse_command(command: str) -> list[str]:
    if os.name == "nt":
        parts = shlex.split(command, posix=False)
        return [_strip_wrapping_quotes(part) for part in parts]

    return shlex.split(command)


def execute_command_adapter(root=".", command=None, timeout_seconds=DEFAULT_TIMEOUT_SECONDS) -> dict:
    root_path = Path(root)
    effective_timeout = timeout_seconds if type(timeout_seconds) is int and timeout_seconds > 0 else DEFAULT_TIMEOUT_SECONDS

    if command is None or not str(command).strip():
        return _build_result(
            status="not_ready",
            executed=False,
            returncode=None,
            timed_out=False,
            stdout="",
            stderr="",
            patch_status="missing",
            patch_valid=False,
            targets=[],
            errors=["Command is not configured."],
            warnings=[],
            message="Command adapter is not ready.",
        )

    try:
        argv = parse_command(str(command))
    except ValueError as error:
        return _build_result(
            status="invalid_command",
            executed=False,
            returncode=None,
            timed_out=False,
            stdout="",
            stderr="",
            patch_status="missing",
            patch_valid=False,
            targets=[],
            errors=[f"Command parsing failed: {error}"],
            warnings=[],
            message="Command parsing failed.",
        )

    if not argv:
        return _build_result(
            status="not_ready",
            executed=False,
            returncode=None,
            timed_out=False,
            stdout="",
            stderr="",
            patch_status="missing",
            patch_valid=False,
            targets=[],
            errors=["Command is not configured."],
            warnings=[],
            message="Command adapter is not ready.",
        )

    stdout = ""
    stderr = ""
    returncode = None
    timed_out = False

    try:
        completed = subprocess.run(
            argv,
            cwd=str(root_path),
            capture_output=True,
            text=True,
            timeout=effective_timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        timed_out = True
        stdout = _coerce_output(error.stdout)
        stderr = _coerce_output(error.stderr)
    else:
        returncode = completed.returncode
        stdout = _coerce_output(completed.stdout)
        stderr = _coerce_output(completed.stderr)

    patch_summary = inspect_patch(root_path)
    patch_status = str(patch_summary.get("status", "missing")).lower()
    validation = None

    if patch_status == "ready":
        validation = validate_patch_file(root_path)

    if timed_out:
        return _build_result(
            status="timeout",
            executed=True,
            returncode=None,
            timed_out=True,
            stdout=stdout,
            stderr=stderr,
            patch_status=patch_status,
            patch_valid=False,
            targets=[],
            errors=[f"Command timed out after {effective_timeout} seconds."],
            warnings=[],
            message="Command execution timed out.",
        )

    if returncode != 0:
        return _build_result(
            status="command_failed",
            executed=True,
            returncode=returncode,
            timed_out=False,
            stdout=stdout,
            stderr=stderr,
            patch_status=patch_status,
            patch_valid=False,
            targets=[],
            errors=[f"Command exited with code {returncode}."],
            warnings=[],
            message="Command execution failed.",
        )

    if patch_status == "missing":
        return _build_result(
            status="missing_patch",
            executed=True,
            returncode=returncode,
            timed_out=False,
            stdout=stdout,
            stderr=stderr,
            patch_status=patch_status,
            patch_valid=False,
            targets=[],
            errors=["Command did not produce a patch file."],
            warnings=[],
            message="Command executed but no patch was produced.",
        )

    if patch_status == "empty":
        return _build_result(
            status="empty_patch",
            executed=True,
            returncode=returncode,
            timed_out=False,
            stdout=stdout,
            stderr=stderr,
            patch_status=patch_status,
            patch_valid=False,
            targets=[],
            errors=["Command produced an empty patch file."],
            warnings=[],
            message="Command executed but produced an empty patch.",
        )

    if validation is not None and validation.get("valid"):
        return _build_result(
            status="patch_ready",
            executed=True,
            returncode=returncode,
            timed_out=False,
            stdout=stdout,
            stderr=stderr,
            patch_status=patch_status,
            patch_valid=True,
            targets=list(validation.get("targets", [])),
            errors=[],
            warnings=list(validation.get("warnings", [])),
            message="Command executed and produced a valid patch.",
        )

    return _build_result(
        status="invalid_patch",
        executed=True,
        returncode=returncode,
        timed_out=False,
        stdout=stdout,
        stderr=stderr,
        patch_status=patch_status,
        patch_valid=False,
        targets=[],
        errors=["Patch failed validation."],
        warnings=[],
        message="Command executed but produced an invalid patch.",
    )


def _strip_wrapping_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]

    return value


def _coerce_output(value: object) -> str:
    if value is None:
        return ""

    return str(value)


def _build_result(
    *,
    status: str,
    executed: bool,
    returncode: int | None,
    timed_out: bool,
    stdout: str,
    stderr: str,
    patch_status: str,
    patch_valid: bool,
    targets: list[str] | None,
    errors: list[str] | None,
    warnings: list[str] | None,
    message: str,
) -> dict:
    return {
        "status": status,
        "executed": executed,
        "returncode": returncode,
        "timed_out": timed_out,
        "stdout": stdout,
        "stderr": stderr,
        "patch_status": patch_status,
        "patch_valid": patch_valid,
        "targets": list(targets or []),
        "errors": list(errors or []),
        "warnings": list(warnings or []),
        "message": message,
    }
