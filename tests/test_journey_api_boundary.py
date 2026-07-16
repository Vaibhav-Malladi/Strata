import tempfile
from pathlib import Path

import strata.utils.journey_api_boundary as api_boundary
import strata.utils.user_journey as journey
import strata.utils.workspace_config as workspace_config


def _write(root: Path, path: str, content: str) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _request():
    return journey.JourneyRequest(task="Trace login API", route_hints=("/api/login",))


def _api_step(method="POST", route="/api/login", url=None):
    return journey.JourneyStep(
        repository_id="frontend",
        path="src/api.ts",
        symbol=route,
        step_type=journey.STEP_TYPE_API_REQUEST,
        summary=f"Send {method} {route}.",
        confidence=journey.CONFIDENCE_HIGH,
        confidence_score=0.9,
        sequence_hint=1,
        semantic_discriminator=f"{method}:{url or route}",
        metadata={"http_method": method, "route_path": route, "url": url or route},
    )


def _link(root: Path, step, paths, **kwargs):
    return api_boundary.link_frontend_backend_api_boundary(
        _request(),
        frontend_steps=(step,),
        frontend_repository_id="frontend",
        backend_repository_id=kwargs.pop("backend_repository_id", "backend"),
        backend_repository_root=root,
        selected_backend_paths=paths,
        **kwargs,
    )


def _codes(result):
    return {item["code"] for item in result.to_dict()["diagnostics"]}


def _transition_types(result):
    return {item["transition_type"] for item in result.to_dict()["transitions"]}


def test_angular_httpclient_to_python_route_cross_repository_link():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        _write(root, "app/api.py", '@app.post("/api/login")\ndef login():\n    pass\n')
        result = _link(root, _api_step("POST", "/api/login"), ("app/api.py",))
        payload = result.to_dict()
        assert any(step["step_type"] == journey.STEP_TYPE_WORKSPACE_BOUNDARY for step in payload["steps"])
        assert any(step["step_type"] == journey.STEP_TYPE_BACKEND_ROUTE for step in payload["steps"])
        assert journey.TRANSITION_TYPE_CROSSES_REPOSITORY in _transition_types(result)
        assert any(item["relationship_type"] == workspace_config.RELATIONSHIP_TYPE_CALLS_API for item in payload["transitions"])


def test_react_fetch_to_go_route_and_port_match():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        _write(root, "server.go", 'http.HandleFunc("/api/login", login)\n')
        step = _api_step("GET", "/api/login", url="http://localhost:8080/api/login")
        result = _link(root, step, ("server.go",), known_ports=(8080,), known_repository_urls=("http://localhost:8080",))
        assert journey.STEP_TYPE_BACKEND_ROUTE in {item["step_type"] for item in result.to_dict()["steps"]}
        assert journey.DIAGNOSTIC_API_TARGET_AMBIGUOUS not in _codes(result)


def test_frontend_api_helper_to_express_route():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        _write(root, "routes.ts", 'router.post("/api/login", loginHandler)\n')
        result = _link(root, _api_step("POST", "/api/login"), ("routes.ts",))
        backend_steps = [item for item in result.to_dict()["steps"] if item["step_type"] == journey.STEP_TYPE_BACKEND_ROUTE]
        assert backend_steps[0]["metadata"]["framework"] == "express"


def test_method_matching_and_parameterized_route():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        _write(root, "app.py", '@app.get("/api/users/{user_id}")\ndef get_user():\n    pass\n')
        result = _link(root, _api_step("GET", "/api/users/42"), ("app.py",))
        assert journey.STEP_TYPE_BACKEND_ROUTE in {item["step_type"] for item in result.to_dict()["steps"]}
        assert journey.DIAGNOSTIC_ROUTE_PARAMETER_UNRESOLVED in _codes(result)


def test_ambiguous_routes_and_ambiguous_ports_create_gaps():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        _write(
            root,
            "app.py",
            '@app.post("/api/login")\ndef login_one():\n    pass\n\n@router.post("/api/login")\ndef login_two():\n    pass\n',
        )
        step = _api_step("POST", "/api/login", url="http://localhost:9999/api/login")
        result = _link(root, step, ("app.py",), known_ports=(8080,))
        payload = result.to_dict()
        assert journey.DIAGNOSTIC_BACKEND_ROUTE_AMBIGUOUS in _codes(result)
        assert journey.DIAGNOSTIC_API_TARGET_AMBIGUOUS in _codes(result)
        assert any(gap["reason"] == journey.GAP_REASON_API_TARGET_AMBIGUOUS for gap in payload["gaps"])


def test_missing_target_repository_and_no_speculative_edge():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        _write(root, "app.py", '@app.post("/api/other")\ndef other():\n    pass\n')
        missing_repo = _link(root, _api_step("POST", "/api/login"), ("app.py",), backend_repository_id=None)
        assert any(gap["reason"] == journey.GAP_REASON_TARGET_REPOSITORY_UNKNOWN for gap in missing_repo.to_dict()["gaps"])
        assert journey.DIAGNOSTIC_TARGET_REPOSITORY_UNKNOWN in _codes(missing_repo)

        no_match = _link(root, _api_step("POST", "/api/login"), ("app.py",))
        assert journey.DIAGNOSTIC_BACKEND_ROUTE_NOT_FOUND in _codes(no_match)
        assert journey.TRANSITION_TYPE_CROSSES_REPOSITORY not in _transition_types(no_match)


def test_workspace_graph_calls_api_edge_is_compatible():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        _write(root, "app.py", '@app.post("/api/login")\ndef login():\n    pass\n')
        graph = {"edges": [{"source_repository_id": "frontend", "target_repository_id": "backend", "relationship_type": workspace_config.RELATIONSHIP_TYPE_CALLS_API}]}
        result = _link(root, _api_step("POST", "/api/login"), ("app.py",), workspace_graph=graph)
        assert journey.DIAGNOSTIC_WORKSPACE_RELATIONSHIP_MISSING not in _codes(result)


TESTS = [
    test_angular_httpclient_to_python_route_cross_repository_link,
    test_react_fetch_to_go_route_and_port_match,
    test_frontend_api_helper_to_express_route,
    test_method_matching_and_parameterized_route,
    test_ambiguous_routes_and_ambiguous_ports_create_gaps,
    test_missing_target_repository_and_no_speculative_edge,
    test_workspace_graph_calls_api_edge_is_compatible,
]
