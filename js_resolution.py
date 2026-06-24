from __future__ import annotations

import json
import os
from pathlib import Path


IGNORED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".aidc",
    "node_modules",
    "dist",
    "build",
    "coverage",
    ".next",
    "out",
    ".angular",
    ".turbo",
    ".vite",
    ".cache",
    "vendor",
}


JS_TS_SOURCE_EXTENSIONS = (
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
)


EXACT_IMPORT_EXTENSIONS = JS_TS_SOURCE_EXTENSIONS + (".json",)


def load_json_file(path: str | Path) -> dict:
    """Load a JSON file and return a fresh dict on failure or non-dict input."""

    if path is None or str(path).strip() == "":
        return {}

    path_obj = Path(path)

    try:
        raw_text = path_obj.read_text(encoding="utf-8")
    except OSError:
        return {}

    try:
        loaded = json.loads(raw_text)
    except json.JSONDecodeError:
        return {}

    if isinstance(loaded, dict):
        return dict(loaded)

    return {}


def find_nearest_config(
    start_dir: str | Path,
    names: tuple[str, ...] = ("tsconfig.json", "jsconfig.json"),
) -> Path | None:
    """Find the nearest matching config file by walking up parent directories."""

    current = Path(start_dir)
    if current.is_file():
        current = current.parent
    elif not current.exists():
        current = current.parent

    for directory in [current, *current.parents]:
        for name in names:
            candidate = directory / name
            if candidate.is_file():
                return candidate

    return None


def load_tsconfig_paths(root: str | Path) -> dict:
    """Load heuristic tsconfig/jsconfig path aliases for a repository root."""

    root_path = Path(root)
    config_path = find_nearest_config(root_path)
    raw_config = load_json_file(config_path) if config_path else {}
    compiler_options = raw_config.get("compilerOptions", {})

    if not isinstance(compiler_options, dict):
        compiler_options = {}

    base_url = compiler_options.get("baseUrl", "")
    if not isinstance(base_url, str):
        base_url = ""

    raw_paths = compiler_options.get("paths", {})
    normalized_paths: list[dict] = []

    if isinstance(raw_paths, dict):
        for pattern, targets in raw_paths.items():
            normalized_targets = _normalize_target_list(targets)

            if not normalized_targets:
                continue

            normalized_paths.append(
                {
                    "pattern": str(pattern),
                    "targets": normalized_targets,
                }
            )

    normalized_paths.sort(key=lambda item: _alias_sort_key(item["pattern"]))

    return {
        "config_path": str(config_path) if config_path else None,
        "base_url": _normalize_relative_path(base_url) if base_url else "",
        "paths": {item["pattern"]: list(item["targets"]) for item in normalized_paths},
        "patterns": [
            {
                "pattern": item["pattern"],
                "targets": list(item["targets"]),
            }
            for item in normalized_paths
        ],
        "raw": raw_config,
    }


def load_package_json(root: str | Path) -> dict:
    """Load the repository root package.json heuristically."""

    root_path = Path(root)
    package_path = root_path / "package.json"
    package_data = load_json_file(package_path)

    return {
        "package_path": str(package_path) if package_path.is_file() else None,
        "name": str(package_data.get("name", "")),
        "workspaces": _extract_workspace_patterns(package_data),
        "raw": package_data,
    }


def build_js_resolution_context(root: str | Path) -> dict:
    """Build a deterministic repository-local JS/TS resolution context."""

    root_path = Path(root)
    source_file_index = _build_source_file_index(root_path)
    tsconfig = load_tsconfig_paths(root_path)
    package_json = load_package_json(root_path)
    workspace_packages = _discover_workspace_packages(root_path, package_json)
    package_entries = _collect_package_entries(root_path, package_json, workspace_packages)

    return {
        "root": str(root_path),
        "source_file_index": source_file_index,
        "source_files": list(source_file_index.keys()),
        "tsconfig": tsconfig,
        "package_json": package_json,
        "workspace_packages": workspace_packages,
        "package_entries": package_entries,
    }


