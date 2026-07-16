import json
from pathlib import Path

import strata.utils.workspace_config as workspace_config
import strata.utils.workspace_context as workspace_context
import strata.utils.workspace_contracts as workspace_contracts
import strata.utils.workspace_graph as workspace_graph
import strata.utils.workspace_readiness as workspace_readiness
import strata.utils.workspace_references as workspace_references
import strata.utils.workspace_relationships as workspace_relationships


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = PROJECT_ROOT / "tests" / "fixtures" / "workspaces"


def _repo(repository_id, path, role, **overrides):
    values = {"id": repository_id, "path": path, "role": role}
    values.update(overrides)
    return values


def _workspace(repositories, *, relationships=None, shared_contracts=None):
    return {
        "schema_version": 1,
        "name": "synthetic",
        "repositories": repositories,
        "relationships": relationships or [],
        "shared_contracts": shared_contracts or [],
    }


def _extract(repository_id, root, selected, known):
    return workspace_references.extract_workspace_references(
        repository_id,
        root,
        selected,
        known_repositories=known,
        max_files=4,
        max_references=20,
    )


def _pipeline(workspace, task, *, reference_results=(), contract_result=None, relationship_hints=(), required_repository_ids=(), budget_profile=None):
    normalized = workspace_config.validate_workspace_config(workspace)
    references = tuple(reference for result in reference_results for reference in result.references)
    hints = (*workspace_references.references_to_relationship_hints(references), *relationship_hints)
    assessment = workspace_relationships.build_workspace_relationship_assessment(normalized, inferred_relationships=hints)
    contract_result = contract_result or workspace_contracts.compare_shared_contracts(normalized, references)
    graph = workspace_graph.build_workspace_dependency_graph(
        normalized,
        relationship_assessment=assessment,
        reference_relationship_hints=hints,
        contract_findings=contract_result,
    )
    context = workspace_context.build_workspace_context_representation(
        task,
        graph,
        contract_findings=contract_result,
        diagnostics=tuple(diagnostic for result in reference_results for diagnostic in result.diagnostics),
        budget_profile=budget_profile,
    )
    readiness = workspace_readiness.build_workspace_readiness(
        workspace_config=normalized,
        relationship_assessment=assessment,
        reference_extraction={"diagnostics": [diagnostic.to_dict() for result in reference_results for diagnostic in result.diagnostics]},
        contract_comparison=contract_result,
        graph=graph,
        context_representation=context,
        required_repository_ids=required_repository_ids,
    )
    return normalized, assessment, contract_result, graph, context, readiness


def _payloads(result):
    _, assessment, contracts, graph, context, readiness = result
    return {
        "assessment": assessment.to_dict(),
        "contracts": contracts.to_dict(),
        "graph": graph.to_dict(),
        "context": context.to_dict(),
        "readiness": readiness.to_dict(),
    }


def _edge(graph, relationship_type):
    for edge in graph.to_dict()["edges"]:
        if edge["relationship_type"] == relationship_type:
            return edge
    raise AssertionError(relationship_type)


def test_scenario_angular_frontend_python_backend():
    root = FIXTURES / "angular_python"
    workspace = _workspace(
        [
            _repo("frontend", "frontend", "frontend", known_ports=[4200]),
            _repo("backend", "backend", "backend", known_ports=[8080], known_urls=["http://localhost:8080"]),
        ],
        shared_contracts=[
            {
                "name": "auth-header",
                "contract_type": "auth_header",
                "expected_value": "Authorization",
                "locations": [
                    {"repository_id": "frontend", "path": "src/app/api.ts", "symbol": "AUTH_HEADER"},
                    {"repository_id": "backend", "path": "app/constants.py", "symbol": "AUTH_HEADER"},
                ],
            }
        ],
    )
    refs = (
        _extract("frontend", root / "frontend", ["src/app/api.ts"], workspace["repositories"]),
        _extract("backend", root / "backend", ["app/constants.py"], workspace["repositories"]),
    )

    _, _, contracts, graph, context, readiness = _pipeline(workspace, "fix angular auth header", reference_results=refs)

    assert _edge(graph, "calls_api")["target_repository_id"] == "backend"
    assert _edge(graph, "shares_contract_with")["contract_names"] == ["auth-header"]
    assert context.to_dict()["relationships"]
    assert readiness.to_dict()["status"] in {"ready", "degraded"}
    assert contracts.to_dict()["contract_findings"][0]["status"] == "consistent"


