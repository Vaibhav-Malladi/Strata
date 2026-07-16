import json
import os
import tempfile
from pathlib import Path

import strata.utils.config as workflow_config
import strata.utils.workspace_discovery as workspace_discovery
import strata.utils.workspace_references as references
import strata.utils.workspace_relationships as relationships


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _write(root: Path, path: str, content: str | bytes) -> Path:
    file_path = root / path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        file_path.write_bytes(content)
    else:
        file_path.write_text(content, encoding="utf-8")
    return file_path


def _backend():
    return {
        "id": "backend",
        "path": "../backend",
        "role": "backend",
        "display_name": "Backend",
        "known_ports": [8080, 4201],
        "known_urls": ["http://localhost:8080", "http://localhost:4201/app"],
    }


def _worker():
    return {
        "id": "worker",
        "path": "../worker",
        "role": "worker",
        "known_ports": [9000],
        "known_urls": ["https://worker.example.test"],
    }


def _extract(root: Path, selected, **kwargs):
    return references.extract_workspace_references("frontend", root, selected, **kwargs)


def _payload(result):
    return result.to_dict()


def _refs(result, reference_type=None):
    items = _payload(result)["references"]
    if reference_type is None:
        return items
    return [item for item in items if item["reference_type"] == reference_type]


def _codes(result):
    return [item["code"] for item in _payload(result)["diagnostics"]]


def test_rejects_absolute_selected_path():
    with tempfile.TemporaryDirectory() as temp_dir:
        result = _extract(Path(temp_dir), [str(Path(temp_dir) / "app.py")])

    assert "selected_path_absolute" in _codes(result)


def test_rejects_selected_path_traversal():
    with tempfile.TemporaryDirectory() as temp_dir:
        result = _extract(Path(temp_dir), ["../outside.py"])

    assert "selected_path_traversal" in _codes(result)


def test_handles_missing_file():
    with tempfile.TemporaryDirectory() as temp_dir:
        result = _extract(Path(temp_dir), ["missing.py"])

    assert "selected_path_missing" in _codes(result)


def test_handles_directory_input():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        (root / "src").mkdir()
        result = _extract(root, ["src"])

    assert "selected_path_is_directory" in _codes(result)


def test_handles_unsupported_extension():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "notes.txt", "http://localhost:8080\n")
        result = _extract(root, ["notes.txt"])

    assert "unsupported_file_type" in _codes(result)


def test_skips_symlink_escape_when_supported():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        outside = Path(temp_dir) / "outside.py"
        root.mkdir()
        outside.write_text("API_URL = 'http://localhost:8080'\n", encoding="utf-8")
        try:
            os.symlink(outside, root / "linked.py")
        except OSError:
            return

        result = _extract(root, ["linked.py"])

    assert "symlink_skipped" in _codes(result)


def test_enforces_file_size_cap():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "large.py", "A" * 20)
        result = _extract(root, ["large.py"], max_bytes_per_file=5)

    assert "file_too_large" in _codes(result)


def test_enforces_total_byte_cap():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "a.py", "API_URL = 'http://localhost:8080'\n")
        _write(root, "b.py", "API_URL = 'http://localhost:8081'\n")
        result = _extract(root, ["a.py", "b.py"], max_total_bytes=40)

    assert "total_byte_cap_reached" in _codes(result)


def test_enforces_selected_file_cap():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "a.py", "A = 'x'\n")
        _write(root, "b.py", "B = 'x'\n")
        result = _extract(root, ["a.py", "b.py"], max_files=1)

    assert "file_cap_reached" in _codes(result)


def test_reports_decode_failure():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "bad.py", b"\xff\xfe\x00")
        result = _extract(root, ["bad.py"])

    assert "decode_failed" in _codes(result)


def test_extracts_and_normalizes_localhost_url():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "app.ts", 'const url = "HTTP://LOCALHOST:8080/api/";\n')
        result = _extract(root, ["app.ts"])

    values = [item["normalized_value"] for item in _refs(result, "localhost_url")]
    assert "http://localhost:8080/api/" in values


def test_extracts_127_loopback_url():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "app.ts", 'fetch("http://127.0.0.1:8080/api")\n')
        result = _extract(root, ["app.ts"])

    assert _refs(result, "localhost_url")[0]["normalized_value"] == "http://localhost:8080/api"


def test_extracts_ipv6_loopback_url():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "app.ts", 'fetch("http://[::1]:8080/api")\n')
        result = _extract(root, ["app.ts"])

    assert _refs(result, "localhost_url")[0]["normalized_value"] == "http://localhost:8080/api"


