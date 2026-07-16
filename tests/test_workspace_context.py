import json
from pathlib import Path

import strata.core.context_artifacts as context_artifacts
import strata.core.context_rendering as context_rendering
from strata.core.capability_profiles import CAPABILITY_TIER_MEDIUM, get_capability_profile
import strata.utils.workspace_context as workspace_context
import strata.utils.workspace_contracts as workspace_contracts
import strata.utils.workspace_graph as workspace_graph
import strata.utils.workspace_relationships as workspace_relationships


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _workspace():
    return {
        "schema_version": 1,
        "name": "example",
        "repositories": [
            {"id": "frontend", "path": ".", "role": "frontend", "display_name": "Frontend"},
            {"id": "backend", "path": "../backend", "role": "backend", "display_name": "Backend"},
            {"id": "worker", "path": "../worker", "role": "worker", "display_name": "Worker"},
        ],
    }


def _evidence(summary="frontend calls backend", strength="strong"):
    return workspace_relationships.RelationshipEvidence(
        signal_type="workspace_file",
        source_repository_id="frontend",
        source_path="workspace.yml",
        summary=summary,
        strength=strength,
        target_repository_id="backend",
    )


def _relationship(**overrides):
    values = {
        "source_repository_id": "frontend",
        "target_repository_id": "backend",
        "relationship_type": "calls_api",
        "origin": "explicit",
        "confidence": "high",
        "confidence_score": 1.0,
        "evidence": (_evidence(),),
        "explicit": True,
        "inferred": False,
    }
    values.update(overrides)
    return values


def _contract(name="auth-header", status="consistent", severity="warning"):
    return {
        "name": name,
        "contract_type": "auth_header",
        "status": status,
        "severity": severity,
        "expected_value": "github_pat_super_secret_token",
        "distinct_observed_values": ["github_pat_super_secret_token"],
        "location_findings": [
            {"repository_id": "frontend", "status": status, "path": "src/constants.ts"},
            {"repository_id": "backend", "status": status, "path": "app/constants.py"},
        ],
    }


def _graph(*, relationships=(), contract_findings=()):
    return workspace_graph.build_workspace_dependency_graph(
        _workspace(),
        reference_relationship_hints=relationships,
        contract_findings=contract_findings,
    )


def _context(task="fix frontend auth", graph=None, **kwargs):
    return workspace_context.build_workspace_context_representation(task, graph or _graph(relationships=(_relationship(),)), **kwargs)


def _payload(context):
    return workspace_context.workspace_context_to_dict(context)


def test_task_relevance_prioritizes_matching_repositories():
    graph = _graph(relationships=(_relationship(),))
    payload = _payload(_context("backend auth bug", graph))

    assert payload["repositories"][0]["repository_id"] == "backend"


def test_explicit_relationship_outranks_weak_inferred_relationship():
    graph = _graph(
        relationships=(
            _relationship(source_repository_id="worker", target_repository_id="backend", relationship_type="depends_on", origin="inferred", confidence="low", confidence_score=0.2, explicit=False, inferred=True),
            _relationship(),
        )
    )
    payload = _payload(_context("backend", graph, max_relationships=1))

    assert payload["relationships"][0]["source_repository_id"] == "frontend"
    assert payload["relationships"][0]["explicit"] is True


def test_error_contract_finding_remains_visible_and_redacted():
    payload = _payload(_context(contract_findings=(_contract(status="inconsistent", severity="error"),)))

    assert payload["contracts"][0]["name"] == "auth-header"
    assert payload["contracts"][0]["severity"] == "error"
    assert "super_secret" not in json.dumps(payload, sort_keys=True)


def test_workspace_token_allocation_is_bounded_and_preserves_part_i_fields():
    payload = _payload(
        _context(
            budget_profile={
                "target_context_tokens": 1000,
                "reserved_output_tokens": 200,
                "max_context_pack_tokens": 700,
                "safety_margin": 0.1,
            }
        )
    )

    budget = payload["budget_summary"]
    assert budget["target_workspace_token_allocation"] <= 120
    assert budget["reserved_output_tokens"] == 200
    assert budget["safety_margin"] == 0.1


def test_workspace_allocation_cannot_exceed_configured_share():
    payload = _payload(_context(budget_profile={"target_context_tokens": 1000, "reserved_output_tokens": 0, "max_context_pack_tokens": 1000, "safety_margin": 0}, max_workspace_share=0.1))

    assert payload["budget_summary"]["target_workspace_token_allocation"] == 100
    assert payload["budget_summary"]["max_workspace_share"] == 0.1


def test_caps_and_omitted_counts_are_recorded():
    relationships = tuple(_relationship(relationship_type=kind) for kind in ("calls_api", "depends_on", "imports_package"))
    payload = _payload(_context(graph=_graph(relationships=relationships), max_repositories=1, max_relationships=1, max_contracts=1, contract_findings=(_contract("one"), _contract("two"))))

    assert len(payload["repositories"]) == 1
    assert len(payload["relationships"]) == 1
    assert len(payload["contracts"]) == 1
    assert payload["omitted_counts"]["repositories"] == 2
    assert payload["omitted_counts"]["relationships"] == 2
    assert payload["omitted_counts"]["contracts"] == 1


def test_evidence_cap_is_enforced():
    evidence = tuple(_evidence(summary=f"evidence {index}") for index in range(5))
    graph = _graph(relationships=(_relationship(evidence=evidence),))
    payload = _payload(_context(graph=graph, max_evidence_per_item=2))

    assert len(payload["relationships"][0]["evidence"]) == 2
    assert payload["omitted_counts"]["evidence"] >= 3


