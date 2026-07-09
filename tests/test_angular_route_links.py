from pathlib import Path
from unittest.mock import patch

import strata.core.angular_route_links as angular_route_links
from strata.core.angular_route_links import infer_angular_route_links
from strata.core.frontend_relationships import RELATIONSHIP_TYPES


def _source(routes: str) -> str:
    return f"""
import {{ Routes }} from '@angular/router';

export const routes: Routes = [
  {routes}
];
"""


def _links(routes: str, source_path: str = "src/app/app.routes.ts", **kwargs):
    return infer_angular_route_links(source_path, _source(routes), **kwargs)


def test_component_route_creates_component_route_relationship_with_target_symbol():
    relationships = _links("{ path: 'orders', component: OrdersComponent },")

    assert len(relationships) == 1
    relationship = relationships[0]
    assert relationship.framework == "angular"
    assert relationship.relationship_type == "component_route"
    assert relationship.source_path == "src/app/app.routes.ts"
    assert relationship.target_path is None
    assert relationship.target_symbol == "OrdersComponent"
    assert relationship.confidence == "high"
    assert relationship.relationship_type in RELATIONSHIP_TYPES
    assert "component: OrdersComponent" in relationship.evidence[0]


def test_load_component_lazy_import_creates_route_lazy_target_relationship():
    relationships = _links(
        """
        {
          path: 'orders',
          loadComponent: () => import('./orders/orders.component')
            .then(m => m.OrdersComponent)
        },
        """
    )

    assert len(relationships) == 1
    relationship = relationships[0]
    assert relationship.relationship_type == "route_lazy_target"
    assert relationship.target_path == "src/app/orders/orders.component"
    assert relationship.target_symbol == "OrdersComponent"
    assert relationship.confidence == "high"
    assert "loadComponent" in relationship.evidence[0]


def test_load_children_lazy_import_creates_route_lazy_target_relationship():
    relationships = _links(
        """
        {
          path: 'admin',
          loadChildren: () => import('./admin/admin.routes')
            .then(m => m.ADMIN_ROUTES)
        },
        """
    )

    assert len(relationships) == 1
    relationship = relationships[0]
    assert relationship.relationship_type == "route_lazy_target"
    assert relationship.target_path == "src/app/admin/admin.routes"
    assert relationship.target_symbol == "ADMIN_ROUTES"
    assert relationship.confidence == "high"


def test_nested_children_route_produces_relationships_from_supplied_source():
    relationships = _links(
        """
        {
          path: 'parent',
          component: ParentComponent,
          children: [
            { path: 'child', component: ChildComponent },
            {
              path: 'lazy-child',
              loadComponent: () => import('./child/child.component')
                .then(m => m.ChildComponent)
            }
          ]
        },
        """
    )

    assert [(item.relationship_type, item.target_symbol) for item in relationships] == [
        ("component_route", "ChildComponent"),
        ("component_route", "ParentComponent"),
        ("route_lazy_target", "ChildComponent"),
    ]
    assert relationships[2].target_path == "src/app/child/child.component"


def test_redirect_to_does_not_create_component_or_lazy_target_relationship():
    assert _links("{ path: '', redirectTo: 'home', pathMatch: 'full' },") == ()


def test_malformed_route_metadata_degrades_with_warning_not_crash():
    relationships = _links(
        """
        { path: 'broken', component: , },
        { path: 'lazy-broken', loadComponent: () => import(, },
        """
    )

    assert len(relationships) == 2
    assert {item.relationship_type for item in relationships} == {
        "component_route",
        "route_lazy_target",
    }
    assert {item.confidence for item in relationships} == {"low"}
    assert all(item.target_path is None for item in relationships)
    assert all(item.warnings for item in relationships)


def test_relative_lazy_import_paths_normalize_deterministically():
    relationships = infer_angular_route_links(
        r"src\app\features\feature.routes.ts",
        _source(
            """
            {
              path: 'orders',
              loadChildren: () => import('../orders/./orders.routes')
                .then(m => m.ORDERS_ROUTES)
            },
            """
        ),
    )

    assert relationships[0].target_path == "src/app/orders/orders.routes"


