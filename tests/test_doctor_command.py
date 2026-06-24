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
        assert "Adapter family" in output
        assert "Prompt" in output
        assert "Patch" in output
        assert "Command timeout" in output
        assert "Base URL" in output
        assert "API key env" in output
        assert "HTTP timeout seconds" in output
        assert "Message" in output
        assert "ready" in output
        assert "prompt_file" in output


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
        assert "Adapter family" in output


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
        assert "Adapter family" in output
        assert "command" in output
        assert "Command timeout" in output


def test_doctor_http_adapter_shows_ollama_defaults_and_ready():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _write_prompt(root)
        _save_config(root, adapter="ollama", http_timeout_seconds=180)

        with change_directory(root):
            with change_argv(["cli.py", "doctor", "adapter"]):
                exit_code, output = capture_output(cli_main)

        assert exit_code == 0
        assert "ready" in output
        assert "Adapter family" in output
        assert "http" in output
        assert "Base URL" in output
        assert "http://localhost:11434" in output
        assert "Model" in output
        assert "qwen2.5-coder" in output
        assert "HTTP timeout seconds" in output
        assert "180" in output
        assert "Ollama adapter appears ready. Runtime availability is checked during execute." in output


def test_doctor_http_adapter_shows_base_url_api_key_env_and_http_timeout():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _write_prompt(root)
        _save_config(
            root,
            adapter="openai_compatible_http",
            base_url="http://localhost:1234/v1",
            api_key_env="OPENAI_API_KEY",
            http_timeout_seconds=240,
        )

        with change_directory(root):
            with change_argv(["cli.py", "doctor", "adapter"]):
                exit_code, output = capture_output(cli_main)

        assert exit_code == 0
        assert "ready" in output
        assert "Adapter family" in output
        assert "http" in output
        assert "Base URL" in output
        assert "http://localhost:1234/v1" in output
        assert "API key env" in output
        assert "OPENAI_API_KEY" in output
        assert "HTTP timeout seconds" in output
        assert "240" in output
        assert "HTTP adapter appears ready for execution." in output


def test_doctor_without_target_returns_nonzero_and_shows_usage():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)

        with change_directory(root):
            with change_argv(["cli.py", "doctor"]):
                exit_code, output = capture_output(cli_main)

        assert exit_code == 1
        assert "Supported usage is `strata doctor adapter` or `strata doctor install`." in output


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
        assert "strata doctor install" in output


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
        assert "Command timeout" in output
        assert "Base URL" in output
        assert "API key env" in output
        assert "HTTP timeout seconds" in output
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


def test_doctor_install_reports_python_and_path_diagnostics():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)

        with change_directory(root):
            with change_argv(["cli.py", "doctor", "install"]):
                exit_code, output = capture_output(cli_main)

        assert exit_code == 0
        assert "Install diagnostics" in output
        assert "Current working directory" in output
        assert "Python executable" in output
        assert "Python version" in output
        assert "strata on PATH" in output
        assert "Resolved strata path" in output
        assert "Expected Scripts dir" in output
        assert "python -m strata" in output
        assert "cli module" in output
        assert "commands.run_command" in output
        assert "Windows tips" in output
        assert "py -m pip install -e ." in output
        assert "py -m strata" in output
        assert "Restart the VS Code terminal" in output
        assert "close and reopen VS Code" in output
        assert "project environment or reinstall Strata" in output


def test_install_ps1_contains_bootstrap_prompts():
    script_path = Path(__file__).resolve().parents[1] / "install.ps1"
    text = script_path.read_text(encoding="utf-8")

    assert "Strata Installer" in text
    assert text.index("function Get-RequiredPythonVersion") < text.index(
        "$script:RequiredPythonVersion = Get-RequiredPythonVersion"
    )
    assert text.index("function Test-PyLauncher") < text.index("if (-not (Test-PyLauncher))")
    assert "if ($null -eq $response)" in text
    assert "Install Python using winget now? [y/N]" in text
    assert "Add the Python Scripts folder to your user PATH? [y/N]" in text
    assert "py -m pip install -e" in text
    assert "Get-Command strata" in text
    assert "py -m strata doctor install" in text
    assert "Try: strata start" in text


def test_install_strata_ps1_contains_bootstrap_flow():
    script_path = Path(__file__).resolve().parents[1] / "install-strata.ps1"
    text = script_path.read_text(encoding="utf-8")

    assert "Strata Bootstrap Installer" in text
    assert "Install Git using winget now? [y/N]" in text
    assert "Update existing Strata checkout? [Y/n]" in text
    assert "if ($null -eq $response)" in text
    assert "git clone --branch" in text
    assert "git -C" in text
    assert "powershell -NoProfile -ExecutionPolicy Bypass -File" in text
    assert "strata doctor install" in text
    assert "py -m strata help" in text
    assert "Try:" in text
    assert "strata start" in text
    assert text.index("function Test-CommandAvailable") < text.index(
        "Write-Host \"========================================\""
    )


def test_readme_install_section_mentions_bootstrap_and_fallback():
    readme_path = Path(__file__).resolve().parents[1] / "README.md"
    text = readme_path.read_text(encoding="utf-8")

    assert "install-strata.ps1" in text
    assert "install.ps1" in text
    assert "py -m pip install -e" in text
    assert "py -m strata help" in text
    assert "strata doctor install" in text
    assert "No need to `cd` into `strata`" in text
    assert "restart VS Code" in text or "restart VS Code or the affected terminal" in text


TESTS = [
    test_doctor_adapter_ready_returns_zero,
    test_doctor_adapter_optional_root_argument_works,
    test_doctor_adapter_not_ready_returns_nonzero,
    test_doctor_without_target_returns_nonzero_and_shows_usage,
    test_doctor_unknown_target_returns_nonzero_and_shows_usage,
    test_doctor_output_includes_status_adapter_prompt_patch_message,
    test_doctor_command_does_not_execute_configured_command,
    test_doctor_http_adapter_shows_ollama_defaults_and_ready,
    test_doctor_http_adapter_shows_base_url_api_key_env_and_http_timeout,
    test_doctor_command_does_not_create_aidc,
    test_doctor_install_reports_python_and_path_diagnostics,
    test_install_ps1_contains_bootstrap_prompts,
    test_install_strata_ps1_contains_bootstrap_flow,
    test_readme_install_section_mentions_bootstrap_and_fallback,
]