def test_downgrade_before_skip_and_budget_exhaustion_are_recorded():
    evidence = tuple(_evidence(summary=f"large evidence {index} " + "x" * 80) for index in range(15))
    graph = _graph(relationships=tuple(_relationship(relationship_type=kind, evidence=evidence) for kind in ("calls_api", "depends_on", "imports_package")))
    payload = _payload(
        _context(
            graph=graph,
            budget_profile={"target_context_tokens": 80, "reserved_output_tokens": 0, "max_context_pack_tokens": 80, "safety_margin": 0},
            max_workspace_share=0.2,
        )
    )

    assert payload["omitted_counts"]["downgraded"] > 0
    assert payload["budget_summary"]["largest_workspace_token_savings"]
    assert payload["budget_summary"]["budget_exhausted"] is True


def test_identity_only_fallback_is_used_under_budget_pressure():
    graph = _graph(relationships=(_relationship(evidence=tuple(_evidence(summary=f"long {index} " + "x" * 100) for index in range(10))),))
    payload = _payload(_context(graph=graph, budget_profile={"target_context_tokens": 200, "reserved_output_tokens": 0, "max_context_pack_tokens": 200, "safety_margin": 0}, max_workspace_share=0.2))

    tiers = {item["representation_tier"] for item in [*payload["repositories"], *payload["relationships"]]}
    assert "identity_only" in tiers or payload["omitted_counts"]["skipped"] > 0


def test_deterministic_serialization():
    first = _payload(_context())
    second = _payload(_context())

    assert first == second
    assert list(first) == list(workspace_context.RESULT_FIELD_ORDER)
    assert list(first["budget_summary"]) == list(workspace_context.BUDGET_FIELD_ORDER)


def test_no_workspace_input_preserves_old_context_output():
    old = context_artifacts.render_strata_context(task="fix auth", relevant_files=["src/app.py"])
    again = context_artifacts.render_strata_context(task="fix auth", relevant_files=["src/app.py"])

    assert old == again
    assert "## Workspace context" not in old


def test_workspace_section_appears_in_canonical_markdown():
    context = _payload(_context())
    rendered = context_artifacts.render_strata_context(task="fix auth", workspace_context=context)

    assert "## Workspace context" in rendered
    assert "### Cross-repository relationships" in rendered


def test_workspace_data_appears_in_machine_readable_context_pack():
    context = _payload(_context())
    rendered = context_rendering.render_context_pack(
        {"task": "fix auth", "workspace_context": context},
        get_capability_profile(CAPABILITY_TIER_MEDIUM),
    )

    assert rendered["workspace_context"]["schema_version"] == 1
    assert rendered["metadata"]["rendered_workspace_context"] is True
    assert "## Workspace context" in context_rendering.render_context_pack_markdown(rendered)


def test_part_i_remains_authoritative_budget_source():
    payload = _payload(_context())

    assert payload["metadata"]["part_i_authoritative"] is True
    assert payload["budget_summary"]["tokenizer_strategy"] == "conservative_char_estimate"


def test_contract_result_object_is_supported():
    location = workspace_contracts.ContractLocationFinding(
        contract_name="auth-header",
        repository_id="frontend",
        path="src/constants.ts",
        status="consistent",
        expected_value="Authorization",
        allowed_values=(),
        observed_values=("Authorization",),
        normalized_expected="Authorization",
        normalized_allowed_values=(),
        normalized_observed_values=("Authorization",),
        matching_reference_ids=("frontend:auth",),
        confidence="high",
        confidence_score=0.9,
    )
    finding = workspace_contracts.SharedContractFinding(
        name="auth-header",
        contract_type="auth_header",
        severity="warning",
        normalization="exact",
        status="consistent",
        expected_value="Authorization",
        allowed_values=(),
        location_findings=(location,),
        distinct_observed_values=("Authorization",),
        confidence="high",
        confidence_score=0.9,
    )
    result = workspace_contracts.SharedContractComparisonResult(contract_findings=(finding,))

    assert _payload(_context(contract_findings=result))["contracts"][0]["name"] == "auth-header"


def test_scanner_compatible_imports_and_architecture_boundary():
    source = (PROJECT_ROOT / "strata" / "utils" / "workspace_context.py").read_text(encoding="utf-8")

    assert "import strata.utils.workspace_graph as workspace_graph" in source
    assert "from strata.utils import" not in source
    assert "strata.core" not in source
    assert "strata.commands" not in source


TESTS = [
    test_task_relevance_prioritizes_matching_repositories,
    test_explicit_relationship_outranks_weak_inferred_relationship,
    test_error_contract_finding_remains_visible_and_redacted,
    test_workspace_token_allocation_is_bounded_and_preserves_part_i_fields,
    test_workspace_allocation_cannot_exceed_configured_share,
    test_caps_and_omitted_counts_are_recorded,
    test_evidence_cap_is_enforced,
    test_downgrade_before_skip_and_budget_exhaustion_are_recorded,
    test_identity_only_fallback_is_used_under_budget_pressure,
    test_deterministic_serialization,
    test_no_workspace_input_preserves_old_context_output,
    test_workspace_section_appears_in_canonical_markdown,
    test_workspace_data_appears_in_machine_readable_context_pack,
    test_part_i_remains_authoritative_budget_source,
    test_contract_result_object_is_supported,
    test_scanner_compatible_imports_and_architecture_boundary,
]
