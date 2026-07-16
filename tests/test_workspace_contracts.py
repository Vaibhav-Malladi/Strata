import json
from pathlib import Path

import strata.utils.config as workflow_config
import strata.utils.workspace_contracts as contracts
import strata.utils.workspace_discovery as workspace_discovery
import strata.utils.workspace_references as workspace_references
import strata.utils.workspace_relationships as workspace_relationships


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _workspace(shared_contracts):
    return {
        "schema_version": 1,
        "name": "example",
        "repositories": [
            {"id": "frontend", "path": ".", "role": "frontend"},
            {"id": "backend", "path": "../backend", "role": "backend"},
        ],
        "shared_contracts": shared_contracts,
    }


def _contract(**overrides):
    values = {
        "name": "auth-header",
        "contract_type": "auth_header",
        "expected_value": "Authorization",
        "locations": [
            {"repository_id": "frontend", "path": "src/constants.ts", "symbol": "AUTH_HEADER"},
            {"repository_id": "backend", "path": "app/constants.py", "symbol": "AUTH_HEADER"},
        ],
        "severity": "error",
        "normalization": "exact",
    }
    values.update(overrides)
    return values


def _reference(
    repository_id="frontend",
    source_path="src/constants.ts",
    reference_type="shared_constant",
    value="Authorization",
    symbol="AUTH_HEADER",
    metadata=None,
    confidence_score=0.8,
):
    return workspace_references.WorkspaceReference(
        repository_id=repository_id,
        source_path=source_path,
        reference_type=reference_type,
        raw_value=value,
        normalized_value=value,
        confidence="high" if confidence_score >= 0.7 else "medium" if confidence_score >= 0.4 else "low",
        confidence_score=confidence_score,
        symbol=symbol,
        metadata=metadata or {},
    )


def _compare(shared_contracts, refs=(), **kwargs):
    return contracts.compare_shared_contracts(_workspace(shared_contracts), refs, **kwargs)


def _payload(result):
    return result.to_dict()


def _finding(result, index=0):
    return _payload(result)["contract_findings"][index]


def _location(result, repository_id="frontend"):
    for item in _finding(result)["location_findings"]:
        if item["repository_id"] == repository_id:
            return item
    raise AssertionError(f"location not found: {repository_id}")


def _codes(result):
    return [item["code"] for item in _payload(result)["diagnostics"]]


def test_matching_value_is_consistent():
    result = _compare(
        [_contract(locations=[{"repository_id": "frontend", "path": "src/constants.ts", "symbol": "AUTH_HEADER"}])],
        [_reference()],
    )

    assert _finding(result)["status"] == "consistent"
    assert _location(result)["status"] == "consistent"


def test_mismatched_value_is_inconsistent():
    result = _compare(
        [_contract(locations=[{"repository_id": "frontend", "path": "src/constants.ts", "symbol": "AUTH_HEADER"}])],
        [_reference(value="X-Auth-Token")],
    )

    assert _finding(result)["status"] == "inconsistent"
    assert "contract_value_mismatch" in _codes(result)


def test_missing_reference_is_missing():
    result = _compare(
        [_contract(locations=[{"repository_id": "frontend", "path": "src/constants.ts", "symbol": "AUTH_HEADER"}])],
        [],
    )

    assert _finding(result)["status"] == "missing"
    assert "contract_location_missing" in _codes(result)


def test_explicit_unreadable_state_is_unreadable():
    result = _compare(
        [_contract(locations=[{"repository_id": "frontend", "path": "src/constants.ts", "symbol": "AUTH_HEADER"}])],
        [],
        location_states=[{"repository_id": "frontend", "path": "src/constants.ts", "symbol": "AUTH_HEADER", "state": "unreadable"}],
    )

    assert _finding(result)["status"] == "unreadable"
    assert "contract_location_unreadable" in _codes(result)


def test_explicit_skipped_state_is_skipped():
    result = _compare(
        [_contract(locations=[{"repository_id": "frontend", "path": "src/constants.ts", "symbol": "AUTH_HEADER"}])],
        [],
        location_states=[{"repository_id": "frontend", "path": "src/constants.ts", "symbol": "AUTH_HEADER", "state": "skipped"}],
    )

    assert _finding(result)["status"] == "skipped"


