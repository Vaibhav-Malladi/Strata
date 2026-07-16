import json
from pathlib import Path

import strata.utils.config as workflow_config
import strata.utils.workspace_config as workspace_config
import strata.utils.workspace_discovery as workspace_discovery
import strata.utils.workspace_relationships as relationships


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _workspace(*, repositories=None, relationships_value=None):
    return {
        "schema_version": 1,
        "name": "example",
        "repositories": repositories
        or [
            {"id": "frontend", "path": ".", "role": "frontend"},
            {"id": "backend", "path": "../backend", "role": "backend"},
        ],
        "relationships": relationships_value or [],
    }


def _evidence(
    signal_type="local_path_reference",
    source_repository_id="frontend",
    target_repository_id="backend",
    strength="strong",
    summary="local path reference",
):
    return relationships.RelationshipEvidence(
        signal_type=signal_type,
        source_repository_id=source_repository_id,
        source_path="package.json",
        summary=summary,
        strength=strength,
        target_repository_id=target_repository_id,
        referenced_path="../backend",
        metadata={"key": "value"},
    )


def _inferred(**overrides):
    values = {
        "source_repository_id": "frontend",
        "target_repository_id": "backend",
        "relationship_type": "imports_package",
        "origin": "local_path_reference",
        "confidence": "high",
        "confidence_score": 0.8,
        "evidence": (_evidence(),),
    }
    values.update(overrides)
    return values


def _assessment(**kwargs):
    return relationships.build_workspace_relationship_assessment(_workspace(), **kwargs)


def _payload(assessment):
    return assessment.to_dict()


def _diagnostic_codes(assessment):
    return [item["code"] for item in _payload(assessment)["diagnostics"]]


def test_explicit_repository_role_is_authoritative():
    role = _payload(_assessment())["role_assessments"][1]

    assert role["repository_id"] == "frontend"
    assert role["role"] == "frontend"
    assert role["origin"] == "explicit"
    assert role["confidence"] == "high"


def test_explicit_unknown_role_retains_inferred_suggestion_safely():
    workspace = _workspace(
        repositories=[
            {"id": "frontend", "path": ".", "role": "unknown"},
        ]
    )
    discovery = {
        "candidates": [
            {
                "suggested_id": "frontend",
                "probable_role": "frontend",
                "evidence": [
                    {
                        "signal_type": "project_manifest",
                        "source_path": "package.json",
                        "summary": "React dependency.",
                        "strength": "medium",
                    }
                ],
            }
        ]
    }

    role = _payload(
        relationships.build_workspace_relationship_assessment(workspace, discovery_result=discovery)
    )["role_assessments"][0]

    assert role["role"] == "unknown"
    assert role["origin"] == "discovered"
    assert role["suggested_role"] == "frontend"


def test_discovered_role_used_when_no_explicit_repository_exists():
    discovery = {
        "candidates": [
            {
                "suggested_id": "worker",
                "probable_role": "backend",
                "evidence": [
                    {
                        "signal_type": "project_manifest",
                        "source_path": "../worker/go.mod",
                        "summary": "go.mod marker.",
                        "strength": "medium",
                    }
                ],
            }
        ]
    }

    payload = _payload(_assessment(discovery_result=discovery))
    role = next(item for item in payload["role_assessments"] if item["repository_id"] == "worker")

    assert role["role"] == "backend"
    assert role["origin"] == "discovered"


def test_conflicting_inferred_roles_produce_diagnostic():
    discovery = {
        "candidates": [
            {
                "suggested_id": "frontend",
                "probable_role": "backend",
                "evidence": [
                    {
                        "signal_type": "project_manifest",
                        "source_path": "go.mod",
                        "summary": "go.mod marker.",
                        "strength": "medium",
                    }
                ],
            }
        ]
    }

    assessment = _assessment(discovery_result=discovery)

    assert "conflicting_role_evidence" in _diagnostic_codes(assessment)


def test_insufficient_role_evidence_yields_unknown():
    workspace = _workspace(repositories=[{"id": "unknown", "path": ".", "role": "unknown"}])

    role = _payload(relationships.build_workspace_relationship_assessment(workspace))["role_assessments"][0]

    assert role["role"] == "unknown"
    assert role["origin"] == "default"
    assert role["confidence"] == "low"


def test_role_evidence_cap_is_enforced():
    discovery = {
        "candidates": [
            {
                "suggested_id": "worker",
                "probable_role": "backend",
                "evidence": [
                    {
                        "signal_type": f"signal_{index}",
                        "source_path": f"file{index}.json",
                        "summary": f"evidence {index}",
                        "strength": "medium",
                    }
                    for index in range(4)
                ],
            }
        ]
    }

    assessment = _assessment(discovery_result=discovery, max_role_evidence=2)
    role = next(item for item in _payload(assessment)["role_assessments"] if item["repository_id"] == "worker")

    assert len(role["evidence"]) == 2
    assert "role_evidence_truncated" in _diagnostic_codes(assessment)