def test_preserves_ipv6_loopback_query_and_fragment():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "app.ts", 'fetch("https://[::1]/path?x=1#part")\n')
        result = _extract(root, ["app.ts"])

    assert _refs(result, "localhost_url")[0]["normalized_value"] == "https://localhost/path?x=1#part"


def test_extracts_ipv6_loopback_ws_and_wss_urls():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "app.ts", 'connect("ws://[::1]:3000/socket"); connect("wss://[::1]/socket")\n')
        result = _extract(root, ["app.ts"])

    values = [item["normalized_value"] for item in _refs(result, "localhost_url")]

    assert "ws://localhost:3000/socket" in values
    assert "wss://localhost/socket" in values


def test_non_loopback_ipv6_remains_absolute_http_url():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "app.ts", 'fetch("http://[2001:db8::1]:8080/api")\n')
        result = _extract(root, ["app.ts"])

    assert _refs(result, "localhost_url") == []
    assert _refs(result, "absolute_http_url")[0]["normalized_value"] == "http://[2001:db8::1]:8080/api"


def test_extracts_absolute_https_url_and_preserves_query_fragment():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "app.ts", 'fetch("HTTPS://API.EXAMPLE.test/v1?q=1#top")\n')
        result = _extract(root, ["app.ts"])

    assert _refs(result, "absolute_http_url")[0]["normalized_value"] == "https://api.example.test/v1?q=1#top"


def test_skips_credentialed_url():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "app.ts", 'fetch("https://user:pass@example.test/api")\n')
        result = _extract(root, ["app.ts"])

    assert "credentialed_url_skipped" in _codes(result)
    assert _payload(result)["references"] == []


def test_extracts_api_url_from_env():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, ".env", "API_URL=http://localhost:8080\n")
        result = _extract(root, [".env"])

    assert _refs(result, "api_base_url")[0]["symbol"] == "API_URL"


def test_extracts_url_from_json():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "config.json", '{"service": {"BACKEND_URL": "http://localhost:8080"}}')
        result = _extract(root, ["config.json"])

    assert _refs(result, "api_base_url")[0]["symbol"] == "service.BACKEND_URL"


def test_extracts_url_from_toml():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "settings.toml", 'AUTH_URL = "https://auth.example.test"\n')
        result = _extract(root, ["settings.toml"])

    assert _refs(result, "api_base_url")[0]["normalized_value"] == "https://auth.example.test"


def test_extracts_simple_yaml_url_and_reports_partial_parse():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "compose.yml", "SERVICE_URL: http://localhost:8080\n")
        result = _extract(root, ["compose.yml"])

    assert _refs(result, "api_base_url")
    assert "yaml_partial_parse" in _codes(result)


def test_handles_malformed_json():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "config.json", '{"API_URL": ')
        result = _extract(root, ["config.json"])

    assert "malformed_json" in _codes(result)


def test_handles_malformed_toml():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "settings.toml", 'API_URL = "http://localhost:8080"\n[')
        result = _extract(root, ["settings.toml"])

    assert "malformed_toml" in _codes(result)


def test_does_not_collect_secret_like_config_values():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, ".env", "API_TOKEN=abcdefghijklmnopqrstuvwxyz1234567890\n")
        result = _extract(root, [".env"])

    assert "sensitive_config_value_skipped" in _codes(result)
    assert _payload(result)["references"] == []


def test_extracts_html_iframe_literal_src():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "index.html", '<iframe src="http://localhost:4201/app"></iframe>')
        result = _extract(root, ["index.html"])

    assert _refs(result, "iframe_src")[0]["normalized_value"] == "http://localhost:4201/app"


def test_extracts_jsx_iframe_literal_src():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "App.tsx", 'export const App = () => <iframe src="http://localhost:4201/app" />;')
        result = _extract(root, ["App.tsx"])

    assert _refs(result, "iframe_src")[0]["reference_type"] == "iframe_src"


def test_extracts_angular_bound_src_symbol():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "app.component.html", '<iframe [src]="trustedUrl"></iframe>')
        result = _extract(root, ["app.component.html"])

    iframe = _refs(result, "iframe_src")[0]
    assert iframe["symbol"] == "trustedUrl"
    assert iframe["target_hint"] == "trustedUrl"


def test_degrades_confidence_for_dynamic_iframe_expression():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "App.tsx", "<iframe src={items[index].url} />")
        result = _extract(root, ["App.tsx"])

    assert _refs(result, "iframe_src")[0]["confidence"] == "low"
    assert "dynamic_reference_unresolved" in _codes(result)


