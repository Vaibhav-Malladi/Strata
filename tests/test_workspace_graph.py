import json
from pathlib import Path

import strata.utils.workspace_config as workspace_config
import strata.utils.workspace_contracts as workspace_contracts
import strata.utils.workspace_discovery as workspace_discovery
import strata.utils.workspace_graph as workspace_graph
import strata.utils.workspace_relationships as workspace_relationships


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _repo(repository_id, path, role, **overrides):
    values = {"id": repository_id, "path": path, "role": role}
    values.update(overrides)
    return values


def _workspace(*, repositories=None, relationships_value=None, shared_contracts=None):
    return {
        "schema_version": 1,
        "name": "example",
        "repositories": repositories
        or [
            _repo("frontend", ".", "frontend", display_name="Frontend", known_ports=[3000], known_urls=["http://localhost:3000"]),
            _repo("backend", "../backend", "backend", display_name="Backend", known_ports=[8080], known_urls=["http://localhost:8080"]),
            _repo("worker", "../worker", "worker", display_name="Worker"),
        ],
        "relationships": relationships_value or [],
        "shared_contracts": shared_contracts or [],
    }


def _evidence(
    *,
    signal_type="workspace_file",
    source_repository_id="frontend",
    target_repository_id="backend",
    source_path="workspace.yml",
    summary="relationship evidence",
    strength="strong",
    referenced_path="../backend",
    metadata=None,
):
    return workspace_relationships.RelationshipEvidence(
        signal_type=signal_type,
        source_repository_id=source_repository_id,
        source_path=source_path,
        summary=summary,
        strength=strength,
        target_repository_id=target_repository_id,
        referenced_path=referenced_path,
        metadata=metadata or {},
    )


def _relationship(**overrides):
    values = {
        "source_repository_id": "frontend",
        "target_repository_id": "backend",
        "relationship_type": "calls_api",
        "origin": "inferred",
        "confidence": "high",
        "confidence_score": 0.8,
        "evidence": (_evidence(),),
        "warnings": (),
        "description": "frontend calls backend",
    }
    values.update(overrides)
    return values


def _assessment(*, roles=(), relationships=()):
    return {
        "role_assessments": list(roles),
        "relationships": list(relationships),
        "diagnostics": [],
    }


def _role(repository_id="frontend", role="frontend", **overrides):
    values = {
        "repository_id": repository_id,
        "role": role,
        "origin": "inferred",
        "confidence": "medium",
        "confidence_score": 0.55,
        "evidence": (_evidence(source_repository_id=repository_id, target_repository_id=None, summary="role evidence"),),
        "warnings": (),
        "suggested_role": None,
    }
    values.update(overrides)
    return values


def _discovery(candidate_id="frontend", path=".", role="frontend", **overrides):
    evidence = workspace_discovery.WorkspaceDiscoveryEvidence(
        signal_type="project_manifest",
        source_path="package.json",
        summary="Manifest suggests repository role.",
        strength="medium",
    )
    candidate = workspace_discovery.WorkspaceRepositorySuggestion(
        path=path,
        suggested_id=candidate_id,
        display_name=overrides.pop("display_name", candidate_id.title()),
        probable_role=role,
        confidence=overrides.pop("confidence", "medium"),
        confidence_score=overrides.pop("confidence_score", 0.55),
        evidence=overrides.pop("evidence", (evidence,)),
        **overrides,
    )
    return workspace_discovery.WorkspaceDiscoveryResult(
        repository_root=".",
        search_root="..",
        candidates=(candidate,),
    )


def _contract_finding(name="auth-header", status="consistent", repositories=("frontend", "backend"), confidence_score=0.9):
    return {
        "name": name,
        "status": status,
        "confidence_score": confidence_score,
        "location_findings": [
            {"repository_id": repository_id, "path": f"{repository_id}/constants.ts", "status": status}
            for repository_id in repositories
        ],
        "evidence": (_evidence(signal_type="shared_contract", summary=f"{name} contract evidence"),),
        "expected_value": "super-secret-token",
        "distinct_observed_values": ["super-secret-token"],
    }


