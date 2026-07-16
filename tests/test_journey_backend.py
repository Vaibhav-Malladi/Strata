import tempfile
import textwrap
from pathlib import Path

import strata.utils.journey_backend as backend
import strata.utils.user_journey as journey


def _write(root: Path, path: str, content: str) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _request():
    return journey.JourneyRequest(task="Trace backend login", route_hints=("/api/login",))


def _route(symbol="login", path="app.py"):
    return journey.JourneyStep(
        repository_id="backend",
        path=path,
        symbol=symbol,
        step_type=journey.STEP_TYPE_BACKEND_ROUTE,
        summary="Backend route.",
        confidence=journey.CONFIDENCE_HIGH,
        confidence_score=0.9,
        sequence_hint=1,
        semantic_discriminator=f"route:{symbol}:{path}",
        metadata={"route_path": "/api/login", "http_method": "POST"},
    )


def _types(result):
    return {item["step_type"] for item in result.to_dict()["steps"]}


def _codes(result):
    return {item["code"] for item in result.to_dict()["diagnostics"]}


def _gaps(result):
    return {item["reason"] for item in result.to_dict()["gaps"]}


def _steps_by_type(result, step_type):
    return [item for item in result.to_dict()["steps"] if item["step_type"] == step_type]


def test_direct_validation_call_without_helper_definition_is_classified():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        _write(
            root,
            "app.py",
            textwrap.dedent(
                """
                @app.post("/api/login")
                def login():
                    check_input_payload()
                    return JSONResponse({})
                """
            ).lstrip(),
        )
        result = backend.trace_backend_journey(_request(), (_route(),), "backend", root, ("app.py",))
        validation_steps = _steps_by_type(result, journey.STEP_TYPE_VALIDATION)
        handler_steps = _steps_by_type(result, journey.STEP_TYPE_BACKEND_HANDLER)
        assert validation_steps
        assert validation_steps[0]["symbol"] == "check_input_payload"
        assert validation_steps[0]["evidence"][0]["signal_type"] == "direct_backend_call"
        assert validation_steps[0]["step_id"] != handler_steps[0]["step_id"]
        transitions = result.to_dict()["transitions"]
        assert any(item["source_step_id"] == handler_steps[0]["step_id"] and item["target_step_id"] == validation_steps[0]["step_id"] for item in transitions)
        assert not any(item["source_step_id"] == validation_steps[0]["step_id"] for item in transitions)
        assert result.to_dict() == backend.trace_backend_journey(_request(), (_route(),), "backend", root, ("app.py",)).to_dict()


def test_defined_validation_helper_is_classified_and_can_be_traversed():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        _write(
            root,
            "app.py",
            textwrap.dedent(
                """
                @app.post("/api/login")
                def login():
                    validate_payload(None)
                    return JSONResponse({})

                def validate_payload(data):
                    pass
                """
            ).lstrip(),
        )
        result = backend.trace_backend_journey(_request(), (_route(),), "backend", root, ("app.py",))
        validation_steps = _steps_by_type(result, journey.STEP_TYPE_VALIDATION)
        handler_steps = _steps_by_type(result, journey.STEP_TYPE_BACKEND_HANDLER)
        assert validation_steps
        assert validation_steps[0]["symbol"] == "validate_payload"
        assert validation_steps[0]["step_id"] != handler_steps[0]["step_id"]
        assert any(item["source_step_id"] == handler_steps[0]["step_id"] and item["target_step_id"] == validation_steps[0]["step_id"] for item in result.to_dict()["transitions"])


