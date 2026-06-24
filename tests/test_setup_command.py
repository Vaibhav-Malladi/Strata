from __future__ import annotations

import builtins
import contextlib
import os
import tempfile
from pathlib import Path
from unittest import mock
import sys

from cli import main as cli_main
from cli_help import print_usage
from commands.setup_command import (
    setup_aider,
    setup_codex_cli,
    setup_command,
    setup_http,
    setup_manual,
    setup_ollama,
    setup_show,
    write_setup_ai_command,
    write_setup_command,
)
from tests.helpers import capture_output, change_directory
from workflow_config import config_path, default_config, load_config, save_config


@contextlib.contextmanager
def change_argv(args: list[str]):
    original = sys.argv[:]
    sys.argv = args
    try:
        yield
    finally:
        sys.argv = original


@contextlib.contextmanager
def patched_input(values: list[str]):
    iterator = iter(values)
    original = builtins.input
    builtins.input = lambda prompt="": next(iterator)
    try:
        yield
    finally:
        builtins.input = original


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


def _write_prompt(root: Path) -> None:
    prompt_path = root / ".aidc" / "agent_prompt.md"
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text("prompt", encoding="utf-8")


def _create_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "main.py").write_text("print('hello')\n", encoding="utf-8")


def _save_config(root: Path, **overrides) -> None:
    config = default_config()
    config.update(overrides)
    save_config(config, root)

def test_setup_manual_writes_prompt_file_adapter_and_clears_connection_fields():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        result, output = capture_output(setup_manual, str(root))
        config = load_config(root)

        assert result["status"] == "configured"
        assert result["adapter"] == "prompt_file"
        assert config["adapter"] == "prompt_file"
        assert config["command"] is None
        assert config["base_url"] is None
        assert config["api_key_env"] is None
        assert config["mode"] == "hybrid"
        assert config["agent"] == "codex"
        _assert_terms(output, "setup summary", "prompt_file", "manual", "browser", ".aidc/agent_prompt.md", ".aidc/agent_patch.diff")
        _assert_terms(output, ("chatgpt", "claude", "gemini", "copilot chat"))


def test_setup_command_writes_adapter_and_saves_command_string():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        result, _ = capture_output(setup_command, str(root), "py fake_ai.py")
        config = load_config(root)

        assert result["status"] == "configured"
        assert config["adapter"] == "command"
        assert config["command"] == "py fake_ai.py"


def test_setup_command_without_command_returns_warning_and_keeps_configurable_state():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        result, output = capture_output(setup_command, str(root), None)
        config = load_config(root)

        assert result["status"] == "needs_input"
        assert result["warnings"]
        assert "strata config set command" in result["warnings"][0]
        assert config["adapter"] == "command"
        assert config["command"] is None
        _assert_terms(output, "no command configured yet", "setup summary")


def test_setup_http_writes_adapter_and_saves_connection_values():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        original = os.environ.get("OPENAI_API_KEY")
        os.environ["OPENAI_API_KEY"] = "sk-testsecret-123456"
        try:
            result, output = capture_output(
                setup_http,
                str(root),
                "http://localhost:1234/v1",
                "gpt-test",
                "OPENAI_API_KEY",
            )
        finally:
            if original is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = original

        config = load_config(root)

        assert result["status"] == "configured"
        assert config["adapter"] == "openai_compatible_http"
        assert config["base_url"] == "http://localhost:1234/v1"
        assert config["model"] == "gpt-test"
        assert config["api_key_env"] == "OPENAI_API_KEY"
        _assert_terms(output, "api key", "found", "stores only the variable name")


def test_setup_http_without_base_url_returns_warning():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        result, output = capture_output(setup_http, str(root), None, None, None)
        config = load_config(root)

        assert result["status"] == "needs_input"
        assert result["warnings"]
        assert "strata config set base_url" in result["warnings"][0]
        assert config["adapter"] == "openai_compatible_http"
        assert config["base_url"] is None
        _assert_terms(output, "base url is not configured yet", "setup summary")


