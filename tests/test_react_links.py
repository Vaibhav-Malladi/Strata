from pathlib import Path
from unittest.mock import patch

import strata.core.react_links as react_links
from strata.core.frontend_relationships import RELATIONSHIP_TYPES
from strata.core.react_links import infer_react_links


def _links(source: str, source_path: str = "src/components/OrdersPage.tsx", **kwargs):
    return infer_react_links(source_path, source, **kwargs)


def _by_type(relationships, relationship_type: str):
    return [item for item in relationships if item.relationship_type == relationship_type]


def test_uppercase_jsx_child_component_creates_relationship():
    relationships = _links(
        """
        export function OrdersPage() {
          return <section><UserCard user={user} /></section>;
        }
        """
    )

    child_links = _by_type(relationships, "component_child_component")
    assert len(child_links) == 1
    relationship = child_links[0]
    assert relationship.framework == "react"
    assert relationship.source_path == "src/components/OrdersPage.tsx"
    assert relationship.target_symbol == "UserCard"
    assert relationship.target_path is None
    assert relationship.confidence == "high"
    assert relationship.relationship_type in RELATIONSHIP_TYPES


def test_lowercase_html_tags_are_ignored():
    relationships = _links(
        """
        export function OrdersPage() {
          return <div><span><button>Save</button></span></div>;
        }
        """
    )

    assert _by_type(relationships, "component_child_component") == []


def test_component_calling_use_something_creates_hook_component_relationship():
    relationships = _links(
        """
        export function OrdersPage() {
          const orders = useOrders();
          return <OrdersTable orders={orders} />;
        }
        """
    )

    hook_links = _by_type(relationships, "hook_component")
    assert [item.target_symbol for item in hook_links] == ["useOrders"]
    assert hook_links[0].confidence == "high"
    assert "component calls a hook" in hook_links[0].reason


def test_hook_calling_another_hook_is_detected_deterministically():
    relationships = _links(
        """
        export function useOrders() {
          const auth = useAuth();
          return auth;
        }
        """,
        source_path="src/hooks/useOrders.ts",
    )

    hook_links = _by_type(relationships, "hook_component")
    assert [item.target_symbol for item in hook_links] == ["useAuth"]
    assert "hook calls another hook" in hook_links[0].reason


def test_component_calling_api_client_creates_component_api_relationship():
    relationships = _links(
        """
        export function OrdersPage() {
          api.get('/orders');
          OrdersClient();
          fetch('/health');
          return <OrdersTable />;
        }
        """
    )

    api_links = _by_type(relationships, "component_api_client")
    assert [item.target_symbol for item in api_links] == [
        "OrdersClient",
        "api.get",
        "fetch",
    ]
    assert {item.confidence for item in api_links} == {"medium"}


def test_hook_calling_api_client_creates_hook_api_relationship():
    relationships = _links(
        """
        export function useOrders() {
          ordersService.list();
          return [];
        }
        """,
        source_path="src/hooks/useOrders.ts",
    )

    api_links = _by_type(relationships, "hook_api_client")
    assert [item.target_symbol for item in api_links] == ["ordersService.list"]
    assert "hook calls an API/client-like function" in api_links[0].reason


def test_react_lazy_dynamic_import_creates_route_component_relationship():
    relationships = _links(
        """
        const OrdersRoute = React.lazy(() => import('./routes/OrdersRoute'));
        export function App() {
          return <OrdersRoute />;
        }
        """
    )

    lazy_links = _by_type(relationships, "react_route_component")
    assert len(lazy_links) == 1
    relationship = lazy_links[0]
    assert relationship.target_path == "src/components/routes/OrdersRoute"
    assert relationship.target_symbol == "OrdersRoute"
    assert relationship.confidence == "high"
    assert "React lazy" in relationship.reason


def test_relative_lazy_import_paths_normalize_deterministically():
    relationships = _links(
        "const OrdersRoute = lazy(() => import('../routes/./OrdersRoute'));",
        source_path=r"src\components\pages\OrdersPage.tsx",
    )

    assert _by_type(relationships, "react_route_component")[0].target_path == (
        "src/components/routes/OrdersRoute"
    )


