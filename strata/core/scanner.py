from __future__ import annotations

import codecs
import os
import importlib.util
import sys
import sysconfig
import time
from pathlib import Path
from typing import Any, Callable

from strata.parsers.js_resolution import build_js_resolution_context, resolve_js_import
from strata.parsers.languages import detect_language, parse_source_file
from strata.core.repo_ignore import should_ignore_directory, should_ignore_file


MAX_SOURCE_FILE_SIZE_BYTES = 2 * 1024 * 1024
MAX_SCAN_FILES = 10_000
FILE_SAFETY_CHUNK_BYTES = 64 * 1024
_PARSABLE_LANGUAGES = {"javascript", "python", "typescript"}


_STDLIB_PATHS = {
    os.path.normcase(path)
    for path in (
        sysconfig.get_paths().get("stdlib"),
        sysconfig.get_paths().get("platstdlib"),
    )
    if path
}


def module_name_from_path(root_path: str, file_path: str) -> str:
    relative_path = os.path.relpath(file_path, root_path)
    without_extension = os.path.splitext(relative_path)[0]
    parts = without_extension.split(os.sep)
    return ".".join(parts)


def same_folder_module_path(file_path: str, import_name: str) -> str:
    folder = os.path.dirname(file_path)
    return os.path.normpath(os.path.join(folder, import_name + ".py"))


def is_stdlib_import(import_name: str) -> bool:
    top_level_name = import_name.split(".")[0]

    stdlib_module_names = getattr(sys, "stdlib_module_names", None)
    if stdlib_module_names is not None:
        return top_level_name in stdlib_module_names

    return _is_stdlib_module_39(top_level_name)


def _is_stdlib_module_39(module_name: str) -> bool:
    spec = importlib.util.find_spec(module_name)

    if spec is None:
        return False

    if spec.origin in {"built-in", "frozen"}:
        return True

    origin = getattr(spec, "origin", None)
    if not origin:
        return False

    normalized_origin = os.path.normcase(os.path.abspath(origin))
    return any(normalized_origin.startswith(root) for root in _STDLIB_PATHS)


def is_relative_import(import_name: str) -> bool:
    return import_name.startswith("./") or import_name.startswith("../")


def is_external_import(language: str | None, import_name: str) -> bool:
    if language == "python":
        return is_stdlib_import(import_name)

    if language in {"javascript", "typescript"}:
        return not is_relative_import(import_name)

    return False


def find_import_line(file_info: dict, import_name: str) -> int | None:
    for import_detail in file_info.get("import_details", []):
        if import_detail["name"] == import_name:
            return import_detail["line"]

    return None


def resolve_python_import(
    from_path: str,
    import_name: str,
    module_index: dict,
    path_index: dict,
) -> str | None:
    if import_name in module_index:
        return module_index[import_name]

    same_folder_path = same_folder_module_path(from_path, import_name)

    if same_folder_path in path_index:
        return same_folder_path

    return None


def resolve_import(
    file_info: dict,
    import_name: str,
    module_index: dict,
    path_index: dict,
) -> str | None:
    if file_info.get("language") != "python":
        return None

    return resolve_python_import(
        file_info["path"],
        import_name,
        module_index,
        path_index,
    )


def _js_resolved_path(root_path: str, resolved_path: str) -> str:
    if os.path.isabs(resolved_path):
        return os.path.normpath(resolved_path)

    return os.path.normpath(os.path.join(root_path, resolved_path))


def _record_js_resolution(
    file_info: dict,
    import_name: str,
    resolution: dict,
) -> str | None:
    status = resolution.get("status")

    if status == "resolved":
        return resolution.get("resolved_path")

    detail = {
        "name": import_name,
        "line": find_import_line(file_info, import_name),
        "reason": resolution.get("reason", ""),
    }

    candidates = list(resolution.get("candidates", []))

    if candidates:
        detail["candidates"] = candidates

    if status == "external":
        file_info["external_imports"].append(import_name)
    elif status == "path_alias":
        file_info["path_alias_imports"].append(import_name)
        detail["kind"] = "path_alias"
        file_info["path_alias_import_details"].append(detail)
    else:
        file_info["unresolved_imports"].append(import_name)
        detail["kind"] = "unresolved"
        file_info["unresolved_import_details"].append(detail)

    return None


