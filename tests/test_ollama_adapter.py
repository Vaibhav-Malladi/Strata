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

import ollama_adapter as old_ollama
import strata.adapters.ollama as new_ollama
from ollama_adapter import (
    DEFAULT_OLLAMA_BASE_URL,
    DEFAULT_OLLAMA_MODEL,
    build_ollama_generate_url,
    build_ollama_payload,
    build_ollama_tags_url,
    check_ollama_health,
    execute_ollama_adapter,
    extract_ollama_models,
    extract_text_from_ollama_response,
    normalize_ollama_base_url,
)
from workflow_config import default_config


def test_ollama_adapter_shim_exports_new_implementation_objects():
    assert old_ollama.execute_ollama_adapter is new_ollama.execute_ollama_adapter


class _ThreadedOllamaServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


class _RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self._handle_request("GET")

    def do_POST(self):  # noqa: N802
        self._handle_request("POST")

    def _handle_request(self, method: str) -> None:
        server = self.server
        length = int(self.headers.get("Content-Length", "0") or 0)
        body = self.rfile.read(length).decode("utf-8", errors="replace") if method == "POST" else ""
        server.request_count += 1
        server.last_request = {
            "method": method,
            "path": self.path,
            "headers": {key: value for key, value in self.headers.items()},
            "body": body,
        }

        if self.path == "/api/generate" and method == "POST":
            status = int(getattr(server, "generate_status", 200))
            response_body = getattr(server, "generate_body", b"")
            response_headers = dict(getattr(server, "generate_headers", {}))
            delay_seconds = float(getattr(server, "generate_delay_seconds", 0) or 0)
        elif self.path == "/api/tags" and method == "GET":
            status = int(getattr(server, "tags_status", 200))
            response_body = getattr(server, "tags_body", b"")
            response_headers = dict(getattr(server, "tags_headers", {}))
            delay_seconds = float(getattr(server, "tags_delay_seconds", 0) or 0)
        else:
            status = 404
            response_body = b'{"error":"not found"}'
            response_headers = {"Content-Type": "application/json"}
            delay_seconds = 0

        if delay_seconds > 0:
            time.sleep(delay_seconds)

        self.send_response(status)
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
def run_ollama_server(
    *,
    generate_status: int = 200,
    generate_body: bytes | str = b"",
    generate_headers: dict[str, str] | None = None,
    generate_delay_seconds: float = 0,
    tags_status: int = 200,
    tags_body: bytes | str = b"",
    tags_headers: dict[str, str] | None = None,
    tags_delay_seconds: float = 0,
):
    server = _ThreadedOllamaServer(("127.0.0.1", 0), _RequestHandler)
    server.generate_status = generate_status
    server.generate_body = generate_body
    server.generate_headers = generate_headers or {}
    server.generate_delay_seconds = generate_delay_seconds
    server.tags_status = tags_status
    server.tags_body = tags_body
    server.tags_headers = tags_headers or {}
    server.tags_delay_seconds = tags_delay_seconds
    server.request_count = 0
    server.last_request = None

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        yield server, f"http://127.0.0.1:{server.server_address[1]}"
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


def test_normalize_ollama_base_url_uses_the_default_base_url():
    assert normalize_ollama_base_url(None) == DEFAULT_OLLAMA_BASE_URL
    assert normalize_ollama_base_url("") == DEFAULT_OLLAMA_BASE_URL


def test_normalize_ollama_base_url_strips_trailing_slashes():
    assert normalize_ollama_base_url("http://localhost:11434/") == "http://localhost:11434"
    assert normalize_ollama_base_url("https://example.com/ollama///") == "https://example.com/ollama"


def test_normalize_ollama_base_url_rejects_unsupported_schemes():
    try:
        normalize_ollama_base_url("file:///tmp/model")
    except ValueError as error:
        assert "http://" in str(error)
        assert "https://" in str(error)
    else:
        raise AssertionError("Expected ValueError for unsupported base_url scheme")


def test_build_ollama_generate_url_appends_the_expected_path():
    assert build_ollama_generate_url(None) == "http://localhost:11434/api/generate"
    assert build_ollama_generate_url("http://localhost:11434/") == "http://localhost:11434/api/generate"