def test_scenario_react_frontend_go_backend_task_relevance():
    root = FIXTURES / "react_go"
    workspace = _workspace(
        [
            _repo("react_frontend", "frontend", "frontend", known_ports=[3000]),
            _repo("go_backend", "backend", "backend", known_ports=[9090], known_urls=["http://localhost:9090"]),
        ]
    )
    refs = (_extract("react_frontend", root / "frontend", ["src/api.ts"], workspace["repositories"]),)

    _, assessment, _, graph, context, _ = _pipeline(workspace, "go backend users api", reference_results=refs)

    assert assessment.to_dict()["role_assessments"]
    assert _edge(graph, "calls_api")["target_repository_id"] == "go_backend"
    assert context.to_dict()["repositories"][0]["repository_id"] == "go_backend"


def test_scenario_host_and_embedded_iframe_application():
    root = FIXTURES / "iframe_apps"
    workspace = _workspace(
        [
            _repo("host", "host", "frontend", known_ports=[4200]),
            _repo("embedded", "embedded", "frontend", known_ports=[4201], known_urls=["http://localhost:4201/app"]),
        ]
    )
    refs = (_extract("host", root / "host", ["src/frame.html"], workspace["repositories"]),)

    _, _, _, graph, _, _ = _pipeline(workspace, "embedded iframe", reference_results=refs)

    assert _edge(graph, "embeds_iframe")["target_repository_id"] == "embedded"


def test_scenario_postmessage_applications():
    root = FIXTURES / "postmessage_apps"
    workspace = _workspace(
        [
            _repo("sender", "sender", "frontend", known_ports=[4200], known_urls=["http://localhost:4200"]),
            _repo("listener", "listener", "frontend", known_ports=[4300], known_urls=["http://localhost:4300"]),
        ]
    )
    refs = (
        _extract("sender", root / "sender", ["src/message.ts"], workspace["repositories"]),
        _extract("listener", root / "listener", ["src/listener.ts"], workspace["repositories"]),
    )

    receive_hint = {
        "source_repository_id": "listener",
        "target_repository_id": "sender",
        "relationship_type": "receives_messages_from",
        "origin": "inferred",
        "confidence": "medium",
        "confidence_score": 0.5,
        "evidence": (),
        "inferred": True,
    }
    _, _, _, graph, _, _ = _pipeline(workspace, "postmessage auth ready", reference_results=refs, relationship_hints=(receive_hint,))
    edge_types = {edge["relationship_type"] for edge in graph.to_dict()["edges"]}

    assert "sends_messages_to" in edge_types
    assert "receives_messages_from" in edge_types


def test_scenario_shared_contract_mismatch_degrades_readiness_and_context_warning():
    root = FIXTURES / "shared_contract_mismatch"
    workspace = _workspace(
        [
            _repo("frontend", "frontend", "frontend"),
            _repo("backend", "backend", "backend"),
        ],
        shared_contracts=[
            {
                "name": "auth-header",
                "contract_type": "auth_header",
                "expected_value": "Authorization",
                "severity": "error",
                "locations": [
                    {"repository_id": "frontend", "path": "src/constants.ts", "symbol": "AUTH_HEADER"},
                    {"repository_id": "backend", "path": "app/constants.py", "symbol": "AUTH_HEADER"},
                ],
            }
        ],
    )
    refs = (
        _extract("frontend", root / "frontend", ["src/constants.ts"], workspace["repositories"]),
        _extract("backend", root / "backend", ["app/constants.py"], workspace["repositories"]),
    )

    _, _, contracts, _, context, readiness = _pipeline(workspace, "auth header mismatch", reference_results=refs)

    assert contracts.to_dict()["contract_findings"][0]["status"] == "inconsistent"
    assert readiness.to_dict()["status"] == "degraded"
    assert context.to_dict()["contracts"][0]["status"] == "inconsistent"


