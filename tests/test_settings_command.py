import contextlib
import io
import json
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from unittest import mock

import strata.commands.cli as cli
import strata.commands.cli_help as cli_help
import strata.commands.config_command as config_command
import strata.commands.settings_command as settings_command
import strata.core.user_settings as user_settings
import strata.utils.config as workflow_config
from tests.helpers import change_directory


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@contextlib.contextmanager
def change_argv(args: list[str]):
    original = sys.argv[:]
    sys.argv = args
    try:
        yield
    finally:
        sys.argv = original


def capture_output(function, *args, **kwargs):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        result = function(*args, **kwargs)
    return result, output.getvalue()


def _payload(root: Path) -> dict:
    return json.loads(workflow_config.config_path(root).read_text(encoding="utf-8"))


def _save_config(root: Path, *, settings: dict | None = None, **overrides) -> None:
    config = workflow_config.default_config()
    config.update(overrides)
    if settings is not None:
        config["user_settings"] = settings
    workflow_config.save_config(config, root)


def _settings(**changes) -> dict[str, object]:
    return user_settings.update_user_settings(user_settings.default_user_settings(), changes)


def test_settings_command_is_registered_once():
    source = (PROJECT_ROOT / "strata" / "commands" / "cli.py").read_text(encoding="utf-8")

    assert source.count('if command == "settings":') == 1


def test_existing_advanced_config_command_remains_registered():
    assert config_command.write_config_command is not None
    source = (PROJECT_ROOT / "strata" / "commands" / "cli.py").read_text(encoding="utf-8")

    assert 'if command == "config":' in source


def test_settings_summary_uses_plain_language_labels():
    output = settings_command.render_settings_summary(user_settings.default_user_settings(), workflow_mode="hybrid")

    assert "Capability selection:" in output
    assert "Delivery surface:" in output
    assert "Workflow mode:" in output
    assert "capability_selection" not in output
    assert "delivery_surface" not in output


def test_capability_default_displays_automatic():
    output = settings_command.render_settings_summary(user_settings.default_user_settings())

    assert "Capability selection: Automatic" in output


def test_delivery_surface_default_displays_browser_copy():
    output = settings_command.render_settings_summary(user_settings.default_user_settings())

    assert "Delivery surface: Browser copy" in output


def test_workflow_mode_default_displays_manual_when_configured():
    output = settings_command.render_settings_summary(user_settings.default_user_settings(), workflow_mode="manual")

    assert "Workflow mode: Manual" in output


def test_raw_internal_dictionaries_are_not_printed():
    settings = _settings(profile_overrides={"max_recommended_files": 4})
    output = settings_command.render_settings_summary(settings)

    assert "profile_overrides" not in output
    assert "max_recommended_files" not in output
    assert "{" not in output


def test_secret_like_fields_are_not_printed():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _save_config(root, api_key_env="OPENAI_API_KEY")

        exit_code, output = capture_output(settings_command.write_settings_command, str(root))

        assert exit_code == 0
        assert "OPENAI_API_KEY" not in output
        assert "api_key" not in output.lower()


def test_capability_can_change_to_weak():
    _assert_setting_change("capability", "weak", "capability_selection", "weak")


def test_capability_can_change_to_medium():
    _assert_setting_change("capability", "medium", "capability_selection", "medium")


def test_capability_can_change_to_strong():
    _assert_setting_change("capability", "strong", "capability_selection", "strong")


def test_capability_can_change_to_unknown():
    _assert_setting_change("capability", "unknown", "capability_selection", "unknown")


def test_capability_can_change_back_to_auto():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        settings_command.update_setting(str(root), "capability", "strong")

        result = settings_command.update_setting(str(root), "capability", "auto")

        assert result["saved"] is True
        assert _payload(root)["user_settings"]["capability_selection"] == "auto"


def test_delivery_surface_can_change_to_browser_copy():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        settings_command.update_setting(str(root), "surface", "cli")

        result = settings_command.update_setting(str(root), "surface", "browser_copy")

        assert result["saved"] is True
        assert _payload(root)["user_settings"]["delivery_surface"] == "browser_copy"


def test_delivery_surface_can_change_to_cli():
    _assert_setting_change("surface", "cli", "delivery_surface", "cli")


def test_delivery_surface_can_change_to_vscode():
    _assert_setting_change("surface", "vscode", "delivery_surface", "vscode")