def test_explicit_relationship_becomes_high_confidence():
    workspace = _workspace(
        relationships_value=[
            {
                "source_repository_id": "frontend",
                "target_repository_id": "backend",
                "relationship_type": "calls_api",
            }
        ]
    )

    relationship = _payload(relationships.build_workspace_relationship_assessment(workspace))["relationships"][0]

    assert relationship["origin"] == "explicit"
    assert relationship["confidence"] == "high"
    assert relationship["confidence_score"] == 1.0


def test_matching_inferred_relationship_deduplicates_into_explicit_relationship():
    workspace = _workspace(
        relationships_value=[
            {
                "source_repository_id": "frontend",
                "target_repository_id": "backend",
                "relationship_type": "imports_package",
            }
        ]
    )

    payload = _payload(
        relationships.build_workspace_relationship_assessment(
            workspace,
            inferred_relationships=(_inferred(),),
        )
    )

    assert len(payload["relationships"]) == 1
    assert payload["relationships"][0]["origin"] == "explicit"


def test_inferred_evidence_may_enrich_explicit_relationship():
    workspace = _workspace(
        relationships_value=[
            {
                "source_repository_id": "frontend",
                "target_repository_id": "backend",
                "relationship_type": "imports_package",
            }
        ]
    )

    relationship = _payload(
        relationships.build_workspace_relationship_assessment(
            workspace,
            inferred_relationships=(_inferred(),),
        )
    )["relationships"][0]

    assert len(relationship["evidence"]) == 2
    assert any(item["signal_type"] == "local_path_reference" for item in relationship["evidence"])


def test_conflicting_inferred_relationship_preserves_explicit_relationship():
    workspace = _workspace(
        relationships_value=[
            {
                "source_repository_id": "frontend",
                "target_repository_id": "backend",
                "relationship_type": "calls_api",
            }
        ]
    )

    assessment = relationships.build_workspace_relationship_assessment(
        workspace,
        inferred_relationships=(_inferred(relationship_type="imports_package"),),
    )
    payload = _payload(assessment)

    assert len(payload["relationships"]) == 1
    assert any(item["origin"] == "explicit" and item["relationship_type"] == "calls_api" for item in payload["relationships"])
    assert "conflicting_inferred_relationship" in _diagnostic_codes(assessment)


def test_matching_inferred_relationships_deduplicate():
    assessment = _assessment(inferred_relationships=(_inferred(), _inferred()))

    assert len(_payload(assessment)["relationships"]) == 1
    assert "duplicate_relationship" in _diagnostic_codes(assessment)


def test_directional_relationships_remain_distinct():
    assessment = _assessment(
        inferred_relationships=(
            _inferred(relationship_type="calls_api"),
            _inferred(
                source_repository_id="backend",
                target_repository_id="frontend",
                relationship_type="calls_api",
                evidence=(
                    _evidence(
                        source_repository_id="backend",
                        target_repository_id="frontend",
                        summary="reverse call",
                    ),
                ),
            ),
        )
    )

    assert len(_payload(assessment)["relationships"]) == 2
    assert "ambiguous_relationship_direction" in _diagnostic_codes(assessment)


def test_shares_contract_with_reverse_duplicate_handling():
    assessment = _assessment(
        inferred_relationships=(
            _inferred(relationship_type="shares_contract_with"),
            _inferred(
                source_repository_id="backend",
                target_repository_id="frontend",
                relationship_type="shares_contract_with",
                evidence=(
                    _evidence(
                        source_repository_id="backend",
                        target_repository_id="frontend",
                        summary="reverse contract",
                    ),
                ),
            ),
        )
    )

    assert len(_payload(assessment)["relationships"]) == 1
    assert "duplicate_relationship" in _diagnostic_codes(assessment)


def test_depends_on_and_imports_package_remain_distinct():
    assessment = _assessment(
        inferred_relationships=(
            _inferred(relationship_type="depends_on"),
            _inferred(relationship_type="imports_package"),
        )
    )

    types = [item["relationship_type"] for item in _payload(assessment)["relationships"]]

    assert types == ["imports_package", "depends_on"]


def test_self_relationship_is_diagnosed():
    assessment = _assessment(
        inferred_relationships=(
            {
                "source_repository_id": "frontend",
                "target_repository_id": "frontend",
                "relationship_type": "depends_on",
            },
        )
    )

    assert "self_relationship" in _diagnostic_codes(assessment)
    assert _payload(assessment)["relationships"] == []