def test_extracts_post_message_literal_type_and_origin():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "messages.ts", 'window.parent.postMessage({ type: "LOGIN_COMPLETE" }, "http://localhost:4200")')
        result = _extract(root, ["messages.ts"])

    message = _refs(result, "post_message_send")[0]
    assert message["metadata"]["message_event"] == "LOGIN_COMPLETE"
    assert message["normalized_value"] == "http://localhost:4200"


def test_reports_wildcard_post_message_origin():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "messages.ts", 'iframe.contentWindow.postMessage("READY", "*")')
        result = _extract(root, ["messages.ts"])

    assert _refs(result, "post_message_send")[0]["confidence"] == "low"
    assert "wildcard_post_message_origin" in _codes(result)


def test_handles_dynamic_post_message_payload():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "messages.ts", "targetWindow.postMessage(payload, origin)")
        result = _extract(root, ["messages.ts"])

    assert _refs(result, "post_message_send")[0]["confidence"] == "low"
    assert "dynamic_reference_unresolved" in _codes(result)


def test_detects_add_event_listener_message_with_checks():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(
            root,
            "listener.ts",
            'window.addEventListener("message", (event) => { if (event.origin === "http://localhost:4200" && event.data.type === "READY") {} });',
        )
        result = _extract(root, ["listener.ts"])

    listener = _refs(result, "message_listener")[0]
    assert listener["metadata"]["message_event"] == "READY"
    assert listener["normalized_value"] == "http://localhost:4200"


def test_detects_onmessage_assignment_without_origin_warning():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "listener.ts", 'window.onmessage = (event) => { if (event.data.type === "READY") {} };')
        result = _extract(root, ["listener.ts"])

    assert _refs(result, "message_listener")[0]["confidence"] == "low"
    assert "message_listener_without_origin_check" in _codes(result)


def test_extracts_python_api_constant():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "settings.py", 'API_BASE_URL = "http://localhost:8080"\n')
        result = _extract(root, ["settings.py"])

    assert _refs(result, "api_base_url")[0]["symbol"] == "API_BASE_URL"


def test_extracts_js_route_constant():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "routes.ts", 'export const LOGIN_ROUTE = "/login";\n')
        result = _extract(root, ["routes.ts"])

    assert _refs(result, "route_constant")[0]["normalized_value"] == "/login"


def test_extracts_go_header_or_event_constant():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "constants.go", 'package main\nconst AuthHeader = "Authorization"\nconst MessageType = "LOGIN_COMPLETE"\n')
        result = _extract(root, ["constants.go"])

    values = [item["normalized_value"] for item in _refs(result, "shared_constant")]
    assert "Authorization" in values
    assert "LOGIN_COMPLETE" in values


def test_ignores_unrelated_arbitrary_string_constants():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "constants.py", 'TITLE = "Welcome"\n')
        result = _extract(root, ["constants.py"])

    assert _payload(result)["references"] == []


def test_matches_exact_configured_url():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, ".env", "API_URL=http://localhost:8080\n")
        result = _extract(root, [".env"], known_repositories=[_backend()])

    assert _refs(result, "api_base_url")[0]["target_repository_id"] == "backend"


def test_matches_unique_configured_port():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, ".env", "API_URL=http://localhost:9000/api\n")
        result = _extract(root, [".env"], known_repositories=[_backend(), _worker()])

    assert _refs(result, "api_base_url")[0]["target_repository_id"] == "worker"


def test_does_not_choose_ambiguous_shared_port():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        first = {**_backend(), "known_urls": [], "known_ports": [8080]}
        second = {**_worker(), "known_urls": [], "known_ports": [8080]}
        _write(root, ".env", "API_URL=http://localhost:8080/api\n")
        result = _extract(root, [".env"], known_repositories=[first, second])

    assert _refs(result, "api_base_url")[0]["target_repository_id"] is None
    assert "ambiguous_target_repository" in _codes(result)


def test_does_not_match_current_repository_as_target():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        current = {"id": "frontend", "path": ".", "role": "frontend", "known_ports": [8080], "known_urls": ["http://localhost:8080"]}
        _write(root, ".env", "API_URL=http://localhost:8080\n")
        result = _extract(root, [".env"], known_repositories=[current])

    assert _refs(result, "api_base_url")[0]["target_repository_id"] is None


def test_keeps_unknown_target_unset():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, ".env", "API_URL=http://localhost:7777\n")
        result = _extract(root, [".env"], known_repositories=[_backend()])

    assert _refs(result, "api_base_url")[0]["target_repository_id"] is None
    assert "unknown_target_repository" in _codes(result)