def test_workflow_mode_can_change_to_hybrid():
    _assert_setting_change("mode", "hybrid", "mode", "hybrid")


def test_workflow_mode_can_change_to_auto():
    _assert_setting_change("mode", "auto", "mode", "auto")


def test_workflow_mode_can_change_to_manual():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        settings_command.update_setting(str(root), "mode", "auto")

        result = settings_command.update_setting(str(root), "mode", "manual")

        assert result["saved"] is True
        assert _payload(root)["mode"] == "manual"


def test_invalid_setting_name_is_rejected():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        exit_code, output = capture_output(settings_command.write_settings_set_command, "model", "premium", str(root))

        assert exit_code == 1
        assert "Unknown setting: model" in output
        assert "Supported settings: capability, surface, mode" in output


def test_invalid_capability_value_is_rejected():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        exit_code, output = capture_output(settings_command.write_settings_set_command, "capability", "premium", str(root))

        assert exit_code == 1
        assert "Invalid capability value: premium" in output
        assert "auto, unknown, weak, medium, strong" in output


def test_invalid_surface_value_is_rejected():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        exit_code, output = capture_output(settings_command.write_settings_set_command, "surface", "terminal", str(root))

        assert exit_code == 1
        assert "Invalid delivery surface: terminal" in output
        assert "browser_copy, cli, vscode" in output


def test_invalid_mode_value_is_rejected():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        exit_code, output = capture_output(settings_command.write_settings_set_command, "mode", "balanced", str(root))

        assert exit_code == 1
        assert "Invalid workflow mode: balanced" in output
        assert "manual, hybrid, auto" in output


def test_invalid_input_performs_no_write():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        exit_code, _ = capture_output(settings_command.write_settings_set_command, "surface", "terminal", str(root))

        assert exit_code == 1
        assert workflow_config.config_path(root).exists() is False


def test_existing_unrelated_config_values_are_preserved():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _save_config(root, mode="hybrid", agent="codex", command="py fake_ai.py")

        settings_command.update_setting(str(root), "capability", "weak")
        payload = _payload(root)

        assert payload["mode"] == "hybrid"
        assert payload["agent"] == "codex"
        assert payload["command"] == "py fake_ai.py"


def test_existing_profile_overrides_are_preserved():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _save_config(root, settings=_settings(profile_overrides={"max_recommended_files": 4}))

        settings_command.update_setting(str(root), "capability", "strong")

        assert _payload(root)["user_settings"]["profile_overrides"] == {"max_recommended_files": 4}


def test_empty_profile_overrides_remain_valid():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _save_config(root, settings=_settings(profile_overrides={}))

        exit_code, output = capture_output(settings_command.write_settings_command, str(root))

        assert exit_code == 0
        assert "Strata settings" in output


def test_missing_config_uses_defaults():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        settings = settings_command.load_settings(str(root))

        assert settings == user_settings.default_user_settings()


def test_viewing_defaults_does_not_create_a_file():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        exit_code, _ = capture_output(settings_command.write_settings_command, str(root))

        assert exit_code == 0
        assert workflow_config.config_path(root).exists() is False


def test_successful_update_writes_through_existing_config_helper():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        real_save = workflow_config.save_config

        with mock.patch.object(settings_command.workflow_config, "save_config", side_effect=real_save) as patched:
            result = settings_command.update_setting(str(root), "capability", "weak")

        assert result["saved"] is True
        assert patched.call_count == 1


def test_successful_output_shows_old_and_new_values():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        exit_code, output = capture_output(settings_command.write_settings_set_command, "capability", "strong", str(root))

        assert exit_code == 0
        assert "Automatic -> Strong" in output


def test_noop_update_returns_normal_completion():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        settings_command.update_setting(str(root), "capability", "auto")

        exit_code, _ = capture_output(settings_command.write_settings_set_command, "capability", "auto", str(root))

        assert exit_code == 0


def test_noop_update_reports_already_configured():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        settings_command.update_setting(str(root), "capability", "auto")

        _, output = capture_output(settings_command.write_settings_set_command, "capability", "auto", str(root))

        assert "Capability selection is already set to Automatic." in output


def test_inputs_are_not_mutated():
    settings = _settings(profile_overrides={"max_recommended_files": 4})
    before = deepcopy(settings)

    settings_command.render_settings_summary(settings)

    assert settings == before


