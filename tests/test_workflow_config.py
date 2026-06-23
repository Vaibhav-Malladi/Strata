import json
import tempfile
from pathlib import Path

from workflow_config import (
    config_path,
    default_config,
    ensure_config,
    load_config,
    save_config,
    validate_config,
)


def test_default_config_returns_fresh_copy():
    first = default_config()
    second = default_config()

    assert first == second
    assert first is not second

    first["mode"] = "hybrid"

    assert second["mode"] == "manual"


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
        assert payload["auto_snapshot"] is False
        assert payload["auto_verify"] is True
        assert payload["require_gate_pass_before_commit"] is False
        assert content.splitlines()[0] == "{"
        assert content.splitlines()[1].startswith('  "agent"')


def test_load_config_merges_missing_keys_with_defaults():
    with tempfile.TemporaryDirectory() as temp_dir:
        path = config_path(temp_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"mode": "hybrid"}\n', encoding="utf-8")

        loaded = load_config(temp_dir)

        assert loaded["mode"] == "hybrid"
        assert loaded["agent"] == "manual"
        assert loaded["auto_snapshot"] is True
        assert loaded["auto_verify"] is True
        assert loaded["require_gate_pass_before_commit"] is True


def test_validate_rejects_invalid_mode():
    try:
        validate_config({"mode": "banana"})
    except ValueError as error:
        assert "mode" in str(error)
    else:
        raise AssertionError("Expected ValueError for invalid mode")


def test_validate_rejects_invalid_agent():
    try:
        validate_config({"agent": "unknown"})
    except ValueError as error:
        assert "agent" in str(error)
    else:
        raise AssertionError("Expected ValueError for invalid agent")


def test_validate_rejects_non_boolean_safety_flags():
    try:
        validate_config({"auto_snapshot": "yes"})
    except ValueError as error:
        assert "auto_snapshot" in str(error)
    else:
        raise AssertionError("Expected ValueError for non-boolean safety flag")


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


def test_ensure_config_writes_default_when_missing():
    with tempfile.TemporaryDirectory() as temp_dir:
        path = ensure_config(temp_dir)

        assert path == config_path(temp_dir)
        assert path.exists()
        assert load_config(temp_dir) == default_config()


def test_ensure_config_does_not_overwrite_existing_valid_config():
    with tempfile.TemporaryDirectory() as temp_dir:
        path = save_config({"mode": "hybrid", "agent": "codex"}, temp_dir)
        original = path.read_text(encoding="utf-8")

        ensured = ensure_config(temp_dir)

        assert ensured == path
        assert path.read_text(encoding="utf-8") == original
        assert load_config(temp_dir)["mode"] == "hybrid"
        assert load_config(temp_dir)["agent"] == "codex"


def test_unknown_extra_keys_are_preserved():
    with tempfile.TemporaryDirectory() as temp_dir:
        save_config({"future_option": "x", "mode": "auto", "agent": "local"}, temp_dir)

        loaded = load_config(temp_dir)

        assert loaded["future_option"] == "x"
        assert loaded["mode"] == "auto"
        assert loaded["agent"] == "local"


TESTS = [
    test_default_config_returns_fresh_copy,
    test_config_path_points_to_aidc_config_json,
    test_load_config_returns_defaults_when_missing,
    test_save_config_creates_aidc_and_writes_pretty_json,
    test_load_config_merges_missing_keys_with_defaults,
    test_validate_rejects_invalid_mode,
    test_validate_rejects_invalid_agent,
    test_validate_rejects_non_boolean_safety_flags,
    test_load_config_rejects_malformed_json,
    test_ensure_config_writes_default_when_missing,
    test_ensure_config_does_not_overwrite_existing_valid_config,
    test_unknown_extra_keys_are_preserved,
]
