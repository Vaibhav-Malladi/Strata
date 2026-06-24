from __future__ import annotations

import re
from pathlib import Path

from patch_contract import resolve_patch_path

_UNIFIED_DIFF_PREFIX = "diff --git "
_OLD_FILE_PREFIX = "--- "
_NEW_FILE_PREFIX = "+++ "
_A_PREFIX = "a/"
_B_PREFIX = "b/"
_DEV_NULL = "/dev/null"
_AIDC_PREFIX = ".aidc/"
_AIDC_CONFIG = ".aidc/config.json"
_DANGEROUS_FILES = {".env", ".env.local"}
_DANGEROUS_DIRS = {".ssh"}
_ABSOLUTE_WINDOWS_RE = re.compile(r"^[A-Za-z]:[\\/]")
_ABSOLUTE_UNIX_RE = re.compile(r"^/")


def validate_patch_text(patch_text: str) -> dict:
    if "\x00" in patch_text:
        return _build_result(
            status="invalid",
            valid=False,
            targets=[],
            errors=["Patch contains NUL bytes."],
            warnings=[],
            message="Patch failed validation.",
        )

    if not patch_text.strip():
        return _build_result(
            status="empty",
            valid=False,
            targets=[],
            errors=["Patch file is empty."],
            warnings=[],
            message="Patch file is empty.",
        )

    lines = patch_text.splitlines()
    has_diff_git = any(line.startswith(_UNIFIED_DIFF_PREFIX) for line in lines)
    has_old_header = any(line.startswith(_OLD_FILE_PREFIX) for line in lines)
    has_new_header = any(line.startswith(_NEW_FILE_PREFIX) for line in lines)

    if not (has_diff_git or (has_old_header and has_new_header)):
        return _build_result(
            status="invalid",
            valid=False,
            targets=[],
            errors=["Patch does not contain a unified diff header."],
            warnings=[],
            message="Patch failed validation.",
        )

    extracted_targets = extract_patch_targets(patch_text)
    if not extracted_targets:
        return _build_result(
            status="invalid",
            valid=False,
            targets=[],
            errors=["Patch does not contain any target files."],
            warnings=[],
            message="Patch failed validation.",
        )

    warnings: list[str] = []
    for target in extracted_targets:
        error = _validate_target(target)
        if error:
            return _build_result(
                status="invalid",
                valid=False,
                targets=[],
                errors=[error],
                warnings=[],
                message="Patch failed validation.",
            )

        if _is_aidc_generated_report(target):
            warnings.append(f"Patch targets generated file '{target}'.")

    return _build_result(
        status="valid",
        valid=True,
        targets=extracted_targets,
        errors=[],
        warnings=warnings,
        message="Patch format looks safe for dry-run validation.",
    )


def validate_patch_file(root=".", configured_path=None) -> dict:
    patch_path = resolve_patch_path(root=root, configured_path=configured_path)

    if not patch_path.is_file():
        return _build_result(
            status="missing",
            valid=False,
            targets=[],
            errors=["Patch file not found."],
            warnings=[],
            message="Patch file not found.",
        )

    patch_bytes = patch_path.read_bytes()
    if not patch_bytes:
        return _build_result(
            status="empty",
            valid=False,
            targets=[],
            errors=["Patch file is empty."],
            warnings=[],
            message="Patch file is empty.",
        )

    patch_text = patch_bytes.decode("utf-8", errors="replace")
    validation = validate_patch_text(patch_text)

    if validation.get("status") != "valid":
        return validation

    create_targets = _extract_create_targets(patch_text)
    if not create_targets:
        return validation

    root_path = Path(root)
    for target in create_targets:
        target_path = _resolve_target_path(root_path, target)
        if target_path is None:
            continue

        if target_path.exists():
            return _build_result(
                status="invalid",
                valid=False,
                targets=[],
                errors=[f"Target file already exists for creation: {target}"],
                warnings=[],
                message="Patch failed validation.",
            )

    return validation


def extract_patch_targets(patch_text: str) -> list[str]:
    targets: list[str] = []
    seen: set[str] = set()

    for line in patch_text.splitlines():
        if line.startswith(_UNIFIED_DIFF_PREFIX):
            parts = line.split()
            if len(parts) >= 4:
                _add_target(parts[2], targets, seen)
                _add_target(parts[3], targets, seen)
            continue

        if line.startswith(_OLD_FILE_PREFIX):
            _add_target(line[len(_OLD_FILE_PREFIX):], targets, seen)
            continue

        if line.startswith(_NEW_FILE_PREFIX):
            _add_target(line[len(_NEW_FILE_PREFIX):], targets, seen)

    return targets


def _add_target(raw_path: str, targets: list[str], seen: set[str]) -> None:
    normalized = _normalize_patch_path(raw_path)
    if normalized is None or normalized in seen:
        return

    seen.add(normalized)
    targets.append(normalized)


