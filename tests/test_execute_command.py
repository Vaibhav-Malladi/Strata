import json
import os
import contextlib
import socket
import sys
import tempfile
import textwrap
from pathlib import Path

import commands.execute_command as execute_command_module
from cli import main as cli_main
from command_executor import execute_command_adapter
from tests.helpers import capture_output, change_directory
from test_http_executor import _valid_patch_text, run_http_server
from workflow_config import default_config, save_config


@contextlib.contextmanager
def change_argv(args: list[str]):
    original = sys.argv[:]
    sys.argv = args
    try:
        yield
    finally:
        sys.argv = original


def _create_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "main.py").write_text("print('hello')\n", encoding="utf-8")


def _write_prompt(root: Path) -> Path:
    prompt_path = root / ".aidc" / "agent_prompt.md"
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text("prompt", encoding="utf-8")
    return prompt_path


def _save_config(root: Path, **overrides) -> None:
    config = default_config()
    config.update(overrides)
    save_config(config, root)


def _run_execute_cli(root: Path, *args: str):
    with change_directory(root):
        with change_argv(["cli.py", "execute", *args]):
            return capture_output(cli_main)


def _write_script(root: Path, name: str, body: str) -> Path:
    script_path = root / name
    script_path.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
    return script_path


def _python_command(script_path: Path) -> str:
    return f'"{sys.executable}" "{script_path}"'


def _valid_patch_text() -> str:
    return (
        "diff --git a/main.py b/main.py\n"
        "--- /dev/null\n"
        "+++ b/main.py\n"
        "@@ -0,0 +1 @@\n"
        '+print("hello")\n'
    )


def test_execute_prompt_file_ready_returns_nonzero_and_says_manual():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _save_config(root, adapter="prompt_file", prompt_path=".aidc/agent_prompt.md")
        _write_prompt(root)

        exit_code, output = _run_execute_cli(root)

        assert exit_code == 1
        assert "Execute adapter" in output
        assert "manual" in output
        assert "prompt_file is manual" in output
        assert "Executes command" in output
        assert "Applies patch" in output


def test_execute_optional_root_argument_works():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _save_config(root, adapter="prompt_file", prompt_path=".aidc/agent_prompt.md")
        _write_prompt(root)

        exit_code, output = _run_execute_cli(Path(temp_dir), str(root))

        assert exit_code == 1
        assert "Execute adapter" in output
        assert "manual" in output


def test_execute_command_ready_returns_zero_when_valid_patch_produced():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _write_prompt(root)

        script_path = _write_script(
            root,
            "fake_ai.py",
            f"""
            from pathlib import Path

            Path(".aidc").mkdir(parents=True, exist_ok=True)
            Path(".aidc/agent_patch.diff").write_text({ _valid_patch_text()!r }, encoding="utf-8")
            """,
        )
        command = _python_command(script_path)
        _save_config(
            root,
            mode="hybrid",
            agent="local",
            adapter="command",
            prompt_path=".aidc/agent_prompt.md",
            command=command,
        )

        exit_code, output = _run_execute_cli(root)

        assert exit_code == 0
        assert "Execute adapter" in output
        assert "patch_ready" in output
        assert "Timeout seconds" in output
        assert "120" in output
        assert "Executes command  yes" in output
        assert "Applies patch     no" in output
        assert "Return code" in output
        assert "Patch status" in output
        assert "Patch valid       yes" in output
        assert "Targets           main.py" in output
        assert "Next" in output
        assert "strata patch" in output
        assert "strata apply --dry-run" in output
        assert "strata apply" in output
        assert (root / "main.py").read_text(encoding="utf-8") == "print('hello')\n"


def test_execute_command_output_includes_stdout_preview():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _write_prompt(root)

        script_path = _write_script(
            root,
            "fake_ai.py",
            f"""
            from pathlib import Path

            print("stdout preview line")
            Path(".aidc").mkdir(parents=True, exist_ok=True)
            Path(".aidc/agent_patch.diff").write_text({ _valid_patch_text()!r }, encoding="utf-8")
            """,
        )
        command = _python_command(script_path)
        _save_config(
            root,
            mode="hybrid",
            agent="local",
            adapter="command",
            prompt_path=".aidc/agent_prompt.md",
            command=command,
        )

        exit_code, output = _run_execute_cli(root)

        assert exit_code == 0
        assert "Stdout" in output
        assert "stdout preview line" in output