def test_scenario_missing_configured_repository_blocks_or_degrades_safely():
    workspace = _workspace([_repo("frontend", "frontend", "frontend")])
    hint = {
        "source_repository_id": "frontend",
        "target_repository_id": "backend",
        "relationship_type": "calls_api",
        "origin": "inferred",
        "confidence": "medium",
        "confidence_score": 0.5,
        "evidence": (),
    }

    _, _, _, graph, _, readiness = _pipeline(workspace, "missing backend", relationship_hints=(hint,), required_repository_ids=("backend",))

    assert graph.to_dict()["unresolved_relationships"][0]["reason"] == "target_repository_missing"
    assert readiness.to_dict()["status"] == "blocked"
    assert readiness.to_dict()["safe_fallback"]["single_repository_context_available"] is True


def test_scenario_ambiguous_port_ownership_creates_no_speculative_edge():
    root = FIXTURES / "ambiguous_port"
    workspace = _workspace(
        [
            _repo("frontend", "frontend", "frontend"),
            _repo("backend_a", "backend-a", "backend", known_ports=[8080]),
            _repo("backend_b", "backend-b", "backend", known_ports=[8080]),
        ]
    )
    refs = (_extract("frontend", root / "frontend", ["src/api.ts"], workspace["repositories"]),)

    _, _, _, graph, _, _ = _pipeline(workspace, "ambiguous backend port", reference_results=refs)

    assert any(diagnostic.code == "ambiguous_target_repository" for diagnostic in refs[0].diagnostics)
    assert graph.to_dict()["edges"] == []


def test_scenario_cyclic_workspace_relationships():
    workspace = _workspace(
        [
            _repo("frontend", ".", "frontend"),
            _repo("backend", "../backend", "backend"),
            _repo("worker", "../worker", "worker"),
        ]
    )
    hints = (
        {"source_repository_id": "frontend", "target_repository_id": "backend", "relationship_type": "calls_api", "origin": "inferred", "confidence": "high", "confidence_score": 0.8, "evidence": ()},
        {"source_repository_id": "backend", "target_repository_id": "worker", "relationship_type": "depends_on", "origin": "inferred", "confidence": "high", "confidence_score": 0.8, "evidence": ()},
        {"source_repository_id": "worker", "target_repository_id": "frontend", "relationship_type": "proxies_to", "origin": "inferred", "confidence": "high", "confidence_score": 0.8, "evidence": ()},
    )

    _, _, _, graph, context, _ = _pipeline(workspace, "cycle", relationship_hints=hints)

    assert graph.to_dict()["summary"]["cycle_count"] == 1
    assert graph.to_dict()["strongly_connected_components"][0]["repository_ids"] == ["backend", "frontend", "worker"]
    assert context.to_dict()["workspace_summary"]["cycle_count"] == 1


def test_scenario_large_evidence_and_token_protection():
    workspace = _workspace([_repo("frontend", ".", "frontend"), _repo("backend", "../backend", "backend")])
    evidence = tuple(
        workspace_relationships.RelationshipEvidence(
            signal_type="workspace_file",
            source_repository_id="frontend",
            source_path=f"src/{index}.ts",
            summary="large evidence " + ("x" * 80),
            strength="weak",
            target_repository_id="backend",
        )
        for index in range(20)
    )
    hints = tuple(
        {
            "source_repository_id": "frontend",
            "target_repository_id": "backend",
            "relationship_type": relationship_type,
            "origin": "inferred",
            "confidence": "low",
            "confidence_score": 0.2,
            "evidence": evidence,
        }
        for relationship_type in ("calls_api", "depends_on", "imports_package")
    )

    _, _, _, _, context, _ = _pipeline(
        workspace,
        "large evidence",
        relationship_hints=hints,
        budget_profile={"target_context_tokens": 80, "reserved_output_tokens": 0, "max_context_pack_tokens": 80, "safety_margin": 0},
    )
    payload = context.to_dict()

    assert payload["omitted_counts"]["evidence"] > 0
    assert payload["budget_summary"]["budget_exhausted"] is True
    assert payload["budget_summary"]["largest_workspace_token_savings"]


