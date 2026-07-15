import json

import strata.core.frontend_relationships as frontend_relationships
from strata.core.frontend_relationships import (
    ANGULAR_RELATIONSHIP_PLACEHOLDERS,
    CUSTOM_ELEMENT_RELATIONSHIP_PLACEHOLDERS,
    FRONTEND_FRAMEWORKS,
    INTERNAL_LIBRARY_RELATIONSHIP_PLACEHOLDERS,
    MODULE_FEDERATION_RELATIONSHIP_PLACEHOLDERS,
    REACT_RELATIONSHIP_PLACEHOLDERS,
    RELATIONSHIP_CONFIDENCES,
    RELATIONSHIP_TYPES,
    create_frontend_relationship,
    frontend_relationship_to_dict,
    group_relationships_by_source_path,
    group_relationships_by_type,
    merge_frontend_relationships,
    normalize_relative_path,
    sort_frontend_relationships,
)


def _relationship(**overrides):
    values = {
        "framework": "angular",
        "source_path": "src/app/orders/orders.component.ts",
        "target_path": "src/app/orders/orders.component.html",
        "relationship_type": "component_template",
        "confidence": "high",
        "evidence": ("templateUrl: ./orders.component.html",),
        "warnings": (),
        "reason": "Angular component metadata can reference an external template.",
    }
    values.update(overrides)
    return create_frontend_relationship(**values)


def _expect_error(error_type, function, *args, contains: str, **kwargs):
    try:
        function(*args, **kwargs)
    except error_type as error:
        assert contains in str(error)
    else:
        raise AssertionError(f"Expected {error_type.__name__}")


def test_relationship_type_constants_are_stable():
    assert RELATIONSHIP_TYPES == (
        "component_template",
        "component_style",
        "component_test",
        "component_route",
        "route_lazy_target",
        "component_child_component",
        "component_service",
        "component_api_client",
        "hook_component",
        "hook_api_client",
        "react_route_component",
        "internal_library_usage",
        "module_federation_remote",
        "custom_element_usage",
    )


def test_framework_constants_are_stable():
    assert FRONTEND_FRAMEWORKS == (
        "angular",
        "react",
        "generic_frontend",
        "unknown",
    )


def test_confidence_constants_are_stable():
    assert RELATIONSHIP_CONFIDENCES == ("high", "medium", "low", "unknown")


def test_placeholder_groups_cover_later_j_producers():
    assert "component_template" in ANGULAR_RELATIONSHIP_PLACEHOLDERS
    assert "route_lazy_target" in ANGULAR_RELATIONSHIP_PLACEHOLDERS
    assert "hook_component" in REACT_RELATIONSHIP_PLACEHOLDERS
    assert INTERNAL_LIBRARY_RELATIONSHIP_PLACEHOLDERS == ("internal_library_usage",)
    assert MODULE_FEDERATION_RELATIONSHIP_PLACEHOLDERS == (
        "module_federation_remote",
    )
    assert CUSTOM_ELEMENT_RELATIONSHIP_PLACEHOLDERS == ("custom_element_usage",)


def test_relationship_dict_output_is_deterministic_and_json_ready():
    relationship = _relationship(
        source_path=r"src\app\orders\orders.component.ts",
        evidence=(
            "templateUrl: ./orders.component.html",
            "templateUrl: ./orders.component.html",
        ),
    )

    payload = frontend_relationship_to_dict(relationship)

    assert payload == {
        "framework": "angular",
        "source_path": "src/app/orders/orders.component.ts",
        "target_path": "src/app/orders/orders.component.html",
        "target_symbol": None,
        "relationship_type": "component_template",
        "confidence": "high",
        "evidence": ["templateUrl: ./orders.component.html"],
        "warnings": [],
        "reason": "Angular component metadata can reference an external template.",
    }
    assert json.loads(json.dumps(payload, allow_nan=False)) == payload


def test_symbol_only_target_relationship_is_json_ready():
    relationship = _relationship(
        framework="react",
        target_path=None,
        target_symbol="useOrders",
        relationship_type="hook_component",
        confidence="medium",
        evidence=("import { useOrders } from './hooks/useOrders'",),
        reason="Future React linking may connect hooks to components.",
    )

    assert relationship.to_dict()["target_path"] is None
    assert relationship.to_dict()["target_symbol"] == "useOrders"


