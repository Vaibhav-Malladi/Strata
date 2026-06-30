import http_adapter_contract as old_http_contract
import strata.adapters.http_contract as new_http_contract
from http_adapter_contract import (
    build_http_contract_summary,
    build_openai_compatible_payload,
    build_openai_compatible_url,
    extract_patch_from_text,
    extract_text_from_openai_compatible_response,
    normalize_base_url,
)


def test_http_contract_shim_exports_new_implementation_objects():
    assert old_http_contract.normalize_base_url is new_http_contract.normalize_base_url


def test_normalize_base_url_strips_trailing_slashes_and_preserves_scheme():
    assert normalize_base_url("http://localhost:1234/v1///") == "http://localhost:1234/v1"
    assert normalize_base_url("https://example.com/api/") == "https://example.com/api"


def test_normalize_base_url_rejects_invalid_values_and_schemes():
    for value in (None, ""):
        try:
            normalize_base_url(value)  # type: ignore[arg-type]
        except ValueError as error:
            assert "non-empty string" in str(error)
        else:
            raise AssertionError("Expected ValueError for invalid base_url")

    try:
        normalize_base_url("file:///tmp/model")
    except ValueError as error:
        assert "Unsupported base_url scheme" in str(error)
    else:
        raise AssertionError("Expected ValueError for unsupported base_url scheme")


def test_build_openai_compatible_url_appends_the_expected_path():
    assert build_openai_compatible_url("http://localhost:1234") == "http://localhost:1234/v1/chat/completions"
    assert build_openai_compatible_url("http://localhost:1234/v1") == "http://localhost:1234/v1/chat/completions"
    assert (
        build_openai_compatible_url("http://localhost:1234/v1/chat/completions")
        == "http://localhost:1234/v1/chat/completions"
    )


def test_build_openai_compatible_payload_is_deterministic_and_prompt_only():
    payload = build_openai_compatible_payload("write a diff", model="gpt-4o-mini")

    assert payload["model"] == "gpt-4o-mini"
    assert payload["temperature"] == 0
    assert payload["messages"] == [
        {
            "role": "system",
            "content": "Return only a unified diff patch. No prose, no markdown wrappers.",
        },
        {
            "role": "user",
            "content": "write a diff",
        },
    ]
    assert "api_key" not in payload


def test_build_openai_compatible_payload_uses_placeholder_model_when_missing():
    payload = build_openai_compatible_payload("prompt text")

    assert payload["model"] == "strata-configured-model"


def test_extract_text_from_openai_compatible_response_returns_message_content():
    response = {
        "choices": [
            {
                "message": {
                    "content": "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n",
                }
            }
        ]
    }

    result = extract_text_from_openai_compatible_response(response)

    assert result == {
        "status": "ok",
        "text": "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n",
        "errors": [],
        "message": "Response text extracted.",
    }


def test_extract_text_from_openai_compatible_response_rejects_missing_content():
    result = extract_text_from_openai_compatible_response({"choices": []})

    assert result["status"] == "invalid_response"
    assert result["text"] == ""
    assert result["errors"]


def test_extract_patch_from_text_prefers_fenced_diff_blocks():
    text = (
        "Here is the patch:\n"
        "```diff\n"
        "diff --git a/main.py b/main.py\n"
        "--- a/main.py\n"
        "+++ b/main.py\n"
        "@@ -1 +1 @@\n"
        "-print('old')\n"
        "+print('new')\n"
        "```\n"
        "Thanks!\n"
    )

    result = extract_patch_from_text(text)

    assert result["status"] == "ok"
    assert result["patch"] == (
        "diff --git a/main.py b/main.py\n"
        "--- a/main.py\n"
        "+++ b/main.py\n"
        "@@ -1 +1 @@\n"
        "-print('old')\n"
        "+print('new')"
    )


def test_extract_patch_from_text_accepts_plain_diff_text():
    text = (
        "diff --git a/main.py b/main.py\n"
        "--- a/main.py\n"
        "+++ b/main.py\n"
        "@@ -1 +1 @@\n"
        "-print('old')\n"
        "+print('new')\n"
    )

    result = extract_patch_from_text(text)

    assert result["status"] == "ok"
    assert result["patch"].startswith("diff --git a/main.py b/main.py")


def test_extract_patch_from_text_returns_invalid_response_when_no_diff_is_present():
    result = extract_patch_from_text("write a better README")

    assert result == {
        "status": "invalid_response",
        "patch": "",
        "errors": ["Unified diff patch was not found in the provided text."],
        "message": "Unified diff patch was not found in the provided text.",
    }


def test_build_http_contract_summary_reports_request_and_response_shapes():
    result = build_http_contract_summary(
        {
            "adapter": "openai_compatible_http",
            "base_url": "http://localhost:1234/v1/",
            "model": "gpt-4o-mini",
            "api_key_env": "OPENAI_API_KEY",
            "http_timeout_seconds": 90,
        },
        prompt_exists=True,
    )

    assert result["status"] == "ok"
    assert result["message"] == "HTTP request/response contract is available locally; network execution is not implemented yet."
    assert result["adapter"] == "openai_compatible_http"
    assert result["adapter_family"] == "http"
    assert result["base_url"] == "http://localhost:1234/v1"
    assert result["request_url"] == "http://localhost:1234/v1/chat/completions"
    assert result["model"] == "gpt-4o-mini"
    assert result["api_key_env"] == "OPENAI_API_KEY"
    assert result["http_timeout_seconds"] == 90
    assert result["prompt_exists"] is True
    assert result["response_text_path"] == "choices[0].message.content"
    assert result["request_payload"]["messages"][1]["content"] == "[prompt text from .aidc/agent_prompt.md]"
    assert result["errors"] == []


def test_build_http_contract_summary_reports_missing_base_url():
    result = build_http_contract_summary({"adapter": "ollama"}, prompt_exists=False)

    assert result["status"] == "not_ready"
    assert result["request_url"] is None
    assert result["errors"] == ["base_url is required for HTTP adapters."]


TESTS = [
    test_http_contract_shim_exports_new_implementation_objects,
    test_normalize_base_url_strips_trailing_slashes_and_preserves_scheme,
    test_normalize_base_url_rejects_invalid_values_and_schemes,
    test_build_openai_compatible_url_appends_the_expected_path,
    test_build_openai_compatible_payload_is_deterministic_and_prompt_only,
    test_build_openai_compatible_payload_uses_placeholder_model_when_missing,
    test_extract_text_from_openai_compatible_response_returns_message_content,
    test_extract_text_from_openai_compatible_response_rejects_missing_content,
    test_extract_patch_from_text_prefers_fenced_diff_blocks,
    test_extract_patch_from_text_accepts_plain_diff_text,
    test_extract_patch_from_text_returns_invalid_response_when_no_diff_is_present,
    test_build_http_contract_summary_reports_request_and_response_shapes,
    test_build_http_contract_summary_reports_missing_base_url,
]