def test_shared_package_reports_unsupported():
    result = _compare(
        [
            _contract(
                name="pkg",
                contract_type="shared_package",
                expected_value="@example/shared",
                locations=[{"repository_id": "frontend", "path": "package.json", "symbol": "dependencies.@example/shared"}],
            )
        ],
        [],
    )

    assert _finding(result)["status"] == "unsupported"


def test_multiple_conflicting_observations_are_ambiguous():
    result = _compare(
        [_contract(locations=[{"repository_id": "frontend", "path": "src/constants.ts"}])],
        [_reference(symbol="AUTH_HEADER"), _reference(value="X-Auth-Token", symbol="ALT_AUTH_HEADER")],
    )

    assert _location(result)["status"] == "ambiguous"


def test_contract_type_mappings_are_supported():
    cases = [
        (_contract(name="frame", contract_type="iframe_url", expected_value="http://localhost:4201/app", normalization="url", locations=[{"repository_id": "frontend", "path": "index.html"}]), _reference(source_path="index.html", reference_type="iframe_src", value="http://localhost:4201/app", symbol=None)),
        (_contract(name="api", contract_type="api_constant", expected_value="http://localhost:8080", normalization="url", locations=[{"repository_id": "frontend", "path": ".env", "symbol": "API_URL"}]), _reference(source_path=".env", reference_type="api_base_url", value="http://localhost:8080", symbol="API_URL")),
        (_contract(name="route", contract_type="route_name", expected_value="/login", locations=[{"repository_id": "frontend", "path": "routes.ts", "symbol": "LOGIN_ROUTE"}]), _reference(source_path="routes.ts", reference_type="route_constant", value="/login", symbol="LOGIN_ROUTE")),
        (_contract(name="port", contract_type="port_number", expected_value=8080, normalization="port", locations=[{"repository_id": "frontend", "path": ".env", "symbol": "API_URL"}]), _reference(source_path=".env", reference_type="api_base_url", value="http://localhost:8080", symbol="API_URL")),
        (_contract(name="msg", contract_type="message_event", expected_value="READY", locations=[{"repository_id": "frontend", "path": "messages.ts"}]), _reference(source_path="messages.ts", reference_type="post_message_send", value="http://localhost:8080", symbol=None, metadata={"message_event": "READY"})),
        (_contract(name="listener", contract_type="message_event", expected_value="READY", locations=[{"repository_id": "frontend", "path": "listener.ts"}]), _reference(source_path="listener.ts", reference_type="message_listener", value="http://localhost:8080", symbol=None, metadata={"message_event": "READY"})),
        (_contract(name="custom", contract_type="custom", expected_value="SAME", locations=[{"repository_id": "frontend", "path": "custom.json", "symbol": "contract.value"}]), _reference(source_path="custom.json", reference_type="shared_constant", value="SAME", symbol="contract.value")),
    ]

    for contract, reference in cases:
        assert _finding(_compare([contract], [reference]))["status"] == "consistent"


def test_exact_normalization_preserves_type_distinction():
    result = _compare(
        [_contract(name="port-exact", contract_type="custom", expected_value=8080, locations=[{"repository_id": "frontend", "path": "custom.json", "symbol": "PORT"}])],
        [_reference(source_path="custom.json", value="8080", symbol="PORT")],
    )

    assert _finding(result)["status"] == "inconsistent"


def test_case_insensitive_and_trimmed_normalization():
    case_result = _compare(
        [_contract(name="event", contract_type="message_event", expected_value="login_complete", normalization="case_insensitive", locations=[{"repository_id": "frontend", "path": "messages.ts"}])],
        [_reference(source_path="messages.ts", reference_type="post_message_send", value="*", symbol=None, metadata={"message_event": "LOGIN_COMPLETE"})],
    )
    trim_result = _compare(
        [_contract(name="route", contract_type="route_name", expected_value="  /login  ", normalization="trimmed", locations=[{"repository_id": "frontend", "path": "routes.ts", "symbol": "LOGIN_ROUTE"}])],
        [_reference(source_path="routes.ts", reference_type="route_constant", value="/login", symbol="LOGIN_ROUTE")],
    )

    assert _finding(case_result)["status"] == "consistent"
    assert _finding(trim_result)["status"] == "consistent"