def test_setup_ollama_writes_adapter_and_defaults_model():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        result, _ = capture_output(setup_ollama, str(root), None, None)
        config = load_config(root)

        assert result["status"] == "configured"
        assert config["adapter"] == "ollama"
        assert config["model"] == "qwen2.5-coder"
        assert config["base_url"] is None
        assert config["api_key_env"] is None


def test_setup_ollama_allows_custom_model_and_no_api_key_env():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        result, _ = capture_output(setup_ollama, str(root), "qwen2.5-coder:7b", None)
        config = load_config(root)

        assert result["status"] == "configured"
        assert config["model"] == "qwen2.5-coder:7b"
        assert config["api_key_env"] is None


def test_setup_aider_writes_adapter_command_and_warning():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        result, output = capture_output(setup_aider, str(root))
        config = load_config(root)

        assert result["status"] == "configured"
        assert result["adapter"] == "aider"
        assert config["adapter"] == "aider"
        assert config["command"] == "aider --message-file .aidc/agent_prompt.md"
        assert config["command_timeout_seconds"] == 120
        assert result["warnings"]
        assert ".aidc/agent_patch.diff" in result["warnings"][0]
        _assert_terms(output, "aider", "setup summary", ".aidc/agent_patch.diff")


def test_setup_codex_cli_writes_adapter_command_and_warning():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        result, output = capture_output(setup_codex_cli, str(root))
        config = load_config(root)

        assert result["status"] == "configured"
        assert result["adapter"] == "codex_cli"
        assert config["adapter"] == "codex_cli"
        assert config["command"] == "codex --prompt-file .aidc/agent_prompt.md"
        assert config["command_timeout_seconds"] == 120
        assert result["warnings"]
        assert ".aidc/agent_patch.diff" in result["warnings"][0]
        _assert_terms(output, "codex cli", "setup summary", ".aidc/agent_patch.diff")


def test_setup_show_returns_current_config_summary():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        save_config(
            {
                "mode": "hybrid",
                "agent": "codex",
                "adapter": "command",
                "prompt_path": ".aidc/agent_prompt.md",
                "command": "py fake_ai.py",
                "base_url": None,
                "api_key_env": None,
                "model": None,
            },
            root,
        )

        result, output = capture_output(setup_show, str(root))

        assert result["status"] == "configured"
        assert result["adapter"] == "command"
        _assert_terms(output, "current setup", "setup summary", "py fake_ai.py")


def test_setup_show_without_config_points_to_setup_and_manual_browser_workflow():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        result, output = capture_output(setup_show, str(root))

        assert result["status"] == "not configured"
        assert result["adapter"] == "prompt_file"
        _assert_terms(
            output,
            "no workflow config saved yet",
            "setup summary",
            "strata setup",
            "strata setup --manual",
            "manual",
            "browser",
            ".aidc/agent_prompt.md",
            ".aidc/agent_patch.diff",
        )
        _assert_terms(output, ("chatgpt", "claude", "gemini", "copilot chat"))


def test_cancelled_interactive_setup_does_not_modify_config():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        save_config(default_config(), root)
        original = (root / ".aidc" / "config.json").read_text(encoding="utf-8")

        with patched_input(["q"]):
            with change_directory(root):
                result, output = capture_output(write_setup_command, str(root))

        assert result == 1
        assert (root / ".aidc" / "config.json").read_text(encoding="utf-8") == original
        _assert_terms(output, "setup cancelled")


def test_invalid_interactive_choice_retries_then_configures_manual_setup():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        with patched_input(["bad", "1"]):
            with change_directory(root):
                result, output = capture_output(write_setup_command, str(root))

        config = load_config(root)

        assert result == 0
        _assert_terms(output, "invalid choice")
        assert config["adapter"] == "prompt_file"


def test_interactive_setup_accepts_aider_alias():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        with patched_input(["aider"]):
            with change_directory(root):
                result, output = capture_output(write_setup_command, str(root))

        config = load_config(root)

        assert result == 0
        assert config["adapter"] == "aider"
        _assert_terms(output, "aider", "setup summary")


