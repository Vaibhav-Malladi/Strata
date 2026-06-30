from __future__ import annotations

import os
import re
from pathlib import Path
from tempfile import NamedTemporaryFile

from strata.patch.contract import read_patch_text, resolve_patch_path
from strata.patch.validator import validate_patch_file, validate_patch_text

_DIFF_GIT_PREFIX = "diff --git "
_OLD_FILE_PREFIX = "--- "
_NEW_FILE_PREFIX = "+++ "
_HUNK_PREFIX = "@@ "
_NO_NEWLINE_MARKER = r"\ No newline at end of file"
_UNSUPPORTED_PREFIXES = (
    "rename from ",
    "rename to ",
    "old mode ",
    "new mode ",
    "similarity index ",
    "dissimilarity index ",
    "Binary files ",
    "GIT binary patch",
)
_HUNK_HEADER_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?: .*)?$")


def apply_patch_file(root: str = ".", configured_path=None) -> dict:
    patch_path = resolve_patch_path(root=root, configured_path=configured_path)
    patch_text = read_patch_text(root=root, configured_path=configured_path)

    if not patch_path.is_file():
        validation = validate_patch_file(root=root, configured_path=configured_path)
        return _build_failure_result(
            targets=validation.get("targets", []),
            errors=validation.get("errors", []),
            warnings=validation.get("warnings", []),
            message=validation.get("message", "Patch was not applied."),
        )

    return apply_patch_text(root=root, patch_text=patch_text)


def apply_patch_text(root: str, patch_text: str) -> dict:
    normalized_patch_text = _normalize_text_newlines(patch_text)
    validation = validate_patch_text(normalized_patch_text, root=root)

    if not validation.get("valid"):
        return _build_failure_result(
            targets=validation.get("targets", []),
            errors=validation.get("errors", []),
            warnings=validation.get("warnings", []),
            message=validation.get("message", "Patch was not applied."),
        )

    parse_result = parse_unified_diff(normalized_patch_text)

    if parse_result.get("status") != "parsed":
        return _build_failure_result(
            targets=list(validation.get("targets", [])),
            errors=list(parse_result.get("errors", [])),
            warnings=list(validation.get("warnings", [])),
            message="Patch was not applied.",
        )

    root_path = Path(root)
    file_patches = list(parse_result.get("files", []))
    targets = [str(file_patch["target"]) for file_patch in file_patches]
    warnings = list(validation.get("warnings", []))

    planned_changes: list[dict[str, object]] = []

    for file_patch in file_patches:
        target = str(file_patch["target"])
        target_path = _resolve_target_path(root_path, target)

        if target_path is None:
            return _build_failure_result(
                targets=targets,
                errors=[f"Patch target escapes root: {target}."],
                warnings=warnings,
                message="Patch was not applied.",
            )

        operation = str(file_patch["operation"])
        original_lines, setup_error = _load_original_lines(target_path, operation)

        if setup_error is not None:
            return _build_failure_result(
                targets=targets,
                errors=[setup_error],
                warnings=warnings,
                message="Patch was not applied.",
            )

        applied_lines, hunk_error = _apply_file_hunks(
            target=target,
            original_lines=original_lines,
            file_patch=file_patch,
        )

        if hunk_error is not None:
            return _build_failure_result(
                targets=targets,
                errors=[hunk_error],
                warnings=warnings,
                message="Patch was not applied.",
            )

        planned_changes.append(
            {
                "operation": operation,
                "target": target,
                "target_path": target_path,
                "original_exists": target_path.exists(),
                "original_bytes": target_path.read_bytes() if target_path.exists() else b"",
                "applied_lines": applied_lines,
            }
        )

    applied_paths: list[Path] = []

    try:
        for change in planned_changes:
            target_path = Path(change["target_path"])
            operation = str(change["operation"])

            if operation == "delete":
                if target_path.exists():
                    target_path.unlink()
                applied_paths.append(target_path)
                continue

            parent = target_path.parent
            parent.mkdir(parents=True, exist_ok=True)
            content = "".join(str(line) for line in change["applied_lines"])

            with NamedTemporaryFile(
                "w",
                encoding="utf-8",
                newline="",
                delete=False,
                dir=str(parent),
            ) as handle:
                handle.write(content)
                temp_path = Path(handle.name)

            os.replace(temp_path, target_path)
            applied_paths.append(target_path)
    except Exception as error:
        _rollback_changes(planned_changes, applied_paths)
        return _build_failure_result(
            targets=targets,
            errors=[f"Patch was not applied: {error}"],
            warnings=warnings,
            message="Patch was not applied.",
        )

    changed_files = [str(change["target"]) for change in planned_changes]
    return _build_success_result(
        targets=targets,
        changed_files=changed_files,
        warnings=warnings,
        message="Patch applied successfully.",
    )


