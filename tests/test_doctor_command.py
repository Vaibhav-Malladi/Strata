import contextlib
import os
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


def _assert_terms(text: str, *terms: object) -> None:
    normalized = text.lower()
    missing: list[str] = []

    for term in terms:
        if isinstance(term, (list, tuple, set, frozenset)):
            options = [str(option) for option in term]
            if not any(option.lower() in normalized for option in options):
                missing.append("one of: " + " | ".join(options))
            continue

        value = str(term)
        if value.lower() not in normalized:
            missing.append(value)

    assert not missing, f"Missing expected concept(s): {', '.join(missing)}"


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
        _assert_terms(
            output,
            "ready",
            "adapter family",
            "http",
            "base url",
            "http://localhost:11434",
            "model",
            "qwen2.5-coder",
            "http timeout seconds",
            "180",
            "ollama",
        )


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

        original = os.environ.get("OPENAI_API_KEY")
        os.environ["OPENAI_API_KEY"] = "sk-testsecret-123456"
        try:
            with change_directory(root):
                with change_argv(["cli.py", "doctor", "adapter"]):
                    exit_code, output = capture_output(cli_main)
        finally:
            if original is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = original

        assert exit_code == 0
        _assert_terms(
            output,
            "ready",
            "adapter family",
            "http",
            "base url",
            "http://localhost:1234/v1",
            "api key env",
            "openai_api_key",
            "api key",
            "found",
            "http timeout seconds",
            "240",
        )


def test_doctor_without_target_returns_nonzero_and_shows_usage():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)

        with change_directory(root):
            with change_argv(["cli.py", "doctor"]):
                exit_code, output = capture_output(cli_main)

        assert exit_code == 1
        _assert_terms(output, "supported usage", "strata doctor adapter", "strata doctor install")


def test_doctor_unknown_target_returns_nonzero_and_shows_usage():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)

        with change_directory(root):
            with change_argv(["cli.py", "doctor", "banana"]):
                exit_code, output = capture_output(cli_main)

        assert exit_code == 1
        _assert_terms(output, "usage:", "strata doctor adapter", "strata doctor install")


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


def test_doctor_http_adapter_reports_missing_api_key_status_when_not_configured():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _write_prompt(root)
        _save_config(
            root,
            adapter="openai_compatible_http",
            base_url="http://localhost:1234/v1",
            api_key_env=None,
            http_timeout_seconds=240,
        )

        with change_directory(root):
            with change_argv(["cli.py", "doctor", "adapter"]):
                exit_code, output = capture_output(cli_main)

        assert exit_code == 0
        _assert_terms(output, "api key", "missing", "api key env")


def test_doctor_install_reports_python_and_path_diagnostics():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)

        with change_directory(root):
            with change_argv(["cli.py", "doctor", "install"]):
                exit_code, output = capture_output(cli_main)

        assert exit_code == 0
        _assert_terms(
            output,
            "install diagnostics",
            "current working directory",
            "python executable",
            "python version",
            "strata on path",
            "resolved strata path",
            "expected scripts dir",
            "python -m strata",
            "cli module",
            "commands.run_command",
            "windows tips",
            "pip",
            "-e",
            "py -m strata",
            "vs code",
            "reinstall strata",
        )


def test_install_ps1_contains_bootstrap_prompts():
    script_path = Path(__file__).resolve().parents[1] / "install.ps1"
    text = script_path.read_text(encoding="utf-8")

    assert "Strata Installer" in text
    assert "-VerboseInstall" in text
    assert text.index("function Get-RequiredPythonVersion") < text.index(
        "$script:RequiredPythonVersion = Get-RequiredPythonVersion"
    )
    assert text.index("function Test-PyLauncher") < text.index("if (-not (Test-PyLauncher))")
    assert "if ($null -eq $response)" in text
    assert ".aidc\\install.log" in text
    _assert_terms(
        text,
        "winget",
        "python",
        "path",
        "scripts",
        "read-host",
        "[y/n]",
        "user",
        "add-userpathentry",
        "pip",
        "-e",
        "editable",
        "reporoot",
        "get-command strata",
        "strata installed",
        "py -m strata available",
        "install diagnostics passed",
        "strata start",
        "next:",
    )


def test_install_strata_ps1_contains_bootstrap_flow():
    script_path = Path(__file__).resolve().parents[1] / "install-strata.ps1"
    text = script_path.read_text(encoding="utf-8")

    _assert_terms(
        text,
        "Strata Bootstrap Installer",
        "-VerboseInstall",
        ".aidc\\install.log",
        "git",
        "winget",
        "checkout",
        "local changes",
        "not a git repository",
        "installdir",
        "read-host",
        "[y/n]",
        "if ($null -eq $response)",
        "clone",
        "--branch",
        "pull --ff-only",
        "git -c",
        "powershell",
        "install.ps1",
        "strata doctor install",
        "py -m strata help",
        "strata checkout ready",
        "install.log",
        "running repo-local installer",
        "confirm-yesdefaultyes",
    )
    assert text.index("function Test-CommandAvailable") < text.index(
        "Write-Host \"========================================\""
    )


def test_readme_install_section_mentions_package_install_paths_and_bootstrap():
    readme_path = Path(__file__).resolve().parents[1] / "README.md"
    text = readme_path.read_text(encoding="utf-8")

    _assert_terms(
        text,
        "strata-repo-intel",
        "pipx install strata-repo-intel",
        "python -m pip install --user strata-repo-intel",
        "python -m pip install -e .",
        "py -m pip install -e .",
        "strata help",
        "strata start",
        'strata context --budget small "your task"',
        "python 3.13",
        "older python versions",
        "user scripts directory",
        "path",
        "reopen",
        "install-strata.ps1",
        "install.ps1",
        "https://raw.githubusercontent.com/vaibhav-malladi/strata/main/install-strata.ps1",
        "strata doctor install",
        ".aidc/",
    )
    assert "python -m strata" not in text.lower()
    assert "<raw-install-strata-url>" not in text
    assert "<repo-url>" not in text
    assert "YOUR_REAL_USERNAME" not in text
    assert "YOUR_REAL_REPO" not in text
    assert "<owner>" not in text
    assert "<repo-name>" not in text


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
    test_doctor_http_adapter_reports_missing_api_key_status_when_not_configured,
    test_doctor_install_reports_python_and_path_diagnostics,
    test_install_ps1_contains_bootstrap_prompts,
    test_install_strata_ps1_contains_bootstrap_flow,
    test_readme_install_section_mentions_package_install_paths_and_bootstrap,
]
