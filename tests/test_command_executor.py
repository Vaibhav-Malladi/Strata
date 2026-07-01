import ast
import sys
import tempfile
import textwrap
from pathlib import Path

import command_executor as command_executor_module
import fs_utils as fs_utils_module
from command_executor import execute_command_adapter, parse_command
import strata.utils.paths as paths
import strata.utils.shell as shell


def test_new_utility_import_paths_match_compatibility_shims():
    assert fs_utils_module.atomic_write_text is paths.atomic_write_text
    assert fs_utils_module.atomic_write_json is paths.atomic_write_json
    assert command_executor_module.parse_command is shell.parse_command
    assert command_executor_module.execute_command_adapter is shell.execute_command_adapter


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


def test_run_argv_always_uses_list_without_shell():
    captured = {}

    def _fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs

        class _Completed:
            returncode = 0
            stdout = ""
            stderr = ""

        return _Completed()

    original_run = shell.subprocess.run
    shell.subprocess.run = _fake_run
    try:
        shell.run_argv(("python", "--version"), cwd=".", timeout=5)
    finally:
        shell.subprocess.run = original_run

    assert captured["argv"] == ["python", "--version"]
    assert captured["kwargs"]["shell"] is False
    assert captured["kwargs"]["check"] is False
    assert captured["kwargs"]["timeout"] == 5


def test_run_argv_rejects_command_strings():
    try:
        shell.run_argv("python --version")
    except TypeError as error:
        assert "sequence of arguments" in str(error)
    else:
        raise AssertionError("run_argv accepted a command string")


def test_command_adapter_uses_named_shell_compatible_path():
    captured = {}

    def _fake_adapter_run(argv, **kwargs):
        captured["argv"] = list(argv)
        captured["kwargs"] = kwargs

        class _Completed:
            returncode = 0
            stdout = ""
            stderr = ""

        return _Completed()

    original_run = shell.run_shell_compatible_adapter_command
    shell.run_shell_compatible_adapter_command = _fake_adapter_run
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = shell.execute_command_adapter(
                temp_dir,
                command='python "fake ai.py" --prompt .aidc/agent_prompt.md',
            )
    finally:
        shell.run_shell_compatible_adapter_command = original_run

    assert result["status"] == "missing_patch"
    assert captured["argv"] == [
        "python",
        "fake ai.py",
        "--prompt",
        ".aidc/agent_prompt.md",
    ]
    assert captured["kwargs"]["timeout"] == 120


def test_product_code_limits_subprocess_execution_to_safe_wrapper():
    product_root = Path(__file__).resolve().parents[1] / "strata"
    violations = []

    for source_path in sorted(product_root.rglob("*.py")):
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(source_path))
        relative_path = source_path.relative_to(product_root.parent).as_posix()
        allowed_calls = set()
        module_aliases = {}
        execution_aliases = {}

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in {"os", "subprocess"}:
                        module_aliases[alias.asname or alias.name] = alias.name
            elif isinstance(node, ast.ImportFrom) and node.module in {"os", "subprocess"}:
                for alias in node.names:
                    execution_aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"

        if relative_path == "strata/utils/shell.py":
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "run_argv":
                    allowed_calls = {id(child) for child in ast.walk(node) if isinstance(child, ast.Call)}
                    break

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            function_name = _ast_call_name(node.func)
            root_name, separator, remainder = function_name.partition(".")
            if root_name in module_aliases:
                function_name = module_aliases[root_name] + (separator + remainder if separator else "")
            elif function_name in execution_aliases:
                function_name = execution_aliases[function_name]
            location = f"{relative_path}:{node.lineno}"

            if function_name in {
                "os.system",
                "os.popen",
                "subprocess.call",
                "subprocess.check_call",
                "subprocess.check_output",
                "subprocess.Popen",
                "subprocess.run",
            } and id(node) not in allowed_calls:
                violations.append(f"{location}: unexpected execution call {function_name}")

            for keyword in node.keywords:
                if keyword.arg == "shell" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True:
                    violations.append(f"{location}: shell=True is forbidden")

    assert not violations, "Unexpected product shell execution:\n" + "\n".join(violations)


def _ast_call_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _ast_call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


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
            """
            from pathlib import Path

            Path(".aidc").mkdir(parents=True, exist_ok=True)
            Path(".aidc/agent_patch.diff").write_text({0!r}, encoding="utf-8")
            """.format(_valid_patch_text()),
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