def test_build_ollama_tags_url_appends_the_expected_path():
    assert build_ollama_tags_url(None) == "http://localhost:11434/api/tags"
    assert build_ollama_tags_url("http://localhost:11434/") == "http://localhost:11434/api/tags"


def test_build_ollama_payload_includes_model_prompt_and_stream_false():
    payload = build_ollama_payload("write a diff", model="qwen2.5-coder:7b")

    assert payload["model"] == "qwen2.5-coder:7b"
    assert payload["stream"] is False
    assert payload["prompt"].startswith("Return only a unified diff patch.")
    assert "write a diff" in payload["prompt"]


def test_extract_text_from_ollama_response_returns_response_text():
    result = extract_text_from_ollama_response({"response": "diff --git a/a.py b/a.py\n"})

    assert result == {
        "status": "ok",
        "text": "diff --git a/a.py b/a.py\n",
        "errors": [],
        "message": "Ollama response text extracted.",
    }


def test_extract_text_from_ollama_response_rejects_invalid_shapes():
    result = extract_text_from_ollama_response({"response": ""})

    assert result["status"] == "invalid_response"
    assert result["text"] == ""
    assert result["errors"]


def test_extract_ollama_models_returns_model_names_from_tags_shape():
    result = extract_ollama_models(
        {
            "models": [
                {"name": "qwen2.5-coder:latest"},
                {"name": "llama3.2:latest"},
                {"not_name": "skip-me"},
            ]
        }
    )

    assert result == ["qwen2.5-coder:latest", "llama3.2:latest"]


def test_extract_ollama_models_returns_empty_list_for_bad_shape():
    assert extract_ollama_models({"models": {}}) == []
    assert extract_ollama_models({"not_models": []}) == []


def test_execute_ollama_adapter_returns_missing_prompt_when_prompt_is_missing():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        config = _save_config(
            root,
            adapter="ollama",
            prompt_path=".aidc/agent_prompt.md",
            model="qwen2.5-coder",
        )

        result = execute_ollama_adapter(root, config=config)

        assert result["status"] == "missing_prompt"
        assert result["executed"] is False
        assert result["errors"] == [f"Prompt file not found: {root / '.aidc' / 'agent_prompt.md'}"]
        assert not (root / ".aidc" / "agent_patch.diff").exists()


def test_execute_ollama_adapter_writes_agent_patch_when_response_is_valid():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_prompt(root)
        config = _save_config(
            root,
            adapter="ollama",
            prompt_path=".aidc/agent_prompt.md",
            model="qwen2.5-coder",
        )

        with run_ollama_server(
            generate_body=json.dumps({"response": _valid_patch_text()}),
            generate_headers={"Content-Type": "application/json"},
        ) as (server, base_url):
            config["base_url"] = base_url
            result = execute_ollama_adapter(root, config=config)

        patch_path = root / ".aidc" / "agent_patch.diff"

        assert result["status"] == "patch_ready"
        assert result["executed"] is True
        assert result["patch_valid"] is True
        assert patch_path.is_file()
        assert patch_path.read_text(encoding="utf-8").strip() == _valid_patch_text().strip()
        assert server.request_count == 1
        assert server.last_request["path"] == "/api/generate"
        assert server.last_request["method"] == "POST"


def test_execute_ollama_adapter_returns_patch_ready_when_patch_valid():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_prompt(root)
        config = _save_config(
            root,
            adapter="ollama",
            prompt_path=".aidc/agent_prompt.md",
            model="qwen2.5-coder",
        )

        with run_ollama_server(
            generate_body=json.dumps({"response": _valid_patch_text()}),
            generate_headers={"Content-Type": "application/json"},
        ) as (_server, base_url):
            config["base_url"] = base_url
            result = execute_ollama_adapter(root, config=config)

        assert result == {
            "status": "patch_ready",
            "executed": True,
            "adapter": "ollama",
            "adapter_family": "http",
            "base_url": base_url,
            "url": base_url + "/api/generate",
            "model": "qwen2.5-coder",
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
            "message": "Ollama adapter executed and produced a valid patch.",
        }