def test_scenario_sensitive_values_redacted_everywhere():
    workspace = _workspace(
        [_repo("frontend", "frontend", "frontend")],
        shared_contracts=[
            {
                "name": "api-token",
                "contract_type": "custom",
                "expected_value": "github_pat_supersecretvalue1234567890",
                "severity": "error",
                "locations": [{"repository_id": "frontend", "path": ".env", "symbol": "API_TOKEN"}],
            }
        ],
    )

    _, _, contracts, graph, context, readiness = _pipeline(workspace, "sensitive values")
    serialized = json.dumps(
        {
            "contracts": contracts.to_dict(),
            "graph": graph.to_dict(),
            "context": context.to_dict(),
            "readiness": readiness.to_dict(),
        },
        sort_keys=True,
    )

    assert "github_pat_supersecretvalue1234567890" not in serialized
    assert "api-token" not in json.dumps(context.to_dict(), sort_keys=True)


def test_repeated_integration_produces_identical_output():
    workspace = _workspace([_repo("frontend", ".", "frontend"), _repo("backend", "../backend", "backend")])
    hint = {"source_repository_id": "frontend", "target_repository_id": "backend", "relationship_type": "calls_api", "origin": "explicit", "confidence": "high", "confidence_score": 1.0, "evidence": (), "explicit": True}

    assert _payloads(_pipeline(workspace, "auth", relationship_hints=(hint,))) == _payloads(_pipeline(workspace, "auth", relationship_hints=(hint,)))


def test_no_network_recursive_discovery_or_unexpected_files():
    workspace_sources = [
        PROJECT_ROOT / "strata" / "utils" / name
        for name in (
            "workspace_context.py",
            "workspace_readiness.py",
            "workspace_config.py",
            "workspace_discovery.py",
            "workspace_references.py",
            "workspace_contracts.py",
            "workspace_graph.py",
        )
    ]
    source = "\n".join(path.read_text(encoding="utf-8") for path in workspace_sources)

    assert "requests." not in source
    assert "urllib.request" not in source
    assert "socket." not in source
    assert "git clone" not in source
    assert "os.walk" not in (PROJECT_ROOT / "strata" / "utils" / "workspace_context.py").read_text(encoding="utf-8")


def test_scanner_compatible_imports_architecture_and_docs():
    for module in ("workspace_context.py", "workspace_readiness.py"):
        source = (PROJECT_ROOT / "strata" / "utils" / module).read_text(encoding="utf-8")
        assert "from strata.utils import" not in source
        assert "strata.core" not in source
        assert "strata.commands" not in source
    docs = (PROJECT_ROOT / "docs" / "roadmap" / "workspace-intelligence.md").read_text(encoding="utf-8")
    assert "Q7" in docs
    assert "Q8" in docs
    assert "Q9" in docs
    assert "Part I remains the token firewall" in docs
    assert "Part P handles User Flow/Journey Intelligence" in docs


TESTS = [
    test_scenario_angular_frontend_python_backend,
    test_scenario_react_frontend_go_backend_task_relevance,
    test_scenario_host_and_embedded_iframe_application,
    test_scenario_postmessage_applications,
    test_scenario_shared_contract_mismatch_degrades_readiness_and_context_warning,
    test_scenario_missing_configured_repository_blocks_or_degrades_safely,
    test_scenario_ambiguous_port_ownership_creates_no_speculative_edge,
    test_scenario_cyclic_workspace_relationships,
    test_scenario_large_evidence_and_token_protection,
    test_scenario_sensitive_values_redacted_everywhere,
    test_repeated_integration_produces_identical_output,
    test_no_network_recursive_discovery_or_unexpected_files,
    test_scanner_compatible_imports_architecture_and_docs,
]
