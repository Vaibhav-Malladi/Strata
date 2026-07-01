import json
import tempfile
from pathlib import Path

from strata.utils.config import default_config as package_default_config
from workflow_config import (
    config_path,
    default_config,
    ensure_config,
    load_config,
    save_config,
    validate_config,
)


def test_new_package_import_path_works():
    assert package_default_config is default_config


def _expect_value_error(function, *args, contains: str | None = None):
    try:
        function(*args)
    except ValueError as error:
        if contains is not None:
            assert contains in str(error)
    else:
        raise AssertionError("Expected ValueError")


def test_default_config_includes_adapter_fields():
    config = default_config()

    assert config["mode"] == "manual"
    assert config["agent"] == "manual"
    assert config["adapter"] == "prompt_file"
    assert config["prompt_path"] == ".aidc/agent_prompt.md"
    assert config["model"] is None
    assert config["command"] is None
    assert config["base_url"] is None
    assert config["api_key_env"] is None
    assert config["command_timeout_seconds"] == 120
    assert config["http_timeout_seconds"] == 120
    assert config["auto_snapshot"] is True
    assert config["auto_verify"] is True
    assert config["require_gate_pass_before_commit"] is True


def test_default_config_returns_fresh_copy():
    first = default_config()
    second = default_config()

    assert first == second
    assert first is not second

    first["mode"] = "hybrid"
    first["adapter"] = "manual"
    first["prompt_path"] = "custom.md"

    assert second["mode"] == "manual"
    assert second["adapter"] == "prompt_file"
    assert second["prompt_path"] == ".aidc/agent_prompt.md"


def test_config_path_points_to_aidc_config_json():
    with tempfile.TemporaryDirectory() as temp_dir:
        path = config_path(temp_dir)

        assert path == Path(temp_dir) / ".aidc" / "config.json"


def test_load_config_returns_defaults_when_missing():
    with tempfile.TemporaryDirectory() as temp_dir:
        path = config_path(temp_dir)

        assert not path.exists()
        assert load_config(temp_dir) == default_config()
        assert not path.exists()


def test_save_config_creates_aidc_and_writes_pretty_json():
    with tempfile.TemporaryDirectory() as temp_dir:
        path = save_config(
            {
                "mode": "hybrid",
                "agent": "codex",
                "adapter": "manual",
                "prompt_path": "custom/prompt.md",
                "model": None,
                "command": None,
                "auto_snapshot": False,
                "auto_verify": True,
                "require_gate_pass_before_commit": False,
            },
            temp_dir,
        )

        assert path == Path(temp_dir) / ".aidc" / "config.json"
        assert path.exists()

        content = path.read_text(encoding="utf-8")
        payload = json.loads(content)

        assert content.endswith("\n")
        assert payload["mode"] == "hybrid"
        assert payload["agent"] == "codex"
        assert payload["adapter"] == "prompt_file"
        assert payload["prompt_path"] == "custom/prompt.md"
        assert payload["model"] is None
        assert payload["command"] is None
        assert payload["base_url"] is None
        assert payload["api_key_env"] is None
        assert payload["http_timeout_seconds"] == 120
        assert payload["auto_snapshot"] is False
        assert payload["auto_verify"] is True
        assert payload["require_gate_pass_before_commit"] is False
        assert content.splitlines()[0] == "{"
        assert content.splitlines()[1].startswith('  "adapter"')


def test_validate_config_backfills_missing_adapter_fields():
    normalized = validate_config({"mode": "hybrid", "agent": "codex"})

    assert normalized["mode"] == "hybrid"
    assert normalized["agent"] == "codex"
    assert normalized["adapter"] == "prompt_file"
    assert normalized["prompt_path"] == ".aidc/agent_prompt.md"
    assert normalized["model"] is None
    assert normalized["command"] is None
    assert normalized["base_url"] is None
    assert normalized["api_key_env"] is None
    assert normalized["command_timeout_seconds"] == 120
    assert normalized["http_timeout_seconds"] == 120
    assert normalized["auto_snapshot"] is True
    assert normalized["auto_verify"] is True
    assert normalized["require_gate_pass_before_commit"] is True


def test_validate_config_accepts_valid_command_timeout():
    normalized = validate_config({"command_timeout_seconds": 30})

    assert normalized["command_timeout_seconds"] == 30


def test_validate_config_accepts_timeout_alias():
    normalized = validate_config({"timeout": 45})

    assert normalized["command_timeout_seconds"] == 45


def test_validate_config_accepts_http_timeout_alias():
    normalized = validate_config({"http_timeout": 45})

    assert normalized["http_timeout_seconds"] == 45


def test_validate_config_rejects_invalid_command_timeout_values():
    for value in (0, -1, 1.5, "30"):
        _expect_value_error(
            validate_config,
            {"command_timeout_seconds": value},
            contains="command_timeout_seconds",
        )