def _contract_result_object():
    locations = tuple(
        workspace_contracts.ContractLocationFinding(
            contract_name="auth-header",
            repository_id=repository_id,
            path=f"{repository_id}/constants.ts",
            status=workspace_contracts.STATUS_CONSISTENT,
            expected_value="Authorization",
            allowed_values=(),
            observed_values=("Authorization",),
            normalized_expected="Authorization",
            normalized_allowed_values=(),
            normalized_observed_values=("Authorization",),
            matching_reference_ids=(f"{repository_id}:auth",),
            confidence="high",
            confidence_score=0.9,
            evidence=(_evidence(signal_type="shared_contract", source_repository_id=repository_id, summary="contract object evidence"),),
        )
        for repository_id in ("frontend", "backend")
    )
    return workspace_contracts.SharedContractComparisonResult(
        contract_findings=(
            workspace_contracts.SharedContractFinding(
                name="auth-header",
                contract_type=workspace_config.SHARED_CONTRACT_TYPE_AUTH_HEADER,
                severity=workspace_config.CONTRACT_SEVERITY_WARNING,
                normalization=workspace_config.CONTRACT_NORMALIZATION_EXACT,
                status=workspace_contracts.STATUS_CONSISTENT,
                expected_value="Authorization",
                allowed_values=(),
                location_findings=locations,
                distinct_observed_values=("Authorization",),
                confidence="high",
                confidence_score=0.9,
                evidence=(_evidence(signal_type="shared_contract", summary="contract finding evidence"),),
            ),
        )
    )


def _graph(workspace=None, **kwargs):
    return workspace_graph.build_workspace_dependency_graph(workspace or _workspace(), **kwargs)


def _payload(result):
    return workspace_graph.workspace_dependency_graph_to_dict(result)


def _nodes(result):
    return {item["repository_id"]: item for item in _payload(result)["nodes"]}


def _edges(result):
    return _payload(result)["edges"]


def _edge(result, source="frontend", target="backend", relationship_type="calls_api"):
    for item in _edges(result):
        if (
            item["source_repository_id"] == source
            and item["target_repository_id"] == target
            and item["relationship_type"] == relationship_type
        ):
            return item
    raise AssertionError(f"edge not found: {source} {relationship_type} {target}")


def _codes(result):
    return [item["code"] for item in _payload(result)["diagnostics"]]


def _unresolved_reasons(result):
    return [item["reason"] for item in _payload(result)["unresolved_relationships"]]


def test_configured_repositories_become_authoritative_nodes():
    payload = _payload(_graph())

    assert [node["repository_id"] for node in payload["nodes"]] == ["backend", "frontend", "worker"]
    assert _nodes(_graph())["frontend"]["path"] == "."
    assert _nodes(_graph())["frontend"]["known_ports"] == [3000]


def test_q3_role_assessment_enriches_unknown_node_metadata():
    workspace = _workspace(repositories=[_repo("frontend", ".", "unknown")])
    result = _graph(
        workspace,
        relationship_assessment=_assessment(
            roles=(
                _role(
                    repository_id="frontend",
                    role="frontend",
                    suggested_role="frontend",
                    confidence="medium",
                    confidence_score=0.55,
                ),
            )
        ),
    )

    node = _nodes(result)["frontend"]
    assert node["role"] == "unknown"
    assert node["metadata"]["suggested_role"] == "frontend"
    assert node["role_confidence_score"] == 0.55


def test_explicit_role_overrides_conflicting_inferred_role():
    result = _graph(
        relationship_assessment=_assessment(
            roles=(_role(repository_id="frontend", role="backend", confidence_score=0.7),)
        )
    )

    assert _nodes(result)["frontend"]["role"] == "frontend"
    assert "conflicting_node_role" in _codes(result)


def test_discovery_enriches_configured_node_without_overwriting_identity():
    result = _graph(discovery_result=_discovery("frontend", "../different", "backend"))

    node = _nodes(result)["frontend"]
    assert node["path"] == "."
    assert node["configured"] is True
    assert node["discovered"] is True
    assert node["metadata"]["discovery_confidence"] == "medium"


def test_discovered_repository_is_omitted_by_default():
    result = _graph(discovery_result=_discovery("mobile", "../mobile", "frontend"))

    assert "mobile" not in _nodes(result)


def test_include_discovered_adds_suggested_repository_node():
    result = _graph(discovery_result=_discovery("mobile", "../mobile", "frontend"), include_discovered=True)

    node = _nodes(result)["mobile"]
    assert node["configured"] is False
    assert node["discovered"] is True
    assert node["role"] == "frontend"