def test_interactive_setup_accepts_codex_alias():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        with patched_input(["codex"]):
            with change_directory(root):
                result, output = capture_output(write_setup_command, str(root))

        config = load_config(root)

        assert result == 0
        assert config["adapter"] == "codex_cli"
        _assert_terms(output, "codex cli", "setup summary")


def test_setup_returns_fresh_lists_each_call():
    with tempfile.TemporaryDirectory() as temp_dir_1, tempfile.TemporaryDirectory() as temp_dir_2:
        result_1, _ = capture_output(setup_manual, temp_dir_1)
        result_2, _ = capture_output(setup_manual, temp_dir_2)

        assert result_1 == result_2
        assert result_1 is not result_2
        assert result_1["changes"] is not result_2["changes"]
        assert result_1["warnings"] is not result_2["warnings"]
        assert result_1["errors"] is not result_2["errors"]
        assert result_1["next_steps"] is not result_2["next_steps"]


def test_setup_functions_do_not_make_network_calls():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        with mock.patch("urllib.request.urlopen", side_effect=AssertionError("network call")):
            capture_output(setup_http, str(root), None, None, None)
            capture_output(setup_ollama, str(root), None, None)


def test_setup_no_secret_value_is_required():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        result, _ = capture_output(setup_http, str(root), "http://localhost:1234/v1", None, None)
        config = load_config(root)

        assert result["status"] in {"configured", "needs_input"}
        assert config["api_key_env"] is None


def test_interactive_http_setup_explains_key_storage_and_reports_status():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        original = os.environ.get("OPENAI_API_KEY")
        os.environ["OPENAI_API_KEY"] = "sk-testsecret-123456"
        try:
            with patched_input(["3", "http://localhost:1234/v1", "gpt-test", "OPENAI_API_KEY"]):
                with change_directory(root):
                    result, output = capture_output(write_setup_command, str(root))
        finally:
            if original is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = original

        config = load_config(root)

        assert result == 0
        assert config["adapter"] == "openai_compatible_http"
        assert config["api_key_env"] == "OPENAI_API_KEY"
        _assert_terms(
            output,
            "strata will not store your key in the repo",
            "stores only the variable name",
            "api key",
            "found",
        )


def test_guided_http_setup_uses_existing_env_var_without_prompting_for_secret():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        original = os.environ.get("OPENAI_API_KEY")
        os.environ["OPENAI_API_KEY"] = "sk-testsecret-123456"
        try:
            with mock.patch("getpass.getpass", side_effect=AssertionError("secret prompt should not run")):
                with patched_input(["2", "http://localhost:1234/v1", "gpt-test", "OPENAI_API_KEY"]):
                    with change_directory(root):
                        result, output = capture_output(write_setup_ai_command, str(root))
        finally:
            if original is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = original

        config = load_config(root)

        assert result == 0
        assert config["adapter"] == "openai_compatible_http"
        assert config["api_key_env"] == "OPENAI_API_KEY"
        assert config["base_url"] == "http://localhost:1234/v1"
        assert config["model"] == "gpt-test"
        _assert_terms(output, "guided ai setup", "key found", "api key env", "doctor adapter")
        assert "sk-testsecret-123456" not in output


def test_guided_http_setup_can_save_missing_key_to_user_environment_without_echoing_it():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        secret = "sk-testsecret-123456"
        original = os.environ.get("OPENAI_API_KEY")
        os.environ.pop("OPENAI_API_KEY", None)
        try:
            with mock.patch("commands.setup_command._save_user_environment_secret", return_value=True):
                with mock.patch("getpass.getpass", return_value=secret):
                    with patched_input(["2", "http://localhost:1234/v1", "gpt-test", "OPENAI_API_KEY", "y"]):
                        with change_directory(root):
                            result, output = capture_output(write_setup_ai_command, str(root))
            assert os.environ.get("OPENAI_API_KEY") == secret
        finally:
            if original is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = original

        config = load_config(root)

        assert result == 0
        assert config["adapter"] == "openai_compatible_http"
        assert config["api_key_env"] == "OPENAI_API_KEY"
        assert secret not in output
        assert "api_key=<redacted>" not in output
        _assert_terms(output, "store this key in your repo", "user environment", "saved to your user environment")


