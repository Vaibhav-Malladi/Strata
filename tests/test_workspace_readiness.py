from pathlib import Path

import strata.utils.workspace_context as workspace_context
import strata.utils.workspace_graph as workspace_graph
import strata.utils.workspace_readiness as workspace_readiness
import strata.utils.workspace_relationships as workspace_relationships


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _workspace():
    return {
        "schema_version": 1,
        "name": "example",
        "repositories": [
            {"id": "frontend", "path": ".", "role": "frontend"},
            {"id": "backend", "path": "../backend", "role": "backend"},
        ],
    }


def _evidence():
    return workspace_relationships.RelationshipEvidence(
        signal_type="workspace_file",
        source_repository_id="frontend",
        source_path="workspace.yml",
        summary="frontend calls backend",
        strength="strong",
        target_repository_id="backend",
    )


def _graph(**kwargs):
    return workspace_graph.build_workspace_dependency_graph(
        _workspace(),
        reference_relationship_hints=(
            {
                "source_repository_id": "frontend",
                "target_repository_id": "backend",
                "relationship_type": "calls_api",
                "origin": "explicit",
                "confidence": "high",
                "confidence_score": 1.0,
                "evidence": (_evidence(),),
                "explicit": True,
                "inferred": False,
            },
        ),
        **kwargs,
    )


def _context(graph=None, **kwargs):
    return workspace_context.build_workspace_context_representation("fix frontend auth", graph or _graph(), **kwargs)


def _readiness(**kwargs):
    return workspace_readiness.build_workspace_readiness(
        workspace_config=_workspace(),
        graph=_graph(),
        context_representation=_context(),
        **kwargs,
    )


def _payload(result):
    return workspace_readiness.workspace_readiness_to_dict(result)


def _codes(result):
    return [item["code"] for item in _payload(result)["diagnostics"]]


def _stage(result, stage):
    for item in _payload(result)["stages"]:
        if item["stage"] == stage:
            return item
    raise AssertionError(stage)


def test_no_workspace_returns_not_configured():
    result = workspace_readiness.build_workspace_readiness(workspace_requested=False)

    assert _payload(result)["status"] == "not_configured"
    assert "workspace_not_configured" in _codes(result)


def test_fully_valid_workspace_returns_ready():
    result = _readiness(
        discovery_result={"diagnostics": []},
        relationship_assessment={"diagnostics": []},
        reference_extraction={"diagnostics": []},
        contract_comparison={"diagnostics": []},
    )

    assert _payload(result)["status"] == "ready"
    assert _payload(result)["safe_fallback"]["single_repository_context_available"] is True


def test_partial_evidence_returns_degraded():
    result = _readiness(reference_extraction={"diagnostics": [{"code": "selected_file_missing", "severity": "warning", "summary": "A selected file was missing."}]})

    assert _payload(result)["status"] == "degraded"
    assert _stage(result, "reference_extraction")["warning_count"] == 1


def test_required_repository_missing_blocks_workspace():
    result = _readiness(required_repository_ids=("billing",))

    assert _payload(result)["status"] == "blocked"
    assert "workspace_required_repository_missing" in _codes(result)
    assert _payload(result)["recommended_action"] == "Review missing repository path for billing."


def test_optional_repository_missing_degrades_workspace():
    result = _readiness(optional_repository_ids=("billing",))

    assert _payload(result)["status"] == "degraded"
    assert "workspace_stage_degraded" in _codes(result)


def test_stage_failure_isolated_from_other_results():
    result = _readiness(stage_failures={"reference_extraction": {"severity": "warning", "summary": "One file failed."}})

    assert _payload(result)["status"] == "degraded"
    assert _stage(result, "graph_construction")["status"] == "ready"
    assert "workspace_stage_failed" in _codes(result)


def test_graph_unavailable_is_safe_failure():
    result = workspace_readiness.build_workspace_readiness(workspace_config=_workspace(), graph=None)

    assert _payload(result)["status"] == "unavailable"
    assert "workspace_graph_unavailable" in _codes(result)
    assert _payload(result)["safe_fallback"]["single_repository_context_available"] is True


