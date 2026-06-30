import adapter_presets as old_adapter_presets
import strata.adapters.presets as new_adapter_presets
from adapter_presets import (
    build_aider_command,
    build_codex_cli_command,
    get_adapter_preset,
    supported_presets,
)


def test_adapter_presets_shim_exports_new_implementation_objects():
    assert old_adapter_presets.get_adapter_preset is new_adapter_presets.get_adapter_preset


def test_supported_presets_include_aider_and_codex_cli():
    presets = supported_presets()

    assert "aider" in presets
    assert "codex_cli" in presets


def test_aider_preset_returns_command_family_command_and_warning():
    preset = get_adapter_preset("aider")

    assert preset["adapter"] == "aider"
    assert preset["adapter_family"] == "command"
    assert preset["command"] == build_aider_command()
    assert ".aidc/agent_prompt.md" in str(preset["command"])
    assert ".aidc/agent_patch.diff" in str(preset["warning"])
    assert "verify" in str(preset["warning"]).lower()


def test_codex_cli_preset_accepts_aliases_and_mentions_patch_output():
    preset = get_adapter_preset("codex-cli")

    assert preset["adapter"] == "codex_cli"
    assert preset["adapter_family"] == "command"
    assert preset["command"] == build_codex_cli_command()
    assert ".aidc/agent_prompt.md" in str(preset["command"])
    assert ".aidc/agent_patch.diff" in str(preset["warning"])
    assert "verify" in str(preset["warning"]).lower()


TESTS = [
    test_adapter_presets_shim_exports_new_implementation_objects,
    test_supported_presets_include_aider_and_codex_cli,
    test_aider_preset_returns_command_family_command_and_warning,
    test_codex_cli_preset_accepts_aliases_and_mentions_patch_output,
]
