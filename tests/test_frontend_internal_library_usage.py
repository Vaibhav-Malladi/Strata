from pathlib import Path
from unittest.mock import patch

import strata.core.frontend_internal_library_usage as internal_usage
from strata.core.frontend_internal_library_usage import (
    infer_frontend_internal_library_usage,
)
from strata.core.frontend_relationships import RELATIONSHIP_TYPES


def _links(source: str, source_path: str = "src/app/orders.component.ts", **kwargs):
    return infer_frontend_internal_library_usage(source_path, source, **kwargs)


def test_import_from_known_internal_package_is_high_confidence():
    relationships = _links(
        "import { InternalButton } from '@acme/ui';",
        known_internal_packages=("@acme/ui",),
        framework="react",
    )

    assert len(relationships) == 1
    relationship = relationships[0]
    assert relationship.framework == "react"
    assert relationship.relationship_type == "internal_library_usage"
    assert relationship.target_path == "@acme/ui"
    assert relationship.target_symbol == "InternalButton"
    assert relationship.confidence == "high"
    assert relationship.warnings == ()


def test_private_package_prefix_import_is_low_confidence_guess():
    relationships = _links(
        "import { CompanyButton } from '@company/design-system';",
        framework="generic_frontend",
    )

    relationship = relationships[0]
    assert relationship.target_path == "@company/design-system"
    assert relationship.target_symbol == "CompanyButton"
    assert relationship.confidence == "low"
    assert relationship.warnings
    assert "private-looking package prefix" in relationship.reason


def test_angular_template_selector_matching_known_symbol_creates_relationship():
    relationships = _links(
        "<company-card [title]='title'></company-card>",
        source_path="src/app/orders.component.html",
        known_internal_symbols=("CompanyCard",),
    )

    relationship = relationships[0]
    assert relationship.framework == "angular"
    assert relationship.target_symbol == "CompanyCard"
    assert relationship.confidence == "medium"


def test_angular_attribute_directive_matching_known_symbol_creates_relationship():
    relationships = _links(
        "<button [companyTooltip]='message'>Save</button>",
        source_path="src/app/orders.component.html",
        known_internal_symbols=("CompanyTooltip",),
        framework="angular",
    )

    assert [item.target_symbol for item in relationships] == ["CompanyTooltip"]
    assert relationships[0].confidence == "medium"


def test_angular_pipe_matching_known_symbol_creates_relationship():
    relationships = _links(
        "{{ total | companyCurrency }}",
        source_path="src/app/orders.component.html",
        known_internal_symbols=("CompanyCurrencyPipe",),
        framework="angular",
    )

    assert [item.target_symbol for item in relationships] == ["CompanyCurrencyPipe"]


def test_angular_injected_service_matching_known_symbol_creates_relationship():
    relationships = _links(
        """
        export class OrdersComponent {
          constructor(private api: CompanyOrdersService) {}
        }
        """,
        known_internal_symbols=("CompanyOrdersService",),
        framework="angular",
    )

    assert [item.target_symbol for item in relationships] == ["CompanyOrdersService"]


def test_react_jsx_component_matching_known_symbol_creates_relationship():
    relationships = _links(
        "export function Page() { return <CompanyCard />; }",
        source_path="src/Page.tsx",
        known_internal_symbols=("CompanyCard",),
    )

    assert relationships[0].framework == "react"
    assert relationships[0].target_symbol == "CompanyCard"
    assert relationships[0].confidence == "medium"


def test_react_hook_matching_known_symbol_creates_relationship():
    relationships = _links(
        "export function Page() { const data = useCompanyData(); return null; }",
        source_path="src/Page.tsx",
        known_internal_symbols=("useCompanyData",),
    )

    assert [item.target_symbol for item in relationships] == ["useCompanyData"]


def test_api_client_service_symbol_matching_known_symbol_creates_relationship():
    relationships = _links(
        "export function Page() { CompanyOrdersClient.fetch(); return null; }",
        source_path="src/Page.tsx",
        known_internal_symbols=("CompanyOrdersClient",),
        framework="react",
    )

    assert [item.target_symbol for item in relationships] == ["CompanyOrdersClient"]


def test_unknown_prefix_guess_is_low_confidence_with_warning_and_reason():
    relationships = _links(
        "<company-unknown-widget></company-unknown-widget>",
        source_path="src/app/orders.component.html",
        framework="angular",
    )

    relationship = relationships[0]
    assert relationship.target_symbol == "company-unknown-widget"
    assert relationship.confidence == "low"
    assert relationship.warnings
    assert "private-looking selector prefix" in relationship.reason


def test_duplicates_are_deduped_deterministically():
    relationships = _links(
        "<CompanyCard /><CompanyCard /><company-card></company-card>",
        source_path="src/Page.tsx",
        known_internal_symbols=("CompanyCard",),
        framework="react",
    )

    assert [item.target_symbol for item in relationships] == ["CompanyCard"]
    assert len(relationships[0].evidence) == 2


def test_output_uses_j1_contract_constants():
    relationships = _links(
        "import { InternalButton } from '@internal/ui';",
        framework="generic_frontend",
    )
    payload = relationships[0].to_dict()

    assert payload["relationship_type"] == "internal_library_usage"
    assert payload["relationship_type"] in RELATIONSHIP_TYPES
    assert payload["framework"] == "generic_frontend"
    assert payload["source_path"] == "src/app/orders.component.ts"
    assert payload["target_path"] == "@internal/ui"


def test_helper_does_not_scan_or_read_paths():
    with (
        patch("builtins.open", side_effect=AssertionError("opened a path")),
        patch.object(Path, "read_text", side_effect=AssertionError("read a path")),
        patch.object(Path, "stat", side_effect=AssertionError("statted a path")),
    ):
        relationships = _links(
            "import { InternalButton } from '@acme/ui';",
            known_internal_packages=("@acme/ui",),
            framework="react",
        )

    assert relationships[0].target_path == "@acme/ui"


def test_module_does_not_expose_module_federation_or_workspace_apis():
    forbidden_fragments = ("federation", "workspace", "node_modules", "package_json")
    public_names = {
        name
        for name in dir(internal_usage)
        if not name.startswith("_")
    }

    assert not {
        name
        for name in public_names
        if any(fragment in name.lower() for fragment in forbidden_fragments)
    }


TESTS = [
    test_import_from_known_internal_package_is_high_confidence,
    test_private_package_prefix_import_is_low_confidence_guess,
    test_angular_template_selector_matching_known_symbol_creates_relationship,
    test_angular_attribute_directive_matching_known_symbol_creates_relationship,
    test_angular_pipe_matching_known_symbol_creates_relationship,
    test_angular_injected_service_matching_known_symbol_creates_relationship,
    test_react_jsx_component_matching_known_symbol_creates_relationship,
    test_react_hook_matching_known_symbol_creates_relationship,
    test_api_client_service_symbol_matching_known_symbol_creates_relationship,
    test_unknown_prefix_guess_is_low_confidence_with_warning_and_reason,
    test_duplicates_are_deduped_deterministically,
    test_output_uses_j1_contract_constants,
    test_helper_does_not_scan_or_read_paths,
    test_module_does_not_expose_module_federation_or_workspace_apis,
]