def test_execute_command_output_includes_stderr_preview():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _write_prompt(root)

        script_path = _write_script(
            root,
            "fake_ai.py",
            f"""
            import sys
            from pathlib import Path

            sys.stderr.write("stderr preview line\\n")
            Path(".aidc").mkdir(parents=True, exist_ok=True)
            Path(".aidc/agent_patch.diff").write_text({ _valid_patch_text()!r }, encoding="utf-8")
            """,
        )
        command = _python_command(script_path)
        _save_config(
            root,
            mode="hybrid",
            agent="local",
            adapter="command",
            prompt_path=".aidc/agent_prompt.md",
            command=command,
        )

        exit_code, output = _run_execute_cli(root)

        assert exit_code == 0
        assert "Stderr" in output
        assert "stderr preview line" in output


def test_execute_command_output_truncates_long_stdout():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _write_prompt(root)

        long_stdout = "x" * 1000
        script_path = _write_script(
            root,
            "fake_ai.py",
            f"""
            from pathlib import Path

            print({long_stdout!r})
            Path(".aidc").mkdir(parents=True, exist_ok=True)
            Path(".aidc/agent_patch.diff").write_text({ _valid_patch_text()!r }, encoding="utf-8")
            """,
        )
        command = _python_command(script_path)
        _save_config(
            root,
            mode="hybrid",
            agent="local",
            adapter="command",
            prompt_path=".aidc/agent_prompt.md",
            command=command,
        )

        exit_code, output = _run_execute_cli(root)

        assert exit_code == 0
        assert "Stdout" in output
        assert long_stdout not in output


def test_execute_command_output_does_not_print_full_patch_content():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _write_prompt(root)

        stdout_payload = _valid_patch_text() + ("A" * 900) + "TAIL_MARKER"
        script_path = _write_script(
            root,
            "fake_ai.py",
            f"""
            from pathlib import Path

            print({stdout_payload!r})
            Path(".aidc").mkdir(parents=True, exist_ok=True)
            Path(".aidc/agent_patch.diff").write_text({ _valid_patch_text()!r }, encoding="utf-8")
            """,
        )
        command = _python_command(script_path)
        _save_config(
            root,
            mode="hybrid",
            agent="local",
            adapter="command",
            prompt_path=".aidc/agent_prompt.md",
            command=command,
        )

        exit_code, output = _run_execute_cli(root)

        assert exit_code == 0
        assert "Stdout" in output
        assert "TAIL_MARKER" not in output


def test_execute_command_output_shows_timeout_row():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _write_prompt(root)

        script_path = _write_script(
            root,
            "fake_ai.py",
            f"""
            from pathlib import Path

            Path(".aidc").mkdir(parents=True, exist_ok=True)
            Path(".aidc/agent_patch.diff").write_text({ _valid_patch_text()!r }, encoding="utf-8")
            """,
        )
        command = _python_command(script_path)
        _save_config(
            root,
            mode="hybrid",
            agent="local",
            adapter="command",
            prompt_path=".aidc/agent_prompt.md",
            command=command,
            command_timeout_seconds=33,
        )

        exit_code, output = _run_execute_cli(root)

        assert exit_code == 0
        assert "Timeout seconds" in output
        assert "33" in output


def test_execute_command_passes_configured_timeout_to_executor():
    original_execute = execute_command_module.execute_command_adapter
    captured = {}

    def _fake_execute(root_path: str = ".", command=None, timeout_seconds=120):
        captured["timeout_seconds"] = timeout_seconds
        return {
            "status": "patch_ready",
            "executed": True,
            "returncode": 0,
            "timed_out": False,
            "stdout": "",
            "stderr": "",
            "patch_status": "ready",
            "patch_valid": True,
            "targets": ["main.py"],
            "errors": [],
            "warnings": [],
            "message": "Command executed and produced a valid patch.",
        }

    execute_command_module.execute_command_adapter = _fake_execute
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _create_repo(root)
            _write_prompt(root)
            _save_config(
                root,
                mode="hybrid",
                agent="local",
                adapter="command",
                prompt_path=".aidc/agent_prompt.md",
                command="fake-command",
                command_timeout_seconds=77,
            )

            exit_code, output = _run_execute_cli(root)

            assert exit_code == 0
            assert "Timeout seconds" in output
            assert "77" in output
    finally:
        execute_command_module.execute_command_adapter = original_execute

    assert captured["timeout_seconds"] == 77