def test_default_timeout_is_passed_to_subprocess_run():
    captured = {}

    def _fake_run(*_args, **kwargs):
        captured["timeout"] = kwargs.get("timeout")

        class _Completed:
            returncode = 0
            stdout = ""
            stderr = ""

        return _Completed()

    original_run = command_executor_module.subprocess.run
    command_executor_module.subprocess.run = _fake_run
    try:
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

            execute_command_adapter(root, command=_python_command(script_path))
    finally:
        command_executor_module.subprocess.run = original_run

    assert captured["timeout"] == 120


def test_custom_timeout_is_passed_to_subprocess_run():
    captured = {}

    def _fake_run(*_args, **kwargs):
        captured["timeout"] = kwargs.get("timeout")

        class _Completed:
            returncode = 0
            stdout = ""
            stderr = ""

        return _Completed()

    original_run = command_executor_module.subprocess.run
    command_executor_module.subprocess.run = _fake_run
    try:
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

            execute_command_adapter(root, command=_python_command(script_path), timeout_seconds=7)
    finally:
        command_executor_module.subprocess.run = original_run

    assert captured["timeout"] == 7


def test_stdout_and_stderr_are_captured():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        script_path = _write_script(
            root,
            "fake_ai.py",
            """
            import sys
            from pathlib import Path

            sys.stdout.write("hello stdout\\n")
            sys.stderr.write("hello stderr\\n")
            Path(".aidc").mkdir(parents=True, exist_ok=True)
            Path(".aidc/agent_patch.diff").write_text({0!r}, encoding="utf-8")
            """.format(_valid_patch_text()),
        )

        result = execute_command_adapter(root, command=_python_command(script_path))

        assert "hello stdout" in result["stdout"]
        assert "hello stderr" in result["stderr"]


def test_stdout_and_stderr_are_redacted_when_they_contain_secrets():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        secret = "sk-testsecret-123456"
        script_path = _write_script(
            root,
            "fake_ai.py",
            f"""
            import sys

            sys.stdout.write("token={secret}\\n")
            sys.stderr.write("Authorization: Bearer {secret}\\n")
            sys.exit(2)
            """,
        )

        result = execute_command_adapter(root, command=_python_command(script_path))

        assert result["status"] == "command_failed"
        assert secret not in result["stdout"]
        assert secret not in result["stderr"]
        assert "<redacted>" in result["stdout"] or "<redacted>" in result["stderr"]
        assert result["errors"] == ["Command exited with code 2."]


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
        actual = Path(
            (root / "cwd.txt").read_text(encoding="utf-8").strip()
        ).resolve()
        assert actual == root.resolve()


def test_result_dict_uses_fresh_lists():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        script_path = _write_script(
            root,
            "fake_ai.py",
            """
            from pathlib import Path

            Path(".aidc").mkdir(parents=True, exist_ok=True)
            Path(".aidc/agent_patch.diff").write_text({0!r}, encoding="utf-8")
            """.format(_valid_patch_text()),
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
    test_new_utility_import_paths_match_compatibility_shims,
    test_parse_command_splits_simple_command,
    test_run_argv_always_uses_list_without_shell,
    test_run_argv_rejects_command_strings,
    test_command_adapter_uses_named_shell_compatible_path,
    test_product_code_limits_subprocess_execution_to_safe_wrapper,
    test_empty_command_returns_not_ready_and_executed_false,
    test_none_command_returns_not_ready_and_executed_false,
    test_invalid_command_returns_invalid_command,
    test_command_returning_zero_and_writing_valid_patch_returns_patch_ready,
    test_command_returning_non_zero_returns_command_failed,
    test_command_returning_zero_but_no_patch_returns_missing_patch,
    test_command_writing_empty_patch_returns_empty_patch,
    test_command_writing_invalid_patch_returns_invalid_patch,
    test_timeout_returns_timeout,
    test_default_timeout_is_passed_to_subprocess_run,
    test_custom_timeout_is_passed_to_subprocess_run,
    test_stdout_and_stderr_are_captured,
    test_stdout_and_stderr_are_redacted_when_they_contain_secrets,
    test_command_runs_with_cwd_root,
    test_result_dict_uses_fresh_lists,
    test_executor_does_not_apply_patch,
]