def test_unknown_repository_reference_is_diagnosed():
    assessment = _assessment(inferred_relationships=(_inferred(target_repository_id="missing"),))

    assert "unknown_repository_reference" in _diagnostic_codes(assessment)
    assert _payload(assessment)["relationships"] == []


def test_missing_target_and_unsupported_relationship_type_are_diagnosed():
    assessment = _assessment(
        inferred_relationships=(
            {
                "source_repository_id": "frontend",
                "relationship_type": "depends_on",
            },
            {
                "source_repository_id": "frontend",
                "target_repository_id": "backend",
                "relationship_type": "syncs",
            },
        )
    )

    assert "missing_relationship_target" in _diagnostic_codes(assessment)
    assert "unsupported_relationship_type" in _diagnostic_codes(assessment)


def test_relationship_evidence_cap_is_enforced():
    inferred = _inferred(
        evidence=tuple(
            _evidence(signal_type=f"signal_{index}", summary=f"evidence {index}")
            for index in range(4)
        )
    )

    assessment = _assessment(
        inferred_relationships=(inferred,),
        max_evidence_per_relationship=2,
    )

    relationship = _payload(assessment)["relationships"][0]

    assert len(relationship["evidence"]) == 2
    assert "relationship_evidence_truncated" in _diagnostic_codes(assessment)


def test_relationship_candidate_cap_is_enforced():
    workspace = _workspace(
        repositories=[
            {"id": "frontend", "path": ".", "role": "frontend"},
            {"id": "backend", "path": "../backend", "role": "backend"},
            {"id": "worker", "path": "../worker", "role": "worker"},
        ]
    )

    assessment = relationships.build_workspace_relationship_assessment(
        workspace,
        inferred_relationships=(
            _inferred(target_repository_id="backend"),
            _inferred(target_repository_id="worker"),
        ),
        max_relationships=1,
    )

    assert len(_payload(assessment)["relationships"]) == 1
    assert "relationship_candidate_cap_reached" in _diagnostic_codes(assessment)


def test_diagnostic_cap_is_enforced():
    assessment = _assessment(
        inferred_relationships=(
            _inferred(target_repository_id="missing-a"),
            _inferred(target_repository_id="missing-b"),
            _inferred(target_repository_id="missing-c"),
        ),
        max_diagnostics=2,
    )

    codes = _diagnostic_codes(assessment)

    assert len(codes) == 2
    assert "diagnostic_cap_reached" in codes


def test_stable_relationship_and_evidence_identity():
    evidence = _evidence()
    relationship = relationships.RelationshipCandidate(
        source_repository_id="backend",
        target_repository_id="frontend",
        relationship_type="shares_contract_with",
        origin="inferred",
        confidence="medium",
        confidence_score=0.5,
        evidence=(evidence,),
    )

    assert relationships.evidence_identity_key(evidence) == relationships.evidence_identity_key(_evidence())
    assert relationships.relationship_identity_key(relationship) == (
        "backend",
        "frontend",
        "shares_contract_with",
    )
    assert relationships.relationship_identity_key(_inferred(relationship_type="shares_contract_with")) == (
        "backend",
        "frontend",
        "shares_contract_with",
    )


def test_deterministic_serialization_and_sorting():
    first = _payload(
        _assessment(
            inferred_relationships=(
                _inferred(target_repository_id="backend"),
                _inferred(
                    source_repository_id="backend",
                    target_repository_id="frontend",
                    relationship_type="depends_on",
                    evidence=(
                        _evidence(
                            source_repository_id="backend",
                            target_repository_id="frontend",
                            summary="reverse",
                        ),
                    ),
                ),
            )
        )
    )
    second = _payload(
        _assessment(
            inferred_relationships=(
                _inferred(
                    source_repository_id="backend",
                    target_repository_id="frontend",
                    relationship_type="depends_on",
                    evidence=(
                        _evidence(
                            source_repository_id="backend",
                            target_repository_id="frontend",
                            summary="reverse",
                        ),
                    ),
                ),
                _inferred(target_repository_id="backend"),
            )
        )
    )

    assert first == second
    assert list(first) == list(relationships.ASSESSMENT_FIELD_ORDER)
    assert list(first["role_assessments"][0]) == list(relationships.ROLE_ASSESSMENT_FIELD_ORDER)
    assert list(first["relationships"][0]) == list(relationships.RELATIONSHIP_CANDIDATE_FIELD_ORDER)
    assert list(first["relationships"][0]["evidence"][0]) == list(relationships.EVIDENCE_FIELD_ORDER)
    assert json.loads(json.dumps(first, allow_nan=False)) == first


