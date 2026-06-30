import tempfile
from pathlib import Path

import patch_validator as old_patch_validator
import strata.patch.validator as new_patch_validator

from patch_validator import extract_patch_targets, validate_patch_file, validate_patch_text


def test_patch_validator_module_compatibility():
    assert (
        old_patch_validator.validate_patch_text
        is new_patch_validator.validate_patch_text
    )
    assert (
        old_patch_validator.validate_patch_file
        is new_patch_validator.validate_patch_file
    )
    assert (
        old_patch_validator.extract_patch_targets
        is new_patch_validator.extract_patch_targets
    )


def _write_patch_file(root: Path, content: str) -> Path:
    patch_path = root / ".aidc" / "agent_patch.diff"
    patch_path.parent.mkdir(parents=True, exist_ok=True)
    patch_path.write_text(content, encoding="utf-8")
    return patch_path


def test_missing_patch_file_returns_missing():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        result = validate_patch_file(root=root)

        assert result == {
            "status": "missing",
            "valid": False,
            "targets": [],
            "errors": ["Patch file not found."],
            "warnings": [],
            "message": "Patch file not found.",
        }


def test_empty_patch_file_returns_empty():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_patch_file(root, "")

        result = validate_patch_file(root=root)

        assert result == {
            "status": "empty",
            "valid": False,
            "targets": [],
            "errors": ["Patch file is empty."],
            "warnings": [],
            "message": "Patch file is empty.",
        }


def test_valid_diff_git_patch_returns_valid():
    patch = (
        "diff --git a/file.py b/file.py\n"
        "--- a/file.py\n"
        "+++ b/file.py\n"
        "@@ -1 +1 @@\n"
        "-print('old')\n"
        "+print('new')\n"
    )

    result = validate_patch_text(patch)

    assert result["status"] == "valid"
    assert result["valid"] is True
    assert result["targets"] == ["file.py"]
    assert result["errors"] == []
    assert result["warnings"] == []
    assert result["message"] == "Patch format looks safe for dry-run validation."


def test_valid_old_new_patch_returns_valid():
    patch = (
        "--- a/file.py\n"
        "+++ b/file.py\n"
        "@@ -1 +1 @@\n"
        "-print('old')\n"
        "+print('new')\n"
    )

    result = validate_patch_text(patch)

    assert result["status"] == "valid"
    assert result["targets"] == ["file.py"]


def test_target_extraction_strips_a_and_b_prefixes():
    patch = "diff --git a/src/app.py b/src/app.py\n"

    assert extract_patch_targets(patch) == ["src/app.py"]


def test_rejects_unix_absolute_path():
    patch = (
        "--- /etc/passwd\n"
        "+++ /etc/passwd\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    )

    result = validate_patch_text(patch)

    assert result["status"] == "invalid"
    assert result["valid"] is False
    assert result["targets"] == []
    assert "/etc/passwd" in result["errors"][0]


def test_rejects_windows_absolute_path():
    patch = (
        "--- C:\\temp\\evil.txt\n"
        "+++ C:\\temp\\evil.txt\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    )

    result = validate_patch_text(patch)

    assert result["status"] == "invalid"
    assert "C:/temp/evil.txt" in result["errors"][0]


def test_rejects_parent_traversal_path():
    patch = (
        "--- a/../file.py\n"
        "+++ b/../file.py\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    )

    result = validate_patch_text(patch)

    assert result["status"] == "invalid"
    assert ".." in result["errors"][0]


def test_rejects_git_path():
    patch = (
        "--- a/.git/config\n"
        "+++ b/.git/config\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    )

    result = validate_patch_text(patch)

    assert result["status"] == "invalid"
    assert ".git" in result["errors"][0]


def test_rejects_aidc_config_path():
    patch = (
        "--- a/.aidc/config.json\n"
        "+++ b/.aidc/config.json\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    )

    result = validate_patch_text(patch)

    assert result["status"] == "invalid"
    assert ".aidc/config.json" in result["errors"][0]


def test_rejects_env_path():
    patch = (
        "--- a/.env\n"
        "+++ b/.env\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    )

    result = validate_patch_text(patch)

    assert result["status"] == "invalid"
    assert ".env" in result["errors"][0]


def test_rejects_ssh_path():
    patch = (
        "--- a/.ssh/id_rsa\n"
        "+++ b/.ssh/id_rsa\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    )

    result = validate_patch_text(patch)

    assert result["status"] == "invalid"
    assert ".ssh/id_rsa" in result["errors"][0]


def test_warns_for_aidc_generated_report_but_does_not_fail():
    patch = (
        "diff --git a/.aidc/gate_report.json b/.aidc/gate_report.json\n"
        "--- a/.aidc/gate_report.json\n"
        "+++ b/.aidc/gate_report.json\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    )

    result = validate_patch_text(patch)

    assert result["status"] == "valid"
    assert result["valid"] is True
    assert result["targets"] == [".aidc/gate_report.json"]
    assert result["warnings"]
    assert ".aidc/gate_report.json" in result["warnings"][0]


def test_rejects_text_with_no_unified_diff_header():
    result = validate_patch_text("just some text\n")

    assert result["status"] == "invalid"
    assert "unified diff header" in result["errors"][0]


def test_rejects_text_with_nul_byte():
    result = validate_patch_text("diff --git a/file.py b/file.py\x00\n")

    assert result["status"] == "invalid"
    assert "NUL" in result["errors"][0]


def test_rejects_patch_with_no_targets():
    patch = (
        "--- /dev/null\n"
        "+++ /dev/null\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    )

    result = validate_patch_text(patch)

    assert result["status"] == "invalid"
    assert "any target files" in result["errors"][0]


def test_validate_patch_text_returns_fresh_dicts_and_lists():
    patch = (
        "diff --git a/file.py b/file.py\n"
        "--- a/file.py\n"
        "+++ b/file.py\n"
    )

    first = validate_patch_text(patch)
    second = validate_patch_text(patch)

    assert first == second
    assert first is not second
    assert first["targets"] is not second["targets"]
    assert first["errors"] is not second["errors"]
    assert first["warnings"] is not second["warnings"]


TESTS = [
    test_patch_validator_module_compatibility,
    test_missing_patch_file_returns_missing,
    test_empty_patch_file_returns_empty,
    test_valid_diff_git_patch_returns_valid,
    test_valid_old_new_patch_returns_valid,
    test_target_extraction_strips_a_and_b_prefixes,
    test_rejects_unix_absolute_path,
    test_rejects_windows_absolute_path,
    test_rejects_parent_traversal_path,
    test_rejects_git_path,
    test_rejects_aidc_config_path,
    test_rejects_env_path,
    test_rejects_ssh_path,
    test_warns_for_aidc_generated_report_but_does_not_fail,
    test_rejects_text_with_no_unified_diff_header,
    test_rejects_text_with_nul_byte,
    test_rejects_patch_with_no_targets,
    test_validate_patch_text_returns_fresh_dicts_and_lists,
]