def parse_unified_diff(patch_text: str) -> dict:
    lines = patch_text.splitlines(keepends=True)
    files: list[dict[str, object]] = []
    errors: list[str] = []
    warnings: list[str] = []

    current_file: dict[str, object] | None = None
    current_hunk: dict[str, object] | None = None
    index = 0

    while index < len(lines):
        raw_line = lines[index]
        line = raw_line.rstrip("\r\n")

        if current_hunk is not None:
            if line.startswith(_NO_NEWLINE_MARKER):
                index += 1
                continue

            if line.startswith(" ") or line.startswith("+") or line.startswith("-"):
                current_hunk["lines"].append(raw_line)
                index += 1
                continue

            current_file["hunks"].append(current_hunk)
            current_hunk = None
            continue

        if line.startswith(_DIFF_GIT_PREFIX):
            if current_file is not None:
                if not _finalize_current_file(current_file, files, errors):
                    break

            current_file = _start_file_entry_from_diff_git(line)
            index += 1
            continue

        if line.startswith(_OLD_FILE_PREFIX):
            if current_file is not None and _is_file_complete(current_file):
                if not _finalize_current_file(current_file, files, errors):
                    break
                current_file = None
                continue

            if current_file is None:
                current_file = _new_file_entry()

            current_file["old_path"] = _normalize_header_path(line[len(_OLD_FILE_PREFIX):])
            index += 1
            continue

        if line.startswith(_NEW_FILE_PREFIX):
            if current_file is None or current_file.get("old_path") is None:
                errors.append("Patch contains a new-file header before an old-file header.")
                break

            current_file["new_path"] = _normalize_header_path(line[len(_NEW_FILE_PREFIX):])
            index += 1
            continue

        if line.startswith(_HUNK_PREFIX):
            if current_file is None or current_file.get("old_path") is None or current_file.get("new_path") is None:
                errors.append("Patch contains a hunk before file headers.")
                break

            hunk = _parse_hunk_header(line)

            if hunk is None:
                errors.append(f"Invalid unified diff hunk header: {line}")
                break

            current_hunk = hunk
            index += 1
            continue

        if _is_unsupported_line(line):
            errors.append(f"Unsupported patch feature: {line}")
            break

        if not line.strip():
            index += 1
            continue

        if line.startswith("index ") and current_file is not None:
            index += 1
            continue

        if line.startswith("new file mode ") or line.startswith("deleted file mode "):
            mode = line.split(" ", 3)[-1].strip()

            if mode == "100644":
                index += 1
                continue

            errors.append(f"Unsupported patch feature: {line}")
            break

        errors.append(f"Unsupported patch line: {line}")
        break

    if not errors:
        if current_hunk is not None:
            current_file["hunks"].append(current_hunk)

        if current_file is not None and not _finalize_current_file(current_file, files, errors):
            pass

    if not errors and not files:
        errors.append("Patch does not contain any file sections.")

    status = "parsed" if not errors else "invalid"
    message = "Patch parsed successfully." if not errors else "Patch parsing failed."

    return {
        "status": status,
        "files": files,
        "targets": [str(file_patch["target"]) for file_patch in files],
        "errors": list(errors),
        "warnings": list(warnings),
        "message": message,
    }