def test_python_fastapi_and_flask_route_to_handler_classifications_and_response():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        _write(
            root,
            "app.py",
            textwrap.dedent(
                """
            @app.post("/api/login")
            def login():
                validate_login()
                authenticate_user()
                authorize_role()
                user_repository_find()
                cache_get()
                publish_event()
                external_client()
                return JSONResponse({})
            @flask_app.route("/api/other")
            def other():
                return response.json({})
            """
            ).lstrip(),
        )
        result = backend.trace_backend_journey(_request(), (_route(),), "backend", root, ("app.py",))
        types = _types(result)
        assert journey.STEP_TYPE_BACKEND_HANDLER in types
        assert journey.STEP_TYPE_VALIDATION in types
        assert journey.STEP_TYPE_AUTHENTICATION in types
        assert journey.STEP_TYPE_AUTHORIZATION in types
        assert journey.STEP_TYPE_DATABASE_ACCESS in types
        assert journey.STEP_TYPE_CACHE_ACCESS in types
        assert journey.STEP_TYPE_QUEUE_PUBLISH in types
        assert journey.STEP_TYPE_EXTERNAL_SERVICE in types
        assert journey.STEP_TYPE_RESPONSE in types


def test_python_service_to_database_helper():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        _write(root, "app.py", "def login():\n    account_service()\n\ndef account_service():\n    user_repo_find()\n")
        result = backend.trace_backend_journey(_request(), (_route(),), "backend", root, ("app.py",))
        assert journey.STEP_TYPE_BACKEND_SERVICE in _types(result)
        assert journey.STEP_TYPE_DATABASE_ACCESS in _types(result)


def test_go_route_handler_service_database_and_response_writer():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        _write(root, "server.go", 'func SaveHandler(w http.ResponseWriter, r *http.Request) { saveService(); repoFind(); w.WriteHeader(200) }\n')
        result = backend.trace_backend_journey(_request(), (_route("SaveHandler", "server.go"),), "backend", root, ("server.go",))
        assert journey.STEP_TYPE_BACKEND_HANDLER in _types(result)
        assert journey.STEP_TYPE_BACKEND_SERVICE in _types(result)
        assert journey.STEP_TYPE_DATABASE_ACCESS in _types(result)
        assert journey.STEP_TYPE_RESPONSE in _types(result)


def test_go_undefined_selector_service_target_is_classified():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        _write(root, "server.go", "func SaveHandler(w http.ResponseWriter, r *http.Request) { userService.CreateUser(ctx, input); w.WriteHeader(200) }\n")
        result = backend.trace_backend_journey(_request(), (_route("SaveHandler", "server.go"),), "backend", root, ("server.go",))
        service_steps = _steps_by_type(result, journey.STEP_TYPE_BACKEND_SERVICE)
        handler_steps = _steps_by_type(result, journey.STEP_TYPE_BACKEND_HANDLER)
        assert service_steps
        assert service_steps[0]["symbol"] == "userService.CreateUser"
        assert service_steps[0]["step_id"] != handler_steps[0]["step_id"]
        assert any(item["source_step_id"] == handler_steps[0]["step_id"] and item["target_step_id"] == service_steps[0]["step_id"] for item in result.to_dict()["transitions"])
        assert not any(item["source_step_id"] == service_steps[0]["step_id"] for item in result.to_dict()["transitions"])
        assert journey.STEP_TYPE_RESPONSE in _types(result)
        assert result.to_dict() == backend.trace_backend_journey(_request(), (_route("SaveHandler", "server.go"),), "backend", root, ("server.go",)).to_dict()


def test_go_defined_selector_service_traces_repository_call():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        _write(
            root,
            "server.go",
            "func SaveHandler(w http.ResponseWriter, r *http.Request) { userService.CreateUser(ctx, input); w.WriteHeader(200) }\n"
            "func (s *UserService) CreateUser(ctx context.Context, input Input) { repo.FindByID(ctx, input.ID) }\n",
        )
        result = backend.trace_backend_journey(_request(), (_route("SaveHandler", "server.go"),), "backend", root, ("server.go",))
        service_steps = _steps_by_type(result, journey.STEP_TYPE_BACKEND_SERVICE)
        database_steps = _steps_by_type(result, journey.STEP_TYPE_DATABASE_ACCESS)
        handler_steps = _steps_by_type(result, journey.STEP_TYPE_BACKEND_HANDLER)
        assert service_steps
        assert database_steps
        assert service_steps[0]["symbol"] == "userService.CreateUser"
        assert database_steps[0]["symbol"] == "repo.FindByID"
        transitions = result.to_dict()["transitions"]
        assert any(item["source_step_id"] == handler_steps[0]["step_id"] and item["target_step_id"] == service_steps[0]["step_id"] for item in transitions)
        assert any(item["source_step_id"] == service_steps[0]["step_id"] and item["target_step_id"] == database_steps[0]["step_id"] for item in transitions)
        assert journey.STEP_TYPE_RESPONSE in _types(result)