def scan_repo(
    root_path: str,
    progress: Callable[[dict[str, Any]], None] | None = None,
    expected_file_count: int | None = None,
) -> dict:
    """
    Scan a repository folder and parse all supported source files.
    """

    graph = {
        "schema_version": 1,
        "root": root_path,
        "files": [],
        "edges": [],
    }

    module_index = {}
    path_index = {}
    start_time = time.monotonic()
    discovered_count = 0
    scanned_count = 0
    skipped_count = 0
    failed_count = 0
    limit_reached = False

    _emit_progress(
        progress,
        phase="discovering_files",
        discovered=0,
        scanned=0,
        skipped=0,
        failed=0,
        elapsed=0.0,
        eta=None,
        expected_file_count=expected_file_count,
    )

    for current_dir, dir_names, file_names in os.walk(root_path):
        dir_names[:] = [
            name
            for name in sorted(dir_names)
            if not should_ignore_directory(name)
            and not (Path(current_dir) / name).is_symlink()
        ]
        file_names.sort()

        for file_name in file_names:
            file_path = os.path.join(current_dir, file_name)
            file_path = os.path.normpath(file_path)

            if os.path.islink(file_path) or should_ignore_file(file_path):
                skipped_count += 1
                continue

            if discovered_count >= MAX_SCAN_FILES:
                limit_reached = True
                break

            discovered_count += 1

            language = detect_language(file_path)
            if language not in _PARSABLE_LANGUAGES or not _is_safe_source_file(Path(file_path)):
                skipped_count += 1
                _emit_progress_if_needed(
                    progress,
                    start_time=start_time,
                    discovered_count=discovered_count,
                    scanned_count=scanned_count,
                    skipped_count=skipped_count,
                    failed_count=failed_count,
                    expected_file_count=expected_file_count,
                )
                continue

            try:
                parsed = parse_source_file(file_path)
            except (OSError, UnicodeDecodeError):
                parsed = None

            if parsed is None:
                skipped_count += 1
                _emit_progress_if_needed(
                    progress,
                    start_time=start_time,
                    discovered_count=discovered_count,
                    scanned_count=scanned_count,
                    skipped_count=skipped_count,
                    failed_count=failed_count,
                    expected_file_count=expected_file_count,
                )
                continue

            parsed["path"] = os.path.normpath(parsed["path"])
            parsed["external_imports"] = []
            parsed["unresolved_imports"] = []
            parsed["unresolved_import_details"] = []
            parsed["path_alias_imports"] = []
            parsed["path_alias_import_details"] = []

            graph["files"].append(parsed)
            scanned_count += 1

            error_value = parsed.get("error")
            if error_value:
                failed_count += 1

            module_name = module_name_from_path(root_path, file_path)
            module_index[module_name] = file_path
            path_index[file_path] = file_path

            _emit_progress_if_needed(
                progress,
                start_time=start_time,
                discovered_count=discovered_count,
                scanned_count=scanned_count,
                skipped_count=skipped_count,
                failed_count=failed_count,
                expected_file_count=expected_file_count,
            )

        if limit_reached:
            break

    _emit_progress(
        progress,
        phase="parsing_source_files",
        discovered=discovered_count,
        scanned=scanned_count,
        skipped=skipped_count,
        failed=failed_count,
        elapsed=time.monotonic() - start_time,
        eta=_estimate_eta(
            start_time=start_time,
            processed_count=scanned_count or discovered_count,
            total_count=expected_file_count,
        ),
        expected_file_count=expected_file_count,
    )

    js_files = [
        file_info["path"]
        for file_info in graph["files"]
        if file_info.get("language") in {"javascript", "typescript"}
    ]
    js_resolution_context = (
        build_js_resolution_context(root_path, source_files=js_files)
        if js_files
        else None
    )

    for file_info in graph["files"]:
        from_path = file_info["path"]
        language = detect_language(from_path)

        if language in {"javascript", "typescript"}:
            for import_name in file_info["imports"]:
                resolution = resolve_js_import(
                    root_path,
                    from_path,
                    import_name,
                    js_resolution_context,
                )
                resolved_path = _record_js_resolution(
                    file_info,
                    import_name,
                    resolution,
                )

                if resolved_path is not None:
                    graph["edges"].append(
                        {
                            "from": from_path,
                            "to": _js_resolved_path(root_path, resolved_path),
                            "type": "imports",
                            "import": import_name,
                        }
                    )

            for export_info in file_info.get("exports", []):
                source = str(export_info.get("source", "")).strip()

                if not source:
                    continue

                resolution = resolve_js_import(
                    root_path,
                    from_path,
                    source,
                    js_resolution_context,
                )

                resolved_path = resolution.get("resolved_path")

                if resolution.get("status") == "resolved" and resolved_path:
                    graph["edges"].append(
                        {
                            "from": from_path,
                            "to": _js_resolved_path(root_path, str(resolved_path)),
                            "type": "imports",
                            "import": source,
                        }
                    )

            continue

        for import_name in file_info["imports"]:
            target_path = resolve_import(
                file_info,
                import_name,
                module_index,
                path_index,
            )

            if target_path is not None:
                graph["edges"].append(
                    {
                        "from": from_path,
                        "to": target_path,
                        "type": "imports",
                        "import": import_name,
                    }
                )
            elif is_external_import(language, import_name):
                file_info["external_imports"].append(import_name)
            else:
                file_info["unresolved_imports"].append(import_name)
                file_info["unresolved_import_details"].append(
                    {
                        "name": import_name,
                        "line": find_import_line(file_info, import_name),
                    }
                )

    _emit_progress(
        progress,
        phase="building_graph",
        discovered=discovered_count,
        scanned=scanned_count,
        skipped=skipped_count,
        failed=failed_count,
        elapsed=time.monotonic() - start_time,
        eta=_estimate_eta(
            start_time=start_time,
            processed_count=scanned_count or discovered_count,
            total_count=expected_file_count,
        ),
        expected_file_count=expected_file_count,
    )

    return graph