def test_execute_command_timeout_failure_returns_nonzero_and_shows_timeout_status():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _write_prompt(root)

        script_path = _write_script(
            root,
            "fake_ai.py",
            """
            import time

            time.sleep(2)
            """,
        )
        command = _python_command(script_path)
        _save_config(
            root,
            mode="hybrid",
            agent="local",
            adapter="command",
            prompt_path=".aidc/agent_prompt.md",
            command=command,
            command_timeout_seconds=1,
        )

        exit_code, output = _run_execute_cli(root)

        assert exit_code == 1
        assert "timeout" in output
        assert "Command execution timed out." in output
        assert "Timeout seconds" in output
        assert "1" in output


def test_execute_command_missing_patch_returns_nonzero():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _write_prompt(root)

        script_path = _write_script(
            root,
            "fake_ai.py",
            """
            from pathlib import Path

            Path(".aidc").mkdir(parents=True, exist_ok=True)
            """,
        )
        command = _python_command(script_path)
        _save_config(
            root,
            mode="hybrid",
            agent="local",
            adapter="command",
            prompt_path=".aidc/agent_prompt.md",
            command=command,
        )

        exit_code, output = _run_execute_cli(root)

        assert exit_code == 1
        assert "missing_patch" in output
        assert "Command did not produce a patch file." in output
        assert "Patch valid       no" in output
        assert "Targets           -" in output


def test_execute_command_empty_patch_returns_nonzero():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _write_prompt(root)

        script_path = _write_script(
            root,
            "fake_ai.py",
            """
            from pathlib import Path

            Path(".aidc").mkdir(parents=True, exist_ok=True)
            Path(".aidc/agent_patch.diff").write_text("", encoding="utf-8")
            """,
        )
        command = _python_command(script_path)
        _save_config(
            root,
            mode="hybrid",
            agent="local",
            adapter="command",
            prompt_path=".aidc/agent_prompt.md",
            command=command,
        )

        exit_code, output = _run_execute_cli(root)

        assert exit_code == 1
        assert "empty_patch" in output
        assert "Command executed but produced an empty patch." in output
        assert "Patch valid       no" in output


def test_execute_command_invalid_patch_returns_nonzero():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _write_prompt(root)

        script_path = _write_script(
            root,
            "fake_ai.py",
            """
            from pathlib import Path

            Path(".aidc").mkdir(parents=True, exist_ok=True)
            Path(".aidc/agent_patch.diff").write_text("this is not a diff\\n", encoding="utf-8")
            """,
        )
        command = _python_command(script_path)
        _save_config(
            root,
            mode="hybrid",
            agent="local",
            adapter="command",
            prompt_path=".aidc/agent_prompt.md",
            command=command,
        )

        exit_code, output = _run_execute_cli(root)

        assert exit_code == 1
        assert "invalid_patch" in output
        assert "Patch failed validation." in output
        assert "Patch valid       no" in output
        assert "Targets           -" in output


def test_execute_command_non_zero_exit_returns_nonzero():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _write_prompt(root)

        script_path = _write_script(
            root,
            "fake_ai.py",
            """
            import sys

            sys.exit(2)
            """,
        )
        command = _python_command(script_path)
        _save_config(
            root,
            mode="hybrid",
            agent="local",
            adapter="command",
            prompt_path=".aidc/agent_prompt.md",
            command=command,
        )

        exit_code, output = _run_execute_cli(root)

        assert exit_code == 1
        assert "command_failed" in output
        assert "Command exited with code 2." in output
        assert "Return code       2" in output
        assert "Patch status" in output
        assert "missing" in output


def test_execute_missing_prompt_returns_nonzero_and_says_not_ready():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _save_config(
            root,
            mode="hybrid",
            agent="codex",
            adapter="prompt_file",
            prompt_path=".aidc/agent_prompt.md",
        )

        exit_code, output = _run_execute_cli(root)

        assert exit_code == 1
        assert "not_ready" in output
        assert "Prompt file not found" in output