def resolve_js_import(
    root: str | Path,
    importer_path: str | Path,
    import_source: str,
    context: dict | None = None,
) -> dict:
    """Resolve a JS/TS import or re-export source to a repository-local file."""

    root_path = Path(root)
    context = context or build_js_resolution_context(root_path)
    source = str(import_source).strip()
    resolved = _resolution_result(source)

    if not source:
        resolved["reason"] = "empty import source"
        return resolved

    source_file_index = context.get("source_file_index", {})
    tsconfig = context.get("tsconfig", {})
    package_entries = context.get("package_entries", [])

    if _is_relative_source(source):
        candidate_result = _resolve_relative_source(
            root_path,
            importer_path,
            source,
            source_file_index,
        )
        return candidate_result

    tsconfig_result = _resolve_tsconfig_source(
        source,
        source_file_index,
        tsconfig,
    )
    if tsconfig_result is not None:
        return tsconfig_result

    package_result = _resolve_package_source(
        source,
        source_file_index,
        package_entries,
    )
    if package_result is not None:
        return package_result

    if _looks_like_path_alias(source):
        resolved["status"] = "path_alias"
        resolved["reason"] = "alias-like import did not match local tsconfig or package mappings"
        return resolved

    resolved["status"] = "external"
    resolved["reason"] = "bare package import"
    return resolved


def _build_source_file_index(root_path: Path) -> dict:
    source_file_index: dict[str, str] = {}

    for current_dir, dir_names, file_names in os.walk(root_path):
        dir_names[:] = [
            name for name in sorted(dir_names)
            if name not in IGNORED_DIRS
        ]

        for file_name in sorted(file_names):
            file_path = Path(current_dir) / file_name
            if not _is_source_file(file_path):
                continue

            rel_path = _relative_to_root(root_path, file_path)
            source_file_index[rel_path] = rel_path

    return source_file_index


def _discover_workspace_packages(root_path: Path, package_json: dict) -> list[dict]:
    package_data = package_json.get("raw", {})
    workspace_patterns = _extract_workspace_patterns(package_data)
    discovered_packages: list[dict] = []
    seen_paths = set()

    for pattern in workspace_patterns:
        for workspace_dir in sorted(root_path.glob(pattern), key=lambda path: str(path)):
            if not workspace_dir.is_dir():
                continue

            package_path = workspace_dir / "package.json"
            if not package_path.is_file():
                continue

            normalized_package_path = os.path.normpath(str(package_path))
            if normalized_package_path in seen_paths:
                continue

            package_data = load_json_file(package_path)
            package_name = str(package_data.get("name", "")).strip()
            if not package_name:
                continue

            seen_paths.add(normalized_package_path)
            discovered_packages.append(
                {
                    "name": package_name,
                    "root": _relative_to_root(root_path, workspace_dir),
                    "package_path": normalized_package_path,
                    "raw": package_data,
                    "is_root": False,
                }
            )

    discovered_packages.sort(
        key=lambda item: (
            -len(item.get("name", "")),
            item.get("name", ""),
            item.get("root", ""),
        )
    )

    return discovered_packages


def _collect_package_entries(
    root_path: Path,
    package_json: dict,
    workspace_packages: list[dict],
) -> list[dict]:
    package_entries: list[dict] = []
    root_package_name = str(package_json.get("name", "")).strip()

    if root_package_name:
        package_entries.append(
            {
                "name": root_package_name,
                "root": ".",
                "package_path": package_json.get("package_path"),
                "raw": package_json.get("raw", {}),
                "is_root": True,
            }
        )

    for workspace_package in workspace_packages:
        package_entries.append(
            {
                "name": str(workspace_package.get("name", "")).strip(),
                "root": str(workspace_package.get("root", "")).strip() or ".",
                "package_path": workspace_package.get("package_path"),
                "raw": workspace_package.get("raw", {}),
                "is_root": False,
            }
        )

    package_entries.sort(
        key=lambda item: (
            -len(item.get("name", "")),
            item.get("name", ""),
            item.get("root", ""),
        )
    )

    return package_entries


