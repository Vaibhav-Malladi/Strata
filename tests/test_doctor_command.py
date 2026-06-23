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


def test_doctor_adapter_ready_returns_zero():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _save_config(root, adapter="prompt_file", prompt_path=".aidc/agent_prompt.md")
        _write_prompt(root)

        with change_directory(root):
            with change_argv(["cli.py", "doctor", "adapter"]):
                exit_code, output = capture_output(cli_main)

        assert exit_code == 0
        assert "Adapter doctor" in output
        assert "Status" in output
        assert "Adapter" in output
        assert "Prompt" in output
        assert "Patch" in output
        assert "Message" in output
        assert "ready" in output


def test_doctor_adapter_optional_root_argument_works():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _save_config(root, adapter="prompt_file", prompt_path=".aidc/agent_prompt.md")
        _write_prompt(root)

        with change_argv(["cli.py", "doctor", "adapter", str(root)]):
            exit_code, output = capture_output(cli_main)

        assert exit_code == 0
        assert "Adapter doctor" in output
        assert "ready" in output


def test_doctor_adapter_not_ready_returns_nonzero():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _save_config(
            root,
            adapter="command",
            command="my-ai --prompt .aidc/agent_prompt.md",
            prompt_path=".aidc/agent_prompt.md",
        )

        with change_directory(root):
            with change_argv(["cli.py", "doctor", "adapter"]):
                exit_code, output = capture_output(cli_main)

        assert exit_code == 1
        assert "not_ready" in output
        assert "Prompt file not found" in output


def test_doctor_without_target_returns_nonzero_and_shows_usage():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)

        with change_directory(root):
            with change_argv(["cli.py", "doctor"]):
                exit_code, output = capture_output(cli_main)

        assert exit_code == 1
        assert "Supported usage is `strata doctor adapter`" in output


def test_doctor_unknown_target_returns_nonzero_and_shows_usage():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)

        with change_directory(root):
            with change_argv(["cli.py", "doctor", "banana"]):
                exit_code, output = capture_output(cli_main)

        assert exit_code == 1
        assert "Usage:" in output
        assert "strata doctor adapter" in output


def test_doctor_output_includes_status_adapter_prompt_patch_message():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _save_config(root, adapter="prompt_file", prompt_path=".aidc/agent_prompt.md")
        _write_prompt(root)

        with change_directory(root):
            with change_argv(["cli.py", "doctor", "adapter"]):
                exit_code, output = capture_output(cli_main)

        assert exit_code == 0
        assert "Status" in output
        assert "Adapter" in output
        assert "Prompt" in output
        assert "Patch" in output
        assert "Message" in output


def test_doctor_command_does_not_execute_configured_command():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _save_config(
            root,
            adapter="command",
            command="my-ai --prompt .aidc/agent_prompt.md",
            prompt_path=".aidc/agent_prompt.md",
        )

        original_run = subprocess.run

        def _fail(*_args, **_kwargs):
            raise AssertionError("subprocess.run should not be called")

        subprocess.run = _fail
        try:
            with change_directory(root):
                with change_argv(["cli.py", "doctor", "adapter"]):
                    exit_code, output = capture_output(cli_main)
        finally:
            subprocess.run = original_run

        assert exit_code == 1
        assert "not_ready" in output


def test_doctor_command_does_not_create_aidc():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)

        with change_directory(root):
            with change_argv(["cli.py", "doctor", "adapter"]):
                exit_code, output = capture_output(cli_main)

        assert exit_code == 1
        assert not (root / ".aidc").exists()
        assert "Adapter doctor" in output


TESTS = [
    test_doctor_adapter_ready_returns_zero,
    test_doctor_adapter_optional_root_argument_works,
    test_doctor_adapter_not_ready_returns_nonzero,
    test_doctor_without_target_returns_nonzero_and_shows_usage,
    test_doctor_unknown_target_returns_nonzero_and_shows_usage,
    test_doctor_output_includes_status_adapter_prompt_patch_message,
    test_doctor_command_does_not_execute_configured_command,
    test_doctor_command_does_not_create_aidc,
]
