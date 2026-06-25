from __future__ import annotations

import contextlib
import json
import os
import socketserver
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from http_executor import build_http_headers, execute_openai_compatible_http_adapter
from workflow_config import default_config, save_config


class _ThreadedHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


class _RequestHandler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        server = self.server
        length = int(self.headers.get("Content-Length", "0") or 0)
        body = self.rfile.read(length).decode("utf-8", errors="replace")
        server.request_count += 1
        server.last_request = {
            "path": self.path,
            "headers": {key: value for key, value in self.headers.items()},
            "body": body,
        }

        delay_seconds = float(getattr(server, "delay_seconds", 0) or 0)
        if delay_seconds > 0:
            time.sleep(delay_seconds)

        response_status = int(getattr(server, "response_status", 200))
        response_body = getattr(server, "response_body", b"")
        response_headers = dict(getattr(server, "response_headers", {}))

        self.send_response(response_status)
        if "Content-Type" not in response_headers:
            response_headers["Content-Type"] = "application/json"

        for key, value in response_headers.items():
            self.send_header(key, value)

        self.end_headers()

        if isinstance(response_body, str):
            response_body = response_body.encode("utf-8")

        try:
            self.wfile.write(response_body)
        except OSError:
            return

    def log_message(self, *_args):  # noqa: D401
        return


@contextlib.contextmanager
def run_http_server(
    *,
    response_status: int = 200,
    response_body: bytes | str = b"",
    response_headers: dict[str, str] | None = None,
    delay_seconds: float = 0,
):
    server = _ThreadedHTTPServer(("127.0.0.1", 0), _RequestHandler)
    server.response_status = response_status
    server.response_body = response_body
    server.response_headers = response_headers or {}
    server.delay_seconds = delay_seconds
    server.request_count = 0
    server.last_request = None

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        yield server, f"http://127.0.0.1:{server.server_address[1]}/v1"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _write_prompt(root: Path, content: str = "prompt") -> Path:
    prompt_path = root / ".aidc" / "agent_prompt.md"
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(content, encoding="utf-8")
    return prompt_path


def _save_config(root: Path, **overrides) -> dict:
    config = default_config()
    config.update(overrides)
    save_config(config, root)
    return config


def _make_config(root: Path, **overrides) -> dict:
    config = default_config()
    config.update(overrides)
    return config


def _valid_patch_text() -> str:
    return (
        "diff --git a/main.py b/main.py\n"
        "--- a/main.py\n"
        "+++ b/main.py\n"
        "@@ -1 +1 @@\n"
        "-print('old')\n"
        "+print('new')\n"
    )


def _invalid_patch_text() -> str:
    return (
        "diff --git a/../evil.py b/../evil.py\n"
        "--- a/../evil.py\n"
        "+++ b/../evil.py\n"
        "@@ -1 +1 @@\n"
        "-print('old')\n"
        "+print('new')\n"
    )


def test_missing_base_url_returns_missing_base_url():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_prompt(root)
        config = _make_config(root, adapter="openai_compatible_http", prompt_path=".aidc/agent_prompt.md")

        result = execute_openai_compatible_http_adapter(root, config=config)

        assert result["status"] == "missing_base_url"
        assert result["executed"] is False
        assert result["errors"] == ["base_url is required for HTTP adapters."]
        assert result["http_status"] is None
        assert result["patch_valid"] is False


def test_missing_prompt_returns_missing_prompt():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        config = _make_config(
            root,
            adapter="openai_compatible_http",
            prompt_path=".aidc/agent_prompt.md",
            base_url="http://127.0.0.1:1234/v1",
        )

        result = execute_openai_compatible_http_adapter(root, config=config)

        assert result["status"] == "missing_prompt"
        assert result["executed"] is False
        assert len(result["errors"]) == 1
        prefix = "Prompt file not found: "
        assert result["errors"][0].startswith(prefix)

        actual_text = result["errors"][0][len(prefix):].replace("\\", "/")
        assert actual_text.endswith(".aidc/agent_prompt.md")


def test_missing_api_key_env_returns_missing_api_key_before_network_call():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_prompt(root)
        config = _make_config(
            root,
            adapter="openai_compatible_http",
            prompt_path=".aidc/agent_prompt.md",
            base_url="http://127.0.0.1:1234/v1",
            api_key_env="OPENAI_API_KEY",
        )

        with run_http_server(response_body=json.dumps({"choices": []})) as (server, _base_url):
            result = execute_openai_compatible_http_adapter(root, config=config)

        assert result["status"] == "missing_api_key"
        assert result["executed"] is False
        assert server.request_count == 0