def _extract_workspace_patterns(package_data: dict) -> list[str]:
    workspaces = package_data.get("workspaces")

    patterns: list[str] = []

    if isinstance(workspaces, list):
        patterns.extend(
            str(item)
            for item in workspaces
            if isinstance(item, (str, Path))
        )
    elif isinstance(workspaces, dict):
        workspace_packages = workspaces.get("packages")
        if isinstance(workspace_packages, list):
            patterns.extend(
                str(item)
                for item in workspace_packages
                if isinstance(item, (str, Path))
            )

    return _dedupe_preserve_order(patterns)


def _normalize_target_list(targets: object) -> list[str]:
    if isinstance(targets, str):
        return [targets]

    if not isinstance(targets, list):
        return []

    normalized_targets = [
        str(target)
        for target in targets
        if isinstance(target, (str, Path))
    ]

    return _dedupe_preserve_order(normalized_targets)


def _is_source_file(path: str | Path) -> bool:
    return Path(path).suffix.lower() in JS_TS_SOURCE_EXTENSIONS


def _is_relative_source(import_source: str) -> bool:
    return import_source.startswith("./") or import_source.startswith("../")


def _looks_like_path_alias(import_source: str) -> bool:
    return import_source.startswith("@/") or import_source.startswith("~/")


def _resolve_relative_source(
    root_path: Path,
    importer_path: str | Path,
    import_source: str,
    source_file_index: dict,
) -> dict:
    importer_dir = Path(_relative_to_root(root_path, Path(importer_path))).parent
    base_relative = _normalize_relative_path(importer_dir / import_source)
    candidates = _expand_source_candidates(base_relative)
    resolved = _resolution_result(import_source)
    resolved["candidates"] = list(candidates)

    for candidate in candidates:
        if candidate in source_file_index:
            resolved["status"] = "resolved"
            resolved["resolved_path"] = candidate
            resolved["reason"] = "relative import resolved to local source file"
            return resolved

    resolved["reason"] = "relative import did not match a local source file"
    return resolved


def _resolve_tsconfig_source(
    import_source: str,
    source_file_index: dict,
    tsconfig: dict,
) -> dict | None:
    patterns = tsconfig.get("patterns", [])
    if not patterns:
        return None

    base_url = tsconfig.get("base_url", "")
    matched_alias = False
    candidates: list[str] = []

    for pattern in patterns:
        pattern_name = str(pattern.get("pattern", ""))
        wildcard = _match_alias_pattern(pattern_name, import_source)

        if wildcard is None:
            continue

        matched_alias = True

        for target in pattern.get("targets", []):
            target_path = _apply_wildcard(str(target), wildcard)
            target_path = _join_base_url(base_url, target_path)
            target_candidates = _expand_source_candidates(target_path)
            candidates.extend(target_candidates)

            for candidate in target_candidates:
                if candidate in source_file_index:
                    return {
                        "status": "resolved",
                        "source": import_source,
                        "resolved_path": candidate,
                        "reason": f"tsconfig alias {pattern_name!r} resolved to local file",
                        "candidates": _dedupe_preserve_order(candidates),
                    }

    if matched_alias:
        return {
            "status": "path_alias",
            "source": import_source,
            "resolved_path": None,
            "reason": "tsconfig alias matched but no local file was found",
            "candidates": _dedupe_preserve_order(candidates),
        }

    return None


