import json
from dataclasses import dataclass

from strata.core.backend_relationships import create_backend_relationship
from strata.core.relationship_limits import (
    DEFAULT_RELATIONSHIP_LIMIT_PROFILE,
    DROP_REASON_MALFORMED_RELATIONSHIP,
    DROP_REASON_PER_FRAMEWORK_LIMIT,
    DROP_REASON_PER_SOURCE_LIMIT,
    DROP_REASON_PER_TYPE_LIMIT,
    DROP_REASON_SUMMARY_PAYLOAD_LIMIT,
    DROP_REASON_TOTAL_RELATIONSHIP_LIMIT,
    MAX_DUPLICATE_RECORDS,
    MAX_RELATIONSHIPS_PER_FRAMEWORK,
    MAX_RELATIONSHIPS_PER_SOURCE,
    MAX_RELATIONSHIPS_PER_TARGET,
    MAX_RELATIONSHIPS_PER_TYPE,
    MAX_ROUTE_PATHS,
    MAX_SUMMARY_PAYLOAD_RELATIONSHIPS,
    MAX_TOTAL_RELATIONSHIPS,
    MAX_WARNINGS,
    RELATIONSHIP_LIMIT_PROFILE_VERSION,
    RELATIONSHIP_LIMIT_STATUS_FAIL,
    RELATIONSHIP_LIMIT_STATUS_PASS,
    RELATIONSHIP_LIMIT_STATUS_WARN,
    RelationshipLimitProfile,
    apply_relationship_limits,
    bound_relationship_summary_payload,
    bound_relationship_warnings,
    count_duplicate_relationships,
    default_relationship_limit_profile,
    normalize_relationship_payload,
    sort_relationship_payloads,
)


def _relationship(**overrides):
    values = {
        "framework": "fastapi",
        "relationship_type": "route_handler",
        "source_path": "app/api/users.py",
        "target_path": "app/services/users.py",
        "route_path": "/users",
        "http_method": "GET",
        "target_symbol": "UserService",
        "handler_symbol": "get_users",
        "confidence": "high",
        "evidence": ["route literal"],
        "warnings": [],
        "reason": "test fixture",
    }
    values.update(overrides)
    return values


@dataclass
class ObjectRelationship:
    framework: str
    relationship_type: str
    source_path: str
    target_path: str


class ToDictRelationship:
    def to_dict(self):
        return _relationship(source_path="web/App.tsx", target_path="web/api.ts")


def _expect_error(error_type, function, *args, contains: str, **kwargs):
    try:
        function(*args, **kwargs)
    except error_type as error:
        assert contains in str(error)
    else:
        raise AssertionError(f"Expected {error_type.__name__}")


def test_default_limit_profile_shape_is_stable_and_json_ready():
    payload = default_relationship_limit_profile()

    assert payload == {
        "profile_version": RELATIONSHIP_LIMIT_PROFILE_VERSION,
        "profile_name": "default",
        "max_total_relationships": MAX_TOTAL_RELATIONSHIPS,
        "max_relationships_per_source": MAX_RELATIONSHIPS_PER_SOURCE,
        "max_relationships_per_target": MAX_RELATIONSHIPS_PER_TARGET,
        "max_relationships_per_framework": MAX_RELATIONSHIPS_PER_FRAMEWORK,
        "max_relationships_per_type": MAX_RELATIONSHIPS_PER_TYPE,
        "max_warnings": MAX_WARNINGS,
        "max_duplicate_records": MAX_DUPLICATE_RECORDS,
        "max_route_paths": MAX_ROUTE_PATHS,
        "max_summary_payload_relationships": MAX_SUMMARY_PAYLOAD_RELATIONSHIPS,
    }
    assert DEFAULT_RELATIONSHIP_LIMIT_PROFILE.to_dict() == payload
    assert json.loads(json.dumps(payload, allow_nan=False)) == payload


def test_invalid_negative_and_non_integer_limits_are_rejected():
    _expect_error(
        ValueError,
        RelationshipLimitProfile,
        max_total_relationships=-1,
        contains="max_total_relationships",
    )
    _expect_error(
        TypeError,
        RelationshipLimitProfile,
        max_total_relationships=1.5,
        contains="max_total_relationships",
    )
    _expect_error(
        TypeError,
        RelationshipLimitProfile,
        max_total_relationships=True,
        contains="max_total_relationships",
    )