def test_guided_http_setup_from_ollama_config_uses_openai_like_default_base_url():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _save_config(root, adapter="ollama", model="qwen2.5-coder")

        with mock.patch("getpass.getpass", side_effect=AssertionError("api key prompt should not run")):
            with patched_input(["2", "", "gpt-test", "STRATA_FAKE_API_KEY", "n"]):
                with change_directory(root):
                    result, output = capture_output(write_setup_ai_command, str(root))

        config = load_config(root)

        assert result == 0
        assert config["adapter"] == "openai_compatible_http"
        assert config["base_url"] == "https://api.openai.com/v1"
        assert "http://localhost:11434" not in output
        assert "api_key=<redacted>" not in output
        _assert_terms(output, "api key env is missing", "environment variable name")


def test_guided_ollama_setup_does_not_prompt_for_api_key():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        with mock.patch("getpass.getpass", side_effect=AssertionError("api key prompt should not run")):
            with patched_input(["1", "qwen2.5-coder", "http://localhost:11434"]):
                with change_directory(root):
                    result, output = capture_output(write_setup_ai_command, str(root))

        config = load_config(root)

        assert result == 0
        assert config["adapter"] == "ollama"
        assert config["model"] == "qwen2.5-coder"
        assert config["api_key_env"] is None
        _assert_terms(output, "guided ai setup", "ollama", "doctor adapter")


def test_guided_command_adapter_setup_does_not_store_api_key():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        with mock.patch("getpass.getpass", side_effect=AssertionError("api key prompt should not run")):
            with patched_input(["3", "py fake_ai.py"]):
                with change_directory(root):
                    result, output = capture_output(write_setup_ai_command, str(root))

        config = load_config(root)

        assert result == 0
        assert config["adapter"] == "command"
        assert config["command"] == "py fake_ai.py"
        assert config["api_key_env"] is None
        _assert_terms(output, "does not manage the external tool's authentication", "command", "doctor adapter")


def test_setup_ai_check_runs_doctor_adapter_after_setup():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _write_prompt(root)
        _save_config(
            root,
            adapter="openai_compatible_http",
            base_url="http://localhost:1234/v1",
            api_key_env="OPENAI_API_KEY",
        )

        with mock.patch("builtins.input", side_effect=AssertionError("setup check should not prompt")):
            with change_directory(root):
                result, output = capture_output(write_setup_ai_command, str(root), True)

        assert result == 0
        assert "choose a guided ai setup option" not in output.lower()
        _assert_terms(output, "setup check", "adapter doctor", "ready", "api key")


def test_setup_command_output_includes_summary():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        _, output = capture_output(setup_manual, str(root))

        _assert_terms(output, "setup summary", "manual", "browser", "next steps")
        _assert_terms(output, ("chatgpt", "claude", "gemini", "copilot chat"))


def test_cli_routes_setup_manual():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        with change_directory(root):
            with change_argv(["cli.py", "setup", "--manual"]):
                exit_code, output = capture_output(cli_main)

        config = load_config(root)

        assert exit_code == 0
        assert config["adapter"] == "prompt_file"
        _assert_terms(output, "setup summary", "manual", "browser")


def test_cli_routes_setup_ollama():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        with change_directory(root):
            with change_argv(["cli.py", "setup", "--ollama"]):
                exit_code, output = capture_output(cli_main)

        config = load_config(root)

        assert exit_code == 0
        assert config["adapter"] == "ollama"
        assert config["model"] == "qwen2.5-coder"
        _assert_terms(output, "setup summary", "ollama")