def test_execute_ollama_adapter_returns_missing_patch_and_does_not_write_patch():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_prompt(root)
        config = _save_config(
            root,
            adapter="ollama",
            prompt_path=".aidc/agent_prompt.md",
        )

        with run_ollama_server(
            generate_body=json.dumps({"response": "No diff here."}),
            generate_headers={"Content-Type": "application/json"},
        ) as (_server, base_url):
            config["base_url"] = base_url
            result = execute_ollama_adapter(root, config=config)

        assert result["status"] == "missing_patch"
        assert result["executed"] is True
        assert result["errors"] == ["Unified diff patch was not found in the provided text."]
        assert not (root / ".aidc" / "agent_patch.diff").exists()


def test_execute_ollama_adapter_returns_invalid_json_for_bad_json():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_prompt(root)
        config = _save_config(
            root,
            adapter="ollama",
            prompt_path=".aidc/agent_prompt.md",
        )

        with run_ollama_server(
            generate_body="not json",
            generate_headers={"Content-Type": "text/plain"},
        ) as (_server, base_url):
            config["base_url"] = base_url
            result = execute_ollama_adapter(root, config=config)

        assert result["status"] == "invalid_json"
        assert result["executed"] is True
        assert not (root / ".aidc" / "agent_patch.diff").exists()


def test_execute_ollama_adapter_returns_http_error_for_server_error():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_prompt(root)
        config = _save_config(
            root,
            adapter="ollama",
            prompt_path=".aidc/agent_prompt.md",
        )

        with run_ollama_server(
            generate_status=500,
            generate_body=json.dumps({"error": "boom"}),
            generate_headers={"Content-Type": "application/json"},
        ) as (_server, base_url):
            config["base_url"] = base_url
            result = execute_ollama_adapter(root, config=config)

        assert result["status"] == "http_error"
        assert result["executed"] is True
        assert result["http_status"] == 500


def test_execute_ollama_adapter_returns_timeout_for_slow_server():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_prompt(root)
        config = _save_config(
            root,
            adapter="ollama",
            prompt_path=".aidc/agent_prompt.md",
            http_timeout_seconds=1,
        )

        with run_ollama_server(
            generate_delay_seconds=2,
            generate_body=json.dumps({"response": _valid_patch_text()}),
            generate_headers={"Content-Type": "application/json"},
        ) as (_server, base_url):
            config["base_url"] = base_url
            result = execute_ollama_adapter(root, config=config)

        assert result["status"] == "timeout"
        assert result["executed"] is True
        assert result["timed_out"] is True


def test_execute_ollama_adapter_returns_invalid_patch_for_forbidden_targets():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_prompt(root)
        config = _save_config(
            root,
            adapter="ollama",
            prompt_path=".aidc/agent_prompt.md",
        )

        with run_ollama_server(
            generate_body=json.dumps({"response": _invalid_patch_text()}),
            generate_headers={"Content-Type": "application/json"},
        ) as (_server, base_url):
            config["base_url"] = base_url
            result = execute_ollama_adapter(root, config=config)

        patch_path = root / ".aidc" / "agent_patch.diff"

        assert result["status"] == "invalid_patch"
        assert result["executed"] is True
        assert result["patch_valid"] is False
        assert patch_path.is_file()


def test_execute_ollama_adapter_does_not_apply_patch_automatically():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        root.joinpath("main.py").write_text("print('old')\n", encoding="utf-8")
        _write_prompt(root)
        config = _save_config(
            root,
            adapter="ollama",
            prompt_path=".aidc/agent_prompt.md",
        )

        with run_ollama_server(
            generate_body=json.dumps({"response": _valid_patch_text()}),
            generate_headers={"Content-Type": "application/json"},
        ) as (_server, base_url):
            config["base_url"] = base_url
            result = execute_ollama_adapter(root, config=config)

        assert result["status"] == "patch_ready"
        assert root.joinpath("main.py").read_text(encoding="utf-8") == "print('old')\n"


def test_check_ollama_health_returns_models_from_local_fake_server():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        config = _save_config(root, adapter="ollama", model="qwen2.5-coder")

        with run_ollama_server(
            tags_body=json.dumps(
                {
                    "models": [
                        {"name": "qwen2.5-coder:latest"},
                        {"name": "llama3.2:latest"},
                    ]
                }
            ),
            tags_headers={"Content-Type": "application/json"},
        ) as (_server, base_url):
            config["base_url"] = base_url
            result = check_ollama_health(config)

        assert result["status"] == "ok"
        assert result["models"] == ["qwen2.5-coder:latest", "llama3.2:latest"]
        assert result["model_available"] is True
        assert result["base_url"] == base_url
        assert result["tags_url"] == base_url + "/api/tags"