def test_duplicate_repository_id_and_path_are_diagnosed():
    workspace = _workspace(
        repositories=[
            _repo("frontend", ".", "frontend"),
            _repo("frontend", "../duplicate", "backend"),
            _repo("backend", ".", "backend"),
        ]
    )

    codes = _codes(_graph(workspace))

    assert "duplicate_repository_id" in codes
    assert "duplicate_repository_path" in codes


def test_node_evidence_cap_is_enforced():
    evidence = tuple(
        _evidence(source_repository_id="frontend", source_path=f"src/{index}.ts", target_repository_id=None)
        for index in range(4)
    )
    result = _graph(
        relationship_assessment=_assessment(
            roles=(_role(repository_id="frontend", evidence=evidence),)
        ),
        max_evidence_per_node=2,
    )

    assert len(_nodes(result)["frontend"]["evidence"]) == 2
    assert "graph_evidence_truncated" in _codes(result)


def test_explicit_relationship_becomes_high_confidence_edge():
    workspace = _workspace(
        relationships_value=[
            {
                "source_repository_id": "frontend",
                "target_repository_id": "backend",
                "relationship_type": "calls_api",
                "description": "frontend calls backend",
            }
        ]
    )

    edge = _edge(_graph(workspace))

    assert edge["explicit"] is True
    assert edge["origin"] == "explicit"
    assert edge["confidence"] == "high"
    assert edge["confidence_score"] == 1.0


def test_matching_inferred_edge_enriches_explicit_edge_without_lowering_confidence():
    workspace = _workspace(
        relationships_value=[
            {
                "source_repository_id": "frontend",
                "target_repository_id": "backend",
                "relationship_type": "calls_api",
            }
        ]
    )
    result = _graph(
        workspace,
        reference_relationship_hints=(_relationship(confidence="low", confidence_score=0.25),),
    )

    edge = _edge(result)
    assert len(_edges(result)) == 1
    assert edge["explicit"] is True
    assert edge["inferred"] is True
    assert edge["confidence_score"] == 1.0
    assert len(edge["evidence"]) == 2


def test_directional_reverse_edges_remain_separate():
    result = _graph(
        reference_relationship_hints=(
            _relationship(source_repository_id="frontend", target_repository_id="backend"),
            _relationship(source_repository_id="backend", target_repository_id="frontend"),
        )
    )

    assert len([edge for edge in _edges(result) if edge["relationship_type"] == "calls_api"]) == 2


def test_symmetric_shared_contract_edges_deduplicate_reverse_direction():
    result = _graph(
        reference_relationship_hints=(
            _relationship(relationship_type="shares_contract_with", source_repository_id="frontend", target_repository_id="backend"),
            _relationship(relationship_type="shares_contract_with", source_repository_id="backend", target_repository_id="frontend"),
        )
    )

    edges = [edge for edge in _edges(result) if edge["relationship_type"] == "shares_contract_with"]
    assert len(edges) == 1
    assert edges[0]["source_repository_id"] == "backend"
    assert edges[0]["target_repository_id"] == "frontend"


def test_distinct_relationship_types_between_same_pair_remain_separate():
    result = _graph(
        reference_relationship_hints=(
            _relationship(relationship_type="depends_on"),
            _relationship(relationship_type="imports_package"),
        )
    )

    assert sorted(edge["relationship_type"] for edge in _edges(result)) == ["depends_on", "imports_package"]


def test_q4_hints_map_and_weak_duplicates_do_not_promote_to_high_confidence():
    result = _graph(
        reference_relationship_hints=(
            _relationship(
                relationship_type="embeds_iframe",
                confidence="low",
                confidence_score=0.25,
                evidence=(_evidence(signal_type="iframe_src", strength="weak", summary="weak iframe hint"),),
            ),
            _relationship(
                relationship_type="embeds_iframe",
                confidence="low",
                confidence_score=0.3,
                evidence=(_evidence(signal_type="iframe_src", strength="weak", source_path="src/other.ts", summary="other weak iframe hint"),),
            ),
        )
    )

    edge = _edge(result, relationship_type="embeds_iframe")
    assert edge["confidence"] == "low"
    assert edge["confidence_score"] == 0.35


def test_untargeted_hint_becomes_unresolved_relationship():
    result = _graph(reference_relationship_hints=(_relationship(target_repository_id=""),))

    assert "target_repository_missing" in _unresolved_reasons(result)
    assert _edges(result) == []