def test_execute_http_dry_run_returns_zero_and_makes_no_network_call():
    original_execute = execute_command_module.execute_openai_compatible_http_adapter

    def _fail(*_args, **_kwargs):
        raise AssertionError("HTTP execution should not run during dry-run")

    execute_command_module.execute_openai_compatible_http_adapter = _fail
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _create_repo(root)
            _write_prompt(root)
            _save_config(
                root,
                mode="hybrid",
                agent="local",
                adapter="openai_compatible_http",
                prompt_path=".aidc/agent_prompt.md",
                base_url="http://localhost:1234/v1",
                api_key_env="OPENAI_API_KEY",
                http_timeout_seconds=150,
            )

            exit_code, output = _run_execute_cli(Path(temp_dir), "--dry-run", str(root))

            assert exit_code == 0
            assert "dry-run" in output
            assert "Prompt exists" in output
            assert "Executes HTTP" in output
            assert "Applies patch" in output
            assert "Base URL" in output
            assert "URL" in output
            assert "Model" in output
    finally:
        execute_command_module.execute_openai_compatible_http_adapter = original_execute


def test_execute_http_normal_execute_against_local_fake_server_returns_patch_ready():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _write_prompt(root)
        secret = "sk-test-secret-cli"
        original = os.environ.get("OPENAI_API_KEY")
        os.environ["OPENAI_API_KEY"] = secret
        try:
            _save_config(
                root,
                mode="hybrid",
                agent="local",
                adapter="openai_compatible_http",
                prompt_path=".aidc/agent_prompt.md",
                base_url="http://localhost:1234/v1",
                api_key_env="OPENAI_API_KEY",
                model="qwen2.5-coder",
                http_timeout_seconds=150,
            )

            with run_http_server(
                response_body=json.dumps(
                    {
                        "choices": [
                            {
                                "message": {
                                    "content": _valid_patch_text(),
                                }
                            }
                        ]
                    }
                ),
                response_headers={"Content-Type": "application/json"},
            ) as (server, base_url):
                _save_config(
                    root,
                    mode="hybrid",
                    agent="local",
                    adapter="openai_compatible_http",
                    prompt_path=".aidc/agent_prompt.md",
                    base_url=base_url,
                    api_key_env="OPENAI_API_KEY",
                    model="qwen2.5-coder",
                    http_timeout_seconds=150,
                )

                exit_code, output = _run_execute_cli(root)

            assert exit_code == 0
            assert "patch_ready" in output
            assert "HTTP status" in output
            assert "Patch valid" in output
            assert "Targets" in output
            assert "main.py" in output
            assert "Next" in output
            assert "strata patch" in output
            assert "print(\"hello\")" not in output
            assert secret not in output
            assert server.last_request is not None
            auth_header = next(
                (
                    value
                    for key, value in server.last_request["headers"].items()
                    if key.lower() == "authorization"
                ),
                None,
            )
            assert auth_header == f"Bearer {secret}"
        finally:
            if original is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = original


def test_execute_http_missing_base_url_returns_nonzero():
    original_execute = execute_command_module.execute_openai_compatible_http_adapter

    def _fail(*_args, **_kwargs):
        raise AssertionError("HTTP execution should not run when base_url is missing")

    execute_command_module.execute_openai_compatible_http_adapter = _fail
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _create_repo(root)
            _write_prompt(root)
            _save_config(
                root,
                mode="hybrid",
                agent="local",
                adapter="openai_compatible_http",
                prompt_path=".aidc/agent_prompt.md",
                base_url=None,
                api_key_env="OPENAI_API_KEY",
                http_timeout_seconds=150,
            )

            exit_code, output = _run_execute_cli(root)

            assert exit_code == 1
            assert "not_ready" in output
            assert "base_url is required for HTTP adapters." in output
            assert "Executes HTTP" in output
    finally:
        execute_command_module.execute_openai_compatible_http_adapter = original_execute


def test_execute_command_family_planned_adapters_do_not_execute():
    original_execute = execute_command_module.execute_command_adapter

    def _fail(*_args, **_kwargs):
        raise AssertionError("execute_command_adapter should not be called")

    execute_command_module.execute_command_adapter = _fail
    try:
        for adapter in ("aider", "codex_cli"):
            with tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                _create_repo(root)
                _save_config(
                    root,
                    mode="hybrid",
                    agent="local",
                    adapter=adapter,
                    prompt_path=".aidc/agent_prompt.md",
                )

                exit_code, output = _run_execute_cli(root)

                assert exit_code == 1
                assert "not_implemented" in output
                assert "Command-family preset execution is not implemented yet." in output
                assert adapter in output
    finally:
        execute_command_module.execute_command_adapter = original_execute


