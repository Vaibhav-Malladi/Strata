import os
import socket
import subprocess
import tempfile
from pathlib import Path

from adapter_doctor import check_adapter
from ollama_adapter import DEFAULT_OLLAMA_BASE_URL, DEFAULT_OLLAMA_MODEL
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
        assert result["adapter_family"] == "prompt_file"
        assert result["mode"] == "manual"
        assert result["agent"] == "manual"
        assert result["prompt"] == ".aidc/agent_prompt.md"
        assert result["patch"].replace("\\", "/").endswith(".aidc/agent_patch.diff")
        assert result["command"] == "-"
        assert result["command_timeout_seconds"] is None
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
        assert result["adapter_family"] == "prompt_file"
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
        assert result["adapter_family"] == "command"
        assert result["command"] == "my-ai --prompt .aidc/agent_prompt.md"
        assert result["command_timeout_seconds"] == 120
        assert result["errors"] == []
        assert result["message"] == "Adapter configuration looks ready."
        assert [check["status"] for check in result["checks"]] == ["pass", "pass", "pass", "pass", "pass", "info"]


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
        assert result["adapter_family"] == "command"
        assert result["command_timeout_seconds"] == 120


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
        assert result["adapter_family"] == "command"
        assert result["command_timeout_seconds"] == 120


def test_adapter_doctor_http_planned_adapters_return_not_ready_with_family():
    original_run = subprocess.run
    original_create_connection = socket.create_connection

    def _fail(*_args, **_kwargs):
        raise AssertionError("network or subprocess calls should not be made")

    subprocess.run = _fail
    socket.create_connection = _fail
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_prompt(root)
            _save_config(
                root,
                adapter="openai_compatible_http",
                base_url=None,
                api_key_env="OPENAI_API_KEY",
                http_timeout_seconds=150,
            )

            result = check_adapter(root)

            assert result["status"] == "not_ready"
            assert result["ready"] is False
            assert result["adapter"] == "openai_compatible_http"
            assert result["adapter_family"] == "http"
            assert result["base_url"] is None
            assert result["api_key_env"] == "OPENAI_API_KEY"
            assert result["http_timeout_seconds"] == 150
            assert result["message"] == "HTTP adapter is not ready for execution."
            assert result["errors"] == ["base_url is required for HTTP adapters."]
            assert [check["status"] for check in result["checks"]] == [
                "pass",
                "pass",
                "info",
                "fail",
                "pass",
                "info",
                "info",
            ]
    finally:
        subprocess.run = original_run
        socket.create_connection = original_create_connection


def test_adapter_doctor_ollama_ready_uses_default_base_url_without_network_calls():
    original_run = subprocess.run
    original_create_connection = socket.create_connection

    def _fail(*_args, **_kwargs):
        raise AssertionError("network or subprocess calls should not be made")

    subprocess.run = _fail
    socket.create_connection = _fail
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_prompt(root)
            _save_config(
                root,
                adapter="ollama",
                base_url=None,
                model=None,
                http_timeout_seconds=150,
            )

            result = check_adapter(root)

            assert result["status"] == "ready"
            assert result["ready"] is True
            assert result["adapter"] == "ollama"
            assert result["adapter_family"] == "http"
            assert result["base_url"] == DEFAULT_OLLAMA_BASE_URL
            assert result["model"] == DEFAULT_OLLAMA_MODEL
            assert result["api_key_env"] is None
            assert result["http_timeout_seconds"] == 150
            assert result["message"] == (
                "Ollama adapter appears ready. Runtime availability is checked during execute."
            )
            assert result["errors"] == []
            assert result["warnings"] == []
            assert [check["status"] for check in result["checks"]] == [
                "pass",
                "pass",
                "pass",
                "pass",
                "pass",
                "info",
            ]
    finally:
        subprocess.run = original_run
        socket.create_connection = original_create_connection