def test_consistent_multi_repository_contract_creates_shared_contract_edge():
    result = _graph(contract_findings=(_contract_finding(),))

    edge = _edge(result, source="backend", target="frontend", relationship_type="shares_contract_with")
    assert edge["contract_names"] == ["auth-header"]
    assert edge["confidence"] == "high"
    assert edge["metadata"]["contract_status"] == "consistent"


def test_inconsistent_contract_creates_degraded_shared_contract_edge():
    result = _graph(
        contract_findings=(
            _contract_finding(status="inconsistent", confidence_score=0.8),
        )
    )

    edge = _edge(result, source="backend", target="frontend", relationship_type="shares_contract_with")
    assert edge["confidence"] == "medium"
    assert "shared contract auth-header is inconsistent" in edge["warnings"]
    assert "contract_edge_degraded" in _codes(result)


def test_missing_and_single_repository_contracts_create_no_edges():
    result = _graph(
        contract_findings=(
            _contract_finding(status="missing"),
            _contract_finding(name="single", repositories=("frontend",)),
        )
    )

    assert _edges(result) == []


def test_sensitive_contract_values_are_not_exposed_in_graph_payload():
    payload_text = json.dumps(_payload(_graph(contract_findings=(_contract_finding(),))), sort_keys=True)

    assert "super-secret-token" not in payload_text
    assert "auth-header" in payload_text


def test_acyclic_graph_reports_roots_leaves_and_no_cycles():
    result = _graph(
        reference_relationship_hints=(
            _relationship(source_repository_id="frontend", target_repository_id="backend", relationship_type="calls_api"),
            _relationship(source_repository_id="backend", target_repository_id="worker", relationship_type="depends_on"),
        )
    )
    payload = _payload(result)

    assert payload["cycles"] == []
    assert payload["strongly_connected_components"] == []
    assert payload["root_repository_ids"] == ["frontend"]
    assert payload["leaf_repository_ids"] == ["worker"]


def test_two_node_cycle_and_component_are_detected():
    result = _graph(
        reference_relationship_hints=(
            _relationship(source_repository_id="frontend", target_repository_id="backend", relationship_type="calls_api"),
            _relationship(source_repository_id="backend", target_repository_id="frontend", relationship_type="depends_on"),
        )
    )
    payload = _payload(result)

    assert len(payload["cycles"]) == 1
    assert payload["strongly_connected_components"][0]["repository_ids"] == ["backend", "frontend"]
    assert "cycle_detected" in _codes(result)


def test_three_node_cycle_is_reported_deterministically():
    result = _graph(
        reference_relationship_hints=(
            _relationship(source_repository_id="frontend", target_repository_id="backend", relationship_type="calls_api"),
            _relationship(source_repository_id="backend", target_repository_id="worker", relationship_type="depends_on"),
            _relationship(source_repository_id="worker", target_repository_id="frontend", relationship_type="proxies_to"),
        )
    )

    assert _payload(result)["strongly_connected_components"][0]["repository_ids"] == ["backend", "frontend", "worker"]
    assert _payload(result)["summary"]["cycle_count"] == 1


def test_shared_contract_edges_are_excluded_from_directed_cycles():
    result = _graph(
        reference_relationship_hints=(
            _relationship(relationship_type="shares_contract_with", source_repository_id="frontend", target_repository_id="backend"),
            _relationship(relationship_type="shares_contract_with", source_repository_id="backend", target_repository_id="frontend"),
        )
    )

    assert _payload(result)["cycles"] == []
    assert _payload(result)["strongly_connected_components"] == []


def test_complementary_message_receive_edges_do_not_double_count_cycles():
    result = _graph(
        reference_relationship_hints=(
            _relationship(relationship_type="sends_messages_to", source_repository_id="frontend", target_repository_id="backend"),
            _relationship(relationship_type="receives_messages_from", source_repository_id="backend", target_repository_id="frontend"),
        )
    )

    assert _payload(result)["cycles"] == []
    assert len(_edges(result)) == 2


def test_isolated_repository_diagnostic_is_reported():
    result = _graph(reference_relationship_hints=(_relationship(),))

    assert _payload(result)["isolated_repository_ids"] == ["worker"]
    assert "isolated_repository" in _codes(result)


