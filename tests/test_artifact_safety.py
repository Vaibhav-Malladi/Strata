import os
import tempfile
from pathlib import Path

import strata.utils.artifacts as artifacts
from tests.helpers import try_symlink_or_skip


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


def test_artifact_write_accepts_mixed_separators_and_preserves_public_shape():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        root.mkdir()

        path = artifacts.write_artifact_text(root, "reports\\nested/result.md", "safe\n")

        assert path == root / ".aidc" / "reports" / "nested" / "result.md"
        assert path.read_text(encoding="utf-8") == "safe\n"


def test_artifact_resolution_keeps_canonical_path_internal():
    with tempfile.TemporaryDirectory() as temp_dir:
        previous = Path.cwd()
        try:
            os.chdir(temp_dir)
            Path("repo").mkdir()
            root = Path("parent") / ".." / "repo"

            resolved = artifacts.resolve_artifact_path(root, "reports\\result.md")
            written = artifacts.write_artifact_text(root, "reports\\result.md", "safe\n")
            expected = root / ".aidc" / "reports" / "result.md"
            json_expected = root / ".aidc" / "reports" / "result.json"
            output_expected = root / ".aidc" / "reports" / "output.md"
            json_written = artifacts.write_artifact_json(root, "reports/result.json", {"safe": True})
            output_written = artifacts.write_artifact_output_path(output_expected, "safe\n")

            assert resolved == expected
            assert written == expected
            assert json_written == json_expected
            assert output_written == output_expected
            assert ".." in written.parts
            assert written.resolve() == (Path("repo") / ".aidc" / "reports" / "result.md").resolve()
        finally:
            os.chdir(previous)


def test_artifact_write_rejects_parent_traversal():
    with tempfile.TemporaryDirectory() as temp_dir:
        for name in (
            "../outside.txt",
            "..\\outside.txt",
            "reports/../outside.txt",
            "reports\\..\\outside.txt",
            "reports/..\\outside.txt",
        ):
            try:
                artifacts.write_artifact_text(temp_dir, name, "unsafe")
            except ValueError as error:
                assert "parent traversal" in str(error)
            else:
                raise AssertionError(f"Artifact traversal path was accepted: {name}")


def test_artifact_write_rejects_absolute_name():
    with tempfile.TemporaryDirectory() as temp_dir:
        absolute_names = [
            Path(temp_dir).resolve() / "outside.txt",
            "C:\\outside.txt",
            "C:/outside.txt",
            "D:\\reports/outside.txt",
            "/outside.txt",
            "\\outside.txt",
            "\\\\server\\share\\outside.txt",
        ]

        for name in absolute_names:
            try:
                artifacts.write_artifact_text(temp_dir, name, "unsafe")
            except ValueError as error:
                assert "relative to .aidc" in str(error)
            else:
                raise AssertionError(f"Absolute artifact name was accepted: {name}")


def test_artifact_write_preserves_utf8_and_newlines():
    with tempfile.TemporaryDirectory() as temp_dir:
        path = artifacts.write_artifact_text(temp_dir, "reports/newlines.md", "alpha\r\nβeta\n")

        assert path.read_bytes() == "alpha\r\nβeta\n".encode("utf-8")


def test_artifact_write_rejects_aidc_symlink():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        outside = Path(temp_dir) / "outside"
        root.mkdir()
        outside.mkdir()

        if not try_symlink_or_skip(root / ".aidc", outside, target_is_directory=True):
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

        if not try_symlink_or_skip(
            root / ".aidc" / "result.md",
            outside_target,
            target_is_directory=False,
        ):
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
    test_artifact_write_accepts_mixed_separators_and_preserves_public_shape,
    test_artifact_resolution_keeps_canonical_path_internal,
    test_artifact_write_rejects_parent_traversal,
    test_artifact_write_rejects_absolute_name,
    test_artifact_write_preserves_utf8_and_newlines,
    test_artifact_write_rejects_aidc_symlink,
    test_artifact_write_rejects_symlink_target,
    test_artifact_file_permissions_are_owner_only_on_posix,
]
