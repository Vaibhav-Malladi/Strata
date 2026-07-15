from pathlib import Path
from unittest.mock import patch

import strata.core.frontend_linking_summary as frontend_linking_summary
from strata.core.angular_component_links import infer_angular_component_links
from strata.core.angular_route_links import infer_angular_route_links
from strata.core.frontend_boundary_signals import infer_frontend_boundary_signals
from strata.core.frontend_internal_library_usage import (
    infer_frontend_internal_library_usage,
)
from strata.core.frontend_linking_summary import (
    frontend_linking_summary_to_dict,
    summarize_frontend_relationships,
)
from strata.core.react_links import infer_react_links


def _angular_relationships():
    component_source = """
    @Component({
      selector: 'app-orders',
      templateUrl: './orders.component.html',
      styleUrls: ['./orders.component.css']
    })
    export class OrdersComponent {
      constructor(private service: CompanyOrdersService) {}
    }
    """
    route_source = """
    export const routes = [
      { path: 'orders', component: OrdersComponent },
      {
        path: 'remote',
        loadChildren: () => import('./remote/remote.routes')
          .then(m => m.REMOTE_ROUTES)
      }
    ];
    """
    template_source = """
    <company-card companyTooltip></company-card>
    <company-unknown-widget></company-unknown-widget>
    {{ total | companyCurrency }}
    """
    boundary_source = """
    loadRemoteModule({
      remoteName: 'orders',
      remoteEntry: 'orders/remoteEntry.js',
      exposedModule: './OrdersModule'
    });
    <mfe-orders></mfe-orders>
    """

    return (
        *infer_angular_component_links(
            "src/app/orders/orders.component.ts",
            component_source,
        ),
        *infer_angular_route_links("src/app/app.routes.ts", route_source),
        *infer_frontend_internal_library_usage(
            "src/app/orders/orders.component.html",
            template_source,
            known_internal_symbols=(
                "CompanyCard",
                "CompanyTooltip",
                "CompanyCurrencyPipe",
                "CompanyOrdersService",
            ),
            framework="angular",
        ),
        *infer_frontend_boundary_signals(
            "src/app/app.routes.ts",
            boundary_source,
            framework="angular",
        ),
    )


def _react_relationships():
    page_source = """
    import { CompanyCard } from '@company/design-system';
    const OrdersRoute = React.lazy(() => import('./routes/OrdersRoute'));
    export function OrdersPage() {
      const orders = useCompanyOrders();
      api.get('/orders');
      return <CompanyCard orders={orders} />;
    }
    """
    boundary_source = """
    customElements.define('company-widget', CompanyWidget);
    <company-unknown-widget></company-unknown-widget>
    const remote = 'orders/remoteEntry.js';
    """

    return (
        *infer_react_links("src/components/OrdersPage.tsx", page_source),
        *infer_frontend_internal_library_usage(
            "src/components/OrdersPage.tsx",
            page_source,
            known_internal_packages=("@company/design-system",),
            known_internal_symbols=("CompanyCard", "useCompanyOrders"),
            framework="react",
        ),
        *infer_frontend_boundary_signals(
            "src/components/OrdersPage.tsx",
            boundary_source,
            framework="react",
        ),
    )


def test_combined_angular_frontend_linking_synthetic_example():
    summary = summarize_frontend_relationships(_angular_relationships()).to_dict()

    assert summary["frameworks"] == {"angular": summary["relationship_count"]}
    assert summary["relationship_types"] == {
        "component_route": 1,
        "component_style": 1,
        "component_template": 1,
        "custom_element_usage": 1,
        "internal_library_usage": 4,
        "module_federation_remote": 2,
        "route_lazy_target": 1,
    }
    assert "src/app/orders/orders.component.html" in summary["target_paths"]
    assert "CompanyCard" in summary["target_symbols"]
    assert "orders" in summary["target_symbols"]


def test_combined_react_frontend_linking_synthetic_example():
    summary = summarize_frontend_relationships(_react_relationships()).to_dict()

    assert summary["frameworks"] == {"react": summary["relationship_count"]}
    assert summary["relationship_types"] == {
        "component_api_client": 1,
        "component_child_component": 1,
        "custom_element_usage": 2,
        "hook_component": 1,
        "internal_library_usage": 3,
        "module_federation_remote": 1,
        "react_route_component": 1,
    }
    assert "@company/design-system" in summary["target_paths"]
    assert "OrdersRoute" in summary["target_symbols"]


def test_summary_output_is_deterministic_and_json_ready():
    relationships = (*_react_relationships(), *_angular_relationships())

    forward = frontend_linking_summary_to_dict(
        summarize_frontend_relationships(relationships)
    )
    reverse = frontend_linking_summary_to_dict(
        summarize_frontend_relationships(reversed(relationships))
    )

    assert forward == reverse
    assert isinstance(forward["relationships"], list)
    assert forward["relationship_count"] == len(forward["relationships"])


def test_duplicate_relationship_handling_is_reported_consistently():
    relationships = _react_relationships()
    summary = summarize_frontend_relationships((*relationships, relationships[0]))

    payload = summary.to_dict()

    assert payload["duplicate_relationship_count"] == 1
    assert payload["relationship_count"] == len(set(relationships))


def test_low_confidence_warnings_are_preserved():
    relationships = _angular_relationships()
    payload = summarize_frontend_relationships(relationships).to_dict()

    assert payload["confidences"]["low"] >= 1
    assert payload["warning_count"] >= 1
    assert any("confirm ownership" in warning for warning in payload["warnings"])


def test_no_file_reads_or_scanning_are_required_for_integration_summary():
    with (
        patch("builtins.open", side_effect=AssertionError("opened a path")),
        patch.object(Path, "read_text", side_effect=AssertionError("read a path")),
        patch.object(Path, "stat", side_effect=AssertionError("statted a path")),
    ):
        payload = summarize_frontend_relationships(_react_relationships()).to_dict()

    assert payload["relationship_count"] > 0


def test_summary_module_does_not_expose_scanning_or_workspace_apis():
    forbidden_fragments = (
        "scan",
        "read",
        "workspace",
        "journey",
        "backend",
        "route_graph",
    )
    public_names = {
        name
        for name in dir(frontend_linking_summary)
        if not name.startswith("_")
    }

    assert not {
        name
        for name in public_names
        if any(fragment in name.lower() for fragment in forbidden_fragments)
    }


def test_docs_mention_every_j_batch_and_required_handoffs():
    with open("docs/roadmap/frontend-deep-linking.md", encoding="utf-8") as handle:
        text = " ".join(handle.read().split())

    for batch in ("J1", "J2", "J3", "J4", "J5", "J6", "J7"):
        assert batch in text
    assert "Part I remains the token firewall" in text
    assert "Q owns workspace intelligence" in text
    assert "P owns user journey intelligence" in text
    assert "K Backend Intelligence Foundation" in text
    assert "M Workflow State and Diagnostics" in text
    assert "Q Workspace Intelligence" in text
    assert "P User Flow / Journey Intelligence" in text


TESTS = [
    test_combined_angular_frontend_linking_synthetic_example,
    test_combined_react_frontend_linking_synthetic_example,
    test_summary_output_is_deterministic_and_json_ready,
    test_duplicate_relationship_handling_is_reported_consistently,
    test_low_confidence_warnings_are_preserved,
    test_no_file_reads_or_scanning_are_required_for_integration_summary,
    test_summary_module_does_not_expose_scanning_or_workspace_apis,
    test_docs_mention_every_j_batch_and_required_handoffs,
]