def _finalize_current_file(
    current_file: dict[str, object],
    files: list[dict[str, object]],
    errors: list[str],
) -> bool:
    if current_file.get("hunks") is None or not current_file["hunks"]:
        target = _current_file_target(current_file)
        errors.append(f"Patch for {target} does not contain any hunks.")
        return False

    target = _current_file_target(current_file)
    if target is None:
        errors.append("Patch does not contain any target files.")
        return False

    old_path = str(current_file.get("old_path") or "")
    new_path = str(current_file.get("new_path") or "")

    if old_path == new_path:
        operation = "modify"
        target_path = old_path
    elif old_path == "/dev/null" and new_path != "/dev/null":
        operation = "create"
        target_path = new_path
    elif new_path == "/dev/null" and old_path != "/dev/null":
        operation = "delete"
        target_path = old_path
    else:
        errors.append(f"Rename patches are not supported for '{target}'.")
        return False

    current_file["operation"] = operation
    current_file["target"] = target_path
    files.append(
        {
            "operation": operation,
            "target": target_path,
            "old_path": old_path,
            "new_path": new_path,
            "hunks": [
                {
                    "old_start": int(hunk["old_start"]),
                    "old_count": int(hunk["old_count"]),
                    "new_start": int(hunk["new_start"]),
                    "new_count": int(hunk["new_count"]),
                    "lines": list(hunk["lines"]),
                }
                for hunk in current_file["hunks"]
            ],
        }
    )
    return True


def _current_file_target(current_file: dict[str, object]) -> str | None:
    old_path = current_file.get("old_path")
    new_path = current_file.get("new_path")

    if old_path == "/dev/null" and new_path not in {None, "/dev/null"}:
        return str(new_path)

    if new_path == "/dev/null" and old_path not in {None, "/dev/null"}:
        return str(old_path)

    if old_path and new_path and old_path == new_path:
        return str(old_path)

    if old_path and not new_path:
        return str(old_path)

    if new_path and not old_path:
        return str(new_path)

    return None


def _start_file_entry_from_diff_git(line: str) -> dict[str, object]:
    parts = line[len(_DIFF_GIT_PREFIX):].split()
    current_file = _new_file_entry()

    if len(parts) >= 2:
        current_file["diff_old_path"] = _normalize_header_path(parts[0])
        current_file["diff_new_path"] = _normalize_header_path(parts[1])
        current_file["old_path"] = current_file["diff_old_path"]
        current_file["new_path"] = current_file["diff_new_path"]

    return current_file


def _new_file_entry() -> dict[str, object]:
    return {
        "diff_old_path": None,
        "diff_new_path": None,
        "old_path": None,
        "new_path": None,
        "operation": None,
        "target": None,
        "hunks": [],
    }


def _parse_hunk_header(line: str) -> dict[str, object] | None:
    match = _HUNK_HEADER_RE.match(line)

    if match is None:
        return None

    old_start = int(match.group(1))
    old_count = int(match.group(2) or "1")
    new_start = int(match.group(3))
    new_count = int(match.group(4) or "1")

    return {
        "old_start": old_start,
        "old_count": old_count,
        "new_start": new_start,
        "new_count": new_count,
        "lines": [],
    }


