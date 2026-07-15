from pathlib import Path
from unittest.mock import patch

import strata.core.frontend_boundary_signals as boundary_signals
from strata.core.frontend_boundary_signals import infer_frontend_boundary_signals
from strata.core.frontend_relationships import RELATIONSHIP_TYPES


def _links(source: str, source_path: str = "webpack.config.js", **kwargs):
    return infer_frontend_boundary_signals(source_path, source, **kwargs)


def _by_type(relationships, relationship_type: str):
    return [item for item in relationships if item.relationship_type == relationship_type]


def test_remotes_object_creates_module_federation_remote_relationship():
    relationships = _links(
        "module.exports = { remotes: { orders: 'orders@cdn/remoteEntry.js' } };"
    )

    relationship = _by_type(relationships, "module_federation_remote")[0]
    assert relationship.framework == "generic_frontend"
    assert relationship.target_symbol == "orders"
    assert relationship.target_path == "orders@cdn/remoteEntry.js"
    assert relationship.confidence == "high"


def test_remotes_array_creates_module_federation_remote_relationship():
    relationships = _links(
        "module.exports = { remotes: ['orders@cdn/remoteEntry.js'] };"
    )

    relationship = _by_type(relationships, "module_federation_remote")[0]
    assert relationship.target_symbol == "orders"
    assert relationship.target_path == "orders@cdn/remoteEntry.js"
    assert relationship.confidence == "high"


def test_exposes_object_creates_module_federation_remote_relationship():
    relationships = _links(
        "module.exports = { exposes: { './Widget': './src/app/widget.ts' } };"
    )

    relationship = _by_type(relationships, "module_federation_remote")[0]
    assert relationship.target_symbol == "./Widget"
    assert relationship.target_path == "src/app/widget.ts"
    assert relationship.confidence == "high"


def test_load_remote_module_creates_module_federation_remote_relationship():
    relationships = _links(
        """
        loadRemoteModule({
          remoteName: 'orders',
          exposedModule: './OrdersModule',
          remoteEntry: 'orders/remoteEntry.js'
        });
        """,
        source_path="src/app/app.routes.ts",
        framework="angular",
    )

    relationship = _by_type(relationships, "module_federation_remote")[0]
    assert relationship.framework == "angular"
    assert relationship.target_symbol == "orders"
    assert relationship.target_path == "orders/remoteEntry.js"
    assert relationship.confidence == "high"


def test_remote_entry_literal_creates_module_federation_remote_relationship():
    relationships = _links("const remote = 'orders/remoteEntry.js';")

    relationship = _by_type(relationships, "module_federation_remote")[0]
    assert relationship.target_symbol == "orders"
    assert relationship.target_path == "orders/remoteEntry.js"
    assert relationship.confidence == "medium"
    assert relationship.warnings


def test_dynamic_remote_import_creates_medium_confidence_relationship():
    relationships = _links("const mod = await import('orders/Module');")

    relationship = _by_type(relationships, "module_federation_remote")[0]
    assert relationship.target_symbol == "orders"
    assert relationship.target_path == "orders/Module"
    assert relationship.confidence == "medium"


def test_custom_elements_define_creates_high_confidence_custom_element_usage():
    relationships = _links(
        "customElements.define('company-widget', CompanyWidget);",
        source_path="src/elements/company-widget.ts",
    )

    relationship = _by_type(relationships, "custom_element_usage")[0]
    assert relationship.target_symbol == "company-widget"
    assert relationship.target_path is None
    assert relationship.confidence == "high"


def test_hyphenated_template_tag_creates_low_confidence_custom_element_usage():
    relationships = _links(
        "<company-widget></company-widget>",
        source_path="src/app/app.component.html",
        framework="angular",
    )

    relationship = _by_type(relationships, "custom_element_usage")[0]
    assert relationship.framework == "angular"
    assert relationship.target_symbol == "company-widget"
    assert relationship.confidence == "low"
    assert relationship.warnings


def test_lowercase_normal_html_tags_are_ignored():
    relationships = _links("<div><span><button>Save</button></span></div>")

    assert _by_type(relationships, "custom_element_usage") == []


def test_document_create_element_custom_tag_creates_custom_element_usage():
    relationships = _links("document.createElement('mfe-orders');")

    relationship = _by_type(relationships, "custom_element_usage")[0]
    assert relationship.target_symbol == "mfe-orders"
    assert relationship.confidence == "medium"


def test_duplicate_boundary_signals_are_deduped_deterministically():
    relationships = _links(
        """
        const remote = 'orders/remoteEntry.js';
        const duplicate = 'orders/remoteEntry.js';
        <company-widget></company-widget>
        <company-widget></company-widget>
        """
    )

    module_links = _by_type(relationships, "module_federation_remote")
    element_links = _by_type(relationships, "custom_element_usage")

    assert [item.target_symbol for item in module_links] == ["orders"]
    assert [item.target_symbol for item in element_links] == ["company-widget"]
    assert len(module_links[0].evidence) == 1
    assert len(element_links[0].evidence) == 1


def test_output_uses_j1_frontend_relationship_constants():
    relationships = _links("customElements.define('company-widget', CompanyWidget);")
    payload = relationships[0].to_dict()

    assert payload["relationship_type"] == "custom_element_usage"
    assert payload["relationship_type"] in RELATIONSHIP_TYPES
    assert payload["framework"] == "generic_frontend"
    assert payload["source_path"] == "webpack.config.js"


def test_helper_does_not_scan_or_read_paths():
    with (
        patch("builtins.open", side_effect=AssertionError("opened a path")),
        patch.object(Path, "read_text", side_effect=AssertionError("read a path")),
        patch.object(Path, "stat", side_effect=AssertionError("statted a path")),
    ):
        relationships = _links(
            "module.exports = { remotes: { orders: 'orders@cdn/remoteEntry.js' } };"
        )

    assert relationships[0].target_symbol == "orders"


def test_module_does_not_expose_workspace_or_user_journey_apis():
    forbidden_fragments = ("workspace", "journey", "flow", "cross_repo")
    public_names = {
        name
        for name in dir(boundary_signals)
        if not name.startswith("_")
    }

    assert not {
        name
        for name in public_names
        if any(fragment in name.lower() for fragment in forbidden_fragments)
    }


TESTS = [
    test_remotes_object_creates_module_federation_remote_relationship,
    test_remotes_array_creates_module_federation_remote_relationship,
    test_exposes_object_creates_module_federation_remote_relationship,
    test_load_remote_module_creates_module_federation_remote_relationship,
    test_remote_entry_literal_creates_module_federation_remote_relationship,
    test_dynamic_remote_import_creates_medium_confidence_relationship,
    test_custom_elements_define_creates_high_confidence_custom_element_usage,
    test_hyphenated_template_tag_creates_low_confidence_custom_element_usage,
    test_lowercase_normal_html_tags_are_ignored,
    test_document_create_element_custom_tag_creates_custom_element_usage,
    test_duplicate_boundary_signals_are_deduped_deterministically,
    test_output_uses_j1_frontend_relationship_constants,
    test_helper_does_not_scan_or_read_paths,
    test_module_does_not_expose_workspace_or_user_journey_apis,
]
