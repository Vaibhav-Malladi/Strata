import ast
import inspect
import tempfile
from pathlib import Path

import patch_applier
import strata.patch.applier as new_patch_applier
from patch_applier import apply_patch_file, apply_patch_text, parse_unified_diff
from tests.helpers import change_directory


def test_patch_applier_module_compatibility():
    assert patch_applier.apply_patch_file is new_patch_applier.apply_patch_file
    assert patch_applier.apply_patch_text is new_patch_applier.apply_patch_text
    assert patch_applier.parse_unified_diff is new_patch_applier.parse_unified_diff


def _write_file(root: Path, relative_path: str, content: str) -> Path:
    file_path = root / relative_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    return file_path


def _write_patch_file(root: Path, content: str) -> Path:
    patch_path = root / ".aidc" / "agent_patch.diff"
    patch_path.parent.mkdir(parents=True, exist_ok=True)
    patch_path.write_text(content, encoding="utf-8")
    return patch_path


def _create_symlink(link: Path, target: Path) -> bool:
    try:
        link.symlink_to(target)
    except (NotImplementedError, OSError) as error:
        print(f"SKIP: symlink creation is not permitted on this platform: {error}")
        return False
    return True


def test_apply_patch_file_modifies_existing_file():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_file(root, "main.py", 'print("old")\n')
        _write_patch_file(
            root,
            (
                "diff --git a/main.py b/main.py\n"
                "--- a/main.py\n"
                "+++ b/main.py\n"
                "@@ -1 +1 @@\n"
                '-print("old")\n'
                '+print("new")\n'
            ),
        )

        with change_directory(root):
            result = apply_patch_file(root)

        assert result == {
            "status": "applied",
            "applied": True,
            "targets": ["main.py"],
            "changed_files": ["main.py"],
            "errors": [],
            "warnings": [],
            "message": "Patch applied successfully.",
        }
        assert (root / "main.py").read_text(encoding="utf-8") == 'print("new")\n'


def test_apply_patch_text_creates_new_file():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        patch = (
            "diff --git a/new_file.py b/new_file.py\n"
            "new file mode 100644\n"
            "index 0000000..1111111\n"
            "--- /dev/null\n"
            "+++ b/new_file.py\n"
            "@@ -0,0 +1,2 @@\n"
            '+print("hello")\n'
            '+print("world")\n'
        )

        result = apply_patch_text(root, patch)

        assert result["status"] == "applied"
        assert result["applied"] is True
        assert result["targets"] == ["new_file.py"]
        assert result["changed_files"] == ["new_file.py"]
        assert (root / "new_file.py").read_text(encoding="utf-8") == 'print("hello")\nprint("world")\n'


def test_apply_patch_text_deletes_file():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_file(root, "remove_me.py", 'print("delete")\n')
        patch = (
            "diff --git a/remove_me.py b/remove_me.py\n"
            "deleted file mode 100644\n"
            "index 2222222..0000000\n"
            "--- a/remove_me.py\n"
            "+++ /dev/null\n"
            "@@ -1 +0,0 @@\n"
            '-print("delete")\n'
        )

        result = apply_patch_text(root, patch)

        assert result["status"] == "applied"
        assert result["applied"] is True
        assert result["targets"] == ["remove_me.py"]
        assert result["changed_files"] == ["remove_me.py"]
        assert not (root / "remove_me.py").exists()


def test_apply_patch_text_rejects_rename_patch():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        patch = (
            "diff --git a/old_name.py b/new_name.py\n"
            "rename from old_name.py\n"
            "rename to new_name.py\n"
            "--- a/old_name.py\n"
            "+++ b/new_name.py\n"
            "@@ -1 +1 @@\n"
            '-print("old")\n'
            '+print("new")\n'
        )

        result = apply_patch_text(root, patch)

        assert result["status"] == "failed"
        assert result["applied"] is False
        assert "rename from" in result["errors"][0]