def test_traversal_lazy_import_warns_safely_when_repo_root_is_provided():
    relationships = _links(
        "const OutsideRoute = React.lazy(() => import('../../../outside'));",
        repo_root="D:/AI-PROJECT/strata",
    )

    relationship = _by_type(relationships, "react_route_component")[0]
    assert relationship.target_path is None
    assert relationship.target_symbol == "OutsideRoute"
    assert relationship.confidence == "low"
    assert any(
        "outside the repository" in warning for warning in relationship.warnings
    )
    assert any("repo_root" in warning for warning in relationship.warnings)


def test_absolute_lazy_import_warns_safely_when_repo_root_is_provided():
    relationships = _links(
        "const AbsoluteRoute = React.lazy(() => import('C:/tmp/AbsoluteRoute'));",
        repo_root="D:/AI-PROJECT/strata",
    )

    relationship = _by_type(relationships, "react_route_component")[0]
    assert relationship.target_path is None
    assert relationship.target_symbol == "AbsoluteRoute"
    assert relationship.confidence == "low"
    assert any(
        "not a repository-relative target" in warning
        for warning in relationship.warnings
    )


def test_malformed_source_degrades_with_warning_not_crash():
    relationships = _links("const BrokenRoute = React.lazy(() => import(,")

    relationship = _by_type(relationships, "react_route_component")[0]
    assert relationship.target_path is None
    assert relationship.target_symbol == "BrokenRoute"
    assert relationship.confidence == "low"
    assert relationship.warnings == ("React lazy import metadata is malformed.",)


def test_relationship_output_uses_j1_contract_shape_and_constants():
    relationships = _links(
        """
        const OrdersRoute = React.lazy(() => import('./routes/OrdersRoute'));
        export function OrdersPage() {
          const orders = useOrders();
          api.get('/orders');
          return <UserCard />;
        }
        """
    )
    payloads = [relationship.to_dict() for relationship in relationships]

    assert {payload["framework"] for payload in payloads} == {"react"}
    assert {payload["relationship_type"] for payload in payloads} == {
        "component_api_client",
        "component_child_component",
        "hook_component",
        "react_route_component",
    }
    assert all(
        payload["relationship_type"] in RELATIONSHIP_TYPES for payload in payloads
    )
    assert all(
        payload["source_path"] == "src/components/OrdersPage.tsx"
        for payload in payloads
    )


def test_helper_does_not_scan_or_read_paths():
    with (
        patch("builtins.open", side_effect=AssertionError("opened a path")),
        patch.object(Path, "read_text", side_effect=AssertionError("read a path")),
        patch.object(Path, "stat", side_effect=AssertionError("statted a path")),
    ):
        relationships = _links(
            "const OrdersRoute = React.lazy(() => import('./routes/OrdersRoute'));"
        )

    assert _by_type(relationships, "react_route_component")[0].target_path == (
        "src/components/routes/OrdersRoute"
    )


def test_module_does_not_expose_angular_module_federation_or_workspace_apis():
    forbidden_fragments = (
        "angular",
        "federation",
        "workspace",
        "package",
        "tsconfig",
    )
    public_names = {name for name in dir(react_links) if not name.startswith("_")}

    assert not {
        name
        for name in public_names
        if any(fragment in name.lower() for fragment in forbidden_fragments)
    }


TESTS = [
    test_uppercase_jsx_child_component_creates_relationship,
    test_lowercase_html_tags_are_ignored,
    test_component_calling_use_something_creates_hook_component_relationship,
    test_hook_calling_another_hook_is_detected_deterministically,
    test_component_calling_api_client_creates_component_api_relationship,
    test_hook_calling_api_client_creates_hook_api_relationship,
    test_react_lazy_dynamic_import_creates_route_component_relationship,
    test_relative_lazy_import_paths_normalize_deterministically,
    test_traversal_lazy_import_warns_safely_when_repo_root_is_provided,
    test_absolute_lazy_import_warns_safely_when_repo_root_is_provided,
    test_malformed_source_degrades_with_warning_not_crash,
    test_relationship_output_uses_j1_contract_shape_and_constants,
    test_helper_does_not_scan_or_read_paths,
    test_module_does_not_expose_angular_module_federation_or_workspace_apis,
]
