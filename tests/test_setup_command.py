from __future__ import annotations

import builtins
import contextlib
import tempfile
from pathlib import Path
from unittest import mock
import sys

from cli import main as cli_main
from cli_help import print_usage
from commands.setup_command import (
    setup_command,
    setup_http,
    setup_manual,
    setup_ollama,
    setup_show,
    write_setup_command,
)
from tests.helpers import capture_output, change_directory
from workflow_config import default_config, load_config, save_config


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
        assert "Setup summary" in output
        assert "prompt_file" in output


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
        assert result["warnings"] == ['No command configured yet. Run `strata config set command "..."`.']
        assert config["adapter"] == "command"
        assert config["command"] is None
        assert "No command configured yet" in output


def test_setup_http_writes_adapter_and_saves_connection_values():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        result, _ = capture_output(
            setup_http,
            str(root),
            "http://localhost:1234/v1",
            "gpt-test",
            "OPENAI_API_KEY",
        )
        config = load_config(root)

        assert result["status"] == "configured"
        assert config["adapter"] == "openai_compatible_http"
        assert config["base_url"] == "http://localhost:1234/v1"
        assert config["model"] == "gpt-test"
        assert config["api_key_env"] == "OPENAI_API_KEY"


def test_setup_http_without_base_url_returns_warning():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        result, output = capture_output(setup_http, str(root), None, None, None)
        config = load_config(root)

        assert result["status"] == "needs_input"
        assert result["warnings"] == ["Base URL is not configured yet. Run `strata config set base_url <url>`."]
        assert config["adapter"] == "openai_compatible_http"
        assert config["base_url"] is None
        assert "Base URL is not configured yet" in output


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
        assert "Current setup" in output
        assert "Setup summary" in output
        assert "py fake_ai.py" in output


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
        assert "Setup cancelled" in output


def test_invalid_interactive_choice_retries_then_configures_manual_setup():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        with patched_input(["bad", "1"]):
            with change_directory(root):
                result, output = capture_output(write_setup_command, str(root))

        config = load_config(root)

        assert result == 0
        assert "Invalid choice" in output
        assert config["adapter"] == "prompt_file"


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


def test_setup_command_output_includes_summary():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        _, output = capture_output(setup_manual, str(root))

        assert "Setup summary" in output
        assert "Next steps" in output
        assert "strata doctor adapter" in output


def test_cli_routes_setup_manual():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        with change_directory(root):
            with change_argv(["cli.py", "setup", "--manual"]):
                exit_code, output = capture_output(cli_main)

        config = load_config(root)

        assert exit_code == 0
        assert config["adapter"] == "prompt_file"
        assert "Setup summary" in output


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
        assert "Setup summary" in output


def test_cli_help_includes_setup():
    _, output = capture_output(print_usage)

    assert "strata setup" in output
    assert "strata setup --manual" in output
    assert "strata setup --command" in output
    assert "strata setup --http" in output
    assert "strata setup --ollama" in output
    assert "strata setup --show" in output


TESTS = [
    test_setup_manual_writes_prompt_file_adapter_and_clears_connection_fields,
    test_setup_command_writes_adapter_and_saves_command_string,
    test_setup_command_without_command_returns_warning_and_keeps_configurable_state,
    test_setup_http_writes_adapter_and_saves_connection_values,
    test_setup_http_without_base_url_returns_warning,
    test_setup_ollama_writes_adapter_and_defaults_model,
    test_setup_ollama_allows_custom_model_and_no_api_key_env,
    test_setup_show_returns_current_config_summary,
    test_cancelled_interactive_setup_does_not_modify_config,
    test_invalid_interactive_choice_retries_then_configures_manual_setup,
    test_setup_returns_fresh_lists_each_call,
    test_setup_functions_do_not_make_network_calls,
    test_setup_no_secret_value_is_required,
    test_setup_command_output_includes_summary,
    test_cli_routes_setup_manual,
    test_cli_routes_setup_ollama,
    test_cli_help_includes_setup,
]