def test_apply_patch_text_rejects_binary_patch():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        patches = [
            "diff --git a/image.png b/image.png\n"
            "Binary files a/image.png and b/image.png differ\n",
            "diff --git a/image.png b/image.png\n"
            "GIT binary patch\n"
            "literal 0\n",
        ]

        for patch in patches:
            result = apply_patch_text(root, patch)

            assert result["status"] == "failed"
            assert result["applied"] is False
            assert any(
                marker in error
                for marker in ("Binary files", "GIT binary patch")
                for error in result["errors"]
            )


def test_apply_patch_text_rejects_mode_only_change_patch():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        patch = (
            "diff --git a/script.py b/script.py\n"
            "old mode 100644\n"
            "new mode 100755\n"
            "--- a/script.py\n"
            "+++ b/script.py\n"
            "@@ -1 +1 @@\n"
            '-print("old")\n'
            '+print("new")\n'
        )

        result = apply_patch_text(root, patch)

        assert result["status"] == "failed"
        assert result["applied"] is False
        assert any("mode" in error for error in result["errors"])


def test_apply_patch_text_rejects_symlink_mode_patch():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        patch = (
            "diff --git a/link b/link\n"
            "new file mode 120000\n"
            "index 0000000..1234567\n"
            "--- /dev/null\n"
            "+++ b/link\n"
            "@@ -0,0 +1 @@\n"
            "+target\n"
        )

        result = apply_patch_text(root, patch)

        assert result["status"] == "failed"
        assert result["applied"] is False
        assert "120000" in result["errors"][0]


def test_apply_patch_text_handles_multiple_files():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_file(root, "first.py", 'print("first")\n')
        _write_file(root, "second.py", 'print("second")\n')
        patch = (
            "diff --git a/first.py b/first.py\n"
            "--- a/first.py\n"
            "+++ b/first.py\n"
            "@@ -1 +1 @@\n"
            '-print("first")\n'
            '+print("alpha")\n'
            "diff --git a/second.py b/second.py\n"
            "--- a/second.py\n"
            "+++ b/second.py\n"
            "@@ -1 +1 @@\n"
            '-print("second")\n'
            '+print("beta")\n'
        )

        result = apply_patch_text(root, patch)

        assert result["status"] == "applied"
        assert result["changed_files"] == ["first.py", "second.py"]
        assert (root / "first.py").read_text(encoding="utf-8") == 'print("alpha")\n'
        assert (root / "second.py").read_text(encoding="utf-8") == 'print("beta")\n'


def test_apply_patch_text_handles_multiple_hunks():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_file(
            root,
            "multi.py",
            "line1\nline2\nline3\nline4\nline5\nline6\n",
        )
        patch = (
            "diff --git a/multi.py b/multi.py\n"
            "--- a/multi.py\n"
            "+++ b/multi.py\n"
            "@@ -1,3 +1,3 @@\n"
            " line1\n"
            "-line2\n"
            "+LINE2\n"
            " line3\n"
            "@@ -4,3 +4,3 @@\n"
            " line4\n"
            "-line5\n"
            "+LINE5\n"
            " line6\n"
        )

        result = apply_patch_text(root, patch)

        assert result["status"] == "applied"
        assert result["changed_files"] == ["multi.py"]
        assert (root / "multi.py").read_text(encoding="utf-8") == "line1\nLINE2\nline3\nline4\nLINE5\nline6\n"


def test_apply_patch_text_fails_safely_when_target_file_is_missing_for_modification():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        patch = (
            "diff --git a/missing.py b/missing.py\n"
            "--- a/missing.py\n"
            "+++ b/missing.py\n"
            "@@ -1 +1 @@\n"
            "-print(\"old\")\n"
            "+print(\"new\")\n"
        )

        result = apply_patch_text(root, patch)

        assert result["status"] == "failed"
        assert result["applied"] is False
        assert result["changed_files"] == []
        assert "Target file not found" in result["errors"][0]
        assert not (root / "missing.py").exists()


