from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fs_utils import atomic_write_json

FULL_SCAN_CACHE_FILE = Path(".aidc") / "cache" / "repo_scan.json"
FULL_SCAN_TEMP_FILE = Path(".aidc") / "cache" / "repo_scan.tmp.json"
FULL_SCAN_SCHEMA_VERSION = 1
LARGE_REPO_THRESHOLD = 5000
MASSIVE_DRIFT_ABSOLUTE_THRESHOLD = 500
MASSIVE_DRIFT_PERCENT_THRESHOLD = 0.10


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_full_scan_cache(root: str | Path) -> dict[str, Any] | None:
    root_path = Path(root)
    cache_path = root_path / FULL_SCAN_CACHE_FILE
    temp_path = root_path / FULL_SCAN_TEMP_FILE

    temp_payload = _read_json(temp_path)
    if temp_payload is not None or temp_path.exists():
        payload = temp_payload if isinstance(temp_payload, dict) else {}
        payload.setdefault("schema_version", FULL_SCAN_SCHEMA_VERSION)
        payload["status"] = "interrupted"
        payload["interrupted"] = True
        payload["cache_path"] = str(cache_path)
        payload["temp_path"] = str(temp_path)
        payload["root"] = str(root_path)
        if cache_path.exists():
            payload["last_complete_cache"] = str(cache_path)
        return payload

    payload = _read_json(cache_path)
    if not isinstance(payload, dict):
        return None

    payload.setdefault("schema_version", FULL_SCAN_SCHEMA_VERSION)
    payload["cache_path"] = str(cache_path)
    payload["temp_path"] = str(temp_path)
    payload.setdefault("status", "missing")
    payload.setdefault("interrupted", False)
    return payload


def load_completed_full_scan_cache(root: str | Path) -> dict[str, Any] | None:
    root_path = Path(root)
    cache_path = root_path / FULL_SCAN_CACHE_FILE
    payload = _read_json(cache_path)

    if not isinstance(payload, dict):
        return None

    payload.setdefault("schema_version", FULL_SCAN_SCHEMA_VERSION)
    payload["cache_path"] = str(cache_path)
    payload["temp_path"] = str(root_path / FULL_SCAN_TEMP_FILE)
    payload.setdefault("status", "missing")
    payload.setdefault("interrupted", False)
    return payload


def format_full_scan_status(scan_result: dict[str, Any] | None) -> str:
    if not scan_result:
        return "missing"

    status = str(scan_result.get("status") or "missing").strip().lower()
    changed_during_scan_count = int(scan_result.get("changed_during_scan_count", 0) or 0)
    stale_count = int(scan_result.get("stale_count", 0) or 0)

    if status == "interrupted":
        return "interrupted"

    if status == "partial" and changed_during_scan_count:
        return f"partial ({changed_during_scan_count} changed during scan)"

    if status == "stale" and stale_count:
        return f"stale ({stale_count} stale)"

    return status or "missing"


def build_full_scan_payload(
    *,
    root: str | Path,
    before_snapshot: dict[str, Any],
    after_snapshot: dict[str, Any],
    graph: dict[str, Any],
    scanned_count: int,
    skipped_count: int,
    failed_count: int,
    started_at: str | None,
    finished_at: str | None,
    graph_path: str | Path,
    previous_cache: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root_path = Path(root)
    before_fingerprints = before_snapshot.get("file_fingerprints", {})
    after_fingerprints = after_snapshot.get("file_fingerprints", {})
    previous_fingerprints = _read_previous_fingerprints(previous_cache)

    changed_during_scan = _diff_fingerprints(before_fingerprints, after_fingerprints)
    changed_since_snapshot = _diff_fingerprints(previous_fingerprints, after_fingerprints)
    stale_files = sorted({*changed_during_scan, *changed_since_snapshot})
    file_count = int(after_snapshot.get("file_count", 0) or 0)
    ignored_count = int(after_snapshot.get("ignored_count", 0) or 0)
    drift_count = len(changed_during_scan)
    drift_is_massive = drift_count > MASSIVE_DRIFT_ABSOLUTE_THRESHOLD or (
        file_count > 0 and drift_count / max(file_count, 1) > MASSIVE_DRIFT_PERCENT_THRESHOLD
    )

    if drift_count == 0 and not changed_since_snapshot:
        status = "fresh"
    elif drift_is_massive:
        status = "stale"
    elif drift_count:
        status = "partial"
    elif previous_cache is None:
        status = "fresh"
    elif changed_since_snapshot:
        status = "stale"
    else:
        status = "fresh"

    payload = {
        "schema_version": FULL_SCAN_SCHEMA_VERSION,
        "status": status,
        "created_at": finished_at or _now_iso(),
        "started_at": started_at,
        "finished_at": finished_at or _now_iso(),
        "root": str(root_path),
        "git_head": after_snapshot.get("git_head"),
        "file_count": file_count,
        "ignored_count": ignored_count,
        "scanned_count": scanned_count,
        "skipped_count": skipped_count,
        "failed_count": failed_count,
        "changed_during_scan": changed_during_scan,
        "changed_during_scan_count": len(changed_during_scan),
        "changed_since_snapshot": changed_since_snapshot,
        "changed_since_snapshot_count": len(changed_since_snapshot),
        "stale_files": stale_files,
        "stale_count": len(stale_files),
        "graph_path": str(graph_path),
        "file_fingerprints": after_fingerprints,
        "interrupted": False,
    }

    if drift_is_massive:
        payload["recommendation"] = "strata scan --force"

    return payload


def write_full_scan_temp_marker(root: str | Path, payload: dict[str, Any]) -> Path:
    root_path = Path(root)
    temp_path = root_path / FULL_SCAN_TEMP_FILE
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return temp_path


def finalize_full_scan_cache(root: str | Path, payload: dict[str, Any]) -> Path:
    root_path = Path(root)
    cache_path = root_path / FULL_SCAN_CACHE_FILE
    atomic_write_json(cache_path, payload)
    (root_path / FULL_SCAN_TEMP_FILE).unlink(missing_ok=True)
    return cache_path


def clear_full_scan_temp_marker(root: str | Path) -> None:
    (Path(root) / FULL_SCAN_TEMP_FILE).unlink(missing_ok=True)


def _read_previous_fingerprints(previous_cache: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(previous_cache, dict):
        return {}

    fingerprints = previous_cache.get("file_fingerprints", {})
    return fingerprints if isinstance(fingerprints, dict) else {}


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        raw_text = path.read_text(encoding="utf-8")
        payload = json.loads(raw_text)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None

    return payload if isinstance(payload, dict) else None


def _diff_fingerprints(
    before: dict[str, dict[str, int]] | dict[str, Any],
    after: dict[str, dict[str, int]] | dict[str, Any],
) -> list[str]:
    before_map = before if isinstance(before, dict) else {}
    after_map = after if isinstance(after, dict) else {}

    changed_paths = set(before_map) ^ set(after_map)

    for path in set(before_map) & set(after_map):
        if before_map.get(path) != after_map.get(path):
            changed_paths.add(path)

    return sorted(changed_paths)