def test_unknown_source_target_both_and_ambiguous_targets_are_unresolved():
    result = _graph(
        reference_relationship_hints=(
            _relationship(source_repository_id="missing", target_repository_id="backend"),
            _relationship(source_repository_id="frontend", target_repository_id="missing"),
            _relationship(source_repository_id="missing-a", target_repository_id="missing-b"),
            _relationship(source_repository_id="frontend", target_repository_id="backend", metadata={"ambiguous_target": True}),
        )
    )

    assert sorted(_unresolved_reasons(result)) == [
        "ambiguous_target",
        "both_repositories_missing",
        "source_repository_missing",
        "target_repository_missing",
    ]


def test_unsupported_and_self_relationships_are_unresolved():
    result = _graph(
        reference_relationship_hints=(
            _relationship(relationship_type="uses_magic"),
            _relationship(source_repository_id="frontend", target_repository_id="frontend", relationship_type="calls_api"),
        )
    )

    assert sorted(_unresolved_reasons(result)) == ["self_relationship", "unsupported_relationship_type"]
    assert "unsupported_relationship_type" in _codes(result)
    assert "self_relationship_rejected" in _codes(result)


def test_edge_and_unresolved_caps_are_enforced():
    result = _graph(
        reference_relationship_hints=(
            _relationship(relationship_type="calls_api"),
            _relationship(relationship_type="depends_on"),
            _relationship(relationship_type="imports_package"),
        ),
        max_edges=1,
        max_unresolved_relationships=1,
    )

    assert len(_edges(result)) == 1
    assert _unresolved_reasons(result) == ["edge_cap_reached"]
    assert "graph_edge_cap_reached" in _codes(result)


def test_edge_evidence_contract_name_and_diagnostic_caps_are_enforced():
    evidence = tuple(
        _evidence(source_path=f"src/{index}.ts", summary=f"evidence {index}")
        for index in range(4)
    )
    result = _graph(
        reference_relationship_hints=(
            _relationship(evidence=evidence, contract_names=("z", "a", "b")),
        ),
        max_evidence_per_edge=2,
        max_contract_names_per_edge=2,
        max_diagnostics=1,
    )

    edge = _edge(result)
    assert len(edge["evidence"]) == 2
    assert edge["contract_names"] == ["a", "b"]
    assert _codes(result) == ["graph_diagnostic_cap_reached"]


def test_component_and_cycle_caps_are_enforced():
    workspace = _workspace(
        repositories=[
            _repo("frontend", ".", "frontend"),
            _repo("backend", "../backend", "backend"),
            _repo("worker", "../worker", "worker"),
            _repo("gateway", "../gateway", "gateway"),
        ]
    )
    result = _graph(
        workspace,
        reference_relationship_hints=(
            _relationship(source_repository_id="frontend", target_repository_id="backend", relationship_type="calls_api"),
            _relationship(source_repository_id="backend", target_repository_id="frontend", relationship_type="depends_on"),
            _relationship(source_repository_id="worker", target_repository_id="gateway", relationship_type="calls_api"),
            _relationship(source_repository_id="gateway", target_repository_id="worker", relationship_type="depends_on"),
        ),
        max_strongly_connected_components=2,
        max_cycles=1,
    )

    payload = _payload(result)
    assert len(payload["strongly_connected_components"]) == 2
    assert len(payload["cycles"]) == 1


def test_serialization_summary_and_metadata_are_stable():
    result = _graph(
        reference_relationship_hints=(
            _relationship(relationship_type="depends_on"),
            _relationship(relationship_type="calls_api", confidence="medium", confidence_score=0.55),
        )
    )
    first = _payload(result)
    second = _payload(_graph(reference_relationship_hints=(_relationship(relationship_type="depends_on"), _relationship(relationship_type="calls_api", confidence="medium", confidence_score=0.55))))

    assert first == second
    assert list(first) == list(workspace_graph.RESULT_FIELD_ORDER)
    assert list(first["summary"]) == list(workspace_graph.SUMMARY_FIELD_ORDER)
    assert first["summary"]["node_count"] == 3
    assert first["metadata"]["dependency_edge_types"] == list(workspace_graph.DEPENDENCY_RELATIONSHIP_TYPES)


