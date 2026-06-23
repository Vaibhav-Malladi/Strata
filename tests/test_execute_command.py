import contextlib
import sys
import tempfile
import textwrap
from pathlib import Path

import commands.execute_command as execute_command_module
from cli import main as cli_main
from command_executor import execute_command_adapter
from tests.helpers import capture_output, change_directory
from workflow_config import default_config, save_config


@contextlib.contextmanager
def change_argv(args: list[str]):
    original = sys.argv[:]
    sys.argv = args
    try:
        yield
    finally:
        sys.argv = original


def _create_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "main.py").write_text("print('hello')\n", encoding="utf-8")


def _write_prompt(root: Path) -> Path:
    prompt_path = root / ".aidc" / "agent_prompt.md"
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text("prompt", encoding="utf-8")
    return prompt_path


def _save_config(root: Path, **overrides) -> None:
    config = default_config()
    config.update(overrides)
    save_config(config, root)


def _run_execute_cli(root: Path, *args: str):
    with change_directory(root):
        with change_argv(["cli.py", "execute", *args]):
            return capture_output(cli_main)


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


def test_execute_prompt_file_ready_returns_nonzero_and_says_manual():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _save_config(root, adapter="prompt_file", prompt_path=".aidc/agent_prompt.md")
        _write_prompt(root)

        exit_code, output = _run_execute_cli(root)

        assert exit_code == 1
        assert "Execute adapter" in output
        assert "manual" in output
        assert "prompt_file is manual" in output
        assert "Executes command" in output
        assert "Applies patch" in output


def test_execute_optional_root_argument_works():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _save_config(root, adapter="prompt_file", prompt_path=".aidc/agent_prompt.md")
        _write_prompt(root)

        exit_code, output = _run_execute_cli(Path(temp_dir), str(root))

        assert exit_code == 1
        assert "Execute adapter" in output
        assert "manual" in output


def test_execute_command_ready_returns_zero_when_valid_patch_produced():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _write_prompt(root)

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
        _save_config(
            root,
            mode="hybrid",
            agent="local",
            adapter="command",
            prompt_path=".aidc/agent_prompt.md",
            command=command,
        )

        exit_code, output = _run_execute_cli(root)

        assert exit_code == 0
        assert "Execute adapter" in output
        assert "patch_ready" in output
        assert "Executes command  yes" in output
        assert "Applies patch     no" in output
        assert "Return code" in output
        assert "Patch status" in output
        assert "Patch valid       yes" in output
        assert "Targets           main.py" in output
        assert "Next" in output
        assert "strata patch" in output
        assert "strata apply --dry-run" in output
        assert "strata apply" in output
        assert (root / "main.py").read_text(encoding="utf-8") == "print('hello')\n"


def test_execute_command_missing_patch_returns_nonzero():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _write_prompt(root)

        script_path = _write_script(
            root,
            "fake_ai.py",
            """
            from pathlib import Path

            Path(".aidc").mkdir(parents=True, exist_ok=True)
            """,
        )
        command = _python_command(script_path)
        _save_config(
            root,
            mode="hybrid",
            agent="local",
            adapter="command",
            prompt_path=".aidc/agent_prompt.md",
            command=command,
        )

        exit_code, output = _run_execute_cli(root)

        assert exit_code == 1
        assert "missing_patch" in output
        assert "Command did not produce a patch file." in output
        assert "Patch valid       no" in output
        assert "Targets           -" in output


def test_execute_command_empty_patch_returns_nonzero():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _write_prompt(root)

        script_path = _write_script(
            root,
            "fake_ai.py",
            """
            from pathlib import Path

            Path(".aidc").mkdir(parents=True, exist_ok=True)
            Path(".aidc/agent_patch.diff").write_text("", encoding="utf-8")
            """,
        )
        command = _python_command(script_path)
        _save_config(
            root,
            mode="hybrid",
            agent="local",
            adapter="command",
            prompt_path=".aidc/agent_prompt.md",
            command=command,
        )

        exit_code, output = _run_execute_cli(root)

        assert exit_code == 1
        assert "empty_patch" in output
        assert "Command executed but produced an empty patch." in output
        assert "Patch valid       no" in output


def test_execute_command_invalid_patch_returns_nonzero():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _write_prompt(root)

        script_path = _write_script(
            root,
            "fake_ai.py",
            """
            from pathlib import Path

            Path(".aidc").mkdir(parents=True, exist_ok=True)
            Path(".aidc/agent_patch.diff").write_text("this is not a diff\\n", encoding="utf-8")
            """,
        )
        command = _python_command(script_path)
        _save_config(
            root,
            mode="hybrid",
            agent="local",
            adapter="command",
            prompt_path=".aidc/agent_prompt.md",
            command=command,
        )

        exit_code, output = _run_execute_cli(root)

        assert exit_code == 1
        assert "invalid_patch" in output
        assert "Patch failed validation." in output
        assert "Patch valid       no" in output
        assert "Targets           -" in output