def test_unknown_and_low_confidence_relationships_preserve_reason_and_warnings():
    relationship = _relationship(
        framework="unknown",
        target_path=None,
        target_symbol="remote-admin",
        relationship_type="module_federation_remote",
        confidence="low",
        evidence=(),
        warnings=("Producer could not prove the remote target path.",),
        reason="Module federation support is a later placeholder.",
    )

    payload = relationship.to_dict()

    assert payload["confidence"] == "low"
    assert payload["reason"] == "Module federation support is a later placeholder."
    assert payload["warnings"] == ["Producer could not prove the remote target path."]


def test_bounded_values_and_invalid_targets_are_rejected():
    _expect_error(ValueError, _relationship, framework="vue", contains="framework")
    _expect_error(
        ValueError,
        _relationship,
        relationship_type="template_parser",
        contains="relationship_type",
    )
    _expect_error(ValueError, _relationship, confidence="certain", contains="confidence")
    _expect_error(
        ValueError,
        _relationship,
        target_path=None,
        target_symbol=None,
        contains="target_path or target_symbol",
    )


def test_absolute_and_escaping_paths_are_rejected():
    for path in ("/src/app.tsx", "C:\\src\\app.tsx", "../app.tsx", "src/../app.tsx"):
        _expect_error(ValueError, normalize_relative_path, path, contains="path must")


def test_ordering_helper_is_deterministic():
    style = _relationship(
        target_path="src/app/orders/orders.component.css",
        relationship_type="component_style",
    )
    child = _relationship(
        source_path="src/app/orders/order-list.component.ts",
        target_path="src/app/orders/order-row.component.ts",
        relationship_type="component_child_component",
    )
    template = _relationship()

    assert sort_frontend_relationships((style, child, template)) == (
        child,
        style,
        template,
    )
    assert merge_frontend_relationships((template, style, template)) == (
        style,
        template,
    )


def test_grouping_helpers_are_deterministic():
    template = _relationship()
    style = _relationship(
        target_path="src/app/orders/orders.component.css",
        relationship_type="component_style",
    )
    react = _relationship(
        framework="react",
        source_path="src/components/OrdersPage.tsx",
        target_path=None,
        target_symbol="useOrders",
        relationship_type="hook_component",
        confidence="medium",
        evidence=("import useOrders",),
        reason="Future React producer may populate this relationship.",
    )

    by_source = group_relationships_by_source_path((react, style, template))
    by_type = group_relationships_by_type((react, style, template))

    assert tuple(by_source) == (
        "src/app/orders/orders.component.ts",
        "src/components/OrdersPage.tsx",
    )
    assert by_source["src/app/orders/orders.component.ts"] == (style, template)
    assert tuple(by_type) == (
        "component_style",
        "component_template",
        "hook_component",
    )


def test_module_does_not_expose_parser_scanner_or_detector_apis_yet():
    forbidden_fragments = ("parse", "scan", "detect", "trace", "analyze")
    public_names = {
        name
        for name in dir(frontend_relationships)
        if not name.startswith("_")
    }

    assert not {
        name
        for name in public_names
        if any(fragment in name.lower() for fragment in forbidden_fragments)
    }


def test_roadmap_documents_j1_as_contract_only():
    with open("docs/roadmap/frontend-deep-linking.md", encoding="utf-8") as handle:
        text = " ".join(handle.read().split())

    assert "J1: Frontend Relationship Contract" in text
    assert "contract-only" in text
    assert "does not parse, scan, trace, detect, or read frontend files" in text


def test_roadmap_mentions_later_batches_without_implementing_them():
    with open("docs/roadmap/frontend-deep-linking.md", encoding="utf-8") as handle:
        text = handle.read()

    for batch in ("J2", "J3", "J4", "J5", "J6", "J7"):
        assert batch in text
    assert "Later batches may populate" in text


TESTS = [
    test_relationship_type_constants_are_stable,
    test_framework_constants_are_stable,
    test_confidence_constants_are_stable,
    test_placeholder_groups_cover_later_j_producers,
    test_relationship_dict_output_is_deterministic_and_json_ready,
    test_symbol_only_target_relationship_is_json_ready,
    test_unknown_and_low_confidence_relationships_preserve_reason_and_warnings,
    test_bounded_values_and_invalid_targets_are_rejected,
    test_absolute_and_escaping_paths_are_rejected,
    test_ordering_helper_is_deterministic,
    test_grouping_helpers_are_deterministic,
    test_module_does_not_expose_parser_scanner_or_detector_apis_yet,
    test_roadmap_documents_j1_as_contract_only,
    test_roadmap_mentions_later_batches_without_implementing_them,
]