def test_context_unavailable_degrades_without_corrupting_fallback():
    result = workspace_readiness.build_workspace_readiness(workspace_config=_workspace(), graph=_graph(), context_representation=None)

    assert _payload(result)["status"] == "degraded"
    assert "workspace_context_unavailable" in _codes(result)
    assert _payload(result)["safe_fallback"]["automatic_patches"] is False


def test_budget_exhaustion_degrades_workspace():
    context = _context(
        budget_profile={"target_context_tokens": 60, "reserved_output_tokens": 0, "max_context_pack_tokens": 60, "safety_margin": 0},
        max_workspace_share=0.2,
    )
    result = workspace_readiness.build_workspace_readiness(workspace_config=_workspace(), graph=_graph(), context_representation=context)

    assert _payload(result)["status"] == "degraded"
    assert "workspace_budget_exhausted" in _codes(result)


def test_error_level_contract_mismatch_is_represented():
    result = _readiness(contract_comparison={"diagnostics": [{"code": "contract_value_mismatch", "severity": "error", "summary": "Contract mismatch."}]})

    assert _payload(result)["status"] == "degraded"
    assert "contract_value_mismatch" in _codes(result)


def test_diagnostic_cap_is_enforced():
    noisy = {"diagnostics": [{"code": f"diag_{index}", "severity": "warning", "summary": "Noisy diagnostic."} for index in range(5)]}
    result = workspace_readiness.build_workspace_readiness(workspace_config=_workspace(), graph=_graph(), context_representation=_context(), reference_extraction=noisy, max_diagnostics=3)

    assert len(_payload(result)["diagnostics"]) == 3
    assert "workspace_diagnostic_cap_reached" in _codes(result)


def test_recommended_action_is_deterministic_for_budget_pressure():
    context = _context(
        budget_profile={"target_context_tokens": 60, "reserved_output_tokens": 0, "max_context_pack_tokens": 60, "safety_margin": 0},
        max_workspace_share=0.2,
    )
    result = workspace_readiness.build_workspace_readiness(workspace_config=_workspace(), graph=_graph(), context_representation=context)

    assert _payload(result)["recommended_action"] == "Increase context budget or narrow the task."


def test_single_repository_fallback_and_no_automatic_config_changes():
    payload = _payload(_readiness(stage_failures={"contract_comparison": "contract mismatch"}))

    assert payload["safe_fallback"]["single_repository_context_available"] is True
    assert payload["safe_fallback"]["automatic_configuration_changes"] is False
    assert payload["safe_fallback"]["automatic_patches"] is False


def test_deterministic_serialization():
    first = _payload(_readiness())
    second = _payload(_readiness())

    assert first == second
    assert list(first) == list(workspace_readiness.RESULT_FIELD_ORDER)
    assert [item["stage"] for item in first["stages"]] == list(workspace_readiness.STAGES)


def test_scanner_compatible_imports_and_architecture_boundary():
    source = (PROJECT_ROOT / "strata" / "utils" / "workspace_readiness.py").read_text(encoding="utf-8")

    assert "import strata.utils.workspace_context as workspace_context" in source
    assert "import strata.utils.workspace_graph as workspace_graph" in source
    assert "from strata.utils import" not in source
    assert "strata.core" not in source
    assert "strata.commands" not in source


TESTS = [
    test_no_workspace_returns_not_configured,
    test_fully_valid_workspace_returns_ready,
    test_partial_evidence_returns_degraded,
    test_required_repository_missing_blocks_workspace,
    test_optional_repository_missing_degrades_workspace,
    test_stage_failure_isolated_from_other_results,
    test_graph_unavailable_is_safe_failure,
    test_context_unavailable_degrades_without_corrupting_fallback,
    test_budget_exhaustion_degrades_workspace,
    test_error_level_contract_mismatch_is_represented,
    test_diagnostic_cap_is_enforced,
    test_recommended_action_is_deterministic_for_budget_pressure,
    test_single_repository_fallback_and_no_automatic_config_changes,
    test_deterministic_serialization,
    test_scanner_compatible_imports_and_architecture_boundary,
]
