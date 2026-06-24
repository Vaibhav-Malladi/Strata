import os

from secret_redaction import (
    looks_like_secret,
    redact_secret,
    redact_text,
    safe_env_status,
    validate_env_var_name,
)


def test_looks_like_secret_detects_common_token_shapes():
    assert looks_like_secret("sk-testsecret-123456")
    assert looks_like_secret("sk-ant-testsecret-123456")
    assert looks_like_secret("ghp_abcdefghijklmnopqrstuvwxyz123456")
    assert looks_like_secret("github_pat_abcdefghijklmnopqrstuvwxyz123456")
    assert looks_like_secret("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTYifQ.signature")


def test_redact_text_masks_embedded_secrets_and_auth_headers():
    text = redact_text(
        "\n".join(
            [
                "Authorization: Bearer sk-testsecret-123456",
                "OPENAI_API_KEY=sk-testsecret-123456",
                "token=github_pat_abcdefghijklmnopqrstuvwxyz123456",
                "plain text is preserved",
            ]
        )
    )

    assert "sk-testsecret-123456" not in text
    assert "github_pat_abcdefghijklmnopqrstuvwxyz123456" not in text
    assert "plain text is preserved" in text
    assert "<redacted>" in text


def test_redact_secret_only_changes_secret_like_values():
    assert redact_secret("sk-testsecret-123456") == "<redacted>"
    assert redact_secret("OPENAI_API_KEY") == "OPENAI_API_KEY"


def test_safe_env_status_reports_found_and_missing_without_value_leakage():
    original = os.environ.get("OPENAI_API_KEY")
    os.environ["OPENAI_API_KEY"] = "sk-testsecret-123456"
    try:
        assert safe_env_status("OPENAI_API_KEY") == "found"
        assert safe_env_status("MISSING_STRATA_ENV_VAR") == "missing"
    finally:
        if original is None:
            os.environ.pop("OPENAI_API_KEY", None)
        else:
            os.environ["OPENAI_API_KEY"] = original


def test_validate_env_var_name_accepts_only_valid_names():
    assert validate_env_var_name("OPENAI_API_KEY")
    assert validate_env_var_name("_STRATA_TOKEN")
    assert not validate_env_var_name("1INVALID")
    assert not validate_env_var_name("sk-testsecret-123456")
    assert not validate_env_var_name("")
    assert not validate_env_var_name(None)


TESTS = [
    test_looks_like_secret_detects_common_token_shapes,
    test_redact_text_masks_embedded_secrets_and_auth_headers,
    test_redact_secret_only_changes_secret_like_values,
    test_safe_env_status_reports_found_and_missing_without_value_leakage,
    test_validate_env_var_name_accepts_only_valid_names,
]