def test_relationship_normalization_handles_dicts_and_to_dict_objects():
    dict_payload = normalize_relationship_payload(
        _relationship(source_path="app\\api\\users.py")
    )
    to_dict_payload = normalize_relationship_payload(ToDictRelationship())
    object_payload = normalize_relationship_payload(
        ObjectRelationship(
            framework="react",
            relationship_type="component_api_client",
            source_path="src/App.tsx",
            target_path="src/api.ts",
        )
    )

    assert dict_payload["source_path"] == "app/api/users.py"
    assert to_dict_payload["source_path"] == "web/App.tsx"
    assert object_payload["framework"] == "react"
    assert object_payload["http_method"] == "unknown"


def test_malformed_relationship_records_are_dropped_with_reason():
    result = apply_relationship_limits([
        _relationship(source_path="app/api/users.py"),
        {"target_path": "missing/source.py"},
    ])

    assert result["status"] == RELATIONSHIP_LIMIT_STATUS_FAIL
    assert result["total_input_count"] == 2
    assert result["total_kept_count"] == 1
    assert result["drop_reasons"][DROP_REASON_MALFORMED_RELATIONSHIP] == 1
    assert result["warnings"]


def test_deterministic_ordering_is_stable_despite_input_order():
    first = _relationship(source_path="b.py", target_path="z.py")
    second = _relationship(source_path="a.py", target_path="z.py")
    third = _relationship(source_path="a.py", target_path="a.py")

    ordered = sort_relationship_payloads([first, second, third])
    reordered = sort_relationship_payloads([third, first, second])

    assert ordered == reordered
    assert [(item["source_path"], item["target_path"]) for item in ordered] == [
        ("a.py", "a.py"),
        ("a.py", "z.py"),
        ("b.py", "z.py"),
    ]


def test_total_relationship_cap_drops_extra_records_deterministically():
    profile = RelationshipLimitProfile(
        max_total_relationships=2,
        max_summary_payload_relationships=10,
    )
    result = apply_relationship_limits(
        [
            _relationship(source_path="c.py"),
            _relationship(source_path="a.py"),
            _relationship(source_path="b.py"),
        ],
        profile=profile,
    )

    assert result["status"] == RELATIONSHIP_LIMIT_STATUS_WARN
    assert [item["source_path"] for item in result["kept_relationships"]] == [
        "a.py",
        "b.py",
    ]
    assert result["drop_reasons"][DROP_REASON_TOTAL_RELATIONSHIP_LIMIT] == 1


def test_per_source_cap_drops_extra_records_deterministically():
    profile = RelationshipLimitProfile(
        max_relationships_per_source=1,
        max_summary_payload_relationships=10,
    )
    result = apply_relationship_limits(
        [
            _relationship(source_path="a.py", target_path="z.py"),
            _relationship(source_path="a.py", target_path="a.py"),
            _relationship(source_path="b.py", target_path="a.py"),
        ],
        profile=profile,
    )

    assert [item["target_path"] for item in result["kept_relationships"]] == [
        "a.py",
        "a.py",
    ]
    assert result["drop_reasons"][DROP_REASON_PER_SOURCE_LIMIT] == 1


def test_per_framework_cap_drops_extra_records_deterministically():
    profile = RelationshipLimitProfile(
        max_relationships_per_framework=1,
        max_summary_payload_relationships=10,
    )
    result = apply_relationship_limits(
        [
            _relationship(source_path="a.py", framework="fastapi"),
            _relationship(source_path="b.py", framework="fastapi"),
            _relationship(source_path="c.py", framework="go"),
        ],
        profile=profile,
    )

    assert [item["framework"] for item in result["kept_relationships"]] == [
        "fastapi",
        "go",
    ]
    assert result["drop_reasons"][DROP_REASON_PER_FRAMEWORK_LIMIT] == 1


def test_per_type_cap_drops_extra_records_deterministically():
    profile = RelationshipLimitProfile(
        max_relationships_per_type=1,
        max_summary_payload_relationships=10,
    )
    result = apply_relationship_limits(
        [
            _relationship(source_path="a.py", relationship_type="route_handler"),
            _relationship(source_path="b.py", relationship_type="route_handler"),
            _relationship(source_path="c.py", relationship_type="handler_service"),
        ],
        profile=profile,
    )

    assert [item["relationship_type"] for item in result["kept_relationships"]] == [
        "route_handler",
        "handler_service",
    ]
    assert result["drop_reasons"][DROP_REASON_PER_TYPE_LIMIT] == 1


def test_warnings_are_bounded():
    warnings = bound_relationship_warnings(
        ["first", "second", "third", "fourth"],
        max_warnings=3,
    )

    assert warnings == ["first", "second", "...and 2 more warnings"]


