from pathlib import Path
from unittest.mock import patch

import strata.core.angular_component_links as angular_component_links
from strata.core.angular_component_links import infer_angular_component_links
from strata.core.frontend_relationships import RELATIONSHIP_TYPES


def _source(metadata: str) -> str:
    return f"""
import {{ Component }} from '@angular/core';

@Component({{
  selector: 'app-orders',
  {metadata}
}})
export class OrdersComponent {{}}
"""


def _links(metadata: str, source_path: str = "src/app/orders/orders.component.ts", **kwargs):
    return infer_angular_component_links(source_path, _source(metadata), **kwargs)


def _by_type(relationships, relationship_type: str):
    return [item for item in relationships if item.relationship_type == relationship_type]


def test_external_template_url_creates_component_template_relationship():
    relationships = _links("templateUrl: './orders.component.html',")

    assert len(relationships) == 1
    relationship = relationships[0]
    assert relationship.framework == "angular"
    assert relationship.relationship_type == "component_template"
    assert relationship.source_path == "src/app/orders/orders.component.ts"
    assert relationship.target_path == "src/app/orders/orders.component.html"
    assert relationship.target_symbol is None
    assert relationship.confidence == "high"
    assert relationship.relationship_type in RELATIONSHIP_TYPES
    assert "templateUrl" in relationship.evidence[0]


def test_external_style_url_creates_component_style_relationship():
    relationships = _links("styleUrl: './orders.component.css',")

    assert len(relationships) == 1
    relationship = relationships[0]
    assert relationship.framework == "angular"
    assert relationship.relationship_type == "component_style"
    assert relationship.target_path == "src/app/orders/orders.component.css"
    assert relationship.confidence == "high"


def test_external_style_urls_creates_one_relationship_per_style_file():
    relationships = _links(
        "styleUrls: ['./orders.component.css', './orders.component.scss'],"
    )

    assert [item.target_path for item in relationships] == [
        "src/app/orders/orders.component.css",
        "src/app/orders/orders.component.scss",
    ]
    assert {item.relationship_type for item in relationships} == {"component_style"}


def test_inline_template_creates_component_template_relationship_without_target_path():
    relationships = _links("template: `<button>Save</button>`,")

    assert len(relationships) == 1
    relationship = relationships[0]
    assert relationship.relationship_type == "component_template"
    assert relationship.target_path is None
    assert relationship.target_symbol == "inline template"
    assert "inline template" in relationship.reason
    assert relationship.confidence == "high"


def test_inline_styles_creates_component_style_relationship_without_target_path():
    relationships = _links("styles: [`.save { color: red; }`],")

    assert len(relationships) == 1
    relationship = relationships[0]
    assert relationship.relationship_type == "component_style"
    assert relationship.target_path is None
    assert relationship.target_symbol == "inline styles"
    assert "inline styles" in relationship.reason
    assert relationship.confidence == "high"


def test_malformed_metadata_degrades_with_warning_not_crash():
    relationships = _links("templateUrl: , styleUrls: [,")

    assert len(relationships) == 2
    assert {item.relationship_type for item in relationships} == {
        "component_template",
        "component_style",
    }
    assert {item.confidence for item in relationships} == {"low"}
    assert all(item.warnings for item in relationships)
    assert all(item.target_path is None for item in relationships)


def test_relative_target_paths_normalize_deterministically():
    relationships = infer_angular_component_links(
        r"src\app\orders\orders.component.ts",
        _source(
            """
            templateUrl: '../shared/orders.component.html',
            styleUrls: ['./styles/../orders.component.css'],
            """
        ),
    )

    assert [item.target_path for item in relationships] == [
        "src/app/orders/orders.component.css",
        "src/app/shared/orders.component.html",
    ]


def test_traversal_target_paths_warn_safely_when_repo_root_is_provided():
    relationships = _links(
        "templateUrl: '../../../../outside.html',",
        repo_root="D:/AI-PROJECT/strata",
    )

    relationship = relationships[0]
    assert relationship.relationship_type == "component_template"
    assert relationship.target_path is None
    assert relationship.target_symbol == "unresolved templateUrl"
    assert relationship.confidence == "low"
    assert any("outside the repository" in warning for warning in relationship.warnings)
    assert any("repo_root" in warning for warning in relationship.warnings)


def test_absolute_target_paths_warn_safely_when_repo_root_is_provided():
    relationships = _links(
        "styleUrl: 'C:/tmp/orders.component.css',",
        repo_root="D:/AI-PROJECT/strata",
    )

    relationship = relationships[0]
    assert relationship.relationship_type == "component_style"
    assert relationship.target_path is None
    assert relationship.target_symbol == "unresolved styleUrl"
    assert relationship.confidence == "low"
    assert any(
        "not a repository-relative target" in warning
        for warning in relationship.warnings
    )


def test_relationship_output_uses_j1_contract_shape_and_constants():
    relationships = _links(
        """
        templateUrl: './orders.component.html',
        styleUrls: ['./orders.component.css'],
        """
    )
    payloads = [relationship.to_dict() for relationship in relationships]

    assert [payload["framework"] for payload in payloads] == ["angular", "angular"]
    assert {payload["relationship_type"] for payload in payloads} == {
        "component_template",
        "component_style",
    }
    assert all(payload["relationship_type"] in RELATIONSHIP_TYPES for payload in payloads)
    assert all(
        payload["source_path"] == "src/app/orders/orders.component.ts"
        for payload in payloads
    )


def test_helper_does_not_scan_or_read_paths():
    with (
        patch("builtins.open", side_effect=AssertionError("opened a path")),
        patch.object(Path, "read_text", side_effect=AssertionError("read a path")),
        patch.object(Path, "stat", side_effect=AssertionError("statted a path")),
    ):
        relationships = _links("templateUrl: './orders.component.html',")

    assert relationships[0].target_path == "src/app/orders/orders.component.html"


def test_module_does_not_expose_route_react_module_federation_or_workspace_apis():
    forbidden_fragments = (
        "route",
        "react",
        "federation",
        "workspace",
        "package",
        "tsconfig",
    )
    public_names = {
        name
        for name in dir(angular_component_links)
        if not name.startswith("_")
    }

    assert not {
        name
        for name in public_names
        if any(fragment in name.lower() for fragment in forbidden_fragments)
    }


def test_missing_component_decorator_returns_empty_tuple():
    assert infer_angular_component_links(
        "src/app/orders/orders.component.ts",
        "export class OrdersComponent {}",
    ) == ()


TESTS = [
    test_external_template_url_creates_component_template_relationship,
    test_external_style_url_creates_component_style_relationship,
    test_external_style_urls_creates_one_relationship_per_style_file,
    test_inline_template_creates_component_template_relationship_without_target_path,
    test_inline_styles_creates_component_style_relationship_without_target_path,
    test_malformed_metadata_degrades_with_warning_not_crash,
    test_relative_target_paths_normalize_deterministically,
    test_traversal_target_paths_warn_safely_when_repo_root_is_provided,
    test_absolute_target_paths_warn_safely_when_repo_root_is_provided,
    test_relationship_output_uses_j1_contract_shape_and_constants,
    test_helper_does_not_scan_or_read_paths,
    test_module_does_not_expose_route_react_module_federation_or_workspace_apis,
    test_missing_component_decorator_returns_empty_tuple,
]