def test_url_normalization_reuses_q4_loopback_behaviour():
    result = _compare(
        [_contract(name="api", contract_type="api_constant", expected_value="http://localhost:8080/api", normalization="url", locations=[{"repository_id": "frontend", "path": ".env", "symbol": "API_URL"}])],
        [_reference(source_path=".env", reference_type="api_base_url", value="http://[::1]:8080/api", symbol="API_URL")],
    )

    assert _finding(result)["status"] == "consistent"


def test_port_normalization_accepts_valid_values_and_rejects_invalid():
    valid = _compare(
        [_contract(name="port", contract_type="port_number", expected_value="8080", normalization="port", locations=[{"repository_id": "frontend", "path": ".env", "symbol": "PORT"}])],
        [_reference(source_path=".env", reference_type="shared_constant", value="8080", symbol="PORT")],
    )
    boolean = _compare(
        [_contract(name="bad-bool", contract_type="port_number", expected_value=True, normalization="port", locations=[{"repository_id": "frontend", "path": ".env", "symbol": "PORT"}])],
        [_reference(source_path=".env", reference_type="shared_constant", value="8080", symbol="PORT")],
    )
    zero = _compare(
        [_contract(name="bad-zero", contract_type="port_number", expected_value=0, normalization="port", locations=[{"repository_id": "frontend", "path": ".env", "symbol": "PORT"}])],
        [_reference(source_path=".env", reference_type="shared_constant", value="8080", symbol="PORT")],
    )
    high = _compare(
        [_contract(name="bad-high", contract_type="port_number", expected_value=65536, normalization="port", locations=[{"repository_id": "frontend", "path": ".env", "symbol": "PORT"}])],
        [_reference(source_path=".env", reference_type="shared_constant", value="8080", symbol="PORT")],
    )

    assert _finding(valid)["status"] == "consistent"
    assert "contract_expected_value_unsupported" in _codes(boolean)
    assert "contract_expected_value_unsupported" in _codes(zero)
    assert "contract_expected_value_unsupported" in _codes(high)


def test_invalid_url_reports_diagnostic():
    result = _compare(
        [_contract(name="api", contract_type="api_constant", expected_value="not-a-url", normalization="url", locations=[{"repository_id": "frontend", "path": ".env", "symbol": "API_URL"}])],
        [_reference(source_path=".env", reference_type="api_base_url", value="http://localhost:8080", symbol="API_URL")],
    )

    assert "contract_expected_value_unsupported" in _codes(result)


def test_matching_requires_repository_path_and_symbol_rules():
    contract = _contract(locations=[{"repository_id": "frontend", "path": "src/constants.ts", "symbol": "AUTH_HEADER"}])
    wrong_repo = _compare([contract], [_reference(repository_id="backend", source_path="src/constants.ts")])
    wrong_path = _compare([contract], [_reference(source_path="src/other.ts")])
    wrong_symbol = _compare([contract], [_reference(symbol="OTHER_HEADER")])
    path_only = _compare([_contract(locations=[{"repository_id": "frontend", "path": "src/constants.ts"}])], [_reference(symbol="AUTH_HEADER")])

    assert _finding(wrong_repo)["status"] == "missing"
    assert _finding(wrong_path)["status"] == "missing"
    assert _finding(wrong_symbol)["status"] == "missing"
    assert _finding(path_only)["status"] == "consistent"


def test_duplicate_observations_dedupe_same_value():
    result = _compare(
        [_contract(locations=[{"repository_id": "frontend", "path": "src/constants.ts"}])],
        [_reference(symbol="AUTH_HEADER"), _reference(symbol="AUTH_HEADER")],
    )

    assert _location(result)["status"] == "consistent"
    assert _location(result)["normalized_observed_values"] == ["Authorization"]