def test_duplicate_relationships_are_counted():
    relationship = _relationship()
    summary = count_duplicate_relationships(
        [relationship, dict(relationship), _relationship(source_path="other.py")]
    )

    assert summary["duplicate_count"] == 1
    assert summary["duplicate_record_count"] == 1
    assert summary["duplicate_records"][0]["count"] == 2


def test_summary_payload_limit_is_enforced():
    profile = RelationshipLimitProfile(
        max_summary_payload_relationships=2,
        max_total_relationships=10,
    )
    result = apply_relationship_limits(
        [
            _relationship(source_path="c.py"),
            _relationship(source_path="a.py"),
            _relationship(source_path="b.py"),
        ],
        profile=profile,
    )
    summary = bound_relationship_summary_payload(
        [
            _relationship(source_path="c.py"),
            _relationship(source_path="a.py"),
            _relationship(source_path="b.py"),
        ],
        profile=profile,
    )

    assert result["drop_reasons"][DROP_REASON_SUMMARY_PAYLOAD_LIMIT] == 1
    assert [item["source_path"] for item in summary["relationships"]] == [
        "a.py",
        "b.py",
    ]
    assert summary["drop_reasons"][DROP_REASON_SUMMARY_PAYLOAD_LIMIT] == 1


def test_output_status_is_pass_warn_fail_deterministically():
    passing = apply_relationship_limits([_relationship()])
    warning = apply_relationship_limits(
        [_relationship(source_path="a.py"), _relationship(source_path="b.py")],
        profile=RelationshipLimitProfile(
            max_total_relationships=1,
            max_summary_payload_relationships=10,
        ),
    )
    failing = apply_relationship_limits([{"target_path": "missing/source.py"}])

    assert passing["status"] == RELATIONSHIP_LIMIT_STATUS_PASS
    assert warning["status"] == RELATIONSHIP_LIMIT_STATUS_WARN
    assert failing["status"] == RELATIONSHIP_LIMIT_STATUS_FAIL


def test_no_extractor_is_invoked_by_limit_helper():
    class ExtractorLike:
        @property
        def source_path(self):
            return "src/app.py"

        @property
        def target_path(self):
            return "src/api.py"

        @property
        def framework(self):
            return "react"

        @property
        def relationship_type(self):
            return "component_api_client"

        def extract(self):
            raise AssertionError("limit helper invoked extractor")

    result = apply_relationship_limits([ExtractorLike()])

    assert result["status"] == RELATIONSHIP_LIMIT_STATUS_PASS
    assert result["total_kept_count"] == 1


def test_backend_relationship_contract_objects_can_be_limited():
    relationship = create_backend_relationship(
        framework="go",
        relationship_type="backend_route",
        source_path="cmd/server.go",
        route_path="/health",
        http_method="GET",
        confidence="high",
        reason="go route fixture",
    )

    result = apply_relationship_limits([relationship])

    assert result["kept_relationships"][0]["framework"] == "go"
    assert result["kept_relationships"][0]["route_path"] == "/health"


def test_docs_say_l3_adds_caps_without_broad_extractor_rewrites():
    with open("docs/roadmap/performance-scale-hardening.md", encoding="utf-8") as handle:
        content = handle.read()

    assert "L3 implemented" in content
    assert "relationship caps" in content
    assert "bounded summaries" in content
    assert "Part I remains the token firewall" in content
    assert "does not expand prompt content" in content
    assert "does not yet perform broad extractor rewrites" in content


TESTS = [
    test_default_limit_profile_shape_is_stable_and_json_ready,
    test_invalid_negative_and_non_integer_limits_are_rejected,
    test_relationship_normalization_handles_dicts_and_to_dict_objects,
    test_malformed_relationship_records_are_dropped_with_reason,
    test_deterministic_ordering_is_stable_despite_input_order,
    test_total_relationship_cap_drops_extra_records_deterministically,
    test_per_source_cap_drops_extra_records_deterministically,
    test_per_framework_cap_drops_extra_records_deterministically,
    test_per_type_cap_drops_extra_records_deterministically,
    test_warnings_are_bounded,
    test_duplicate_relationships_are_counted,
    test_summary_payload_limit_is_enforced,
    test_output_status_is_pass_warn_fail_deterministically,
    test_no_extractor_is_invoked_by_limit_helper,
    test_backend_relationship_contract_objects_can_be_limited,
    test_docs_say_l3_adds_caps_without_broad_extractor_rewrites,
]
