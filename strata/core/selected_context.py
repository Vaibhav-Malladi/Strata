from __future__ import annotations

import os
from difflib import SequenceMatcher
from pathlib import Path
from typing import Sequence

from strata.core.context_matching import detect_file_roles, detect_task_hints, extract_identifier_terms
from strata.core.repo_ignore import should_ignore_directory, should_ignore_path
from snapshot_cache import load_repo_snapshot_cache

_SECRET_FILE_NAMES = {
    "credentials.json",
    "id_dsa",
    "id_rsa",
}

_SECRET_FILE_PREFIXES = (
    ".env",
    "secret.",
    "secrets.",
)

_SECRET_FILE_SUFFIXES = (
    ".key",
    ".pem",
)

_TEST_REFERENCE_TERMS = {"test", "tests", "spec", "specs", "specification"}


def normalize_selected_paths(root_path: str | Path, selected_paths: Sequence[str]) -> list[str]:
    """Validate and normalize user-selected file paths relative to the repo root."""

    root = Path(root_path).resolve()
    normalized: list[str] = []
    seen: set[str] = set()

    for raw_path in selected_paths:
        candidate = str(raw_path or "").strip()

        if not candidate:
            raise ValueError("Selected file path cannot be empty.")

        candidate_path = Path(candidate)
        absolute_candidate = candidate_path if candidate_path.is_absolute() else root / candidate_path

        try:
            resolved_candidate = absolute_candidate.resolve(strict=False)
        except OSError as error:
            raise ValueError(f"Could not resolve selected file: {candidate}") from error

        try:
            relative_path = resolved_candidate.relative_to(root)
        except ValueError as error:
            raise ValueError(f"Selected file is outside the repo root: {candidate}") from error

        if not resolved_candidate.exists():
            raise ValueError(f"Selected file does not exist: {relative_path.as_posix()}")

        if resolved_candidate.is_dir():
            raise ValueError(f"Selected path is a directory, not a file: {relative_path.as_posix()}")

        relative_text = relative_path.as_posix()

        if is_secret_like_path(relative_text):
            raise ValueError("This looks like a secret/credential file and cannot be added to AI context.")

        if is_generated_or_ignored_path(relative_text):
            raise ValueError(f"Selected file is ignored or generated: {relative_text}")

        if relative_text in seen:
            continue

        seen.add(relative_text)
        normalized.append(relative_text)

    return normalized


def resolve_file_references(
    root_path: str | Path,
    references: Sequence[str],
    task: str = "",
) -> dict:
    """Resolve human file references to repo-relative paths."""

    root = Path(root_path).resolve()
    reference_list = [str(reference or "").strip() for reference in references if str(reference or "").strip()]
    task_hints = detect_task_hints(task)
    candidate_catalog = _build_candidate_catalog(root)
    results: list[dict] = []
    resolved_paths: list[str] = []
    notes: list[str] = []

    for reference in reference_list:
        result = resolve_one_file_reference(
            root,
            reference,
            task=task,
            task_hints=task_hints,
            candidate_catalog=candidate_catalog,
        )
        results.append(result)

        if result["status"] != "resolved":
            return {
                "status": result["status"],
                "reference": reference,
                "resolved_paths": resolved_paths,
                "notes": notes,
                "results": results,
                "failed": result,
            }

        resolved_path = str(result["path"])
        resolved_paths.append(resolved_path)

        note = result.get("note")
        if note:
            notes.append(str(note))

    return {
        "status": "resolved",
        "reference": None,
        "resolved_paths": resolved_paths,
        "notes": notes,
        "results": results,
        "failed": None,
    }


