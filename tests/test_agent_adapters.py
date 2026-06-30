import tempfile
from pathlib import Path

import agent_adapters as old_agent_adapters
import strata.adapters.agent_adapters as new_agent_adapters
from agent_adapters import (
    adapter_supports_dry_run,
    adapter_family,
    IMPLEMENTED_ADAPTERS,
    SUPPORTED_ADAPTERS,
    supported_adapter_families,
    build_command_dry_run_result,
    build_prompt_file_result,
    implemented_adapters,
    is_adapter_implemented,
    is_adapter_family_supported,
    normalize_adapter_name,
    patch_path,
    prompt_path,
    run_adapter,
    supported_adapters,
    validate_adapter_name,
)


def test_agent_adapters_shim_exports_new_implementation_objects():
    assert old_agent_adapters.run_adapter is new_agent_adapters.run_adapter


def test_supported_adapters_returns_fresh_set():
    first = supported_adapters()
    second = supported_adapters()

    assert first == {
        "prompt_file",
        "command",
        "ollama",
        "openai_compatible_http",
        "aider",
        "codex_cli",
    }
    assert second == first
    assert first is not second

    first.add("banana")

    assert "banana" not in SUPPORTED_ADAPTERS
    assert "banana" not in supported_adapters()


def test_supported_adapter_families_returns_fresh_list():
    first = supported_adapter_families()
    second = supported_adapter_families()

    assert first == ["prompt_file", "command", "http"]
    assert second == first
    assert first is not second

    first.append("banana")

    assert supported_adapter_families() == ["prompt_file", "command", "http"]


def test_implemented_adapters_only_prompt_file():
    adapters = implemented_adapters()

    assert adapters == {"prompt_file"}
    assert "prompt_file" in IMPLEMENTED_ADAPTERS
    assert "command" not in adapters
    assert "ollama" not in adapters
    assert "openai_compatible_http" not in adapters
    assert "aider" not in adapters
    assert "codex_cli" not in adapters


def test_normalize_adapter_name_handles_aliases():
    assert normalize_adapter_name(None) == "prompt_file"
    assert normalize_adapter_name("") == "prompt_file"
    assert normalize_adapter_name(" manual ") == "prompt_file"
    assert normalize_adapter_name("prompt") == "prompt_file"
    assert normalize_adapter_name("http") == "openai_compatible_http"
    assert normalize_adapter_name("codex") == "codex_cli"


def test_adapter_family_maps_aliases_and_canonical_names():
    assert adapter_family("prompt_file") == "prompt_file"
    assert adapter_family("command") == "command"
    assert adapter_family("ollama") == "http"
    assert adapter_family("openai_compatible_http") == "http"
    assert adapter_family("aider") == "command"
    assert adapter_family("codex_cli") == "command"
    assert adapter_family(" prompt ") == "prompt_file"
    assert adapter_family("http") == "http"


def test_is_adapter_family_supported():
    assert is_adapter_family_supported("prompt_file") is True
    assert is_adapter_family_supported("command") is True
    assert is_adapter_family_supported("http") is True
    assert is_adapter_family_supported("HTTP") is True
    assert is_adapter_family_supported("banana") is False
    assert is_adapter_family_supported(None) is False


def test_validate_adapter_rejects_unknown():
    try:
        validate_adapter_name("unknown")
    except ValueError as error:
        assert "Unknown adapter" in str(error)
        assert "prompt_file" in str(error)
    else:
        raise AssertionError("Expected ValueError for unknown adapter")


def test_adapter_family_rejects_unknown():
    try:
        adapter_family("unknown")
    except ValueError as error:
        assert "Unknown adapter" in str(error)
    else:
        raise AssertionError("Expected ValueError for unknown adapter family lookup")


def test_is_adapter_implemented_requires_valid_adapter():
    assert is_adapter_implemented("prompt") is True
    assert is_adapter_implemented("ollama") is False

    try:
        is_adapter_implemented("unknown")
    except ValueError as error:
        assert "Unknown adapter" in str(error)
    else:
        raise AssertionError("Expected ValueError for unknown adapter")


def test_prompt_path_defaults_to_aidc_agent_prompt():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        assert prompt_path(root) == root / ".aidc" / "agent_prompt.md"


def test_patch_path_defaults_to_aidc_agent_patch():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        assert patch_path(root) == root / ".aidc" / "agent_patch.diff"


def test_prompt_path_accepts_relative_configured_path():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        assert prompt_path(root, "custom/prompt.md") == root / "custom" / "prompt.md"


def test_prompt_path_accepts_absolute_configured_path():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        absolute_path = root / "custom" / "prompt.md"

        assert prompt_path(root, absolute_path) == absolute_path


def test_prompt_file_result_ready_when_prompt_exists():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        prompt_file = root / ".aidc" / "agent_prompt.md"
        prompt_file.parent.mkdir(parents=True, exist_ok=True)
        prompt_file.write_text("prompt content\n", encoding="utf-8")

        result = build_prompt_file_result(root)

        assert result["adapter"] == "prompt_file"
        assert result["status"] == "ready"
        assert result["executed"] is False
        assert Path(result["prompt_path"]) == prompt_file
        assert result["patch_path"] is None
        assert "Paste it into your AI coding tool" in result["message"]
        assert "strata review" in result["message"]


def test_prompt_file_result_missing_when_prompt_missing():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        result = build_prompt_file_result(root)

        assert result["adapter"] == "prompt_file"
        assert result["status"] == "missing_prompt"
        assert result["executed"] is False
        assert Path(result["prompt_path"]) == root / ".aidc" / "agent_prompt.md"
        assert result["patch_path"] is None
        assert "Prompt file not found" in result["message"]
        assert "strata prepare" in result["message"]


