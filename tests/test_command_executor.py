import sys
import tempfile
import textwrap
from pathlib import Path

from command_executor import execute_command_adapter, parse_command


def _write_script(root: Path, name: str, body: str) -> Path:
    script_path = root / name
    script_path.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
    return script_path


def _python_command(script_path: Path) -> str:
    return f'"{sys.executable}" "{script_path}"'


def _valid_patch_text() -> str:
    return (
        "diff --git a/main.py b/main.py\n"
        "--- /dev/null\n"
        "+++ b/main.py\n"
        "@@ -0,0 +1 @@\n"
        '+print("hello")\n'
    )


def test_parse_command_splits_simple_command():
    assert parse_command("python -m module") == ["python", "-m", "module"]


def test_empty_command_returns_not_ready_and_executed_false():
    with tempfile.TemporaryDirectory() as temp_dir:
        result = execute_command_adapter(temp_dir, command="")

        assert result["status"] == "not_ready"
        assert result["executed"] is False
        assert result["patch_status"] == "missing"
        assert result["targets"] == []
        assert result["errors"] == ["Command is not configured."]


def test_none_command_returns_not_ready_and_executed_false():
    with tempfile.TemporaryDirectory() as temp_dir:
        result = execute_command_adapter(temp_dir, command=None)

        assert result["status"] == "not_ready"
        assert result["executed"] is False
        assert result["patch_status"] == "missing"


def test_invalid_command_returns_invalid_command():
    with tempfile.TemporaryDirectory() as temp_dir:
        result = execute_command_adapter(temp_dir, command='"unterminated')

        assert result["status"] == "invalid_command"
        assert result["executed"] is False
        assert result["patch_status"] == "missing"
        assert result["patch_valid"] is False
        assert result["targets"] == []
        assert result["errors"]


def test_command_returning_zero_and_writing_valid_patch_returns_patch_ready():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        script_path = _write_script(
            root,
            "fake_ai.py",
            f"""
            from pathlib import Path

            Path(".aidc").mkdir(parents=True, exist_ok=True)
            Path(".aidc/agent_patch.diff").write_text({ _valid_patch_text()!r }, encoding="utf-8")
            """,
        )

        result = execute_command_adapter(root, command=_python_command(script_path))

        assert result["status"] == "patch_ready"
        assert result["executed"] is True
        assert result["returncode"] == 0
        assert result["timed_out"] is False
        assert result["patch_status"] == "ready"
        assert result["patch_valid"] is True
        assert result["targets"] == ["main.py"]
        assert result["message"] == "Command executed and produced a valid patch."


def test_command_returning_non_zero_returns_command_failed():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        script_path = _write_script(
            root,
            "fake_ai.py",
            """
            import sys

            sys.exit(2)
            """,
        )

        result = execute_command_adapter(root, command=_python_command(script_path))

        assert result["status"] == "command_failed"
        assert result["executed"] is True
        assert result["returncode"] == 2
        assert result["timed_out"] is False
        assert result["patch_status"] == "missing"
        assert result["patch_valid"] is False
        assert result["errors"] == ["Command exited with code 2."]


def test_command_returning_zero_but_no_patch_returns_missing_patch():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        script_path = _write_script(
            root,
            "fake_ai.py",
            """
            from pathlib import Path

            Path(".aidc").mkdir(parents=True, exist_ok=True)
            """,
        )

        result = execute_command_adapter(root, command=_python_command(script_path))

        assert result["status"] == "missing_patch"
        assert result["executed"] is True
        assert result["returncode"] == 0
        assert result["patch_status"] == "missing"
        assert result["patch_valid"] is False
        assert result["errors"] == ["Command did not produce a patch file."]


def test_command_writing_empty_patch_returns_empty_patch():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        script_path = _write_script(
            root,
            "fake_ai.py",
            """
            from pathlib import Path

            Path(".aidc").mkdir(parents=True, exist_ok=True)
            Path(".aidc/agent_patch.diff").write_text("", encoding="utf-8")
            """,
        )

        result = execute_command_adapter(root, command=_python_command(script_path))

        assert result["status"] == "empty_patch"
        assert result["patch_status"] == "empty"
        assert result["patch_valid"] is False
        assert result["errors"] == ["Command produced an empty patch file."]


def test_command_writing_invalid_patch_returns_invalid_patch():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        script_path = _write_script(
            root,
            "fake_ai.py",
            """
            from pathlib import Path

            Path(".aidc").mkdir(parents=True, exist_ok=True)
            Path(".aidc/agent_patch.diff").write_text("this is not a diff\\n", encoding="utf-8")
            """,
        )

        result = execute_command_adapter(root, command=_python_command(script_path))

        assert result["status"] == "invalid_patch"
        assert result["executed"] is True
        assert result["returncode"] == 0
        assert result["patch_status"] == "ready"
        assert result["patch_valid"] is False
        assert result["targets"] == []
        assert result["errors"] == ["Patch failed validation."]