def resolve_one_file_reference(
    root_path: str | Path,
    reference: str,
    *,
    task: str = "",
    task_hints: dict | None = None,
    candidate_catalog: Sequence[dict] | None = None,
) -> dict:
    """Resolve one human file reference against the repo."""

    root = Path(root_path).resolve()
    raw_reference = str(reference or "").strip()

    if not raw_reference:
        return {
            "reference": raw_reference,
            "status": "empty",
            "path": None,
            "note": None,
            "message": "Selected file reference cannot be empty.",
            "candidates": [],
            "resolved_by": None,
        }

    resolved_candidate = _resolve_exact_candidate(root, raw_reference)
    if resolved_candidate is not None:
        return resolved_candidate

    catalog = list(candidate_catalog or _build_candidate_catalog(root))
    hints = task_hints if task_hints is not None else detect_task_hints(task)
    if _reference_mentions_tests(raw_reference):
        hints = dict(hints)
        hints["tests"] = True
    scored_candidates = _score_candidate_catalog(raw_reference, catalog, hints)

    if not scored_candidates:
        return {
            "reference": raw_reference,
            "status": "missing",
            "path": None,
            "note": None,
            "message": f"No file matched: {raw_reference}",
            "candidates": [],
            "resolved_by": None,
        }

    best = scored_candidates[0]
    second = scored_candidates[1] if len(scored_candidates) > 1 else None

    if _can_auto_resolve(best, second, len(scored_candidates)):
        resolved_path = best["path"]
        note = None if _is_exact_path_reference(raw_reference, resolved_path) else f"{raw_reference} -> {resolved_path}"
        return {
            "reference": raw_reference,
            "status": "resolved",
            "path": resolved_path,
            "note": note,
            "message": f"Resolved file: {raw_reference} -> {resolved_path}" if note else f"Resolved file: {resolved_path}",
            "candidates": scored_candidates[:5],
            "resolved_by": best["reason"],
        }

    if best["score"] >= 650:
        return {
            "reference": raw_reference,
            "status": "ambiguous",
            "path": None,
            "note": None,
            "message": f"Could not safely choose one file for: {raw_reference}",
            "candidates": scored_candidates[:5],
            "resolved_by": None,
        }

    return {
        "reference": raw_reference,
        "status": "missing",
        "path": None,
        "note": None,
        "message": f"No file matched: {raw_reference}",
        "candidates": scored_candidates[:5],
        "resolved_by": None,
    }


def build_selected_file_entries(graph: dict, selected_paths: Sequence[str]) -> list[dict]:
    """Build context ranking entries for user-selected files."""

    selected_paths = _dedupe_paths(selected_paths)
    if not selected_paths:
        return []

    file_index = _index_graph_files(graph)
    total_selected = len(selected_paths)
    entries: list[dict] = []

    for index, path in enumerate(selected_paths):
        file_info = file_index.get(path) or _make_synthetic_file(path)
        roles = detect_file_roles(file_info)

        entries.append(
            {
                "file": file_info,
                "score": 10_000 + (total_selected - index),
                "matched_terms": [],
                "confidence": "high",
                "is_test": "test" in roles,
                "included_by_hint_only": False,
                "selected_by_user": True,
                "selection_index": index,
                "reason": "user-selected file",
            }
        )

    return entries


def context_mode_label(selected_paths: Sequence[str] | None) -> str:
    """Return the short label used in ask/run summaries."""

    return "selected files" if selected_paths else "focused context"


def context_mode_description(selected_paths: Sequence[str] | None) -> str:
    """Return the short description used in warning copy."""

    return "selected-file context" if selected_paths else "focused context"


def format_selected_file_list(selected_paths: Sequence[str] | None) -> str:
    """Render selected files for compact UI output."""

    paths = _dedupe_paths(selected_paths or [])

    if not paths:
        return "-"

    return ", ".join(paths)


def build_selected_file_section(selected_paths: Sequence[str] | None) -> list[str]:
    """Render a markdown section listing selected file anchors."""

    paths = _dedupe_paths(selected_paths or [])
    if not paths:
        return []

    lines = ["## User-selected files", ""]
    lines.extend(f"- `{path}`" for path in paths)
    lines.append("")
    return lines


def format_file_reference_resolution_lines(result: dict) -> list[str]:
    notes = list(result.get("notes", []) or [])
    if not notes:
        return []

    lines = ["Resolved files:"]
    lines.extend(f"  {note}" for note in notes)
    return lines


def format_file_reference_failure_lines(result: dict) -> list[str]:
    lines = [str(result.get("message") or "File reference could not be resolved.")]
    candidates = list(result.get("candidates", []) or [])

    if candidates:
        lines.append("")
        lines.append("Closest matches:")
        for index, candidate in enumerate(candidates[:5], start=1):
            lines.append(f"{index}. {candidate['path']}")

    if str(result.get("status")) == "ambiguous":
        lines.append("")
        lines.append("Use a more specific reference.")

    return lines


