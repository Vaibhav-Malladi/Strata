import json
import tempfile
from pathlib import Path

from snapshot_cache import (
    SNAPSHOT_CACHE_FILE,
    capture_repo_snapshot,
    format_snapshot_cache_status,
    load_repo_snapshot_cache,
    write_repo_snapshot_cache,
)


def _create_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "main.py").write_text("print('hello')\n", encoding="utf-8")
    (root / "helper.py").write_text("def helper():\n    return True\n", encoding="utf-8")


def _cache_path(root: Path) -> Path:
    return root / SNAPSHOT_CACHE_FILE


def test_write_repo_snapshot_cache_creates_cache_file_with_metadata():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        _create_repo(root)

        before = capture_repo_snapshot(root)
        after = capture_repo_snapshot(root)
        result = write_repo_snapshot_cache(root, before, after)

        payload = json.loads(_cache_path(root).read_text(encoding="utf-8"))

        assert result["cache_existed_before"] is False
        assert result["status"] == "fresh"
        assert result["changed_since_snapshot_count"] == 0
        assert result["changed_during_scan_count"] == 0
        assert _cache_path(root).exists()
        assert payload["schema_version"] == 1
        assert payload["root"] == str(root)
        assert payload["file_count"] == 2
        assert "main.py" in payload["file_fingerprints"]
        assert "helper.py" in payload["file_fingerprints"]
        assert payload["stale_files"] == []


def test_first_time_snapshot_reports_missing_previous_cache():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        _create_repo(root)

        assert load_repo_snapshot_cache(root) is None

        before = capture_repo_snapshot(root)
        after = capture_repo_snapshot(root)
        result = write_repo_snapshot_cache(root, before, after)

        assert result["cache_existed_before"] is False
        assert result["status"] == "fresh"
        assert format_snapshot_cache_status(result) == "fresh"


def test_unchanged_repo_reports_fresh_cache_on_refresh():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        _create_repo(root)

        initial = capture_repo_snapshot(root)
        write_repo_snapshot_cache(root, initial, initial)

        refreshed_before = capture_repo_snapshot(root)
        refreshed_after = capture_repo_snapshot(root)
        result = write_repo_snapshot_cache(root, refreshed_before, refreshed_after)

        assert result["cache_existed_before"] is True
        assert result["status"] == "fresh"
        assert result["changed_since_snapshot_count"] == 0
        assert result["changed_during_scan_count"] == 0


def test_modified_file_after_cache_is_marked_stale():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        _create_repo(root)

        initial = capture_repo_snapshot(root)
        write_repo_snapshot_cache(root, initial, initial)

        (root / "main.py").write_text("print('updated')\n", encoding="utf-8")
        after = capture_repo_snapshot(root)
        result = write_repo_snapshot_cache(root, after, after)

        assert result["status"] == "stale"
        assert "main.py" in result["changed_since_snapshot"]
        assert "main.py" in result["stale_files"]


def test_file_changed_during_scan_is_detected():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        _create_repo(root)

        before = capture_repo_snapshot(root)
        (root / "main.py").write_text("print('changed while scanning')\n", encoding="utf-8")
        after = capture_repo_snapshot(root)
        result = write_repo_snapshot_cache(root, before, after)

        assert result["status"] == "partial"
        assert "main.py" in result["changed_during_scan"]
        assert "main.py" in result["stale_files"]
        assert result["changed_during_scan_count"] == 1


def test_deleted_and_new_files_are_detected():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        _create_repo(root)

        initial = capture_repo_snapshot(root)
        write_repo_snapshot_cache(root, initial, initial)

        (root / "helper.py").unlink()
        (root / "new_feature.py").write_text("print('new')\n", encoding="utf-8")

        after = capture_repo_snapshot(root)
        result = write_repo_snapshot_cache(root, after, after)

        assert result["status"] == "stale"
        assert "helper.py" in result["changed_since_snapshot"]
        assert "new_feature.py" in result["changed_since_snapshot"]
        assert "helper.py" in result["stale_files"]
        assert "new_feature.py" in result["stale_files"]


def test_ignored_directories_are_not_included():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        _create_repo(root)

        ignored_roots = [
            ".aidc",
            ".git",
            ".venv",
            "venv",
            "__pycache__",
            ".cache",
            ".pytest_cache",
            ".ruff_cache",
            ".mypy_cache",
            ".tox",
            ".nox",
            "node_modules",
            "dist",
            "build",
            "coverage",
            "htmlcov",
        ]

        for ignored_root in ignored_roots:
            ignored_dir = root / ignored_root
            ignored_dir.mkdir(parents=True, exist_ok=True)
            (ignored_dir / "ignored.py").write_text("print('ignored')\n", encoding="utf-8")

        snapshot = capture_repo_snapshot(root)
        paths = set(snapshot["file_fingerprints"])

        assert snapshot["file_count"] == 2
        assert "main.py" in paths
        assert "helper.py" in paths
        assert not any(path.startswith(".aidc/") for path in paths)
        assert not any(path.startswith(".git/") for path in paths)
        assert not any(path.startswith(".venv/") for path in paths)
        assert not any(path.startswith("venv/") for path in paths)
        assert not any(path.startswith("__pycache__/") for path in paths)
        assert not any(path.startswith(".cache/") for path in paths)
        assert not any(path.startswith(".pytest_cache/") for path in paths)


TESTS = [
    test_write_repo_snapshot_cache_creates_cache_file_with_metadata,
    test_first_time_snapshot_reports_missing_previous_cache,
    test_unchanged_repo_reports_fresh_cache_on_refresh,
    test_modified_file_after_cache_is_marked_stale,
    test_file_changed_during_scan_is_detected,
    test_deleted_and_new_files_are_detected,
    test_ignored_directories_are_not_included,
]