def _is_safe_source_file(file_path: Path) -> bool:
    try:
        if not file_path.is_file() or file_path.stat().st_size > MAX_SOURCE_FILE_SIZE_BYTES:
            return False

        decoder = codecs.getincrementaldecoder("utf-8")()
        with file_path.open("rb") as handle:
            while chunk := handle.read(FILE_SAFETY_CHUNK_BYTES):
                if b"\x00" in chunk:
                    return False
                decoder.decode(chunk)
        decoder.decode(b"", final=True)
    except (OSError, UnicodeDecodeError):
        return False

    return True


def _emit_progress(
    progress: Callable[[dict[str, Any]], None] | None,
    *,
    phase: str,
    discovered: int,
    scanned: int,
    skipped: int,
    failed: int,
    elapsed: float,
    eta: str | None,
    expected_file_count: int | None,
) -> None:
    if progress is None:
        return

    progress(
        {
            "phase": phase,
            "discovered": discovered,
            "scanned": scanned,
            "skipped": skipped,
            "failed": failed,
            "elapsed": elapsed,
            "eta": eta or "estimating...",
            "expected_file_count": expected_file_count,
        }
    )


def _emit_progress_if_needed(
    progress: Callable[[dict[str, Any]], None] | None,
    *,
    start_time: float,
    discovered_count: int,
    scanned_count: int,
    skipped_count: int,
    failed_count: int,
    expected_file_count: int | None,
) -> None:
    if progress is None:
        return

    should_emit = scanned_count <= 3 or scanned_count % 100 == 0
    if not should_emit:
        return

    _emit_progress(
        progress,
        phase="parsing_source_files",
        discovered=discovered_count,
        scanned=scanned_count,
        skipped=skipped_count,
        failed=failed_count,
        elapsed=time.monotonic() - start_time,
        eta=_estimate_eta(
            start_time=start_time,
            processed_count=scanned_count or discovered_count,
            total_count=expected_file_count,
        ),
        expected_file_count=expected_file_count,
    )


def _estimate_eta(
    *,
    start_time: float,
    processed_count: int,
    total_count: int | None,
) -> str | None:
    if total_count is None or total_count <= 0 or processed_count <= 0:
        return "estimating..."

    elapsed = max(time.monotonic() - start_time, 0.001)

    if elapsed < 5 and processed_count < 200:
        return "estimating..."

    remaining = max(total_count - processed_count, 0)
    if remaining <= 0:
        return "about 0 sec"

    seconds_per_item = elapsed / processed_count
    eta_seconds = max(int(seconds_per_item * remaining), 0)

    if eta_seconds < 90:
        return f"about {max(1, eta_seconds)} sec"

    minutes = round(eta_seconds / 60)
    if minutes <= 1:
        return "about 1 min"

    return f"about {minutes} min"