def test_adapter_doctor_openai_http_reports_configured_base_url_and_api_key_env():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_prompt(root)
        _save_config(
            root,
            adapter="openai_compatible_http",
            base_url="http://localhost:1234/v1",
            api_key_env="OPENAI_API_KEY",
            http_timeout_seconds=200,
        )

        result = check_adapter(root)

        assert result["status"] == "ready"
        assert result["ready"] is True
        assert result["adapter"] == "openai_compatible_http"
        assert result["adapter_family"] == "http"
        assert result["base_url"] == "http://localhost:1234/v1"
        assert result["api_key_env"] == "OPENAI_API_KEY"
        assert result["http_timeout_seconds"] == 200
        assert result["message"] == "HTTP adapter appears ready for execution."
        assert result["errors"] == []
        assert result["warnings"] == []
        assert [check["status"] for check in result["checks"]] == [
            "pass",
            "pass",
            "info",
            "pass",
            "pass",
            "info",
            "info",
        ]


def test_adapter_doctor_openai_http_does_not_read_api_key_value():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_prompt(root)
        secret = "sk-test-secret-doctor"
        original = os.environ.get("OPENAI_API_KEY")
        os.environ["OPENAI_API_KEY"] = secret
        _save_config(
            root,
            adapter="openai_compatible_http",
            base_url="http://localhost:1234/v1",
            api_key_env="OPENAI_API_KEY",
            http_timeout_seconds=200,
        )

        try:
            result = check_adapter(root)
        finally:
            if original is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = original

        assert result["status"] == "ready"
        assert result["ready"] is True
        assert secret not in str(result)
        assert result["api_key_env"] == "OPENAI_API_KEY"


def test_adapter_doctor_command_family_presets_are_ready_with_warning_when_configured():
    original_run = subprocess.run

    def _fail(*_args, **_kwargs):
        raise AssertionError("subprocess.run should not be called")

    subprocess.run = _fail
    try:
        for adapter in ("aider", "codex_cli"):
            with tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                _save_config(
                    root,
                    mode="hybrid",
                    agent="codex",
                    adapter=adapter,
                    command="tool --prompt .aidc/agent_prompt.md",
                    prompt_path=".aidc/agent_prompt.md",
                )
                _write_prompt(root)

                result = check_adapter(root)

                assert result["status"] == "ready"
                assert result["ready"] is True
                assert result["adapter"] == adapter
                assert result["adapter_family"] == "command"
                assert result["command"] == "tool --prompt .aidc/agent_prompt.md"
                assert result["errors"] == []
                assert result["warnings"]
                assert ".aidc/agent_patch.diff" in result["warnings"][0]
                assert "preset" in result["message"].lower()
                assert [check["status"] for check in result["checks"]] == [
                    "pass",
                    "pass",
                    "pass",
                    "pass",
                    "pass",
                    "info",
                ]
    finally:
        subprocess.run = original_run


def test_adapter_doctor_command_family_presets_report_missing_command():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_prompt(root)

        for adapter in ("aider", "codex_cli"):
            _save_config(root, mode="hybrid", agent="codex", adapter=adapter, command=None, prompt_path=".aidc/agent_prompt.md")

            result = check_adapter(root)

            assert result["status"] == "not_ready"
            assert result["ready"] is False
            assert result["adapter"] == adapter
            assert result["adapter_family"] == "command"
            assert result["command"] == "-"
            assert result["errors"]
            assert "configured command" in result["errors"][0].lower()
            assert result["warnings"]
            assert ".aidc/agent_patch.diff" in result["warnings"][0]
            assert [check["status"] for check in result["checks"]] == [
                "pass",
                "pass",
                "fail",
                "pass",
                "pass",
                "info",
            ]


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
    test_adapter_doctor_http_planned_adapters_return_not_ready_with_family,
    test_adapter_doctor_ollama_ready_uses_default_base_url_without_network_calls,
    test_adapter_doctor_openai_http_reports_configured_base_url_and_api_key_env,
    test_adapter_doctor_openai_http_does_not_read_api_key_value,
    test_adapter_doctor_command_family_presets_are_ready_with_warning_when_configured,
    test_adapter_doctor_command_family_presets_report_missing_command,
    test_adapter_doctor_invalid_config_returns_invalid,
    test_adapter_doctor_does_not_create_aidc_when_config_and_prompt_missing,
    test_adapter_doctor_returns_fresh_deterministic_dicts_and_lists,
]