def _normalize_patch_path(raw_path: str) -> str | None:
    path = raw_path.split("\t", 1)[0].strip()
    if not path or path == _DEV_NULL:
        return None

    path = path.replace("\\", "/")
    if path.startswith(_A_PREFIX):
        path = path[len(_A_PREFIX):]
    elif path.startswith(_B_PREFIX):
        path = path[len(_B_PREFIX):]

    path = path.strip()
    if not path or path == _DEV_NULL:
        return None

    while "//" in path:
        path = path.replace("//", "/")

    return path


def _validate_target(target: str) -> str | None:
    if _is_absolute_path(target):
        return f"Patch targets absolute path '{target}'."

    parts = [part for part in target.split("/") if part]
    if not parts:
        return "Patch does not contain any target files."

    if ".." in parts:
        return f"Patch targets parent traversal path '{target}'."

    if ".git" in parts:
        return f"Patch targets forbidden .git path '{target}'."

    if any(part in _DANGEROUS_FILES for part in parts):
        return f"Patch targets dangerous file '{target}'."

    if ".ssh" in parts:
        return f"Patch targets dangerous path '{target}'."

    if target == _AIDC_CONFIG:
        return f"Patch targets forbidden config file '{target}'."

    return None


def _extract_create_targets(patch_text: str) -> list[str]:
    targets: list[str] = []
    current_file: dict[str, object] | None = None

    for line in patch_text.splitlines():
        if line.startswith(_UNIFIED_DIFF_PREFIX):
            if current_file is not None:
                target = _finalize_patch_file_section(current_file)
                if target is not None and target not in targets:
                    targets.append(target)
            current_file = _new_patch_file_section()
            parts = line[len(_UNIFIED_DIFF_PREFIX):].split()
            if len(parts) >= 2:
                current_file["diff_old_path"] = _normalize_header_path(parts[0])
                current_file["diff_new_path"] = _normalize_header_path(parts[1])
            continue

        if current_file is None and (
            line.startswith(_OLD_FILE_PREFIX)
            or line.startswith(_NEW_FILE_PREFIX)
            or line.startswith("new file mode ")
            or line.startswith("deleted file mode ")
        ):
            current_file = _new_patch_file_section()

        if current_file is None:
            continue

        if line.startswith("new file mode "):
            current_file["new_file_mode"] = True
            continue

        if line.startswith(_OLD_FILE_PREFIX):
            current_file["old_path"] = _normalize_header_path(line[len(_OLD_FILE_PREFIX):])
            continue

        if line.startswith(_NEW_FILE_PREFIX):
            current_file["new_path"] = _normalize_header_path(line[len(_NEW_FILE_PREFIX):])
            continue

    if current_file is not None:
        target = _finalize_patch_file_section(current_file)
        if target is not None and target not in targets:
            targets.append(target)

    return targets


def _new_patch_file_section() -> dict[str, object]:
    return {
        "diff_old_path": None,
        "diff_new_path": None,
        "old_path": None,
        "new_path": None,
        "new_file_mode": False,
    }


def _finalize_patch_file_section(current_file: dict[str, object]) -> str | None:
    diff_new_path = current_file.get("diff_new_path")
    old_path = current_file.get("old_path")
    new_path = current_file.get("new_path")
    new_file_mode = bool(current_file.get("new_file_mode"))

    if old_path == "/dev/null" and new_path not in {None, "/dev/null"}:
        return str(new_path)

    if new_path == "/dev/null" and old_path not in {None, "/dev/null"}:
        return None

    if old_path and new_path and old_path == new_path:
        if new_file_mode:
            return str(new_path)
        return None

    if new_file_mode and new_path not in {None, "/dev/null"}:
        return str(new_path)

    if new_file_mode and diff_new_path not in {None, "/dev/null"}:
        return str(diff_new_path)

    return None


def _normalize_header_path(raw_path: str) -> str | None:
    path = raw_path.split("\t", 1)[0].strip()
    if not path:
        return None

    if path == _DEV_NULL:
        return _DEV_NULL

    path = path.replace("\\", "/")
    if path.startswith(_A_PREFIX):
        path = path[len(_A_PREFIX):]
    elif path.startswith(_B_PREFIX):
        path = path[len(_B_PREFIX):]

    path = path.strip()
    if not path:
        return None

    while "//" in path:
        path = path.replace("//", "/")

    return path


def _resolve_target_path(root_path: Path, target: str) -> Path | None:
    resolved_root = root_path.resolve()
    resolved_target = (resolved_root / Path(target)).resolve()

    try:
        resolved_target.relative_to(resolved_root)
    except ValueError:
        return None

    return resolved_target


def _is_aidc_generated_report(target: str) -> bool:
    return target.startswith(_AIDC_PREFIX) and target != _AIDC_CONFIG


def _is_absolute_path(path: str) -> bool:
    return bool(_ABSOLUTE_WINDOWS_RE.match(path) or _ABSOLUTE_UNIX_RE.match(path))


def _build_result(
    *,
    status: str,
    valid: bool,
    targets: list[str] | None,
    errors: list[str] | None,
    warnings: list[str] | None,
    message: str,
) -> dict:
    return {
        "status": status,
        "valid": valid,
        "targets": list(targets or []),
        "errors": list(errors or []),
        "warnings": list(warnings or []),
        "message": message,
    }
