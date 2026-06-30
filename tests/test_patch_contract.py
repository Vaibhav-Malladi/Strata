import tempfile
from pathlib import Path

import patch_contract as old_patch_contract
import strata.patch.contract as new_patch_contract

from patch_contract import (
    DEFAULT_PATCH_METADATA_PATH,
    DEFAULT_PATCH_PATH,
    build_patch_summary,
    inspect_patch,
    read_patch_text,
    resolve_patch_metadata_path,
    resolve_patch_path,
)


def test_patch_contract_module_compatibility():
    assert (
        old_patch_contract.resolve_patch_path
        is new_patch_contract.resolve_patch_path
    )
    assert old_patch_contract.inspect_patch is new_patch_contract.inspect_patch
    assert old_patch_contract.read_patch_text is new_patch_contract.read_patch_text


def _create_patch_file(root: Path, content: str) -> Path:
    patch_path = root / ".aidc" / "agent_patch.diff"
    patch_path.parent.mkdir(parents=True, exist_ok=True)
    patch_path.write_bytes(content.encode("utf-8"))
    return patch_path


def test_default_patch_path_resolution():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        resolved = resolve_patch_path(root=root)

        assert resolved == root / DEFAULT_PATCH_PATH


def test_default_metadata_path_resolution():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        resolved = resolve_patch_metadata_path(root=root)

        assert resolved == root / DEFAULT_PATCH_METADATA_PATH


def test_relative_configured_patch_path():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        resolved = resolve_patch_path(
            root=root,
            configured_path=Path("patches") / "agent_patch.diff",
        )

        assert resolved == root / "patches" / "agent_patch.diff"


def test_absolute_configured_patch_path():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        absolute_path = root / "custom" / "agent_patch.diff"

        resolved = resolve_patch_path(root=root, configured_path=absolute_path)

        assert resolved == absolute_path


def test_missing_patch_returns_missing_status():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        result = inspect_patch(root=root)

        assert result == {
            "status": "missing",
            "patch_path": str(DEFAULT_PATCH_PATH),
            "exists": False,
            "size": 0,
            "message": "Patch file not found.",
        }


def test_empty_patch_returns_empty_status():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_patch_file(root, "")

        result = inspect_patch(root=root)

        assert result == {
            "status": "empty",
            "patch_path": str(DEFAULT_PATCH_PATH),
            "exists": True,
            "size": 0,
            "message": "Patch file is empty.",
        }


def test_non_empty_patch_returns_ready_status():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        content = "diff --git a/file.py b/file.py\n"
        patch_path = _create_patch_file(root, content)

        result = inspect_patch(root=root)

        assert result == {
            "status": "ready",
            "patch_path": str(DEFAULT_PATCH_PATH),
            "exists": True,
            "size": patch_path.stat().st_size,
            "message": "Patch file is ready for review.",
        }


def test_inspect_patch_does_not_create_aidc_when_missing():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        result = inspect_patch(root=root)

        assert result["status"] == "missing"
        assert not (root / ".aidc").exists()


def test_read_patch_text_returns_empty_string_for_missing_patch():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        assert read_patch_text(root=root) == ""


def test_read_patch_text_returns_content_for_ready_patch():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        content = "diff --git a/file.py b/file.py\n+print('hello')\n"
        _create_patch_file(root, content)

        assert read_patch_text(root=root) == content


def test_read_patch_text_respects_max_bytes():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        content = "abcdef"
        _create_patch_file(root, content)

        assert read_patch_text(root=root, max_bytes=3) == "abc"


def test_build_patch_summary_mirrors_inspect_patch():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        assert build_patch_summary(root=root) == inspect_patch(root=root)


def test_repeated_calls_return_fresh_deterministic_dicts():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        first = inspect_patch(root=root)
        second = inspect_patch(root=root)

        assert first == second
        assert first is not second

        first["status"] = "changed"

        assert second["status"] == "missing"


TESTS = [
    test_patch_contract_module_compatibility,
    test_default_patch_path_resolution,
    test_default_metadata_path_resolution,
    test_relative_configured_patch_path,
    test_absolute_configured_patch_path,
    test_missing_patch_returns_missing_status,
    test_empty_patch_returns_empty_status,
    test_non_empty_patch_returns_ready_status,
    test_inspect_patch_does_not_create_aidc_when_missing,
    test_read_patch_text_returns_empty_string_for_missing_patch,
    test_read_patch_text_returns_content_for_ready_patch,
    test_read_patch_text_respects_max_bytes,
    test_build_patch_summary_mirrors_inspect_patch,
    test_repeated_calls_return_fresh_deterministic_dicts,
]