def test_build_http_headers_redacts_secret_like_env_name_in_errors():
    try:
        build_http_headers({"api_key_env": "sk-testsecret-123456"})
    except ValueError as error:
        message = str(error)
        assert "sk-testsecret-123456" not in message
        assert "<redacted>" in message
    else:
        raise AssertionError("Expected ValueError")


def test_successful_local_http_response_writes_patch_file():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_prompt(root)
        config = _make_config(
            root,
            adapter="openai_compatible_http",
            prompt_path=".aidc/agent_prompt.md",
            base_url="http://127.0.0.1:1234/v1",
            model="qwen2.5-coder",
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
            config["base_url"] = base_url
            result = execute_openai_compatible_http_adapter(root, config=config)

        patch_path = root / ".aidc" / "agent_patch.diff"

        assert result["status"] == "patch_ready"
        assert result["executed"] is True
        assert result["http_status"] == 200
        assert result["patch_valid"] is True
        assert patch_path.is_file()
        assert patch_path.read_text(encoding="utf-8").strip() == _valid_patch_text().strip()
        assert server.request_count == 1


def test_successful_local_http_response_returns_patch_ready_when_patch_valid():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_prompt(root)
        config = _make_config(
            root,
            adapter="openai_compatible_http",
            prompt_path=".aidc/agent_prompt.md",
            base_url="http://127.0.0.1:1234/v1",
            model="qwen2.5-coder",
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
        ) as (_server, base_url):
            config["base_url"] = base_url
            result = execute_openai_compatible_http_adapter(root, config=config)

        assert result == {
            "status": "patch_ready",
            "executed": True,
            "adapter": "openai_compatible_http",
            "adapter_family": "http",
            "base_url": base_url,
            "url": base_url + "/chat/completions",
            "model": "qwen2.5-coder",
            "api_key_env": None,
            "http_timeout_seconds": 120,
            "prompt_path": str(root / ".aidc" / "agent_prompt.md"),
            "patch_path": str(root / ".aidc" / "agent_patch.diff"),
            "http_status": 200,
            "timed_out": False,
            "patch_status": "ready",
            "patch_valid": True,
            "targets": ["main.py"],
            "errors": [],
            "warnings": [],
            "message": "HTTP adapter executed and produced a valid patch.",
        }


def test_response_with_no_patch_returns_missing_patch_and_does_not_write_patch():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_prompt(root)
        config = _make_config(
            root,
            adapter="openai_compatible_http",
            prompt_path=".aidc/agent_prompt.md",
            base_url="http://127.0.0.1:1234/v1",
        )

        with run_http_server(
            response_body=json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "content": "No diff here.",
                            }
                        }
                    ]
                }
            ),
            response_headers={"Content-Type": "application/json"},
        ) as (_server, base_url):
            config["base_url"] = base_url
            result = execute_openai_compatible_http_adapter(root, config=config)

        assert result["status"] == "missing_patch"
        assert result["executed"] is True
        assert result["errors"] == ["Unified diff patch was not found in the provided text."]
        assert not (root / ".aidc" / "agent_patch.diff").exists()


def test_invalid_json_returns_invalid_json():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_prompt(root)
        config = _make_config(
            root,
            adapter="openai_compatible_http",
            prompt_path=".aidc/agent_prompt.md",
            base_url="http://127.0.0.1:1234/v1",
        )

        with run_http_server(
            response_body="not json",
            response_headers={"Content-Type": "text/plain"},
        ) as (_server, base_url):
            config["base_url"] = base_url
            result = execute_openai_compatible_http_adapter(root, config=config)

        assert result["status"] == "invalid_json"
        assert result["executed"] is True
        assert result["errors"]
        assert not (root / ".aidc" / "agent_patch.diff").exists()


def test_http_500_returns_http_error():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_prompt(root)
        config = _make_config(
            root,
            adapter="openai_compatible_http",
            prompt_path=".aidc/agent_prompt.md",
            base_url="http://127.0.0.1:1234/v1",
        )

        with run_http_server(
            response_status=500,
            response_body=json.dumps({"error": "boom"}),
            response_headers={"Content-Type": "application/json"},
        ) as (_server, base_url):
            config["base_url"] = base_url
            result = execute_openai_compatible_http_adapter(root, config=config)

        assert result["status"] == "http_error"
        assert result["executed"] is True
        assert result["http_status"] == 500
        assert result["errors"]


def test_timeout_returns_timeout():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_prompt(root)
        config = _make_config(
            root,
            adapter="openai_compatible_http",
            prompt_path=".aidc/agent_prompt.md",
            base_url="http://127.0.0.1:1234/v1",
            http_timeout_seconds=1,
        )

        with run_http_server(
            delay_seconds=2,
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
        ) as (_server, base_url):
            config["base_url"] = base_url
            result = execute_openai_compatible_http_adapter(root, config=config)

        assert result["status"] == "timeout"
        assert result["executed"] is True
        assert result["timed_out"] is True
        assert result["errors"]