def test_validate_config_rejects_overly_large_command_timeout():
    _expect_value_error(
        validate_config,
        {"command_timeout_seconds": 3601},
        contains="command_timeout_seconds",
    )


def test_validate_config_accepts_valid_base_url():
    normalized = validate_config({"base_url": "http://localhost:1234/v1"})

    assert normalized["base_url"] == "http://localhost:1234/v1"


def test_validate_config_accepts_valid_api_key_env():
    normalized = validate_config({"api_key_env": "OPENAI_API_KEY"})

    assert normalized["api_key_env"] == "OPENAI_API_KEY"


def test_validate_config_rejects_secret_like_api_key_env():
    _expect_value_error(
        validate_config,
        {"api_key_env": "sk-testsecret-123456"},
        contains="api_key_env",
    )


def test_validate_config_accepts_valid_http_timeout_seconds():
    normalized = validate_config({"http_timeout_seconds": 120})

    assert normalized["http_timeout_seconds"] == 120


def test_validate_config_accepts_null_base_url_and_api_key_env():
    normalized = validate_config({"base_url": None, "api_key_env": None})

    assert normalized["base_url"] is None
    assert normalized["api_key_env"] is None


def test_validate_config_rejects_empty_base_url():
    _expect_value_error(validate_config, {"base_url": ""}, contains="base_url")


def test_validate_config_rejects_empty_api_key_env():
    _expect_value_error(validate_config, {"api_key_env": ""}, contains="api_key_env")


def test_validate_config_rejects_invalid_http_timeout_values():
    for value in (0, -1, 1.5, "30"):
        _expect_value_error(
            validate_config,
            {"http_timeout_seconds": value},
            contains="http_timeout_seconds",
        )


def test_validate_config_rejects_overly_large_http_timeout():
    _expect_value_error(
        validate_config,
        {"http_timeout_seconds": 3601},
        contains="http_timeout_seconds",
    )


def test_validate_config_normalizes_adapter_alias():
    manual = validate_config({"adapter": "manual"})
    http = validate_config({"adapter": "http"})

    assert manual["adapter"] == "prompt_file"
    assert http["adapter"] == "openai_compatible_http"


def test_validate_config_rejects_unknown_adapter():
    _expect_value_error(validate_config, {"adapter": "banana"}, contains="Unknown adapter")


def test_validate_config_rejects_empty_prompt_path():
    _expect_value_error(validate_config, {"prompt_path": ""}, contains="prompt_path")


def test_validate_config_rejects_non_string_prompt_path():
    _expect_value_error(validate_config, {"prompt_path": 123}, contains="prompt_path")


def test_validate_config_allows_none_model_and_command():
    normalized = validate_config(
        {
            "mode": "manual",
            "agent": "manual",
            "model": None,
            "command": None,
        }
    )

    assert normalized["model"] is None
    assert normalized["command"] is None


def test_validate_config_rejects_empty_model():
    _expect_value_error(validate_config, {"model": ""}, contains="model")


def test_validate_config_rejects_empty_command():
    _expect_value_error(validate_config, {"command": ""}, contains="command")


def test_validate_rejects_invalid_mode():
    _expect_value_error(validate_config, {"mode": "banana"}, contains="mode")


def test_validate_rejects_invalid_agent():
    _expect_value_error(validate_config, {"agent": "unknown"}, contains="agent")


def test_validate_rejects_non_boolean_safety_flags():
    _expect_value_error(validate_config, {"auto_snapshot": "yes"}, contains="auto_snapshot")


def test_load_config_merges_old_config_file():
    with tempfile.TemporaryDirectory() as temp_dir:
        path = config_path(temp_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"mode": "hybrid", "agent": "codex"}\n', encoding="utf-8")

        loaded = load_config(temp_dir)

        assert loaded["mode"] == "hybrid"
        assert loaded["agent"] == "codex"
        assert loaded["adapter"] == "prompt_file"
        assert loaded["prompt_path"] == ".aidc/agent_prompt.md"
        assert loaded["model"] is None
        assert loaded["command"] is None
        assert loaded["base_url"] is None
        assert loaded["api_key_env"] is None
        assert loaded["command_timeout_seconds"] == 120
        assert loaded["http_timeout_seconds"] == 120
        assert loaded["auto_snapshot"] is True
        assert loaded["auto_verify"] is True
        assert loaded["require_gate_pass_before_commit"] is True