def test_traversal_lazy_import_warns_safely_when_repo_root_is_provided():
    relationships = _links(
        """
        {
          path: 'outside',
          loadChildren: () => import('../../../outside.routes')
            .then(m => m.OUTSIDE_ROUTES)
        },
        """,
        repo_root="D:/AI-PROJECT/strata",
    )

    relationship = relationships[0]
    assert relationship.relationship_type == "route_lazy_target"
    assert relationship.target_path is None
    assert relationship.target_symbol == "OUTSIDE_ROUTES"
    assert relationship.confidence == "low"
    assert any(
        "outside the repository" in warning for warning in relationship.warnings
    )
    assert any("repo_root" in warning for warning in relationship.warnings)


def test_absolute_lazy_import_warns_safely_when_repo_root_is_provided():
    relationships = _links(
        """
        {
          path: 'absolute',
          loadComponent: () => import('C:/tmp/absolute.component')
            .then(m => m.AbsoluteComponent)
        },
        """,
        repo_root="D:/AI-PROJECT/strata",
    )

    relationship = relationships[0]
    assert relationship.relationship_type == "route_lazy_target"
    assert relationship.target_path is None
    assert relationship.target_symbol == "AbsoluteComponent"
    assert relationship.confidence == "low"
    assert any(
        "not a repository-relative target" in warning
        for warning in relationship.warnings
    )


def test_relationship_output_uses_j1_contract_shape_and_constants():
    relationships = _links(
        """
        { path: 'orders', component: OrdersComponent },
        {
          path: 'admin',
          loadChildren: () => import('./admin/admin.routes')
            .then(m => m.ADMIN_ROUTES)
        },
        """
    )
    payloads = [relationship.to_dict() for relationship in relationships]

    assert {payload["framework"] for payload in payloads} == {"angular"}
    assert {payload["relationship_type"] for payload in payloads} == {
        "component_route",
        "route_lazy_target",
    }
    assert all(payload["relationship_type"] in RELATIONSHIP_TYPES for payload in payloads)
    assert all(
        payload["source_path"] == "src/app/app.routes.ts" for payload in payloads
    )


def test_helper_does_not_scan_or_read_paths():
    with (
        patch("builtins.open", side_effect=AssertionError("opened a path")),
        patch.object(Path, "read_text", side_effect=AssertionError("read a path")),
        patch.object(Path, "stat", side_effect=AssertionError("statted a path")),
    ):
        relationships = _links(
            """
            {
              path: 'orders',
              loadComponent: () => import('./orders/orders.component')
                .then(m => m.OrdersComponent)
            },
            """
        )

    assert relationships[0].target_path == "src/app/orders/orders.component"


def test_module_does_not_expose_react_module_federation_or_workspace_apis():
    forbidden_fragments = (
        "react",
        "federation",
        "workspace",
        "package",
        "tsconfig",
    )
    public_names = {
        name
        for name in dir(angular_route_links)
        if not name.startswith("_")
    }

    assert not {
        name
        for name in public_names
        if any(fragment in name.lower() for fragment in forbidden_fragments)
    }


def test_empty_source_without_routes_returns_empty_tuple():
    assert infer_angular_route_links(
        "src/app/app.routes.ts",
        "export const value = 1;",
    ) == ()


TESTS = [
    test_component_route_creates_component_route_relationship_with_target_symbol,
    test_load_component_lazy_import_creates_route_lazy_target_relationship,
    test_load_children_lazy_import_creates_route_lazy_target_relationship,
    test_nested_children_route_produces_relationships_from_supplied_source,
    test_redirect_to_does_not_create_component_or_lazy_target_relationship,
    test_malformed_route_metadata_degrades_with_warning_not_crash,
    test_relative_lazy_import_paths_normalize_deterministically,
    test_traversal_lazy_import_warns_safely_when_repo_root_is_provided,
    test_absolute_lazy_import_warns_safely_when_repo_root_is_provided,
    test_relationship_output_uses_j1_contract_shape_and_constants,
    test_helper_does_not_scan_or_read_paths,
    test_module_does_not_expose_react_module_federation_or_workspace_apis,
    test_empty_source_without_routes_returns_empty_tuple,
]