def test_q1_configuration_round_trip_remains_unchanged():
    workspace = _workspace()

    normalized = workflow_config.validate_config({"workspace": workspace})

    assert normalized["workspace"]["repositories"][0]["id"] == "backend"
    assert normalized["workspace"]["repositories"][1]["id"] == "frontend"


def test_q2_discovery_serialization_remains_unchanged():
    evidence = workspace_discovery.WorkspaceDiscoveryEvidence(
        signal_type="local_path_reference",
        source_path="package.json",
        summary="package.json references local dependency.",
        strength="strong",
        referenced_path="../backend",
    )
    suggestion = workspace_discovery.WorkspaceRepositorySuggestion(
        path="../backend",
        suggested_id="backend",
        display_name="backend",
        probable_role="backend",
        confidence="high",
        confidence_score=0.8,
        evidence=(evidence,),
    )
    result = workspace_discovery.WorkspaceDiscoveryResult(
        repository_root=".",
        search_root="..",
        candidates=(suggestion,),
    )

    payload = result.to_dict()

    assert list(payload) == list(workspace_discovery.DISCOVERY_RESULT_FIELD_ORDER)
    assert payload["candidates"][0]["evidence"][0]["referenced_path"] == "../backend"


def test_discovery_result_can_create_relationship_candidate():
    evidence = workspace_discovery.WorkspaceDiscoveryEvidence(
        signal_type="local_path_reference",
        source_path="package.json",
        summary="package.json references local dependency.",
        strength="strong",
        referenced_path="../backend",
    )
    suggestion = workspace_discovery.WorkspaceRepositorySuggestion(
        path="../backend",
        suggested_id="backend",
        display_name="backend",
        probable_role="backend",
        confidence="high",
        confidence_score=0.8,
        evidence=(evidence,),
    )
    discovery = workspace_discovery.WorkspaceDiscoveryResult(
        repository_root=".",
        search_root="..",
        candidates=(suggestion,),
    )

    payload = _payload(_assessment(discovery_result=discovery))

    assert payload["relationships"][0]["relationship_type"] == "imports_package"
    assert payload["relationships"][0]["origin"] == "local_path_reference"


def test_scanner_compatible_imports_and_architecture_boundary():
    source = (PROJECT_ROOT / "strata" / "utils" / "workspace_relationships.py").read_text(
        encoding="utf-8"
    )

    assert "import strata.utils.workspace_config as workspace_config" in source
    assert "import strata.utils.workspace_discovery as workspace_discovery" in source
    assert "from strata.utils import" not in source
    assert "strata.commands" not in source
    assert "strata.core" not in source


def test_workspace_q3_docs_define_contract_only_scope():
    content = (PROJECT_ROOT / "docs" / "roadmap" / "workspace-intelligence.md").read_text(
        encoding="utf-8"
    )

    assert "Q3" in content
    assert "canonical role assessments" in content
    assert "canonical relationship candidates" in content
    assert "does not build a dependency graph" in content
    assert "does not extract cross-repository source references" in content


TESTS = [
    test_explicit_repository_role_is_authoritative,
    test_explicit_unknown_role_retains_inferred_suggestion_safely,
    test_discovered_role_used_when_no_explicit_repository_exists,
    test_conflicting_inferred_roles_produce_diagnostic,
    test_insufficient_role_evidence_yields_unknown,
    test_role_evidence_cap_is_enforced,
    test_explicit_relationship_becomes_high_confidence,
    test_matching_inferred_relationship_deduplicates_into_explicit_relationship,
    test_inferred_evidence_may_enrich_explicit_relationship,
    test_conflicting_inferred_relationship_preserves_explicit_relationship,
    test_matching_inferred_relationships_deduplicate,
    test_directional_relationships_remain_distinct,
    test_shares_contract_with_reverse_duplicate_handling,
    test_depends_on_and_imports_package_remain_distinct,
    test_self_relationship_is_diagnosed,
    test_unknown_repository_reference_is_diagnosed,
    test_missing_target_and_unsupported_relationship_type_are_diagnosed,
    test_relationship_evidence_cap_is_enforced,
    test_relationship_candidate_cap_is_enforced,
    test_diagnostic_cap_is_enforced,
    test_stable_relationship_and_evidence_identity,
    test_deterministic_serialization_and_sorting,
    test_q1_configuration_round_trip_remains_unchanged,
    test_q2_discovery_serialization_remains_unchanged,
    test_discovery_result_can_create_relationship_candidate,
    test_scanner_compatible_imports_and_architecture_boundary,
    test_workspace_q3_docs_define_contract_only_scope,
]