def _index_graph_files(graph: dict) -> dict[str, dict]:
    indexed: dict[str, dict] = {}

    for file_info in graph.get("files", []):
        if not isinstance(file_info, dict):
            continue

        path = str(file_info.get("path", "")).replace("\\", "/").strip()
        if path:
            indexed[path] = file_info

    return indexed


def _make_synthetic_file(path: str) -> dict:
    return {
        "path": path,
        "language": "unknown",
        "classes": [],
        "functions": [],
        "interfaces": [],
        "types": [],
        "enums": [],
        "exports": [],
        "imports": [],
        "external_imports": [],
        "unresolved_imports": [],
        "unresolved_import_details": [],
        "routes": [],
    }


def _dedupe_paths(selected_paths: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []

    for raw_path in selected_paths:
        path = str(raw_path or "").replace("\\", "/").strip()

        if not path or path in seen:
            continue

        seen.add(path)
        normalized.append(path)

    return normalized


def _build_candidate_catalog(root: Path) -> list[dict]:
    candidates: list[dict] = []
    seen: set[str] = set()

    snapshot_cache = load_repo_snapshot_cache(root)
    if isinstance(snapshot_cache, dict):
        for path in _paths_from_snapshot_cache(root, snapshot_cache):
            if path in seen:
                continue
            candidate = _build_candidate_info(root, path)
            if candidate is not None:
                candidates.append(candidate)
                seen.add(candidate["path"])

    for path in _walk_repo_paths(root):
        if path in seen:
            continue
        candidate = _build_candidate_info(root, path)
        if candidate is not None:
            candidates.append(candidate)
            seen.add(candidate["path"])

    candidates.sort(key=lambda item: item["path"])
    return candidates


def _paths_from_snapshot_cache(root: Path, snapshot_cache: dict) -> list[str]:
    file_fingerprints = snapshot_cache.get("file_fingerprints", {})
    if not isinstance(file_fingerprints, dict):
        return []

    paths: list[str] = []
    for raw_path in file_fingerprints.keys():
        candidate = str(raw_path or "").replace("\\", "/").strip()
        if not candidate:
            continue
        absolute_candidate = root / Path(candidate)
        if not absolute_candidate.exists() or absolute_candidate.is_dir():
            continue
        if should_ignore_path(candidate):
            continue
        paths.append(candidate)

    return paths


def _walk_repo_paths(root: Path) -> list[str]:
    paths: list[str] = []

    if not root.exists():
        return paths

    for current_root, dirnames, filenames in os.walk(root):
        dirnames[:] = [dirname for dirname in sorted(dirnames) if not _is_ignored_directory(dirname)]
        filenames.sort()

        for filename in filenames:
            file_path = Path(current_root) / filename
            if not file_path.is_file() or file_path.is_symlink():
                continue

            try:
                relative_path = file_path.relative_to(root).as_posix()
            except ValueError:
                continue

            if should_ignore_path(relative_path):
                continue

            paths.append(relative_path)

    return paths


def _build_candidate_info(root: Path, relative_path: str) -> dict | None:
    path = str(relative_path or "").replace("\\", "/").strip()
    if not path:
        return None

    candidate_path = root / Path(path)
    try:
        candidate_path.resolve(strict=False).relative_to(root)
    except ValueError:
        return None

    if not candidate_path.exists() or candidate_path.is_dir() or is_generated_or_ignored_path(path):
        return None

    basename = Path(path).name
    stem = Path(path).stem
    path_tokens = extract_identifier_terms(path)
    basename_tokens = extract_identifier_terms(basename)
    stem_tokens = extract_identifier_terms(stem)
    roles = detect_file_roles({"path": path})

    return {
        "path": path,
        "path_lower": path.lower(),
        "basename": basename,
        "basename_lower": basename.lower(),
        "stem": stem,
        "stem_lower": stem.lower(),
        "segments": tuple(segment for segment in path.split("/") if segment),
        "path_tokens": tuple(path_tokens),
        "basename_tokens": tuple(basename_tokens),
        "stem_tokens": tuple(stem_tokens),
        "identifier_terms": tuple(_dedupe_terms([*path_tokens, *basename_tokens, *stem_tokens])),
        "path_depth": len([segment for segment in path.split("/") if segment]),
        "is_test": "test" in roles,
    }


def _score_candidate_catalog(reference: str, catalog: Sequence[dict], task_hints: dict) -> list[dict]:
    scored: list[dict] = []

    for candidate in catalog:
        result = _score_candidate(reference, candidate, task_hints)
        if result is None:
            continue
        scored.append(result)

    scored.sort(key=lambda item: (-item["score"], item["path_depth"], len(item["path"]), item["path"]))
    return scored


def _score_candidate(reference: str, candidate: dict, task_hints: dict) -> dict | None:
    raw_reference = str(reference or "").strip()
    if not raw_reference:
        return None

    ref_norm = normalize_file_reference(raw_reference)
    ref_lower = ref_norm.lower()
    ref_has_separator = _reference_has_path_separator(raw_reference)
    ref_tokens = extract_identifier_terms(raw_reference)
    ref_segments = [segment for segment in ref_norm.split("/") if segment]
    candidate_path = str(candidate["path"])
    candidate_path_lower = str(candidate["path_lower"])
    candidate_basename = str(candidate["basename"])
    candidate_basename_lower = str(candidate["basename_lower"])
    candidate_stem = str(candidate["stem"])
    candidate_stem_lower = str(candidate["stem_lower"])
    candidate_tokens = list(candidate.get("identifier_terms", []))

    score = 0
    reason = None

    if ref_norm and ref_lower == candidate_path_lower:
        score = 1000
        reason = "exact path"
    elif not ref_has_separator and raw_reference == candidate_basename:
        score = 950
        reason = "exact filename"
    elif not ref_has_separator and raw_reference == candidate_stem:
        score = 925
        reason = "exact stem"
    elif ref_has_separator and _path_segments_match(ref_segments, candidate_path_lower):
        score = 850 + 10 * len(ref_segments)
        reason = "partial path"
    elif not ref_has_separator and raw_reference.lower() == candidate_basename_lower and raw_reference != candidate_basename:
        score = 800
        reason = "case-insensitive filename"
    elif not ref_has_separator and raw_reference.lower() == candidate_stem_lower and raw_reference != candidate_stem:
        score = 780
        reason = "case-insensitive stem"
    elif len(ref_tokens) >= 2 and _ordered_token_match(ref_tokens, candidate_tokens):
        score = 775 + 10 * len(ref_tokens)
        reason = "normalized component match"
    else:
        shared_terms = len(set(ref_tokens) & set(candidate_tokens))
        if shared_terms:
            score = 650 + 20 * shared_terms
            reason = "token overlap"
        else:
            fuzzy = int(SequenceMatcher(None, ref_lower, candidate_path_lower).ratio() * 100)
            score = 100 + fuzzy
            reason = "fuzzy match" if fuzzy else None

    if score <= 0 or reason is None:
        return None

    score += _shared_path_prefix_bonus(raw_reference, candidate_path)
    score -= candidate["path_depth"]
    score -= len(candidate_path) // 50

    if candidate["is_test"]:
        if task_hints.get("tests"):
            score += 25
        else:
            score -= 35
    elif task_hints.get("tests"):
        score -= 10

    return {
        "path": candidate_path,
        "score": score,
        "reason": reason,
        "path_depth": candidate["path_depth"],
        "is_test": candidate["is_test"],
    }


def _can_auto_resolve(best: dict, second: dict | None, candidate_count: int) -> bool:
    if candidate_count == 1:
        return best["score"] >= 650

    if best["score"] >= 850 and (second is None or best["score"] - second["score"] >= 20):
        return True

    if best["score"] >= 700 and (second is None or best["score"] - second["score"] >= 80):
        return True

    return False


def _resolve_exact_candidate(root: Path, reference: str) -> dict | None:
    candidate_path = Path(reference)
    absolute_candidate = candidate_path if candidate_path.is_absolute() else root / candidate_path

    try:
        resolved_candidate = absolute_candidate.resolve(strict=False)
    except OSError:
        return None

    try:
        relative_path = resolved_candidate.relative_to(root)
    except ValueError:
        if _reference_has_path_separator(reference) or candidate_path.is_absolute() or reference.startswith("."):
            return {
                "reference": reference,
                "status": "outside_root",
                "path": None,
                "note": None,
                "message": f"Selected file is outside the repo root: {reference}",
                "candidates": [],
                "resolved_by": None,
            }
        return None

    if not resolved_candidate.exists():
        return None

    if resolved_candidate.is_dir():
        return {
            "reference": reference,
            "status": "directory",
            "path": None,
            "note": None,
            "message": f"Selected path is a directory, not a file: {relative_path.as_posix()}",
            "candidates": [],
            "resolved_by": None,
        }

    relative_text = relative_path.as_posix()
    if is_secret_like_path(relative_text):
        return {
            "reference": reference,
            "status": "secret",
            "path": None,
            "note": None,
            "message": "This looks like a secret/credential file and cannot be added to AI context.",
            "candidates": [],
            "resolved_by": None,
        }

    if is_generated_or_ignored_path(relative_text):
        return {
            "reference": reference,
            "status": "ignored",
            "path": None,
            "note": None,
            "message": f"Selected file is ignored or generated: {relative_text}",
            "candidates": [],
            "resolved_by": None,
        }

    note = None if _is_exact_path_reference(reference, relative_text) else f"{reference} -> {relative_text}"
    return {
        "reference": reference,
        "status": "resolved",
        "path": relative_text,
        "note": note,
        "message": f"Resolved file: {reference} -> {relative_text}" if note else f"Resolved file: {relative_text}",
        "candidates": [],
        "resolved_by": "exact path",
    }


def _path_segments_match(reference_segments: Sequence[str], candidate_path_lower: str) -> bool:
    if len(reference_segments) < 2:
        return False

    normalized_reference = "/".join(segment.lower() for segment in reference_segments if segment)
    if not normalized_reference:
        return False

    if candidate_path_lower == normalized_reference:
        return True

    if candidate_path_lower.startswith(normalized_reference + "/"):
        return True

    return normalized_reference in candidate_path_lower


def _ordered_token_match(reference_tokens: Sequence[str], candidate_tokens: Sequence[str]) -> bool:
    if len(reference_tokens) < 2:
        return False

    if not candidate_tokens:
        return False

    reference = [token.lower() for token in reference_tokens if token]
    candidate = [token.lower() for token in candidate_tokens if token]
    if len(reference) < 2 or len(candidate) < len(reference):
        return False

    window = len(reference)
    for index in range(len(candidate) - window + 1):
        if candidate[index : index + window] == reference:
            return True

    return False


def _shared_path_prefix_bonus(reference: str, candidate_path: str) -> int:
    ref = normalize_file_reference(reference)
    if not ref:
        return 0

    candidate_lower = candidate_path.lower()
    if candidate_lower == ref.lower():
        return 0

    if ref.lower() in candidate_lower:
        return min(25, max(5, len(ref.split("/")) * 8))

    return 0


def _reference_has_path_separator(reference: str) -> bool:
    text = str(reference or "").strip()
    return any(separator in text for separator in ("/", "\\")) or text.startswith((".", "~"))


def _is_exact_path_reference(reference: str, resolved_path: str) -> bool:
    normalized_reference = normalize_file_reference(reference)
    return normalized_reference == str(resolved_path).replace("\\", "/").lower()


def _reference_mentions_tests(reference: str) -> bool:
    terms = extract_identifier_terms(reference)
    return bool(_TEST_REFERENCE_TERMS & set(terms))


def normalize_file_reference(reference: str) -> str:
    text = str(reference or "").strip().replace("\\", "/")
    while "//" in text:
        text = text.replace("//", "/")
    return text.strip()


def is_secret_like_path(path: str | Path) -> bool:
    candidate = str(path or "").replace("\\", "/").strip()
    if not candidate:
        return False

    parts = [part for part in candidate.split("/") if part]
    if not parts:
        return False

    lower_parts = [part.lower() for part in parts]
    basename = lower_parts[-1]

    if ".ssh" in lower_parts:
        return True

    if basename in _SECRET_FILE_NAMES:
        return True

    if any(basename.startswith(prefix) for prefix in _SECRET_FILE_PREFIXES):
        return True

    if any(basename.endswith(suffix) for suffix in _SECRET_FILE_SUFFIXES):
        return True

    return False


def is_generated_or_ignored_path(path: str | Path) -> bool:
    return should_ignore_path(path)


def _is_ignored_directory(name: str) -> bool:
    normalized = str(name or "").strip()
    if not normalized:
        return True

    return should_ignore_directory(normalized)


def _dedupe_terms(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []

    for value in values:
        term = str(value or "").strip().lower()
        if not term or term in seen:
            continue
        seen.add(term)
        result.append(term)

    return result