def test_allowed_values_and_cross_location_rules():
    allowed_same = _compare(
        [_contract(expected_value="Authorization", allowed_values=["X-Authorization", "X-Authorization"], locations=[{"repository_id": "frontend", "path": "src/constants.ts", "symbol": "AUTH_HEADER"}])],
        [_reference(value="X-Authorization")],
    )
    allowed_disagree = _compare(
        [_contract(allowed_values=["X-Authorization"])],
        [_reference(value="Authorization"), _reference(repository_id="backend", source_path="app/constants.py", value="X-Authorization")],
    )

    assert _finding(allowed_same)["status"] == "consistent"
    assert _finding(allowed_same)["allowed_values"] == ["X-Authorization"]
    assert _finding(allowed_disagree)["status"] == "inconsistent"
    assert "contract_cross_location_mismatch" in _codes(allowed_disagree)


def test_location_state_matching_uses_repository_path_and_symbol():
    result = _compare(
        [_contract(locations=[{"repository_id": "frontend", "path": "src/constants.ts", "symbol": "AUTH_HEADER"}])],
        [],
        location_states=[{"repository_id": "frontend", "path": "src/constants.ts", "symbol": "OTHER", "state": "unsupported"}],
    )

    assert _finding(result)["status"] == "missing"


def test_severity_influences_mismatch_diagnostics():
    error = _compare([_contract(severity="error", locations=[{"repository_id": "frontend", "path": "src/constants.ts", "symbol": "AUTH_HEADER"}])], [_reference(value="Nope")])
    warning = _compare([_contract(name="warn", severity="warning", locations=[{"repository_id": "frontend", "path": "src/constants.ts", "symbol": "AUTH_HEADER"}])], [_reference(value="Nope")])
    info = _compare([_contract(name="info", severity="info", locations=[{"repository_id": "frontend", "path": "src/constants.ts", "symbol": "AUTH_HEADER"}])], [_reference(value="Nope")])

    assert next(item for item in _payload(error)["diagnostics"] if item["code"] == "contract_value_mismatch")["severity"] == "error"
    assert next(item for item in _payload(warning)["diagnostics"] if item["code"] == "contract_value_mismatch")["severity"] == "warning"
    assert next(item for item in _payload(info)["diagnostics"] if item["code"] == "contract_value_mismatch")["severity"] == "info"


def test_sensitive_values_are_redacted_but_auth_header_is_not_secret():
    secret = _compare(
        [_contract(name="api-token", contract_type="custom", expected_value="abcdefghijklmnopqrstuvwxyz1234567890", locations=[{"repository_id": "frontend", "path": "secret.env", "symbol": "API_TOKEN"}])],
        [_reference(source_path="secret.env", value="abcdefghijklmnopqrstuvwxyz1234567890", symbol="API_TOKEN")],
    )
    normal = _compare(
        [_contract(name="auth-header", locations=[{"repository_id": "frontend", "path": "src/constants.ts", "symbol": "AUTH_HEADER"}])],
        [_reference()],
    )

    assert _finding(secret)["expected_value"] == "[redacted]"
    assert _finding(secret)["status"] == "unsupported"
    assert "sensitive_contract_value_redacted" in _codes(secret)
    assert _finding(normal)["expected_value"] == "Authorization"


def test_caps_and_deterministic_serialization():
    workspace_contracts = [
        _contract(name="b", locations=[{"repository_id": "frontend", "path": "src/constants.ts", "symbol": "AUTH_HEADER"}]),
        _contract(name="a", locations=[{"repository_id": "frontend", "path": "src/constants.ts", "symbol": "AUTH_HEADER"}]),
    ]
    first = _payload(_compare(workspace_contracts, [_reference()], max_findings=1, max_evidence_per_contract_finding=1, max_diagnostics=3))
    second = _payload(_compare(list(reversed(workspace_contracts)), [_reference()], max_findings=1, max_evidence_per_contract_finding=1, max_diagnostics=3))

    assert first == second
    assert list(first) == list(contracts.RESULT_FIELD_ORDER)
    assert list(first["contract_findings"][0]) == list(contracts.CONTRACT_FINDING_FIELD_ORDER)
    assert list(first["contract_findings"][0]["location_findings"][0]) == list(contracts.LOCATION_FINDING_FIELD_ORDER)
    assert json.loads(json.dumps(first, allow_nan=False)) == first