def _apply_file_hunks(
    *,
    target: str,
    original_lines: list[str],
    file_patch: dict[str, object],
) -> tuple[list[str] | None, str | None]:
    result_lines: list[str] = []
    cursor = 0
    offset = 0

    hunks = list(file_patch["hunks"])

    for hunk in hunks:
        old_start = int(hunk["old_start"])
        old_count = int(hunk["old_count"])
        new_count = int(hunk["new_count"])
        expected_cursor = (old_start - 1 if old_start > 0 else 0) + offset

        if expected_cursor < 0 or expected_cursor > len(original_lines):
            return None, f"Hunk failed for {target}."

        if cursor != expected_cursor:
            return None, f"Hunk failed for {target}."

        result_lines.extend(original_lines[cursor:expected_cursor])
        hunk_cursor = expected_cursor
        old_consumed = 0
        new_consumed = 0

        for raw_line in hunk["lines"]:
            if raw_line.startswith(_NO_NEWLINE_MARKER):
                continue

            prefix = raw_line[:1]

            if prefix == " ":
                if hunk_cursor >= len(original_lines) or original_lines[hunk_cursor] != raw_line[1:]:
                    return None, f"Hunk failed for {target}."
                result_lines.append(original_lines[hunk_cursor])
                hunk_cursor += 1
                old_consumed += 1
                new_consumed += 1
                continue

            if prefix == "-":
                if hunk_cursor >= len(original_lines) or original_lines[hunk_cursor] != raw_line[1:]:
                    return None, f"Hunk failed for {target}."
                hunk_cursor += 1
                old_consumed += 1
                continue

            if prefix == "+":
                result_lines.append(raw_line[1:])
                new_consumed += 1
                continue

            return None, f"Hunk failed for {target}."

        if old_consumed != old_count or new_consumed != new_count:
            return None, f"Hunk failed for {target}."

        cursor = hunk_cursor
        offset += new_count - old_count

    result_lines.extend(original_lines[cursor:])
    return result_lines, None


def _load_original_lines(target_path: Path, operation: str) -> tuple[list[str], str | None]:
    if operation == "create":
        if target_path.exists():
            return [], f"Target file already exists for creation: {target_path}."
        return [], None

    if not target_path.exists():
        return [], f"Target file not found for {operation}: {target_path}."

    if target_path.is_dir():
        return [], f"Target path is a directory: {target_path}."

    return target_path.read_text(encoding="utf-8").splitlines(keepends=True), None


def _resolve_target_path(root_path: Path, target: str) -> Path | None:
    resolved_root = root_path.resolve()
    resolved_target = (resolved_root / Path(target)).resolve()

    try:
        resolved_target.relative_to(resolved_root)
    except ValueError:
        return None

    return resolved_target


def _rollback_changes(planned_changes: list[dict[str, object]], applied_paths: list[Path]) -> None:
    for change in reversed(planned_changes):
        target_path = Path(change["target_path"])

        if target_path not in applied_paths:
            continue

        operation = str(change["operation"])
        original_exists = bool(change["original_exists"])
        original_bytes = bytes(change["original_bytes"])

        try:
            if operation == "delete":
                target_path.write_bytes(original_bytes)
            elif original_exists:
                target_path.write_bytes(original_bytes)
            elif target_path.exists():
                target_path.unlink()
        except OSError:
            pass


def _is_unsupported_line(line: str) -> bool:
    return any(line.startswith(prefix) for prefix in _UNSUPPORTED_PREFIXES)


def _normalize_header_path(raw_path: str) -> str | None:
    path = raw_path.split("\t", 1)[0].strip()

    if not path or path == "/dev/null":
        return "/dev/null" if path == "/dev/null" else None

    path = path.replace("\\", "/")

    if path.startswith("a/") or path.startswith("b/"):
        path = path[2:]

    while "//" in path:
        path = path.replace("//", "/")

    return path or None


def _normalize_text_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _is_file_complete(current_file: dict[str, object]) -> bool:
    return bool(
        current_file.get("old_path")
        and current_file.get("new_path")
        and current_file.get("hunks")
    )


def _build_success_result(*, targets: list[str], changed_files: list[str], warnings: list[str], message: str) -> dict:
    return {
        "status": "applied",
        "applied": True,
        "targets": list(targets),
        "changed_files": list(changed_files),
        "errors": [],
        "warnings": list(warnings),
        "message": message,
    }


def _build_failure_result(*, targets: list[str], errors: list[str], warnings: list[str], message: str) -> dict:
    return {
        "status": "failed",
        "applied": False,
        "targets": list(targets),
        "changed_files": [],
        "errors": list(errors),
        "warnings": list(warnings),
        "message": message,
    }