def test_q1_q2_q3_q4_q5_compatibility():
    workspace = _workspace(
        shared_contracts=[
            {
                "name": "auth-header",
                "contract_type": "auth_header",
                "expected_value": "Authorization",
                "locations": [
                    {"repository_id": "frontend", "path": "src/constants.ts", "symbol": "AUTH_HEADER"},
                    {"repository_id": "backend", "path": "app/constants.py", "symbol": "AUTH_HEADER"},
                ],
            }
        ]
    )
    normalized = workspace_config.validate_workspace_config(workspace)
    assessment = workspace_relationships.WorkspaceRelationshipAssessment(
        relationships=(
            workspace_relationships.RelationshipCandidate(
                source_repository_id="frontend",
                target_repository_id="backend",
                relationship_type="calls_api",
                origin="workspace_file",
                confidence="high",
                confidence_score=0.8,
                evidence=(_evidence(),),
            ),
        )
    )
    result = _graph(normalized, relationship_assessment=assessment, discovery_result=_discovery(), contract_findings=_contract_result_object())

    assert _edge(result)["relationship_type"] == "calls_api"
    assert _edge(result, source="backend", target="frontend", relationship_type="shares_contract_with")["contract_names"] == ["auth-header"]


def test_scanner_compatible_imports_and_architecture_boundary():
    source = (PROJECT_ROOT / "strata" / "utils" / "workspace_graph.py").read_text(
        encoding="utf-8"
    )

    assert "import strata.utils.workspace_config as workspace_config" in source
    assert "import strata.utils.workspace_relationships as workspace_relationships" in source
    assert "import strata.utils.workspace_contracts as workspace_contracts" in source
    assert "from strata.utils import" not in source
    assert "strata.commands" not in source
    assert "strata.core" not in source


def test_workspace_q6_docs_define_graph_combiner_scope():
    content = (PROJECT_ROOT / "docs" / "roadmap" / "workspace-intelligence.md").read_text(
        encoding="utf-8"
    )

    assert "Q6" in content
    assert "workspace dependency graph" in content
    assert "Q6 reads no files" in content
    assert "Q6 writes no graph files yet" in content
    assert "Q6 does not add graph data to AI context" in content
    assert "Q6 does not trace user journeys" in content


TESTS = [
    test_configured_repositories_become_authoritative_nodes,
    test_q3_role_assessment_enriches_unknown_node_metadata,
    test_explicit_role_overrides_conflicting_inferred_role,
    test_discovery_enriches_configured_node_without_overwriting_identity,
    test_discovered_repository_is_omitted_by_default,
    test_include_discovered_adds_suggested_repository_node,
    test_duplicate_repository_id_and_path_are_diagnosed,
    test_node_evidence_cap_is_enforced,
    test_explicit_relationship_becomes_high_confidence_edge,
    test_matching_inferred_edge_enriches_explicit_edge_without_lowering_confidence,
    test_directional_reverse_edges_remain_separate,
    test_symmetric_shared_contract_edges_deduplicate_reverse_direction,
    test_distinct_relationship_types_between_same_pair_remain_separate,
    test_q4_hints_map_and_weak_duplicates_do_not_promote_to_high_confidence,
    test_untargeted_hint_becomes_unresolved_relationship,
    test_consistent_multi_repository_contract_creates_shared_contract_edge,
    test_inconsistent_contract_creates_degraded_shared_contract_edge,
    test_missing_and_single_repository_contracts_create_no_edges,
    test_sensitive_contract_values_are_not_exposed_in_graph_payload,
    test_acyclic_graph_reports_roots_leaves_and_no_cycles,
    test_two_node_cycle_and_component_are_detected,
    test_three_node_cycle_is_reported_deterministically,
    test_shared_contract_edges_are_excluded_from_directed_cycles,
    test_complementary_message_receive_edges_do_not_double_count_cycles,
    test_isolated_repository_diagnostic_is_reported,
    test_unknown_source_target_both_and_ambiguous_targets_are_unresolved,
    test_unsupported_and_self_relationships_are_unresolved,
    test_edge_and_unresolved_caps_are_enforced,
    test_edge_evidence_contract_name_and_diagnostic_caps_are_enforced,
    test_component_and_cycle_caps_are_enforced,
    test_serialization_summary_and_metadata_are_stable,
    test_q1_q2_q3_q4_q5_compatibility,
    test_scanner_compatible_imports_and_architecture_boundary,
    test_workspace_q6_docs_define_graph_combiner_scope,
]