def test_rendering_is_deterministic():
    settings = _settings(delivery_surface="cli")

    assert settings_command.render_settings_summary(settings) == settings_command.render_settings_summary(settings)


def test_exactly_one_next_action_is_shown_after_update():
    output = settings_command.render_setting_change("capability", "auto", "strong")

    assert output.count("Next step") == 1
    assert output.count("Run `strata start`") == 1


def test_start_remains_the_primary_entry_point():
    _, output = capture_output(cli_help.print_usage)

    assert output.index("Start here:\n  strata start\n  Strata will show your current status and one recommended next step.") < output.index("Settings:\n  strata settings")


def test_no_api_key_or_secret_value_is_displayed():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _save_config(root, api_key_env="SECRET_TOKEN")

        _, output = capture_output(settings_command.write_settings_command, str(root))

        assert "SECRET_TOKEN" not in output
        assert "secret" not in output.lower()
        assert "token" not in output.lower()


def test_no_model_or_provider_detection_is_added():
    source = (PROJECT_ROOT / "strata" / "commands" / "settings_command.py").read_text(encoding="utf-8").lower()

    assert "model" not in source
    assert "provider" not in source
    assert "detect" not in source


def test_imports_use_scanner_compatible_direct_module_syntax():
    source = (PROJECT_ROOT / "strata" / "commands" / "settings_command.py").read_text(encoding="utf-8")

    assert "import strata.core.user_settings as user_settings" in source
    assert "import strata.utils.config as workflow_config" in source
    assert "from strata.core import" not in source
    assert "from strata.commands import" not in source


def test_package_layering_invariant_has_no_new_violation():
    source = (PROJECT_ROOT / "strata" / "core" / "user_settings.py").read_text(encoding="utf-8")

    assert "strata.commands" not in source


def test_cli_routes_settings_summary():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        with change_directory(root):
            with change_argv(["cli.py", "settings"]):
                exit_code, output = capture_output(cli.main)

        assert exit_code == 0
        assert "Strata settings" in output


def _assert_setting_change(setting: str, value: str, field: str, expected: str) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        result = settings_command.update_setting(str(root), setting, value)
        payload = _payload(root)

        assert result["saved"] is True
        if setting == "mode":
            assert payload[field] == expected
        else:
            assert payload["user_settings"][field] == expected


TESTS = [
    test_settings_command_is_registered_once,
    test_existing_advanced_config_command_remains_registered,
    test_settings_summary_uses_plain_language_labels,
    test_capability_default_displays_automatic,
    test_delivery_surface_default_displays_browser_copy,
    test_workflow_mode_default_displays_manual_when_configured,
    test_raw_internal_dictionaries_are_not_printed,
    test_secret_like_fields_are_not_printed,
    test_capability_can_change_to_weak,
    test_capability_can_change_to_medium,
    test_capability_can_change_to_strong,
    test_capability_can_change_to_unknown,
    test_capability_can_change_back_to_auto,
    test_delivery_surface_can_change_to_browser_copy,
    test_delivery_surface_can_change_to_cli,
    test_delivery_surface_can_change_to_vscode,
    test_workflow_mode_can_change_to_hybrid,
    test_workflow_mode_can_change_to_auto,
    test_workflow_mode_can_change_to_manual,
    test_invalid_setting_name_is_rejected,
    test_invalid_capability_value_is_rejected,
    test_invalid_surface_value_is_rejected,
    test_invalid_mode_value_is_rejected,
    test_invalid_input_performs_no_write,
    test_existing_unrelated_config_values_are_preserved,
    test_existing_profile_overrides_are_preserved,
    test_empty_profile_overrides_remain_valid,
    test_missing_config_uses_defaults,
    test_viewing_defaults_does_not_create_a_file,
    test_successful_update_writes_through_existing_config_helper,
    test_successful_output_shows_old_and_new_values,
    test_noop_update_returns_normal_completion,
    test_noop_update_reports_already_configured,
    test_inputs_are_not_mutated,
    test_rendering_is_deterministic,
    test_exactly_one_next_action_is_shown_after_update,
    test_start_remains_the_primary_entry_point,
    test_no_api_key_or_secret_value_is_displayed,
    test_no_model_or_provider_detection_is_added,
    test_imports_use_scanner_compatible_direct_module_syntax,
    test_package_layering_invariant_has_no_new_violation,
    test_cli_routes_settings_summary,
]
