from __future__ import annotations

import os
import shlex
import subprocess
from collections.abc import Sequence
from pathlib import Path

from secret_redaction import redact_text
from patch_contract import inspect_patch
from patch_validator import validate_patch_file

DEFAULT_TIMEOUT_SECONDS = 120


def run_argv(
    argv: Sequence[str],
    *,
    cwd: str | Path | None = None,
    timeout: int | None = None,
    encoding: str | None = None,
    errors: str | None = None,
) -> subprocess.CompletedProcess[str]:
    if isinstance(argv, (str, bytes)):
        raise TypeError("Command argv must be a sequence of arguments, not a command string.")

    command = [str(argument) for argument in argv]
    if not command:
        raise ValueError("Command argv must not be empty.")

    return subprocess.run(
        command,
        cwd=str(cwd) if cwd is not None else None,
        capture_output=True,
        text=True,
        encoding=encoding,
        errors=errors,
        timeout=timeout,
        check=False,
        shell=False,
    )


def parse_command(command: str) -> list[str]:
    if os.name == "nt":
        parts = shlex.split(command, posix=False)
        return [_strip_wrapping_quotes(part) for part in parts]

    return shlex.split(command)


def run_shell_compatible_adapter_command(
    argv: Sequence[str],
    *,
    cwd: str | Path,
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    # Intentionally supports command-adapter strings parsed with shell-like quoting.
    # Execution remains argv-only through run_argv; shell operators are not interpreted.
    return run_argv(argv, cwd=cwd, timeout=timeout)


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
            errors=[redact_text("Command is not configured.")],
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
            errors=[redact_text(f"Command parsing failed: {error}")],
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
            errors=[redact_text("Command is not configured.")],
            warnings=[],
            message="Command adapter is not ready.",
        )

    stdout = ""
    stderr = ""
    returncode = None
    timed_out = False

    try:
        completed = run_shell_compatible_adapter_command(
            argv,
            cwd=str(root_path),
            timeout=effective_timeout,
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
            errors=[redact_text(f"Command timed out after {effective_timeout} seconds.")],
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
            errors=[redact_text(f"Command exited with code {returncode}.")],
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
            errors=[redact_text("Command did not produce a patch file.")],
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
            errors=[redact_text("Command produced an empty patch file.")],
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
        errors=[redact_text("Patch failed validation.")],
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

    return redact_text(value)


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