def test_timeout_returns_timeout():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        script_path = _write_script(
            root,
            "fake_ai.py",
            """
            import time

            time.sleep(5)
            """,
        )

        result = execute_command_adapter(root, command=_python_command(script_path), timeout_seconds=1)

        assert result["status"] == "timeout"
        assert result["executed"] is True
        assert result["timed_out"] is True
        assert result["returncode"] is None
        assert result["errors"] == ["Command timed out after 1 seconds."]


def test_stdout_and_stderr_are_captured():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        script_path = _write_script(
            root,
            "fake_ai.py",
            f"""
            import sys
            from pathlib import Path

            sys.stdout.write("hello stdout\\n")
            sys.stderr.write("hello stderr\\n")
            Path(".aidc").mkdir(parents=True, exist_ok=True)
            Path(".aidc/agent_patch.diff").write_text({ _valid_patch_text()!r }, encoding="utf-8")
            """,
        )

        result = execute_command_adapter(root, command=_python_command(script_path))

        assert "hello stdout" in result["stdout"]
        assert "hello stderr" in result["stderr"]


def test_command_runs_with_cwd_root():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        script_path = _write_script(
            root,
            "fake_ai.py",
            """
            from pathlib import Path

            Path("cwd.txt").write_text(str(Path.cwd()), encoding="utf-8")
            Path(".aidc").mkdir(parents=True, exist_ok=True)
            Path(".aidc/agent_patch.diff").write_text(
                "diff --git a/main.py b/main.py\\n--- /dev/null\\n+++ b/main.py\\n@@ -0,0 +1 @@\\n+print('cwd')\\n",
                encoding="utf-8",
            )
            """,
        )

        result = execute_command_adapter(root, command=_python_command(script_path))

        assert result["status"] == "patch_ready"
        assert (root / "cwd.txt").read_text(encoding="utf-8") == str(root)


def test_result_dict_uses_fresh_lists():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        script_path = _write_script(
            root,
            "fake_ai.py",
            f"""
            from pathlib import Path

            Path(".aidc").mkdir(parents=True, exist_ok=True)
            Path(".aidc/agent_patch.diff").write_text({ _valid_patch_text()!r }, encoding="utf-8")
            """,
        )
        command = _python_command(script_path)

        result_one = execute_command_adapter(root, command=command)
        result_two = execute_command_adapter(root, command=command)

        assert result_one["targets"] is not result_two["targets"]
        assert result_one["errors"] is not result_two["errors"]
        assert result_one["warnings"] is not result_two["warnings"]

        result_one["targets"].append("mutated")
        result_one["errors"].append("mutated")
        result_one["warnings"].append("mutated")

        assert result_two["targets"] == ["main.py"]
        assert result_two["errors"] == []
        assert result_two["warnings"] == []


def test_executor_does_not_apply_patch():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        (root / "main.py").write_text("print('old')\n", encoding="utf-8")

        script_path = _write_script(
            root,
            "fake_ai.py",
            """
            from pathlib import Path

            Path(".aidc").mkdir(parents=True, exist_ok=True)
            Path(".aidc/agent_patch.diff").write_text(
                "diff --git a/main.py b/main.py\\n--- a/main.py\\n+++ b/main.py\\n@@ -1 +1 @@\\n-print('old')\\n+print('new')\\n",
                encoding="utf-8",
            )
            """,
        )

        result = execute_command_adapter(root, command=_python_command(script_path))

        assert result["status"] == "patch_ready"
        assert (root / "main.py").read_text(encoding="utf-8") == "print('old')\n"


TESTS = [
    test_parse_command_splits_simple_command,
    test_empty_command_returns_not_ready_and_executed_false,
    test_none_command_returns_not_ready_and_executed_false,
    test_invalid_command_returns_invalid_command,
    test_command_returning_zero_and_writing_valid_patch_returns_patch_ready,
    test_command_returning_non_zero_returns_command_failed,
    test_command_returning_zero_but_no_patch_returns_missing_patch,
    test_command_writing_empty_patch_returns_empty_patch,
    test_command_writing_invalid_patch_returns_invalid_patch,
    test_timeout_returns_timeout,
    test_stdout_and_stderr_are_captured,
    test_command_runs_with_cwd_root,
    test_result_dict_uses_fresh_lists,
    test_executor_does_not_apply_patch,
]