def test_authorization_header_is_sent_when_api_key_env_is_configured():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_prompt(root)
        config = _make_config(
            root,
            adapter="openai_compatible_http",
            prompt_path=".aidc/agent_prompt.md",
            base_url="http://127.0.0.1:1234/v1",
            api_key_env="OPENAI_API_KEY",
        )

        secret = "sk-test-secret-123"
        original = os.environ.get("OPENAI_API_KEY")
        os.environ["OPENAI_API_KEY"] = secret
        try:
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
                config["base_url"] = base_url
                result = execute_openai_compatible_http_adapter(root, config=config)
        finally:
            if original is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = original

        assert result["status"] == "patch_ready"
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


def test_result_does_not_expose_api_key_value():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_prompt(root)
        config = _make_config(
            root,
            adapter="openai_compatible_http",
            prompt_path=".aidc/agent_prompt.md",
            base_url="http://127.0.0.1:1234/v1",
            api_key_env="OPENAI_API_KEY",
        )

        secret = "sk-test-secret-456"
        original = os.environ.get("OPENAI_API_KEY")
        os.environ["OPENAI_API_KEY"] = secret
        try:
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
            ) as (_server, base_url):
                config["base_url"] = base_url
                result = execute_openai_compatible_http_adapter(root, config=config)
        finally:
            if original is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = original

        assert secret not in str(result)
        assert result["api_key_env"] == "OPENAI_API_KEY"


def test_invalid_patch_returns_invalid_patch():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_prompt(root)
        config = _make_config(
            root,
            adapter="openai_compatible_http",
            prompt_path=".aidc/agent_prompt.md",
            base_url="http://127.0.0.1:1234/v1",
        )

        with run_http_server(
            response_body=json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "content": _invalid_patch_text(),
                            }
                        }
                    ]
                }
            ),
            response_headers={"Content-Type": "application/json"},
        ) as (_server, base_url):
            config["base_url"] = base_url
            result = execute_openai_compatible_http_adapter(root, config=config)

        patch_path = root / ".aidc" / "agent_patch.diff"

        assert result["status"] == "invalid_patch"
        assert result["executed"] is True
        assert result["patch_valid"] is False
        assert result["errors"]
        assert patch_path.is_file()


def test_no_patch_is_applied_automatically():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        root.joinpath("main.py").write_text("print('old')\n", encoding="utf-8")
        _write_prompt(root)
        config = _make_config(
            root,
            adapter="openai_compatible_http",
            prompt_path=".aidc/agent_prompt.md",
            base_url="http://127.0.0.1:1234/v1",
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
        ) as (_server, base_url):
            config["base_url"] = base_url
            result = execute_openai_compatible_http_adapter(root, config=config)

        assert result["status"] == "patch_ready"
        assert root.joinpath("main.py").read_text(encoding="utf-8") == "print('old')\n"


def test_result_uses_fresh_deterministic_dicts_and_lists():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_prompt(root)
        config = _make_config(
            root,
            adapter="openai_compatible_http",
            prompt_path=".aidc/agent_prompt.md",
            base_url="http://127.0.0.1:1234/v1",
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
        ) as (_server, base_url):
            config["base_url"] = base_url
            first = execute_openai_compatible_http_adapter(root, config=config)
            second = execute_openai_compatible_http_adapter(root, config=config)

        assert first == second
        assert first is not second
        assert first["targets"] is not second["targets"]
        assert first["errors"] is not second["errors"]
        assert first["warnings"] is not second["warnings"]

        first["targets"].append("mutated")
        first["errors"].append("mutated")
        first["warnings"].append("mutated")

        assert second["targets"] == ["main.py"]
        assert second["errors"] == []
        assert second["warnings"] == []


TESTS = [
    test_missing_base_url_returns_missing_base_url,
    test_missing_prompt_returns_missing_prompt,
    test_missing_api_key_env_returns_missing_api_key_before_network_call,
    test_build_http_headers_redacts_secret_like_env_name_in_errors,
    test_successful_local_http_response_writes_patch_file,
    test_successful_local_http_response_returns_patch_ready_when_patch_valid,
    test_response_with_no_patch_returns_missing_patch_and_does_not_write_patch,
    test_invalid_json_returns_invalid_json,
    test_http_500_returns_http_error,
    test_timeout_returns_timeout,
    test_authorization_header_is_sent_when_api_key_env_is_configured,
    test_result_does_not_expose_api_key_value,
    test_invalid_patch_returns_invalid_patch,
    test_no_patch_is_applied_automatically,
    test_result_uses_fresh_deterministic_dicts_and_lists,
]
