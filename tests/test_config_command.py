import contextlib
import json
import sys
import tempfile
from pathlib import Path

from cli import main as cli_main
from commands.config_command import (
    write_config_command,
    write_config_init_command,
    write_config_set_command,
)
from tests.helpers import capture_output, change_directory
from workflow_config import config_path, default_config, save_config


@contextlib.contextmanager
def change_argv(args: list[str]):
    original = sys.argv[:]
    sys.argv = args
    try:
        yield
    finally:
        sys.argv = original


def run_config_via_cli(*args: str):
    with change_argv(["cli.py", "config", *args]):
        return capture_output(cli_main)


def test_config_shows_defaults_without_creating_file():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        with change_directory(root):
            exit_code, output = capture_output(write_config_command, ".")

        path = config_path(root)

        assert exit_code == 0
        assert path.exists() is False
        assert "Strata" in output
        assert "Workflow config" in output
        assert "Path" in output
        assert "Exists" in output
        assert "no" in output.lower()
        assert "Mode" in output
        assert "manual" in output
        assert "Agent" in output
        assert "true" in output.lower()


def test_config_init_creates_default_config():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        with change_directory(root):
            exit_code, output = capture_output(write_config_init_command, ".")

        path = config_path(root)
        payload = json.loads(path.read_text(encoding="utf-8"))

        assert exit_code == 0
        assert "Workflow config initialized" in output
        assert path.exists()
        assert payload == default_config()


def test_config_init_does_not_overwrite_existing_valid_config():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        save_config({"mode": "hybrid", "agent": "codex"}, root)
        original = config_path(root).read_text(encoding="utf-8")

        with change_directory(root):
            exit_code, output = capture_output(write_config_init_command, ".")

        path = config_path(root)

        assert exit_code == 0
        assert "Workflow config initialized" in output
        assert path.read_text(encoding="utf-8") == original

        loaded = json.loads(path.read_text(encoding="utf-8"))

        assert loaded["mode"] == "hybrid"
        assert loaded["agent"] == "codex"


def test_config_shows_existing_config():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        save_config({"mode": "hybrid", "agent": "codex"}, root)

        with change_directory(root):
            exit_code, output = capture_output(write_config_command, ".")

        assert exit_code == 0
        assert "Workflow config" in output
        assert "Exists" in output
        assert "yes" in output.lower()
        assert "hybrid" in output
        assert "codex" in output


def test_config_set_mode_creates_config():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        with change_directory(root):
            exit_code, output = capture_output(write_config_set_command, "mode", "hybrid", ".")

        payload = json.loads(config_path(root).read_text(encoding="utf-8"))

        assert exit_code == 0
        assert "Workflow config updated" in output
        assert "Updated" in output
        assert payload["mode"] == "hybrid"


def test_config_set_agent_updates_existing_config():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        save_config({"mode": "manual", "agent": "manual"}, root)

        with change_directory(root):
            exit_code, _ = capture_output(write_config_set_command, "agent", "codex", ".")

        payload = json.loads(config_path(root).read_text(encoding="utf-8"))

        assert exit_code == 0
        assert payload["agent"] == "codex"


def test_config_set_adapter_prompt_file():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        with change_directory(root):
            exit_code, _ = capture_output(write_config_set_command, "adapter", "prompt_file", ".")

        payload = json.loads(config_path(root).read_text(encoding="utf-8"))

        assert exit_code == 0
        assert payload["adapter"] == "prompt_file"


def test_config_set_adapter_alias_manual_normalizes():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        with change_directory(root):
            exit_code, _ = capture_output(write_config_set_command, "adapter", "manual", ".")

        payload = json.loads(config_path(root).read_text(encoding="utf-8"))

        assert exit_code == 0
        assert payload["adapter"] == "prompt_file"


def test_config_set_adapter_alias_http_normalizes():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        with change_directory(root):
            exit_code, _ = capture_output(write_config_set_command, "adapter", "http", ".")

        payload = json.loads(config_path(root).read_text(encoding="utf-8"))

        assert exit_code == 0
        assert payload["adapter"] == "openai_compatible_http"


