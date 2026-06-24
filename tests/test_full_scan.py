import json
import tempfile
from pathlib import Path

from full_scan import (
    FULL_SCAN_CACHE_FILE,
    FULL_SCAN_TEMP_FILE,
    build_full_scan_payload,
    finalize_full_scan_cache,
    format_full_scan_status,
    load_full_scan_cache,
    write_full_scan_temp_marker,
)


def _cache_path(root: Path) -> Path:
    return root / FULL_SCAN_CACHE_FILE


def _temp_path(root: Path) -> Path:
    return root / FULL_SCAN_TEMP_FILE


def test_full_scan_temp_marker_is_detected_as_interrupted():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        root.mkdir(parents=True, exist_ok=True)

        write_full_scan_temp_marker(
            root,
            {
                "schema_version": 1,
                "status": "scanning",
                "root": str(root),
                "file_count": 0,
            },
        )

        state = load_full_scan_cache(root)

        assert state is not None
        assert state["status"] == "interrupted"
        assert _temp_path(root).exists()
        assert format_full_scan_status(state) == "interrupted"


def test_full_scan_cache_finalize_replaces_temp_marker():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        root.mkdir(parents=True, exist_ok=True)

        payload = {
            "schema_version": 1,
            "status": "fresh",
            "root": str(root),
            "file_count": 1,
            "scanned_count": 1,
            "skipped_count": 0,
            "failed_count": 0,
            "changed_during_scan": [],
            "changed_during_scan_count": 0,
            "changed_since_snapshot": [],
            "changed_since_snapshot_count": 0,
            "stale_files": [],
            "stale_count": 0,
            "graph_path": ".aidc/graph.json",
            "file_fingerprints": {"main.py": {"size": 12, "mtime_ns": 1}},
        }

        write_full_scan_temp_marker(root, {"status": "scanning", "root": str(root)})
        finalize_full_scan_cache(root, payload)

        assert _cache_path(root).exists()
        assert not _temp_path(root).exists()
        assert json.loads(_cache_path(root).read_text(encoding="utf-8"))["status"] == "fresh"


def test_build_full_scan_payload_marks_partial_and_stale_states():
    before_snapshot = {
        "captured_at": "2024-01-02T03:04:05+00:00",
        "root": ".",
        "git_head": "abc123",
        "file_count": 1000,
        "ignored_count": 0,
        "file_fingerprints": {
            f"file_{index}.py": {"size": index, "mtime_ns": index}
            for index in range(1000)
        },
    }
    after_snapshot = {
        "captured_at": "2024-01-02T03:05:05+00:00",
        "root": ".",
        "git_head": "abc123",
        "file_count": 1000,
        "ignored_count": 0,
        "file_fingerprints": {
            **{
                f"file_{index}.py": {"size": index, "mtime_ns": index}
                for index in range(995)
            },
            **{
                f"file_{index}.py": {"size": index + 1, "mtime_ns": index + 1}
                for index in range(995, 1000)
            },
        },
    }

    partial_payload = build_full_scan_payload(
        root=".",
        before_snapshot=before_snapshot,
        after_snapshot=after_snapshot,
        graph={"files": [], "edges": []},
        scanned_count=900,
        skipped_count=100,
        failed_count=0,
        started_at="2024-01-02T03:04:05+00:00",
        finished_at="2024-01-02T03:05:05+00:00",
        graph_path=".aidc/graph.json",
        previous_cache=None,
    )

    stale_after_snapshot = dict(after_snapshot)
    stale_after_snapshot["file_fingerprints"] = {
        f"file_{index}.py": {"size": index + 2, "mtime_ns": index + 2}
        for index in range(1000)
    }

    stale_payload = build_full_scan_payload(
        root=".",
        before_snapshot=before_snapshot,
        after_snapshot=stale_after_snapshot,
        graph={"files": [], "edges": []},
        scanned_count=500,
        skipped_count=500,
        failed_count=0,
        started_at="2024-01-02T03:04:05+00:00",
        finished_at="2024-01-02T03:05:05+00:00",
        graph_path=".aidc/graph.json",
        previous_cache={"file_fingerprints": before_snapshot["file_fingerprints"]},
    )

    assert partial_payload["status"] == "partial"
    assert partial_payload["changed_during_scan_count"] == 5
    assert stale_payload["status"] == "stale"
    assert stale_payload["changed_during_scan_count"] == 1000
    assert "file_0.py" in stale_payload["stale_files"]


TESTS = [
    test_full_scan_temp_marker_is_detected_as_interrupted,
    test_full_scan_cache_finalize_replaces_temp_marker,
    test_build_full_scan_payload_marks_partial_and_stale_states,
]