def _resolve_package_source(
    import_source: str,
    source_file_index: dict,
    package_entries: list[dict],
) -> dict | None:
    matched_entry = None
    remainder = ""

    for entry in package_entries:
        package_name = str(entry.get("name", "")).strip()
        if not package_name:
            continue

        if import_source == package_name:
            matched_entry = entry
            remainder = ""
            break

        prefix = package_name + "/"
        if import_source.startswith(prefix):
            matched_entry = entry
            remainder = import_source[len(prefix) :]
            break

    if matched_entry is None:
        return None

    candidates = _package_candidates(matched_entry, remainder)
    result = {
        "status": "path_alias",
        "source": import_source,
        "resolved_path": None,
        "reason": f"package reference {matched_entry.get('name', '')!r} did not match a local file",
        "candidates": list(candidates),
    }

    for candidate in candidates:
        if candidate in source_file_index:
            result["status"] = "resolved"
            result["resolved_path"] = candidate
            result["reason"] = f"package reference {matched_entry.get('name', '')!r} resolved to local file"
            return result

    return result


def _package_candidates(entry: dict, remainder: str) -> list[str]:
    package_root = str(entry.get("root", "")).strip() or "."
    is_root = bool(entry.get("is_root"))
    candidates: list[str] = []

    if remainder:
        if is_root:
            candidates.append(remainder)
            if not remainder.startswith("src/"):
                candidates.append(os.path.join("src", remainder))
        else:
            candidates.append(os.path.join(package_root, remainder))
            candidates.append(os.path.join(package_root, "src", remainder))
    else:
        candidates.append(os.path.join(package_root, "src", "index"))
        candidates.append(os.path.join(package_root, "index"))

    expanded = []
    for candidate in candidates:
        expanded.extend(_expand_source_candidates(candidate))

    return _dedupe_preserve_order(expanded)


def _expand_source_candidates(base_relative: str) -> list[str]:
    normalized = _normalize_relative_path(base_relative)
    extension = Path(normalized).suffix.lower()
    basename = Path(normalized).name

    if extension in EXACT_IMPORT_EXTENSIONS:
        return [normalized]

    candidates = [normalized + source_extension for source_extension in JS_TS_SOURCE_EXTENSIONS]

    if basename != "index":
        for source_extension in JS_TS_SOURCE_EXTENSIONS:
            candidates.append(
                _normalize_relative_path(Path(normalized) / f"index{source_extension}")
            )

    return _dedupe_preserve_order(candidates)


def _apply_wildcard(target: str, wildcard: str) -> str:
    return target.replace("*", wildcard)


def _join_base_url(base_url: str, target_path: str) -> str:
    if not base_url or base_url in {".", "./"}:
        return _normalize_relative_path(target_path)

    return _normalize_relative_path(Path(base_url) / target_path)


def _match_alias_pattern(pattern: str, import_source: str) -> str | None:
    if "*" not in pattern:
        return "" if pattern == import_source else None

    if pattern.count("*") != 1:
        return None

    prefix, suffix = pattern.split("*", 1)

    if not import_source.startswith(prefix):
        return None

    if suffix and not import_source.endswith(suffix):
        return None

    end_index = len(import_source) - len(suffix) if suffix else len(import_source)
    wildcard = import_source[len(prefix) : end_index]
    return wildcard


def _alias_sort_key(pattern: str) -> tuple[int, int, str]:
    has_wildcard = 1 if "*" in pattern else 0
    literal_length = len(pattern.replace("*", ""))
    return (has_wildcard, -literal_length, pattern)


def _resolution_result(source: str) -> dict:
    return {
        "status": "unresolved",
        "source": source,
        "resolved_path": None,
        "reason": "",
        "candidates": [],
    }


def _relative_to_root(root_path: Path, path_value: str | Path) -> str:
    return _normalize_relative_path(os.path.relpath(str(path_value), str(root_path)))


def _normalize_relative_path(path_value: str | Path) -> str:
    return Path(str(path_value)).as_posix()


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen = set()
    result = []

    for item in items:
        if item in seen:
            continue

        seen.add(item)
        result.append(item)

    return result
