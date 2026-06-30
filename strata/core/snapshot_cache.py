from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from strata.core.repo_ignore import should_ignore_directory, should_ignore_file
from strata.utils.paths import atomic_write_json

SNAPSHOT_CACHE_FILE = Path(".aidc") / "cache" / "repo_snapshot.json"

_CACHE_SCHEMA_VERSION = 1


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def capture_repo_snapshot(root: str | Path) -> dict[str, Any]:
    """Capture lightweight fingerprints for the current repository state."""

    root_path = Path(root)
    file_fingerprints, ignored_count = _collect_file_fingerprints(root_path)

    return {
        "captured_at": _now_iso(),
        "root": str(root_path),
        "git_head": _git_head(root_path),
        "file_count": len(file_fingerprints),
        "ignored_count": ignored_count,
        "file_fingerprints": file_fingerprints,
    }


def write_repo_snapshot_cache(
    root: str | Path,
    before_snapshot: dict[str, Any],
    after_snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Persist the repo snapshot cache and summarize drift detected during the run."""

    root_path = Path(root)
    cache_path = root_path / SNAPSHOT_CACHE_FILE
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    previous_cache = load_repo_snapshot_cache(root_path)
    changed_during_scan = _diff_fingerprints(
        before_snapshot.get("file_fingerprints", {}),
        after_snapshot.get("file_fingerprints", {}),
    )
    if isinstance(previous_cache, dict):
        changed_since_snapshot = _diff_fingerprints(
            previous_cache.get("file_fingerprints", {}),
            after_snapshot.get("file_fingerprints", {}),
        )
    else:
        changed_since_snapshot = []
    stale_files = sorted({*changed_during_scan, *changed_since_snapshot})

    if changed_during_scan:
        status = "partial"
    elif previous_cache is None:
        status = "fresh"
    elif changed_since_snapshot:
        status = "stale"
    else:
        status = "fresh"

    payload = {
        "schema_version": _CACHE_SCHEMA_VERSION,
        "status": status,
        "created_at": after_snapshot.get("captured_at") or _now_iso(),
        "started_at": before_snapshot.get("captured_at"),
        "finished_at": after_snapshot.get("captured_at") or _now_iso(),
        "root": str(root_path),
        "git_head": after_snapshot.get("git_head"),
        "file_count": after_snapshot.get("file_count", 0),
        "ignored_count": after_snapshot.get("ignored_count", 0),
        "file_fingerprints": after_snapshot.get("file_fingerprints", {}),
        "stale_files": stale_files,
        "changed_during_scan": changed_during_scan,
        "changed_since_snapshot": changed_since_snapshot,
    }

    atomic_write_json(cache_path, payload)

    return {
        "cache_path": str(cache_path),
        "cache_existed_before": previous_cache is not None,
        "status": status,
        "file_count": payload["file_count"],
        "ignored_count": payload["ignored_count"],
        "changed_since_snapshot": changed_since_snapshot,
        "changed_since_snapshot_count": len(changed_since_snapshot),
        "changed_during_scan": changed_during_scan,
        "changed_during_scan_count": len(changed_during_scan),
        "stale_files": stale_files,
        "stale_count": len(stale_files),
        "snapshot": payload,
    }


def load_repo_snapshot_cache(root: str | Path) -> dict[str, Any] | None:
    """Load the saved repo snapshot cache if it exists."""

    cache_path = Path(root) / SNAPSHOT_CACHE_FILE

    try:
        raw_text = cache_path.read_text(encoding="utf-8")
        payload = json.loads(raw_text)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None

    return payload if isinstance(payload, dict) else None


def format_snapshot_cache_status(cache_result: dict[str, Any] | None) -> str:
    """Return a compact human-readable status for UI cards."""

    if not cache_result:
        return "missing"

    status = str(cache_result.get("status") or "fresh").strip().lower()
    changed_since_snapshot_count = int(cache_result.get("changed_since_snapshot_count", 0) or 0)
    changed_during_scan_count = int(cache_result.get("changed_during_scan_count", 0) or 0)

    if status == "partial" and changed_during_scan_count:
        return f"partial ({changed_during_scan_count} changed during scan)"

    if status == "stale" and changed_since_snapshot_count:
        return f"stale ({changed_since_snapshot_count} changed since snapshot)"

    return status or "fresh"


def _collect_file_fingerprints(root_path: Path) -> tuple[dict[str, dict[str, int]], int]:
    fingerprints: dict[str, dict[str, int]] = {}
    ignored_count = 0

    if not root_path.exists():
        return fingerprints, ignored_count

    for current_root, dirnames, filenames in os.walk(root_path):
        original_dirnames = list(dirnames)
        dirnames[:] = [
            dirname
            for dirname in sorted(dirnames)
            if not should_ignore_directory(dirname)
        ]
        ignored_count += sum(1 for dirname in original_dirnames if should_ignore_directory(dirname))
        filenames.sort()

        for filename in filenames:
            file_path = Path(current_root) / filename

            if not file_path.is_file() or file_path.is_symlink() or should_ignore_file(file_path):
                ignored_count += 1
                continue

            try:
                stat_result = file_path.stat()
            except OSError:
                ignored_count += 1
                continue

            try:
                relative_path = file_path.relative_to(root_path).as_posix()
            except ValueError:
                ignored_count += 1
                continue

            fingerprints[relative_path] = {
                "size": int(stat_result.st_size),
                "mtime_ns": _mtime_ns(stat_result),
            }

    return fingerprints, ignored_count


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


def _mtime_ns(stat_result: os.stat_result) -> int:
    value = getattr(stat_result, "st_mtime_ns", None)
    if isinstance(value, int):
        return value

    return int(stat_result.st_mtime * 1_000_000_000)


def _git_head(root_path: Path) -> str | None:
    if not (root_path / ".git").exists():
        return None

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
    except OSError:
        return None

    if result.returncode != 0:
        return None

    head = result.stdout.strip()
    return head or None