def test_cli_routes_setup_aider():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        with change_directory(root):
            with change_argv(["cli.py", "setup", "--aider"]):
                exit_code, output = capture_output(cli_main)

        config = load_config(root)

        assert exit_code == 0
        assert config["adapter"] == "aider"
        assert config["command"] == "aider --message-file .aidc/agent_prompt.md"
        _assert_terms(output, "aider", "setup summary")


def test_cli_routes_setup_codex_cli():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        with change_directory(root):
            with change_argv(["cli.py", "setup", "--codex-cli"]):
                exit_code, output = capture_output(cli_main)

        config = load_config(root)

        assert exit_code == 0
        assert config["adapter"] == "codex_cli"
        assert config["command"] == "codex --prompt-file .aidc/agent_prompt.md"
        _assert_terms(output, "codex cli", "setup summary")


def test_cli_routes_setup_ai_check():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_prompt(root)
        _save_config(
            root,
            adapter="openai_compatible_http",
            base_url="http://localhost:1234/v1",
            api_key_env="OPENAI_API_KEY",
        )

        with mock.patch("builtins.input", side_effect=AssertionError("setup check should not prompt")):
            with change_directory(root):
                with change_argv(["cli.py", "setup", "ai", "--check"]):
                    exit_code, output = capture_output(cli_main)

        config = load_config(root)

        assert exit_code == 0
        assert config["adapter"] == "openai_compatible_http"
        assert "choose a guided ai setup option" not in output.lower()
        _assert_terms(output, "setup check", "adapter doctor", "ready")


def test_cli_help_includes_setup():
    _, output = capture_output(print_usage)

    assert "strata setup" in output
    assert "strata setup ai" in output
    assert "strata setup ai --check" in output
    assert "strata setup --manual" in output
    assert "strata setup --command" in output
    assert "strata setup --aider" in output
    assert "strata setup --codex-cli" in output
    assert "strata setup --http" in output
    assert "strata setup --ollama" in output
    assert "strata setup --show" in output
    assert 'strata ask "fix bug"' in output
    assert 'strata review' in output
    assert 'strata apply --dry-run' in output
    assert "strata help setup" in output
    assert "strata help ask" in output
    assert "strata help manual" in output


TESTS = [
    test_setup_manual_writes_prompt_file_adapter_and_clears_connection_fields,
    test_setup_command_writes_adapter_and_saves_command_string,
    test_setup_command_without_command_returns_warning_and_keeps_configurable_state,
    test_setup_http_writes_adapter_and_saves_connection_values,
    test_setup_http_without_base_url_returns_warning,
    test_setup_ollama_writes_adapter_and_defaults_model,
    test_setup_ollama_allows_custom_model_and_no_api_key_env,
    test_setup_aider_writes_adapter_command_and_warning,
    test_setup_codex_cli_writes_adapter_command_and_warning,
    test_setup_show_returns_current_config_summary,
    test_cancelled_interactive_setup_does_not_modify_config,
    test_invalid_interactive_choice_retries_then_configures_manual_setup,
    test_interactive_setup_accepts_aider_alias,
    test_interactive_setup_accepts_codex_alias,
    test_setup_returns_fresh_lists_each_call,
    test_setup_functions_do_not_make_network_calls,
    test_setup_no_secret_value_is_required,
    test_interactive_http_setup_explains_key_storage_and_reports_status,
    test_guided_http_setup_uses_existing_env_var_without_prompting_for_secret,
    test_guided_http_setup_can_save_missing_key_to_user_environment_without_echoing_it,
    test_guided_ollama_setup_does_not_prompt_for_api_key,
    test_guided_command_adapter_setup_does_not_store_api_key,
    test_setup_ai_check_runs_doctor_adapter_after_setup,
    test_setup_command_output_includes_summary,
    test_cli_routes_setup_manual,
    test_cli_routes_setup_ollama,
    test_cli_routes_setup_aider,
    test_cli_routes_setup_codex_cli,
    test_cli_routes_setup_ai_check,
    test_cli_help_includes_setup,
]