def test_config_set_adapter_rejects_unknown():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        with change_directory(root):
            exit_code, output = capture_output(write_config_set_command, "adapter", "banana", ".")

        assert exit_code == 1
        assert "Unknown adapter" in output
        assert not config_path(root).exists()


def test_config_set_prompt_path():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        with change_directory(root):
            exit_code, _ = capture_output(
                write_config_set_command,
                "prompt_path",
                "custom/prompt.md",
                ".",
            )

        payload = json.loads(config_path(root).read_text(encoding="utf-8"))

        assert exit_code == 0
        assert payload["prompt_path"] == "custom/prompt.md"


def test_config_set_prompt_path_rejects_empty():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        with change_directory(root):
            exit_code, output = capture_output(write_config_set_command, "prompt_path", "", ".")

        assert exit_code == 1
        assert "prompt_path" in output
        assert not config_path(root).exists()


def test_config_set_model_value():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        with change_directory(root):
            exit_code, _ = capture_output(
                write_config_set_command,
                "model",
                "qwen2.5-coder:12b",
                ".",
            )

        payload = json.loads(config_path(root).read_text(encoding="utf-8"))

        assert exit_code == 0
        assert payload["model"] == "qwen2.5-coder:12b"


def test_config_set_model_null_clears():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        save_config({"mode": "manual", "agent": "manual", "model": "old-model"}, root)

        with change_directory(root):
            exit_code, _ = capture_output(write_config_set_command, "model", "null", ".")

        payload = json.loads(config_path(root).read_text(encoding="utf-8"))

        assert exit_code == 0
        assert payload["model"] is None


def test_config_set_command_value():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        with change_directory(root):
            exit_code, _ = capture_output(
                write_config_set_command,
                "command",
                "my-ai --prompt .aidc/agent_prompt.md",
                ".",
            )

        payload = json.loads(config_path(root).read_text(encoding="utf-8"))

        assert exit_code == 0
        assert payload["command"] == "my-ai --prompt .aidc/agent_prompt.md"


def test_config_set_command_null_clears():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        save_config({"mode": "manual", "agent": "manual", "command": "old-command"}, root)

        with change_directory(root):
            exit_code, _ = capture_output(write_config_set_command, "command", "none", ".")

        payload = json.loads(config_path(root).read_text(encoding="utf-8"))

        assert exit_code == 0
        assert payload["command"] is None


def test_config_set_boolean_false():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        with change_directory(root):
            exit_code, _ = capture_output(write_config_set_command, "auto_snapshot", "false", ".")

        payload = json.loads(config_path(root).read_text(encoding="utf-8"))

        assert exit_code == 0
        assert payload["auto_snapshot"] is False


def test_config_set_boolean_true_variants():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        with change_directory(root):
            exit_code_true, _ = capture_output(write_config_set_command, "auto_snapshot", "true", ".")
            exit_code_on, _ = capture_output(write_config_set_command, "auto_verify", "on", ".")
            exit_code_one, _ = capture_output(
                write_config_set_command,
                "require_gate",
                "1",
                ".",
            )

        payload = json.loads(config_path(root).read_text(encoding="utf-8"))

        assert exit_code_true == 0
        assert exit_code_on == 0
        assert exit_code_one == 0
        assert payload["auto_snapshot"] is True
        assert payload["auto_verify"] is True
        assert payload["require_gate_pass_before_commit"] is True


def test_config_set_boolean_alias_yes_no():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        with change_directory(root):
            exit_code, _ = capture_output(write_config_set_command, "verify", "no", ".")

        payload = json.loads(config_path(root).read_text(encoding="utf-8"))

        assert exit_code == 0
        assert payload["auto_verify"] is False


def test_config_set_key_alias():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        with change_directory(root):
            exit_code, _ = capture_output(write_config_set_command, "snapshot", "off", ".")

        payload = json.loads(config_path(root).read_text(encoding="utf-8"))

        assert exit_code == 0
        assert payload["auto_snapshot"] is False


def test_config_set_root_argument():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        with change_directory(root):
            exit_code, _ = run_config_via_cli("set", "mode", "hybrid", str(root))

        assert exit_code == 0
        assert config_path(root).exists()


