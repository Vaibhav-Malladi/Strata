import tempfile
from pathlib import Path

from adapter_doctor import check_adapter
from workflow_config import default_config, save_config


def _write_prompt(root: Path, content: str = "prompt") -> Path:
    prompt_path = root / ".aidc" / "agent_prompt.md"
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(content, encoding="utf-8")
    return prompt_path


def _save_config(root: Path, **overrides) -> None:
    config = default_config()
    config.update(overrides)
    save_config(config, root)


def test_adapter_doctor_prompt_file_ready_when_config_and_prompt_exist():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _save_config(root, adapter="prompt_file", prompt_path=".aidc/agent_prompt.md")
        _write_prompt(root)

        result = check_adapter(root)

        assert result["status"] == "ready"
        assert result["ready"] is True
        assert result["adapter"] == "prompt_file"
        assert result["mode"] == "manual"
        assert result["agent"] == "manual"
        assert result["prompt"] == ".aidc/agent_prompt.md"
        assert result["patch"].replace("\\", "/").endswith(".aidc/agent_patch.diff")
        assert result["command"] == "-"
        assert result["message"] == "Adapter configuration looks ready."
        assert result["errors"] == []
        assert result["warnings"] == []
        assert [check["status"] for check in result["checks"]] == ["pass", "pass", "pass", "info"]


def test_adapter_doctor_prompt_file_not_ready_when_prompt_missing():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _save_config(root, adapter="prompt_file", prompt_path=".aidc/agent_prompt.md")

        result = check_adapter(root)

        assert result["status"] == "not_ready"
        assert result["ready"] is False
        assert result["adapter"] == "prompt_file"
        assert result["errors"] == ["Prompt file not found: .aidc/agent_prompt.md"]
        assert result["message"] == "Adapter configuration is not ready."


def test_adapter_doctor_command_ready_when_command_and_prompt_exist():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _save_config(
            root,
            mode="hybrid",
            agent="codex",
            adapter="command",
            command="my-ai --prompt .aidc/agent_prompt.md",
            prompt_path=".aidc/agent_prompt.md",
        )
        _write_prompt(root)

        result = check_adapter(root)

        assert result["status"] == "ready"
        assert result["ready"] is True
        assert result["adapter"] == "command"
        assert result["command"] == "my-ai --prompt .aidc/agent_prompt.md"
        assert result["errors"] == []
        assert result["message"] == "Adapter configuration looks ready."
        assert [check["status"] for check in result["checks"]] == ["pass", "pass", "pass", "pass", "info"]


def test_adapter_doctor_command_not_ready_when_command_missing():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _save_config(root, adapter="command", command=None, prompt_path=".aidc/agent_prompt.md")
        _write_prompt(root)

        result = check_adapter(root)

        assert result["status"] == "not_ready"
        assert result["ready"] is False
        assert result["errors"] == ["Command adapter requires a configured command."]
        assert result["message"] == "Adapter configuration is not ready."


def test_adapter_doctor_command_not_ready_when_prompt_missing():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _save_config(
            root,
            adapter="command",
            command="my-ai --prompt .aidc/agent_prompt.md",
            prompt_path=".aidc/agent_prompt.md",
        )

        result = check_adapter(root)

        assert result["status"] == "not_ready"
        assert result["ready"] is False
        assert result["errors"] == ["Prompt file not found: .aidc/agent_prompt.md"]


def test_adapter_doctor_planned_adapter_returns_not_ready_with_clear_message():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _save_config(root, adapter="ollama")

        result = check_adapter(root)

        assert result["status"] == "not_ready"
        assert result["ready"] is False
        assert result["adapter"] == "ollama"
        assert result["message"] == "Adapter health check is not implemented yet."
        assert result["errors"] == ["Adapter health check is not implemented yet."]
        assert [check["status"] for check in result["checks"]] == ["pass", "info", "info", "info"]


def test_adapter_doctor_invalid_config_returns_invalid():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        config_path = root / ".aidc" / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text("{\"mode\": \"manual\"", encoding="utf-8")

        result = check_adapter(root)

        assert result["status"] == "invalid"
        assert result["ready"] is False
        assert result["message"] == "Workflow config is invalid."
        assert result["errors"]
        assert "Invalid workflow config" in result["errors"][0]


def test_adapter_doctor_does_not_create_aidc_when_config_and_prompt_missing():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        result = check_adapter(root)

        assert result["status"] == "not_ready"
        assert not (root / ".aidc").exists()


def test_adapter_doctor_returns_fresh_deterministic_dicts_and_lists():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _save_config(root, adapter="prompt_file", prompt_path=".aidc/agent_prompt.md")
        _write_prompt(root)

        first = check_adapter(root)
        second = check_adapter(root)

        assert first == second
        assert first is not second
        assert first["checks"] is not second["checks"]
        assert first["errors"] is not second["errors"]
        assert first["warnings"] is not second["warnings"]

        first["checks"].append({"name": "extra", "status": "info", "message": "x"})
        first["errors"].append("extra")
        first["warnings"].append("extra")

        assert len(second["checks"]) == 4
        assert second["errors"] == []
        assert second["warnings"] == []


TESTS = [
    test_adapter_doctor_prompt_file_ready_when_config_and_prompt_exist,
    test_adapter_doctor_prompt_file_not_ready_when_prompt_missing,
    test_adapter_doctor_command_ready_when_command_and_prompt_exist,
    test_adapter_doctor_command_not_ready_when_command_missing,
    test_adapter_doctor_command_not_ready_when_prompt_missing,
    test_adapter_doctor_planned_adapter_returns_not_ready_with_clear_message,
    test_adapter_doctor_invalid_config_returns_invalid,
    test_adapter_doctor_does_not_create_aidc_when_config_and_prompt_missing,
    test_adapter_doctor_returns_fresh_deterministic_dicts_and_lists,
]