def test_api_url_becomes_calls_api_relationship_hint():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, ".env", "API_URL=http://localhost:8080\n")
        result = _extract(root, [".env"], known_repositories=[_backend()])

    hints = references.references_to_relationship_hints(result.references)

    assert hints[0]["relationship_type"] == "calls_api"


def test_iframe_becomes_embeds_iframe_relationship_hint():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "index.html", '<iframe src="http://localhost:4201/app"></iframe>')
        result = _extract(root, ["index.html"], known_repositories=[_backend()])

    hints = references.references_to_relationship_hints(result.references)

    assert hints[0]["relationship_type"] == "embeds_iframe"


def test_post_message_becomes_sends_messages_relationship_hint():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "messages.ts", 'window.parent.postMessage({ type: "READY" }, "http://localhost:8080")')
        result = _extract(root, ["messages.ts"], known_repositories=[_backend()])

    hints = references.references_to_relationship_hints(result.references)

    assert hints[0]["relationship_type"] == "sends_messages_to"


def test_message_listener_becomes_receives_messages_relationship_hint():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "listener.ts", 'window.addEventListener("message", (event) => { if (event.origin === "http://localhost:8080") {} });')
        result = _extract(root, ["listener.ts"], known_repositories=[_backend()])

    hints = references.references_to_relationship_hints(result.references)

    assert hints[0]["relationship_type"] == "receives_messages_from"


def test_shared_constant_does_not_become_relationship_hint():
    reference = references.WorkspaceReference(
        repository_id="frontend",
        source_path="constants.ts",
        reference_type="shared_constant",
        raw_value="LOGIN_COMPLETE",
        normalized_value="LOGIN_COMPLETE",
        confidence="medium",
        confidence_score=0.5,
        target_repository_id="backend",
    )

    assert references.references_to_relationship_hints((reference,)) == ()


def test_untargeted_reference_does_not_become_relationship_hint():
    reference = references.WorkspaceReference(
        repository_id="frontend",
        source_path="settings.py",
        reference_type="api_base_url",
        raw_value="http://localhost:8080",
        normalized_value="http://localhost:8080",
        confidence="medium",
        confidence_score=0.5,
    )

    assert references.references_to_relationship_hints((reference,)) == ()


def test_reference_per_file_cap_is_enforced():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, ".env", "\n".join(f"API_URL_{index}=http://localhost:{8000 + index}" for index in range(4)))
        result = _extract(root, [".env"], max_references_per_file=2)

    assert len(_payload(result)["references"]) == 2
    assert "file_reference_cap_reached" in _codes(result)


def test_total_reference_cap_is_enforced():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, ".env", "\n".join(f"API_URL_{index}=http://localhost:{8000 + index}" for index in range(4)))
        result = _extract(root, [".env"], max_references=2)

    assert len(_payload(result)["references"]) == 2
    assert "reference_cap_reached" in _codes(result)


def test_diagnostic_cap_is_enforced():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        result = _extract(root, ["missing.py", "missing.ts", "missing.go"], max_diagnostics=2)

    assert len(_payload(result)["diagnostics"]) == 2


def test_deterministic_reference_ordering_and_serialization():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "b.ts", 'const API_URL = "http://localhost:8080";\n')
        _write(root, "a.ts", 'const LOGIN_ROUTE = "/login";\n')
        first = _payload(_extract(root, ["b.ts", "a.ts"]))
        second = _payload(_extract(root, ["a.ts", "b.ts"]))

    assert first == second
    assert list(first) == list(references.EXTRACTION_RESULT_FIELD_ORDER)
    assert list(first["references"][0]) == list(references.REFERENCE_FIELD_ORDER)
    assert list(first["diagnostics"]) == []
    assert json.loads(json.dumps(first, allow_nan=False)) == first


def test_q1_compatibility_remains_unchanged():
    workspace = {
        "schema_version": 1,
        "name": "example",
        "repositories": [
            {"id": "frontend", "path": ".", "role": "frontend"},
            {"id": "backend", "path": "../backend", "role": "backend"},
        ],
    }

    normalized = workflow_config.validate_config({"workspace": workspace})

    assert normalized["workspace"]["repositories"][0]["id"] == "backend"


def test_q2_compatibility_remains_unchanged():
    evidence = workspace_discovery.WorkspaceDiscoveryEvidence(
        signal_type="local_path_reference",
        source_path="package.json",
        summary="package.json references local dependency.",
        strength="strong",
        referenced_path="../backend",
    )

    assert evidence.to_dict()["referenced_path"] == "../backend"


