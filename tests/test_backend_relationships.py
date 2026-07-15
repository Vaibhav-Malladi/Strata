import json
from importlib import import_module

from strata.core.backend_relationships import (
    BACKEND_CONFIDENCE_VALUES,
    BACKEND_FRAMEWORKS,
    BACKEND_FRAMEWORK_PLACEHOLDERS,
    BACKEND_RELATIONSHIP_FIELD_ORDER,
    BACKEND_RELATIONSHIP_TYPES,
    HTTP_METHODS,
    BackendRelationship,
    backend_relationship_to_dict,
    create_backend_relationship,
    group_backend_relationships_by_framework,
    group_backend_relationships_by_relationship_type,
    group_backend_relationships_by_route_path,
    group_backend_relationships_by_source_path,
    merge_backend_relationships,
    sort_backend_relationships,
)
from strata.core.stage_report import CONFIDENCE_LEVELS


backend = import_module("strata.core.backend_relationships")


def _relationship(**overrides):
    values = {
        "framework": "fastapi",
        "relationship_type": "route_handler",
        "source_path": "app/api/users.py",
        "target_path": "app/services/users.py",
        "target_symbol": "UserService",
        "route_path": "/users/{user_id}",
        "http_method": "GET",
        "handler_symbol": "get_user",
        "service_symbol": "UserService",
        "model_symbol": "User",
        "confidence": "high",
        "evidence": ("route decorator reserved for future extractor",),
        "warnings": (),
        "reason": "contract fixture",
    }
    values.update(overrides)
    return create_backend_relationship(**values)


def _expect_error(error_type, function, *args, contains: str, **kwargs):
    try:
        function(*args, **kwargs)
    except error_type as error:
        assert contains in str(error)
    else:
        raise AssertionError(f"Expected {error_type.__name__}")


def test_relationship_type_constants_are_stable():
    assert BACKEND_RELATIONSHIP_TYPES == (
        "backend_route",
        "route_handler",
        "handler_service",
        "service_repository",
        "service_model",
        "route_schema",
        "route_middleware",
        "route_auth_guard",
        "route_external_api",
        "route_database_access",
        "backend_internal_library_usage",
    )


def test_framework_constants_are_stable_and_have_extraction_placeholders():
    assert BACKEND_FRAMEWORKS == (
        "fastapi",
        "flask",
        "django",
        "django_rest_framework",
        "express",
        "nestjs",
        "go",
        "generic_backend",
        "unknown",
    )
    assert BACKEND_FRAMEWORK_PLACEHOLDERS == (
        ("fastapi", "reserved_for_k3_fastapi"),
        ("flask", "reserved_for_k4_flask"),
        ("django", "reserved_for_k5_django"),
        ("django_rest_framework", "reserved_for_k5_drf"),
        ("express", "reserved_for_k6_express"),
        ("nestjs", "reserved_for_k7_nestjs"),
        ("go", "reserved_for_k8_k9_go"),
    )


def test_http_method_constants_are_stable():
    assert HTTP_METHODS == (
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "OPTIONS",
        "HEAD",
        "ANY",
        "unknown",
    )


def test_confidence_constants_mirror_shared_vocabulary():
    assert BACKEND_CONFIDENCE_VALUES == ("unknown", "low", "medium", "high")
    assert BACKEND_CONFIDENCE_VALUES is CONFIDENCE_LEVELS


def test_backend_relationship_dict_output_is_deterministic_and_json_ready():
    payload = _relationship(source_path="app\\api\\users.py").to_dict()

    assert isinstance(_relationship(), BackendRelationship)
    assert list(payload) == list(BACKEND_RELATIONSHIP_FIELD_ORDER)
    assert payload == {
        "framework": "fastapi",
        "relationship_type": "route_handler",
        "source_path": "app/api/users.py",
        "target_path": "app/services/users.py",
        "target_symbol": "UserService",
        "route_path": "/users/{user_id}",
        "http_method": "GET",
        "handler_symbol": "get_user",
        "service_symbol": "UserService",
        "model_symbol": "User",
        "confidence": "high",
        "evidence": ["route decorator reserved for future extractor"],
        "warnings": [],
        "reason": "contract fixture",
    }
    assert backend_relationship_to_dict(_relationship()) == _relationship().to_dict()
    assert json.loads(json.dumps(payload, allow_nan=False)) == payload