def test_check_ollama_health_marks_configured_model_availability():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        config = _save_config(root, adapter="ollama", model="qwen2.5-coder")

        with run_ollama_server(
            tags_body=json.dumps({"models": [{"name": "qwen2.5-coder"}]}),
            tags_headers={"Content-Type": "application/json"},
        ) as (_server, base_url):
            config["base_url"] = base_url
            result = check_ollama_health(config)

        assert result["status"] == "ok"
        assert result["model_available"] is True

        with run_ollama_server(
            tags_body=json.dumps({"models": [{"name": "llama3.2"}]}),
            tags_headers={"Content-Type": "application/json"},
        ) as (_server, base_url):
            config["base_url"] = base_url
            result = check_ollama_health(config)

        assert result["status"] == "unavailable"
        assert result["model_available"] is False
        assert result["warnings"]


def test_ollama_results_do_not_expose_secrets():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_prompt(root)
        secret = "sk-test-secret-ollama"
        original = os.environ.get("OLLAMA_API_KEY")
        os.environ["OLLAMA_API_KEY"] = secret
        try:
            config = _save_config(
                root,
                adapter="ollama",
                prompt_path=".aidc/agent_prompt.md",
                api_key_env="OLLAMA_API_KEY",
            )

            with run_ollama_server(
                generate_body=json.dumps({"response": _valid_patch_text()}),
                generate_headers={"Content-Type": "application/json"},
            ) as (_server, base_url):
                config["base_url"] = base_url
                result = execute_ollama_adapter(root, config=config)
        finally:
            if original is None:
                os.environ.pop("OLLAMA_API_KEY", None)
            else:
                os.environ["OLLAMA_API_KEY"] = original

        assert result["status"] == "patch_ready"
        assert secret not in str(result)
        assert result.get("model") == DEFAULT_OLLAMA_MODEL


def test_ollama_results_use_fresh_deterministic_dicts_and_lists():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_prompt(root)
        config = _save_config(
            root,
            adapter="ollama",
            prompt_path=".aidc/agent_prompt.md",
        )

        with run_ollama_server(
            generate_body=json.dumps({"response": _valid_patch_text()}),
            generate_headers={"Content-Type": "application/json"},
        ) as (_server, base_url):
            config["base_url"] = base_url
            first = execute_ollama_adapter(root, config=config)
            second = execute_ollama_adapter(root, config=config)

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
    test_ollama_adapter_shim_exports_new_implementation_objects,
    test_normalize_ollama_base_url_uses_the_default_base_url,
    test_normalize_ollama_base_url_strips_trailing_slashes,
    test_normalize_ollama_base_url_rejects_unsupported_schemes,
    test_build_ollama_generate_url_appends_the_expected_path,
    test_build_ollama_tags_url_appends_the_expected_path,
    test_build_ollama_payload_includes_model_prompt_and_stream_false,
    test_extract_text_from_ollama_response_returns_response_text,
    test_extract_text_from_ollama_response_rejects_invalid_shapes,
    test_extract_ollama_models_returns_model_names_from_tags_shape,
    test_extract_ollama_models_returns_empty_list_for_bad_shape,
    test_execute_ollama_adapter_returns_missing_prompt_when_prompt_is_missing,
    test_execute_ollama_adapter_writes_agent_patch_when_response_is_valid,
    test_execute_ollama_adapter_returns_patch_ready_when_patch_valid,
    test_execute_ollama_adapter_returns_missing_patch_and_does_not_write_patch,
    test_execute_ollama_adapter_returns_invalid_json_for_bad_json,
    test_execute_ollama_adapter_returns_http_error_for_server_error,
    test_execute_ollama_adapter_returns_timeout_for_slow_server,
    test_execute_ollama_adapter_returns_invalid_patch_for_forbidden_targets,
    test_execute_ollama_adapter_does_not_apply_patch_automatically,
    test_check_ollama_health_returns_models_from_local_fake_server,
    test_check_ollama_health_marks_configured_model_availability,
    test_ollama_results_do_not_expose_secrets,
    test_ollama_results_use_fresh_deterministic_dicts_and_lists,
]
