import os
import tempfile
from pathlib import Path

import strata.utils.artifacts as artifacts


def test_safe_artifact_write_stays_under_aidc():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        path = artifacts.write_artifact_text(root, "reports/result.md", "safe\n")

        assert path == root / ".aidc" / "reports" / "result.md"
        assert path.read_text(encoding="utf-8") == "safe\n"


def test_artifact_write_rejects_parent_traversal():
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            artifacts.write_artifact_text(temp_dir, "../outside.txt", "unsafe")
        except ValueError as error:
            assert "parent traversal" in str(error)
        else:
            raise AssertionError("Artifact traversal path was accepted")

        try:
            artifacts.write_artifact_text(temp_dir, "..\\outside.txt", "unsafe")
        except ValueError as error:
            assert "parent traversal" in str(error)
        else:
            raise AssertionError("Backslash artifact traversal path was accepted")


def test_artifact_write_rejects_absolute_name():
    with tempfile.TemporaryDirectory() as temp_dir:
        absolute_name = Path(temp_dir).resolve() / "outside.txt"
        try:
            artifacts.write_artifact_text(temp_dir, absolute_name, "unsafe")
        except ValueError as error:
            assert "relative to .aidc" in str(error)
        else:
            raise AssertionError("Absolute artifact name was accepted")


def test_artifact_file_permissions_are_owner_only_on_posix():
    if os.name == "nt":
        return

    with tempfile.TemporaryDirectory() as temp_dir:
        path = artifacts.write_artifact_text(temp_dir, "private.txt", "private")
        assert path.stat().st_mode & 0o777 == 0o600


TESTS = [
    test_safe_artifact_write_stays_under_aidc,
    test_artifact_write_rejects_parent_traversal,
    test_artifact_write_rejects_absolute_name,
    test_artifact_file_permissions_are_owner_only_on_posix,
]