def test_load_config_rejects_malformed_json():
    with tempfile.TemporaryDirectory() as temp_dir:
        path = config_path(temp_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"mode": "manual"', encoding="utf-8")

        try:
            load_config(temp_dir)
        except ValueError as error:
            assert "Invalid workflow config" in str(error)
        else:
            raise AssertionError("Expected ValueError for malformed JSON")


def test_save_config_writes_adapter_fields():
    with tempfile.TemporaryDirectory() as temp_dir:
        path = save_config(
            {
                "mode": "manual",
                "agent": "manual",
                "adapter": "http",
                "prompt_path": "custom/prompt.md",
                "model": "gpt-4o",
                "command": "python run.py",
            },
            temp_dir,
        )

        payload = json.loads(path.read_text(encoding="utf-8"))

        assert payload["adapter"] == "openai_compatible_http"
        assert payload["prompt_path"] == "custom/prompt.md"
        assert payload["model"] == "gpt-4o"
        assert payload["command"] == "python run.py"


def test_ensure_config_creates_new_schema():
    with tempfile.TemporaryDirectory() as temp_dir:
        path = ensure_config(temp_dir)

        assert path == config_path(temp_dir)
        assert path.exists()
        assert load_config(temp_dir) == default_config()

        payload = json.loads(path.read_text(encoding="utf-8"))

        assert payload["adapter"] == "prompt_file"
        assert payload["prompt_path"] == ".aidc/agent_prompt.md"
        assert payload["model"] is None
        assert payload["command"] is None
        assert payload["base_url"] is None
        assert payload["api_key_env"] is None
        assert payload["http_timeout_seconds"] == 120


def test_ensure_config_preserves_existing_valid_config():
    with tempfile.TemporaryDirectory() as temp_dir:
        path = save_config(
            {
                "mode": "hybrid",
                "agent": "codex",
                "adapter": "manual",
                "prompt_path": "custom/prompt.md",
                "model": "gpt-4o",
                "command": "python run.py",
            },
            temp_dir,
        )
        original = path.read_text(encoding="utf-8")

        ensured = ensure_config(temp_dir)

        assert ensured == path
        assert path.read_text(encoding="utf-8") == original

        loaded = load_config(temp_dir)

        assert loaded["mode"] == "hybrid"
        assert loaded["agent"] == "codex"
        assert loaded["adapter"] == "prompt_file"
        assert loaded["prompt_path"] == "custom/prompt.md"
        assert loaded["model"] == "gpt-4o"
        assert loaded["command"] == "python run.py"
        assert loaded["base_url"] is None
        assert loaded["api_key_env"] is None
        assert loaded["http_timeout_seconds"] == 120


def test_unknown_extra_keys_are_rejected():
    with tempfile.TemporaryDirectory() as temp_dir:
        _expect_value_error(
            save_config,
            {
                "future_option": "x",
                "mode": "auto",
                "agent": "local",
                "adapter": "manual",
                "prompt_path": "custom/prompt.md",
            },
            temp_dir,
            contains="Unsupported config key: future_option",
        )


def test_load_config_rejects_unknown_file_keys_before_runtime_use():
    with tempfile.TemporaryDirectory() as temp_dir:
        path = config_path(temp_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            '{"mode": "auto", "future_option": "unsafe"}\n',
            encoding="utf-8",
        )

        _expect_value_error(
            load_config,
            temp_dir,
            contains="Unsupported config key: future_option",
        )


TESTS = [
    test_new_package_import_path_works,
    test_default_config_includes_adapter_fields,
    test_default_config_returns_fresh_copy,
    test_config_path_points_to_aidc_config_json,
    test_load_config_returns_defaults_when_missing,
    test_save_config_creates_aidc_and_writes_pretty_json,
    test_validate_config_backfills_missing_adapter_fields,
    test_validate_config_accepts_valid_command_timeout,
    test_validate_config_accepts_timeout_alias,
    test_validate_config_accepts_http_timeout_alias,
    test_validate_config_rejects_invalid_command_timeout_values,
    test_validate_config_rejects_overly_large_command_timeout,
    test_validate_config_accepts_valid_base_url,
    test_validate_config_accepts_valid_api_key_env,
    test_validate_config_rejects_secret_like_api_key_env,
    test_validate_config_accepts_valid_http_timeout_seconds,
    test_validate_config_accepts_null_base_url_and_api_key_env,
    test_validate_config_rejects_empty_base_url,
    test_validate_config_rejects_empty_api_key_env,
    test_validate_config_rejects_invalid_http_timeout_values,
    test_validate_config_rejects_overly_large_http_timeout,
    test_validate_config_normalizes_adapter_alias,
    test_validate_config_rejects_unknown_adapter,
    test_validate_config_rejects_empty_prompt_path,
    test_validate_config_rejects_non_string_prompt_path,
    test_validate_config_allows_none_model_and_command,
    test_validate_config_rejects_empty_model,
    test_validate_config_rejects_empty_command,
    test_validate_rejects_invalid_mode,
    test_validate_rejects_invalid_agent,
    test_validate_rejects_non_boolean_safety_flags,
    test_load_config_merges_old_config_file,
    test_load_config_rejects_malformed_json,
    test_save_config_writes_adapter_fields,
    test_ensure_config_creates_new_schema,
    test_ensure_config_preserves_existing_valid_config,
    test_unknown_extra_keys_are_rejected,
    test_load_config_rejects_unknown_file_keys_before_runtime_use,
]