def test_apply_patch_text_fails_safely_when_hunk_context_does_not_match():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_file(root, "context.py", 'print("actual")\n')
        patch = (
            "diff --git a/context.py b/context.py\n"
            "--- a/context.py\n"
            "+++ b/context.py\n"
            "@@ -1 +1 @@\n"
            '-print("expected")\n'
            '+print("changed")\n'
        )

        result = apply_patch_text(root, patch)

        assert result["status"] == "failed"
        assert result["applied"] is False
        assert result["changed_files"] == []
        assert "Hunk failed for context.py." in result["errors"][0]
        assert (root / "context.py").read_text(encoding="utf-8") == 'print("actual")\n'


def test_apply_patch_text_fails_safely_for_invalid_patch_text():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_file(root, "safe.py", 'print("safe")\n')

        result = apply_patch_text(root, "this is not a diff\n")

        assert result["status"] == "failed"
        assert result["applied"] is False
        assert "unified diff header" in result["errors"][0]
        assert (root / "safe.py").read_text(encoding="utf-8") == 'print("safe")\n'


def test_apply_patch_text_fails_safely_for_unsafe_path_rejected_by_validator():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        patch = (
            "diff --git a/.env b/.env\n"
            "--- a/.env\n"
            "+++ b/.env\n"
            "@@ -1 +1 @@\n"
            "-SECRET=old\n"
            "+SECRET=new\n"
        )

        result = apply_patch_text(root, patch)

        assert result["status"] == "failed"
        assert result["applied"] is False
        assert ".env" in result["errors"][0]
        assert not (root / ".env").exists()


def test_apply_patch_text_rejects_traversal_before_writing_any_file():
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        root = temp_root / "level1" / "repo"
        root.mkdir(parents=True)
        _write_file(root, "safe.py", 'print("safe")\n')
        outside_path = temp_root / "outside.txt"
        patch = (
            "diff --git a/safe.py b/safe.py\n"
            "--- a/safe.py\n"
            "+++ b/safe.py\n"
            "@@ -1 +1 @@\n"
            '-print("safe")\n'
            '+print("changed")\n'
            "diff --git a/../../outside.txt b/../../outside.txt\n"
            "--- /dev/null\n"
            "+++ b/../../outside.txt\n"
            "@@ -0,0 +1 @@\n"
            "+unsafe\n"
        )

        result = apply_patch_text(root, patch)

        assert result["status"] == "failed"
        assert result["applied"] is False
        assert "Unsafe patch path" in result["errors"][0]
        assert (root / "safe.py").read_text(encoding="utf-8") == 'print("safe")\n'
        assert not outside_path.exists()


def test_apply_patch_text_rejects_symlink_file_target():
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        root = temp_root / "repo"
        root.mkdir()
        outside_path = temp_root / "outside.py"
        outside_path.write_text('print("old")\n', encoding="utf-8")
        if not _create_symlink(root / "linked.py", outside_path):
            return

        patch = (
            "diff --git a/linked.py b/linked.py\n"
            "--- a/linked.py\n"
            "+++ b/linked.py\n"
            "@@ -1 +1 @@\n"
            '-print("old")\n'
            '+print("new")\n'
        )

        result = new_patch_applier.apply_patch_text(root, patch)

        assert result["status"] == "failed"
        assert result["applied"] is False
        assert result["errors"] == [
            "Unsafe patch path 'linked.py': patch targets must not be symbolic links."
        ]
        assert outside_path.read_text(encoding="utf-8") == 'print("old")\n'


