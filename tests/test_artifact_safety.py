import os
import tempfile
from pathlib import Path

import strata.utils.artifacts as artifacts


def _create_symlink(link: Path, target: Path, *, target_is_directory: bool) -> bool:
    try:
        link.symlink_to(target, target_is_directory=target_is_directory)
    except (NotImplementedError, OSError) as error:
        print(f"SKIP: symlink creation is not permitted on this platform: {error}")
        return False
    return True


def test_safe_artifact_write_stays_under_aidc():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        path = artifacts.write_artifact_text(root, "reports/result.md", "safe\n")

        assert path == root / ".aidc" / "reports" / "result.md"
        assert path.exists()
        assert path.resolve() == (root / ".aidc" / "reports" / "result.md").resolve()
        assert path.read_text(encoding="utf-8") == "safe\n"


def test_artifact_write_returns_relative_root_shape():
    with tempfile.TemporaryDirectory() as temp_dir:
        previous = Path.cwd()
        try:
            os.chdir(temp_dir)
            root = Path("repo")
            root.mkdir()

            path = artifacts.write_artifact_text(root, "reports/result.md", "safe\n")
            expected = root / ".aidc" / "reports" / "result.md"

            assert path == expected
            assert path.exists()
            assert path.resolve() == expected.resolve()
        finally:
            os.chdir(previous)


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


def test_artifact_write_rejects_aidc_symlink():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        outside = Path(temp_dir) / "outside"
        root.mkdir()
        outside.mkdir()

        if not _create_symlink(root / ".aidc", outside, target_is_directory=True):
            return

        try:
            artifacts.write_artifact_text(root, "result.md", "unsafe")
        except ValueError as error:
            assert "Artifact directory must not be a symbolic link" in str(error)
        else:
            raise AssertionError(".aidc symlink artifact directory was accepted")


def test_artifact_write_rejects_symlink_target():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        outside = Path(temp_dir) / "outside"
        root.mkdir()
        outside.mkdir()
        (root / ".aidc").mkdir()
        outside_target = outside / "result.md"
        outside_target.write_text("outside\n", encoding="utf-8")

        if not _create_symlink(root / ".aidc" / "result.md", outside_target, target_is_directory=False):
            return

        try:
            artifacts.write_artifact_text(root, "result.md", "unsafe")
        except ValueError as error:
            assert "Artifact target must not be a symbolic link" in str(error)
        else:
            raise AssertionError("Symlink artifact target was accepted")


def test_artifact_file_permissions_are_owner_only_on_posix():
    if os.name == "nt":
        return

    with tempfile.TemporaryDirectory() as temp_dir:
        path = artifacts.write_artifact_text(temp_dir, "private.txt", "private")
        assert path.stat().st_mode & 0o777 == 0o600


TESTS = [
    test_safe_artifact_write_stays_under_aidc,
    test_artifact_write_returns_relative_root_shape,
    test_artifact_write_rejects_parent_traversal,
    test_artifact_write_rejects_absolute_name,
    test_artifact_write_rejects_aidc_symlink,
    test_artifact_write_rejects_symlink_target,
    test_artifact_file_permissions_are_owner_only_on_posix,
]