def test_execute_http_family_planned_adapters_do_not_execute():
    original_execute = execute_command_module.execute_command_adapter
    original_create_connection = socket.create_connection

    def _fail(*_args, **_kwargs):
        raise AssertionError("network or command execution should not be called")

    execute_command_module.execute_command_adapter = _fail
    socket.create_connection = _fail
    try:
        for adapter in ("ollama",):
            with tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                _create_repo(root)
                _save_config(
                    root,
                    mode="hybrid",
                    agent="local",
                    adapter=adapter,
                    prompt_path=".aidc/agent_prompt.md",
                    base_url="http://localhost:11434" if adapter == "ollama" else "http://localhost:1234/v1",
                    api_key_env="OPENAI_API_KEY" if adapter == "openai_compatible_http" else None,
                    http_timeout_seconds=180,
                )

                exit_code, output = _run_execute_cli(root)

                assert exit_code == 1
                assert "not_implemented" in output
                assert "HTTP adapter execution is not implemented yet." in output
                assert adapter in output
                assert "URL" in output
                assert "HTTP timeout seconds" in output
    finally:
        execute_command_module.execute_command_adapter = original_execute
        socket.create_connection = original_create_connection


def test_execute_output_includes_expected_rows():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _save_config(root, adapter="prompt_file", prompt_path=".aidc/agent_prompt.md")
        _write_prompt(root)

        exit_code, output = _run_execute_cli(root)

        assert exit_code == 1
        assert "Status" in output
        assert "Mode" in output
        assert "Agent" in output
        assert "Adapter" in output
        assert "Prompt" in output
        assert "Patch" in output
        assert "Command" in output
        assert "Executes command" in output
        assert "Applies patch" in output
        assert "Return code" in output
        assert "Patch status" in output
        assert "Patch valid" in output
        assert "Targets" in output
        assert "Message" in output


def test_execute_command_captures_stdout_and_stderr_and_does_not_apply_patch():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _write_prompt(root)
        (root / "main.py").write_text("print('old')\n", encoding="utf-8")

        script_path = _write_script(
            root,
            "fake_ai.py",
            f"""
            import sys
            from pathlib import Path

            sys.stdout.write("stdout-line\\n")
            sys.stderr.write("stderr-line\\n")
            Path(".aidc").mkdir(parents=True, exist_ok=True)
            Path(".aidc/agent_patch.diff").write_text({ _valid_patch_text()!r }, encoding="utf-8")
            """,
        )
        command = _python_command(script_path)
        _save_config(
            root,
            mode="hybrid",
            agent="local",
            adapter="command",
            prompt_path=".aidc/agent_prompt.md",
            command=command,
        )

        result = execute_command_adapter(root, command=command)

        assert result["status"] == "patch_ready"
        assert "stdout-line" in result["stdout"]
        assert "stderr-line" in result["stderr"]
        assert (root / "main.py").read_text(encoding="utf-8") == "print('old')\n"


TESTS = [
    test_execute_prompt_file_ready_returns_nonzero_and_says_manual,
    test_execute_optional_root_argument_works,
    test_execute_command_ready_returns_zero_when_valid_patch_produced,
    test_execute_command_output_includes_stdout_preview,
    test_execute_command_output_includes_stderr_preview,
    test_execute_command_output_truncates_long_stdout,
    test_execute_command_output_does_not_print_full_patch_content,
    test_execute_command_output_shows_timeout_row,
    test_execute_command_passes_configured_timeout_to_executor,
    test_execute_command_timeout_failure_returns_nonzero_and_shows_timeout_status,
    test_execute_command_missing_patch_returns_nonzero,
    test_execute_command_empty_patch_returns_nonzero,
    test_execute_command_invalid_patch_returns_nonzero,
    test_execute_command_non_zero_exit_returns_nonzero,
    test_execute_missing_prompt_returns_nonzero_and_says_not_ready,
    test_execute_http_dry_run_returns_zero_and_makes_no_network_call,
    test_execute_http_normal_execute_against_local_fake_server_returns_patch_ready,
    test_execute_http_missing_base_url_returns_nonzero,
    test_execute_http_family_planned_adapters_do_not_execute,
    test_execute_output_includes_expected_rows,
    test_execute_command_captures_stdout_and_stderr_and_does_not_apply_patch,
]