def test_unknown_and_low_confidence_relationships_preserve_reason_and_warnings():
    relationship = _relationship(
        framework="unknown",
        relationship_type="backend_route",
        target_path=None,
        target_symbol=None,
        route_path=None,
        http_method="unknown",
        handler_symbol=None,
        service_symbol=None,
        model_symbol=None,
        confidence="low",
        evidence=(),
        warnings=("route source is approximate",),
        reason="path-only backend hint",
    )

    assert relationship.to_dict()["confidence"] == "low"
    assert relationship.to_dict()["warnings"] == ["route source is approximate"]
    assert relationship.to_dict()["reason"] == "path-only backend hint"


def test_invalid_enum_values_are_rejected():
    _expect_error(ValueError, _relationship, framework="rails", contains="framework")
    _expect_error(
        ValueError,
        _relationship,
        relationship_type="controller_action",
        contains="relationship_type",
    )
    _expect_error(ValueError, _relationship, http_method="TRACE", contains="http_method")
    _expect_error(ValueError, _relationship, confidence="certain", contains="confidence")


def test_ordering_helper_is_deterministic():
    third = _relationship(
        source_path="z/api.py",
        route_path="/z",
        http_method="POST",
    )
    first = _relationship(
        source_path="a/api.py",
        route_path="/z",
        http_method="POST",
    )
    second = _relationship(
        source_path="a/api.py",
        route_path="/a",
        http_method="GET",
    )

    assert sort_backend_relationships((third, first, second)) == (
        second,
        first,
        third,
    )
    assert merge_backend_relationships((third, first, second, first)) == (
        second,
        first,
        third,
    )


def test_grouping_helpers_are_deterministic():
    fastapi = _relationship(source_path="b/routes.py", route_path="/b")
    express = _relationship(
        framework="express",
        relationship_type="route_middleware",
        source_path="a/routes.ts",
        target_path="a/auth.ts",
        route_path="/a",
        http_method="ANY",
    )
    unknown_route = _relationship(
        framework="unknown",
        relationship_type="backend_internal_library_usage",
        source_path="c/lib.py",
        target_path=None,
        route_path=None,
        http_method="unknown",
    )
    relationships = (fastapi, express, unknown_route)

    assert list(group_backend_relationships_by_source_path(relationships)) == [
        "a/routes.ts",
        "b/routes.py",
        "c/lib.py",
    ]
    assert list(group_backend_relationships_by_route_path(relationships)) == [
        "/a",
        "/b",
        "unknown",
    ]
    assert list(group_backend_relationships_by_relationship_type(relationships)) == [
        "backend_internal_library_usage",
        "route_handler",
        "route_middleware",
    ]
    assert list(group_backend_relationships_by_framework(relationships)) == [
        "express",
        "fastapi",
        "unknown",
    ]


def test_module_does_not_expose_framework_parser_scanner_or_detector_apis_yet():
    public_names = tuple(name for name in dir(backend) if not name.startswith("_"))
    forbidden_words = ("parse", "parser", "scan", "scanner", "detect", "detector")

    assert not [
        name
        for name in public_names
        if any(word in name.lower() for word in forbidden_words)
    ]


def test_docs_mention_k1_contract_only_and_later_k_work():
    with open(
        "docs/roadmap/backend-intelligence-foundation.md",
        encoding="utf-8",
    ) as handle:
        content = handle.read()

    assert "K1 is contract-only" in content
    assert "does not implement framework detection or extraction" in content
    assert "Go backend services" in content
    assert "standard net/http and common router patterns later" in content
    for item in ("K2", "K3", "K4", "K5", "K6", "K7", "K8", "K9", "K10"):
        assert item in content


TESTS = [
    test_relationship_type_constants_are_stable,
    test_framework_constants_are_stable_and_have_extraction_placeholders,
    test_http_method_constants_are_stable,
    test_confidence_constants_mirror_shared_vocabulary,
    test_backend_relationship_dict_output_is_deterministic_and_json_ready,
    test_unknown_and_low_confidence_relationships_preserve_reason_and_warnings,
    test_invalid_enum_values_are_rejected,
    test_ordering_helper_is_deterministic,
    test_grouping_helpers_are_deterministic,
    test_module_does_not_expose_framework_parser_scanner_or_detector_apis_yet,
    test_docs_mention_k1_contract_only_and_later_k_work,
]