def test_express_controller_validation_service_database_and_response():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        _write(root, "routes.ts", "const saveController = (req, res) => { validateBody(); saveService(); ormSave(); res.json({ ok: true }) }\n")
        result = backend.trace_backend_journey(_request(), (_route("saveController", "routes.ts"),), "backend", root, ("routes.ts",))
        assert journey.STEP_TYPE_VALIDATION in _types(result)
        assert journey.STEP_TYPE_BACKEND_SERVICE in _types(result)
        assert journey.STEP_TYPE_DATABASE_ACCESS in _types(result)
        assert journey.STEP_TYPE_RESPONSE in _types(result)


def test_dynamic_call_unknown_symbol_and_path_safety():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        _write(root, "app.py", "def login():\n    services[name]()\n")
        dynamic = backend.trace_backend_journey(_request(), (_route(),), "backend", root, ("app.py",))
        assert journey.GAP_REASON_DYNAMIC_CALL_UNRESOLVED in _gaps(dynamic)
        unknown = backend.trace_backend_journey(_request(), (_route("missing"),), "backend", root, ("app.py",))
        assert journey.GAP_REASON_SYMBOL_NOT_FOUND in _gaps(unknown)
        unsafe = backend.trace_backend_journey(_request(), (_route(),), "backend", root, ("../outside.py",))
        assert journey.DIAGNOSTIC_ENTRY_SELECTED_PATH_INVALID in _codes(unsafe)


def test_backend_depth_step_transition_caps_and_determinism():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        _write(root, "app.py", "def login():\n    a(); b(); c(); d(); e()\n\ndef a():\n    b()\n\ndef b():\n    c()\n\ndef c():\n    d()\n\ndef d():\n    e()\n\ndef e():\n    return {'ok': True}\n")
        depth = backend.trace_backend_journey(_request(), (_route(),), "backend", root, ("app.py",), max_depth=1, max_steps=50, max_transitions=50)
        assert journey.GAP_REASON_STEP_CAP_REACHED in _gaps(depth)
        step_cap = backend.trace_backend_journey(_request(), (_route(),), "backend", root, ("app.py",), max_steps=3, max_transitions=50)
        assert journey.DIAGNOSTIC_JOURNEY_STEP_CAP_REACHED in _codes(step_cap)
        transition_cap = backend.trace_backend_journey(_request(), (_route(),), "backend", root, ("app.py",), max_steps=50, max_transitions=2)
        assert journey.DIAGNOSTIC_JOURNEY_TRANSITION_CAP_REACHED in _codes(transition_cap)
        first = backend.trace_backend_journey(_request(), (_route(),), "backend", root, ("app.py",)).to_dict()
        second = backend.trace_backend_journey(_request(), (_route(),), "backend", root, ("app.py",)).to_dict()
        assert first == second


TESTS = [
    test_direct_validation_call_without_helper_definition_is_classified,
    test_defined_validation_helper_is_classified_and_can_be_traversed,
    test_python_fastapi_and_flask_route_to_handler_classifications_and_response,
    test_python_service_to_database_helper,
    test_go_route_handler_service_database_and_response_writer,
    test_go_undefined_selector_service_target_is_classified,
    test_go_defined_selector_service_traces_repository_call,
    test_express_controller_validation_service_database_and_response,
    test_dynamic_call_unknown_symbol_and_path_safety,
    test_backend_depth_step_transition_caps_and_determinism,
]