def test_duplicate_contract_and_location_diagnostics():
    result = _compare(
        [
            _contract(name="dup", expected_value="Authorization"),
            _contract(name="dup", expected_value="X-Authorization"),
        ],
        [_reference(), _reference(repository_id="backend", source_path="app/constants.py")],
    )
    duplicate_location = _compare(
        [_contract(locations=[{"repository_id": "frontend", "path": "src/constants.ts", "symbol": "AUTH_HEADER"}, {"repository_id": "frontend", "path": "src/constants.ts", "symbol": "AUTH_HEADER"}])],
        [_reference()],
    )

    assert "duplicate_contract_name" in _codes(result)
    assert "duplicate_contract_location" in _codes(duplicate_location)


def test_q1_q2_q3_q4_compatibility():
    workspace = _workspace([_contract()])
    normalized = workflow_config.validate_config({"workspace": workspace})
    evidence = workspace_discovery.WorkspaceDiscoveryEvidence(
        signal_type="local_path_reference",
        source_path="package.json",
        summary="package.json references local dependency.",
        strength="strong",
        referenced_path="../backend",
    )
    relationship_assessment = workspace_relationships.build_workspace_relationship_assessment(workspace)
    reference = _reference()

    assert normalized["workspace"]["shared_contracts"][0]["name"] == "auth-header"
    assert evidence.to_dict()["referenced_path"] == "../backend"
    assert relationship_assessment.to_dict()["role_assessments"]
    assert reference.to_dict()["reference_type"] == "shared_constant"


def test_scanner_compatible_imports_and_architecture_boundary():
    source = (PROJECT_ROOT / "strata" / "utils" / "workspace_contracts.py").read_text(
        encoding="utf-8"
    )

    assert "import strata.utils.workspace_config as workspace_config" in source
    assert "import strata.utils.workspace_references as workspace_references" in source
    assert "from strata.utils import" not in source
    assert "strata.commands" not in source
    assert "strata.core" not in source


def test_workspace_q5_docs_define_contract_only_scope():
    content = (PROJECT_ROOT / "docs" / "roadmap" / "workspace-intelligence.md").read_text(
        encoding="utf-8"
    )

    assert "Q5" in content
    assert "shared-contract comparison" in content
    assert "location-level and contract-level findings" in content
    assert "Q5 reads no files directly" in content
    assert "Q5 does not build a dependency graph" in content
    assert "does not add findings to AI context" in content


TESTS = [
    test_matching_value_is_consistent,
    test_mismatched_value_is_inconsistent,
    test_missing_reference_is_missing,
    test_explicit_unreadable_state_is_unreadable,
    test_explicit_skipped_state_is_skipped,
    test_shared_package_reports_unsupported,
    test_multiple_conflicting_observations_are_ambiguous,
    test_contract_type_mappings_are_supported,
    test_exact_normalization_preserves_type_distinction,
    test_case_insensitive_and_trimmed_normalization,
    test_url_normalization_reuses_q4_loopback_behaviour,
    test_port_normalization_accepts_valid_values_and_rejects_invalid,
    test_invalid_url_reports_diagnostic,
    test_matching_requires_repository_path_and_symbol_rules,
    test_duplicate_observations_dedupe_same_value,
    test_allowed_values_and_cross_location_rules,
    test_location_state_matching_uses_repository_path_and_symbol,
    test_severity_influences_mismatch_diagnostics,
    test_sensitive_values_are_redacted_but_auth_header_is_not_secret,
    test_caps_and_deterministic_serialization,
    test_duplicate_contract_and_location_diagnostics,
    test_q1_q2_q3_q4_compatibility,
    test_scanner_compatible_imports_and_architecture_boundary,
    test_workspace_q5_docs_define_contract_only_scope,
]