def test_config_set_invalid_key_returns_nonzero():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        with change_directory(root):
            exit_code, output = capture_output(write_config_set_command, "banana", "x", ".")

        assert exit_code == 1
        assert "Valid keys" in output or "Usage" in output
        assert "adapter" in output
        assert "prompt_path" in output
        assert "model" in output
        assert "command" in output
        assert not config_path(root).exists()


def test_config_set_invalid_mode_returns_nonzero():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        with change_directory(root):
            exit_code, output = capture_output(write_config_set_command, "mode", "banana", ".")

        assert exit_code == 1
        assert "mode" in output.lower()
        assert not config_path(root).exists()


def test_config_set_invalid_boolean_returns_nonzero():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        with change_directory(root):
            exit_code, output = capture_output(write_config_set_command, "auto_snapshot", "maybe", ".")

        assert exit_code == 1
        assert "boolean" in output.lower()
        assert not config_path(root).exists()


def test_config_set_preserves_other_values():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        save_config({"mode": "manual", "agent": "codex"}, root)

        with change_directory(root):
            exit_code, _ = capture_output(write_config_set_command, "mode", "hybrid", ".")

        payload = json.loads(config_path(root).read_text(encoding="utf-8"))

        assert exit_code == 0
        assert payload["mode"] == "hybrid"
        assert payload["agent"] == "codex"


def test_invalid_existing_config_is_not_overwritten():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        path = config_path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        original = '{"mode": "banana"}'
        path.write_text(original, encoding="utf-8")

        with change_directory(root):
            exit_code, output = capture_output(write_config_set_command, "mode", "hybrid", ".")

        assert exit_code == 1
        assert "Workflow config error" in output
        assert path.read_text(encoding="utf-8") == original


def test_invalid_config_returns_nonzero():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        path = config_path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"mode": "banana"}', encoding="utf-8")

        with change_directory(root):
            exit_code, output = capture_output(write_config_command, ".")

        assert exit_code == 1
        assert "Workflow config error" in output
        assert "mode" in output.lower()


def test_invalid_args_return_nonzero():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        with change_directory(root):
            exit_code, output = run_config_via_cli("one", "two")

        assert exit_code == 1
        assert "Usage:" in output


def test_config_set_via_cli():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        with change_directory(root):
            exit_code, output = run_config_via_cli("set", "mode", "hybrid")

        assert exit_code == 0
        assert "Workflow config updated" in output
        assert json.loads(config_path(root).read_text(encoding="utf-8"))["mode"] == "hybrid"


def test_cli_dispatch_supports_config():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        with change_directory(root):
            exit_code, output = run_config_via_cli()

        assert exit_code == 0
        assert "Workflow config" in output


def test_help_mentions_config():
    from cli_help import print_usage

    _, output = capture_output(print_usage)

    assert "strata config [root]" in output
    assert "strata config init [root]" in output
    assert "strata config set <key> <value> [root]" in output
    assert "config" in output


TESTS = [
    test_config_shows_defaults_without_creating_file,
    test_config_init_creates_default_config,
    test_config_init_does_not_overwrite_existing_valid_config,
    test_config_shows_existing_config,
    test_config_set_mode_creates_config,
    test_config_set_agent_updates_existing_config,
    test_config_set_adapter_prompt_file,
    test_config_set_adapter_alias_manual_normalizes,
    test_config_set_adapter_alias_http_normalizes,
    test_config_set_adapter_rejects_unknown,
    test_config_set_prompt_path,
    test_config_set_prompt_path_rejects_empty,
    test_config_set_model_value,
    test_config_set_model_null_clears,
    test_config_set_command_value,
    test_config_set_command_null_clears,
    test_config_set_boolean_false,
    test_config_set_boolean_true_variants,
    test_config_set_boolean_alias_yes_no,
    test_config_set_key_alias,
    test_config_set_root_argument,
    test_config_set_invalid_key_returns_nonzero,
    test_config_set_invalid_mode_returns_nonzero,
    test_config_set_invalid_boolean_returns_nonzero,
    test_config_set_preserves_other_values,
    test_invalid_existing_config_is_not_overwritten,
    test_invalid_config_returns_nonzero,
    test_invalid_args_return_nonzero,
    test_config_set_via_cli,
    test_cli_dispatch_supports_config,
    test_help_mentions_config,
]
