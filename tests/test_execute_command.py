import contextlib
import subprocess
import sys
import tempfile
from pathlib import Path

from cli import main as cli_main
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


def test_execute_command_ready_returns_nonzero_and_says_not_implemented():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _save_config(
            root,
            mode="hybrid",
            agent="local",
            adapter="command",
            prompt_path=".aidc/agent_prompt.md",
            command="my-ai --prompt .aidc/agent_prompt.md --patch .aidc/agent_patch.diff",
        )
        _write_prompt(root)

        exit_code, output = _run_execute_cli(root)

        assert exit_code == 1
        assert "command" in output
        assert "not_implemented" in output
        assert "Command execution is not implemented yet." in output


def test_execute_command_missing_command_returns_nonzero_and_says_not_ready():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _save_config(
            root,
            mode="hybrid",
            agent="local",
            adapter="command",
            prompt_path=".aidc/agent_prompt.md",
            command=None,
        )
        _write_prompt(root)

        exit_code, output = _run_execute_cli(root)

        assert exit_code == 1
        assert "not_ready" in output
        assert "Adapter configuration is not ready." in output


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
        assert "planned" in output
        assert "Command execution is not implemented yet." in output or "Adapter is planned" in output


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
        assert "Message" in output


def test_execute_command_does_not_execute_configured_command():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _save_config(
            root,
            mode="hybrid",
            agent="local",
            adapter="command",
            prompt_path=".aidc/agent_prompt.md",
            command="my-ai --prompt .aidc/agent_prompt.md --patch .aidc/agent_patch.diff",
        )
        _write_prompt(root)

        original_run = subprocess.run

        def _fail(*_args, **_kwargs):
            raise AssertionError("subprocess.run should not be called")

        subprocess.run = _fail
        try:
            exit_code, output = _run_execute_cli(root)
        finally:
            subprocess.run = original_run

        assert exit_code == 1
        assert "Command execution is not implemented yet." in output


def test_execute_command_does_not_create_aidc():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)

        exit_code, output = _run_execute_cli(root)

        assert exit_code == 1
        assert not (root / ".aidc").exists()
        assert "Execute adapter" in output


def test_execute_command_does_not_apply_patches():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _save_config(
            root,
            mode="hybrid",
            agent="local",
            adapter="command",
            prompt_path=".aidc/agent_prompt.md",
            command="my-ai --prompt .aidc/agent_prompt.md --patch .aidc/agent_patch.diff",
        )
        _write_prompt(root)
        (root / "main.py").write_text("print('hello')\n", encoding="utf-8")

        exit_code, output = _run_execute_cli(root)

        assert exit_code == 1
        assert (root / "main.py").read_text(encoding="utf-8") == "print('hello')\n"
        assert "Applies patch" in output


TESTS = [
    test_execute_prompt_file_ready_returns_nonzero_and_says_manual,
    test_execute_optional_root_argument_works,
    test_execute_command_ready_returns_nonzero_and_says_not_implemented,
    test_execute_command_missing_command_returns_nonzero_and_says_not_ready,
    test_execute_missing_prompt_returns_nonzero_and_says_not_ready,
    test_execute_planned_adapter_returns_nonzero_with_clear_message,
    test_execute_output_includes_expected_rows,
    test_execute_command_does_not_execute_configured_command,
    test_execute_command_does_not_create_aidc,
    test_execute_command_does_not_apply_patches,
]