def test_run_adapter_prompt_file_uses_config_prompt_path():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        prompt_file = root / "custom" / "prompt.md"
        prompt_file.parent.mkdir(parents=True, exist_ok=True)
        prompt_file.write_text("prompt content\n", encoding="utf-8")

        result = run_adapter("prompt_file", root, {"prompt_path": "custom/prompt.md"})

        assert result["status"] == "ready"
        assert result["executed"] is False
        assert Path(result["prompt_path"]) == prompt_file


def test_command_dry_run_requires_command():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        for command_value in (None, "", 123):
            try:
                build_command_dry_run_result(root, {"command": command_value})
            except ValueError as error:
                assert "non-empty string command" in str(error)
            else:
                raise AssertionError("Expected ValueError for missing command")

        try:
            build_command_dry_run_result(root, {})
        except ValueError as error:
            assert "non-empty string command" in str(error)
        else:
            raise AssertionError("Expected ValueError for missing command")


def test_command_dry_run_returns_plan_without_execution():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        result = build_command_dry_run_result(
            root,
            {"command": "my-ai --prompt .aidc/agent_prompt.md"},
        )

        assert result["adapter"] == "command"
        assert result["status"] == "dry_run"
        assert result["executed"] is False
        assert result["command"] == "my-ai --prompt .aidc/agent_prompt.md"
        assert Path(result["prompt_path"]) == root / ".aidc" / "agent_prompt.md"
        assert Path(result["patch_path"]) == root / ".aidc" / "agent_patch.diff"
        assert "No command was executed" in result["message"]


def test_command_dry_run_uses_configured_prompt_path():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        result = build_command_dry_run_result(
            root,
            {
                "command": "my-ai --prompt custom/prompt.md",
                "prompt_path": "custom/prompt.md",
            },
        )

        assert Path(result["prompt_path"]) == root / "custom" / "prompt.md"


def test_command_dry_run_never_creates_files():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        build_command_dry_run_result(
            root,
            {"command": "my-ai --prompt .aidc/agent_prompt.md"},
        )

        assert not (root / ".aidc").exists()


def test_run_adapter_command_dry_run():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        result = run_adapter(
            "command",
            root,
            {"command": "my-ai --prompt .aidc/agent_prompt.md"},
            dry_run=True,
        )

        assert result["adapter"] == "command"
        assert result["status"] == "dry_run"
        assert result["executed"] is False
        assert result["command"] == "my-ai --prompt .aidc/agent_prompt.md"


def test_run_adapter_command_normal_reports_ready():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        result = run_adapter(
            "command",
            root,
            {"command": "my-ai --prompt .aidc/agent_prompt.md"},
            dry_run=False,
        )

        assert result["adapter"] == "command"
        assert result["status"] == "ready"
        assert result["executed"] is False
        assert result["command"] == "my-ai --prompt .aidc/agent_prompt.md"
        assert Path(result["prompt_path"]) == root / ".aidc" / "agent_prompt.md"
        assert Path(result["patch_path"]) == root / ".aidc" / "agent_patch.diff"
        assert "Command adapter is configured" in result["message"]
        assert "strata doctor adapter" in result["message"]
        assert "strata execute" in result["message"]


def test_adapter_supports_dry_run_command():
    assert adapter_supports_dry_run("command") is True
    assert adapter_supports_dry_run("prompt_file") is True
    assert adapter_supports_dry_run("ollama") is False


def test_run_adapter_supported_unimplemented_returns_not_implemented():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        result = run_adapter("ollama", root, {})

        assert result["adapter"] == "ollama"
        assert result["status"] == "not_implemented"
        assert result["executed"] is False
        assert Path(result["prompt_path"]) == Path(".aidc") / "agent_prompt.md"
        assert result["patch_path"] is None
        assert "planned but not implemented yet" in result["message"]


def test_run_adapter_never_creates_files():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        result = run_adapter("prompt_file", root, {})

        assert result["status"] == "missing_prompt"
        assert not (root / ".aidc").exists()


def test_run_adapter_invalid_adapter_raises():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        try:
            run_adapter("banana", root, {})
        except ValueError as error:
            assert "Unknown adapter" in str(error)
        else:
            raise AssertionError("Expected ValueError for invalid adapter")


TESTS = [
    test_agent_adapters_shim_exports_new_implementation_objects,
    test_supported_adapters_returns_fresh_set,
    test_implemented_adapters_only_prompt_file,
    test_normalize_adapter_name_handles_aliases,
    test_validate_adapter_rejects_unknown,
    test_is_adapter_implemented_requires_valid_adapter,
    test_prompt_path_defaults_to_aidc_agent_prompt,
    test_patch_path_defaults_to_aidc_agent_patch,
    test_prompt_path_accepts_relative_configured_path,
    test_prompt_path_accepts_absolute_configured_path,
    test_prompt_file_result_ready_when_prompt_exists,
    test_prompt_file_result_missing_when_prompt_missing,
    test_run_adapter_prompt_file_uses_config_prompt_path,
    test_command_dry_run_requires_command,
    test_command_dry_run_returns_plan_without_execution,
    test_command_dry_run_uses_configured_prompt_path,
    test_command_dry_run_never_creates_files,
    test_run_adapter_command_dry_run,
    test_run_adapter_command_normal_reports_ready,
    test_adapter_supports_dry_run_command,
    test_run_adapter_supported_unimplemented_returns_not_implemented,
    test_run_adapter_never_creates_files,
    test_run_adapter_invalid_adapter_raises,
]