def test_apply_patch_text_failure_writes_nothing_and_stays_atomic():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_file(root, "first.py", 'print("one")\n')
        _write_file(root, "second.py", 'print("two")\n')
        patch = (
            "diff --git a/first.py b/first.py\n"
            "--- a/first.py\n"
            "+++ b/first.py\n"
            "@@ -1 +1 @@\n"
            '-print("one")\n'
            '+print("ONE")\n'
            "diff --git a/missing.py b/missing.py\n"
            "--- a/missing.py\n"
            "+++ b/missing.py\n"
            "@@ -1 +1 @@\n"
            '-print("missing")\n'
            '+print("MISSING")\n'
        )

        result = apply_patch_text(root, patch)

        assert result["status"] == "failed"
        assert result["applied"] is False
        assert result["changed_files"] == []
        assert (root / "first.py").read_text(encoding="utf-8") == 'print("one")\n'
        assert (root / "second.py").read_text(encoding="utf-8") == 'print("two")\n'


def test_apply_patch_text_returns_fresh_lists_each_time():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_file(root, "fresh.py", 'print("fresh")\n')
        patch = (
            "diff --git a/fresh.py b/fresh.py\n"
            "--- a/fresh.py\n"
            "+++ b/fresh.py\n"
            "@@ -1 +1 @@\n"
            '-print("fresh")\n'
            '+print("clean")\n'
        )

        first = apply_patch_text(root, patch)
        _write_file(root, "fresh.py", 'print("fresh")\n')
        second = apply_patch_text(root, patch)

        assert first == second
        assert first is not second
        assert first["targets"] is not second["targets"]
        assert first["changed_files"] is not second["changed_files"]
        assert first["errors"] is not second["errors"]
        assert first["warnings"] is not second["warnings"]


def test_patch_applier_does_not_use_subprocess_or_git_execution():
    source = inspect.getsource(new_patch_applier)
    tree = ast.parse(source)

    imported_modules: set[str] = set()
    executed_commands: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                if node.func.value.id == "subprocess":
                    executed_commands.append(node.func.attr)
                if node.func.value.id == "os" and node.func.attr in {"system", "popen"}:
                    executed_commands.append(node.func.attr)

    assert "subprocess" not in imported_modules
    assert "git" not in imported_modules
    assert not executed_commands


def test_parse_unified_diff_returns_targets_for_valid_patch():
    patch = (
        "diff --git a/example.py b/example.py\n"
        "--- a/example.py\n"
        "+++ b/example.py\n"
        "@@ -1 +1 @@\n"
        '-print("old")\n'
        '+print("new")\n'
    )

    result = parse_unified_diff(patch)

    assert result["status"] == "parsed"
    assert result["targets"] == ["example.py"]
    assert result["errors"] == []
    assert result["files"][0]["operation"] == "modify"


TESTS = [
    test_patch_applier_module_compatibility,
    test_apply_patch_file_modifies_existing_file,
    test_apply_patch_text_creates_new_file,
    test_apply_patch_text_deletes_file,
    test_apply_patch_text_rejects_rename_patch,
    test_apply_patch_text_rejects_binary_patch,
    test_apply_patch_text_rejects_mode_only_change_patch,
    test_apply_patch_text_rejects_symlink_mode_patch,
    test_apply_patch_text_handles_multiple_files,
    test_apply_patch_text_handles_multiple_hunks,
    test_apply_patch_text_fails_safely_when_target_file_is_missing_for_modification,
    test_apply_patch_text_fails_safely_when_hunk_context_does_not_match,
    test_apply_patch_text_fails_safely_for_invalid_patch_text,
    test_apply_patch_text_fails_safely_for_unsafe_path_rejected_by_validator,
    test_apply_patch_text_rejects_traversal_before_writing_any_file,
    test_apply_patch_text_rejects_symlink_file_target,
    test_apply_patch_text_failure_writes_nothing_and_stays_atomic,
    test_apply_patch_text_returns_fresh_lists_each_time,
    test_patch_applier_does_not_use_subprocess_or_git_execution,
    test_parse_unified_diff_returns_targets_for_valid_patch,
]