def test_execute_command_non_zero_exit_returns_nonzero():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _write_prompt(root)

        script_path = _write_script(
            root,
            "fake_ai.py",
            """
            import sys

            sys.exit(2)
            """,
        )
        command = _python_command(script_path)
        _save_config(
            root,
            mode="hybrid",
            agent="local",
            adapter="command",
            prompt_path=".aidc/agent_prompt.md",
            command=command,
        )

        exit_code, output = _run_execute_cli(root)

        assert exit_code == 1
        assert "command_failed" in output
        assert "Command exited with code 2." in output
        assert "Return code       2" in output
        assert "Patch status" in output
        assert "missing" in output


def test_execute_missing_prompt_returns_nonzero_and_says_not_ready():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _save_config(
            root,
            mode="hybrid",
            agent="codex",
            adapter="prompt_file",
            prompt_path=".aidc/agent_prompt.md",
        )

        exit_code, output = _run_execute_cli(root)

        assert exit_code == 1
        assert "not_ready" in output
        assert "Prompt file not found" in output


def test_execute_planned_adapter_returns_nonzero_with_clear_message():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _save_config(
            root,
            mode="hybrid",
            agent="local",
            adapter="ollama",
            prompt_path=".aidc/agent_prompt.md",
        )

        exit_code, output = _run_execute_cli(root)

        assert exit_code == 1
        assert "not_implemented" in output
        assert "HTTP adapter execution is not implemented yet." in output


def test_execute_command_family_planned_adapters_do_not_execute():
    original_execute = execute_command_module.execute_command_adapter

    def _fail(*_args, **_kwargs):
        raise AssertionError("execute_command_adapter should not be called")

    execute_command_module.execute_command_adapter = _fail
    try:
        for adapter in ("aider", "codex_cli"):
            with tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                _create_repo(root)
                _save_config(
                    root,
                    mode="hybrid",
                    agent="local",
                    adapter=adapter,
                    prompt_path=".aidc/agent_prompt.md",
                )

                exit_code, output = _run_execute_cli(root)

                assert exit_code == 1
                assert "not_implemented" in output
                assert "Command-family preset execution is not implemented yet." in output
                assert adapter in output
    finally:
        execute_command_module.execute_command_adapter = original_execute


def test_execute_http_family_planned_adapters_do_not_execute():
    original_execute = execute_command_module.execute_command_adapter

    def _fail(*_args, **_kwargs):
        raise AssertionError("execute_command_adapter should not be called")

    execute_command_module.execute_command_adapter = _fail
    try:
        for adapter in ("ollama", "openai_compatible_http"):
            with tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                _create_repo(root)
                _save_config(
                    root,
                    mode="hybrid",
                    agent="local",
                    adapter=adapter,
                    prompt_path=".aidc/agent_prompt.md",
                )

                exit_code, output = _run_execute_cli(root)

                assert exit_code == 1
                assert "not_implemented" in output
                assert "HTTP adapter execution is not implemented yet." in output
                assert adapter in output
    finally:
        execute_command_module.execute_command_adapter = original_execute


def test_execute_output_includes_expected_rows():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _save_config(root, adapter="prompt_file", prompt_path=".aidc/agent_prompt.md")
        _write_prompt(root)

        exit_code, output = _run_execute_cli(root)

        assert exit_code == 1
        assert "Status" in output
        assert "Mode" in output
        assert "Agent" in output
        assert "Adapter" in output
        assert "Prompt" in output
        assert "Patch" in output
        assert "Command" in output
        assert "Executes command" in output
        assert "Applies patch" in output
        assert "Return code" in output
        assert "Patch status" in output
        assert "Patch valid" in output
        assert "Targets" in output
        assert "Message" in output


def test_execute_command_captures_stdout_and_stderr_and_does_not_apply_patch():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _write_prompt(root)
        (root / "main.py").write_text("print('old')\n", encoding="utf-8")

        script_path = _write_script(
            root,
            "fake_ai.py",
            f"""
            import sys
            from pathlib import Path

            sys.stdout.write("stdout-line\\n")
            sys.stderr.write("stderr-line\\n")
            Path(".aidc").mkdir(parents=True, exist_ok=True)
            Path(".aidc/agent_patch.diff").write_text({ _valid_patch_text()!r }, encoding="utf-8")
            """,
        )
        command = _python_command(script_path)
        _save_config(
            root,
            mode="hybrid",
            agent="local",
            adapter="command",
            prompt_path=".aidc/agent_prompt.md",
            command=command,
        )

        result = execute_command_adapter(root, command=command)

        assert result["status"] == "patch_ready"
        assert "stdout-line" in result["stdout"]
        assert "stderr-line" in result["stderr"]
        assert (root / "main.py").read_text(encoding="utf-8") == "print('old')\n"


TESTS = [
    test_execute_prompt_file_ready_returns_nonzero_and_says_manual,
    test_execute_optional_root_argument_works,
    test_execute_command_ready_returns_zero_when_valid_patch_produced,
    test_execute_command_missing_patch_returns_nonzero,
    test_execute_command_empty_patch_returns_nonzero,
    test_execute_command_invalid_patch_returns_nonzero,
    test_execute_command_non_zero_exit_returns_nonzero,
    test_execute_missing_prompt_returns_nonzero_and_says_not_ready,
    test_execute_planned_adapter_returns_nonzero_with_clear_message,
    test_execute_output_includes_expected_rows,
    test_execute_command_captures_stdout_and_stderr_and_does_not_apply_patch,
]