def test_q3_compatibility_remains_unchanged():
    hint = {
        "source_repository_id": "frontend",
        "target_repository_id": "backend",
        "relationship_type": "calls_api",
        "origin": "inferred",
        "confidence": "high",
        "confidence_score": 0.8,
    }
    workspace = {
        "schema_version": 1,
        "name": "example",
        "repositories": [
            {"id": "frontend", "path": ".", "role": "frontend"},
            {"id": "backend", "path": "../backend", "role": "backend"},
        ],
    }

    assessment = relationships.build_workspace_relationship_assessment(workspace, inferred_relationships=(hint,))

    assert assessment.to_dict()["relationships"][0]["relationship_type"] == "calls_api"


def test_scanner_compatible_imports_and_architecture_boundary():
    source = (PROJECT_ROOT / "strata" / "utils" / "workspace_references.py").read_text(
        encoding="utf-8"
    )

    assert "import strata.utils.workspace_relationships as workspace_relationships" in source
    assert "from strata.utils import" not in source
    assert "strata.commands" not in source
    assert "strata.core" not in source


def test_workspace_q4_docs_define_contract_only_scope():
    content = (PROJECT_ROOT / "docs" / "roadmap" / "workspace-intelligence.md").read_text(
        encoding="utf-8"
    )

    assert "Q4" in content
    assert "selected-file extraction only" in content
    assert "does not build the workspace dependency graph" in content
    assert "does not compare shared contracts" in content
    assert "does not add findings to AI context" in content


TESTS = [
    test_rejects_absolute_selected_path,
    test_rejects_selected_path_traversal,
    test_handles_missing_file,
    test_handles_directory_input,
    test_handles_unsupported_extension,
    test_skips_symlink_escape_when_supported,
    test_enforces_file_size_cap,
    test_enforces_total_byte_cap,
    test_enforces_selected_file_cap,
    test_reports_decode_failure,
    test_extracts_and_normalizes_localhost_url,
    test_extracts_127_loopback_url,
    test_extracts_ipv6_loopback_url,
    test_preserves_ipv6_loopback_query_and_fragment,
    test_extracts_ipv6_loopback_ws_and_wss_urls,
    test_non_loopback_ipv6_remains_absolute_http_url,
    test_extracts_absolute_https_url_and_preserves_query_fragment,
    test_skips_credentialed_url,
    test_extracts_api_url_from_env,
    test_extracts_url_from_json,
    test_extracts_url_from_toml,
    test_extracts_simple_yaml_url_and_reports_partial_parse,
    test_handles_malformed_json,
    test_handles_malformed_toml,
    test_does_not_collect_secret_like_config_values,
    test_extracts_html_iframe_literal_src,
    test_extracts_jsx_iframe_literal_src,
    test_extracts_angular_bound_src_symbol,
    test_degrades_confidence_for_dynamic_iframe_expression,
    test_extracts_post_message_literal_type_and_origin,
    test_reports_wildcard_post_message_origin,
    test_handles_dynamic_post_message_payload,
    test_detects_add_event_listener_message_with_checks,
    test_detects_onmessage_assignment_without_origin_warning,
    test_extracts_python_api_constant,
    test_extracts_js_route_constant,
    test_extracts_go_header_or_event_constant,
    test_ignores_unrelated_arbitrary_string_constants,
    test_matches_exact_configured_url,
    test_matches_unique_configured_port,
    test_does_not_choose_ambiguous_shared_port,
    test_does_not_match_current_repository_as_target,
    test_keeps_unknown_target_unset,
    test_api_url_becomes_calls_api_relationship_hint,
    test_iframe_becomes_embeds_iframe_relationship_hint,
    test_post_message_becomes_sends_messages_relationship_hint,
    test_message_listener_becomes_receives_messages_relationship_hint,
    test_shared_constant_does_not_become_relationship_hint,
    test_untargeted_reference_does_not_become_relationship_hint,
    test_reference_per_file_cap_is_enforced,
    test_total_reference_cap_is_enforced,
    test_diagnostic_cap_is_enforced,
    test_deterministic_reference_ordering_and_serialization,
    test_q1_compatibility_remains_unchanged,
    test_q2_compatibility_remains_unchanged,
    test_q3_compatibility_remains_unchanged,
    test_scanner_compatible_imports_and_architecture_boundary,
    test_workspace_q4_docs_define_contract_only_scope,
]
