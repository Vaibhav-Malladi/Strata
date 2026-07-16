import tempfile
from pathlib import Path

import strata.utils.journey_entry_points as entry_points
import strata.utils.journey_frontend as frontend
import strata.utils.user_journey as journey


def _write(root: Path, path: str, content: str) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _request(**overrides):
    data = {"task": "Trace Login", "ui_hints": ("Login",), "starting_symbols": ("handleLogin",)}
    data.update(overrides)
    return journey.JourneyRequest(**data)


def _entry(root: Path, path: str, request=None):
    result = entry_points.detect_journey_entry_points(request or _request(), "frontend", root, (path,))
    return result.entry_points[0]


def _types(result):
    return {item["step_type"] for item in result.to_dict()["steps"]}


def _transition_types(result):
    return {item["transition_type"] for item in result.to_dict()["transitions"]}


def _gap_reasons(result):
    return {item["reason"] for item in result.to_dict()["gaps"]}


def test_angular_template_to_component_service_and_http_request():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        _write(root, "login.component.html", '<button (click)="handleLogin()">Login</button>')
        _write(
            root,
            "login.component.ts",
            """
            function handleLogin() {
              loginService()
              setUser()
              router.navigate(['/home'])
            }
            """,
        )
        _write(root, "auth.service.ts", "export function loginService() { return http.post('/api/login') }\n")
        entry = _entry(root, "login.component.html")
        result = frontend.trace_frontend_journey(_request(), (entry,), "frontend", root, ("login.component.html", "login.component.ts", "auth.service.ts"))
        types = _types(result)
        assert journey.STEP_TYPE_USER_ACTION in types
        assert journey.STEP_TYPE_UI_EVENT_HANDLER in types
        assert journey.STEP_TYPE_FRONTEND_SERVICE in types
        assert journey.STEP_TYPE_API_REQUEST in types
        assert journey.STEP_TYPE_FRONTEND_STATE in types
        assert journey.STEP_TYPE_NAVIGATION in types
        assert journey.TRANSITION_TYPE_SENDS_REQUEST in _transition_types(result)


def test_react_handler_to_api_helper_state_dispatch_and_navigation():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        _write(
            root,
            "Login.tsx",
            """
            export function Login() { return <button onClick={handleLogin}>Login</button> }
            function handleLogin() { loginApi(); setUser(); dispatch({ type: 'ok' }); navigate('/done') }
            function loginApi() { return fetch('/api/login', { method: 'POST' }) }
            """,
        )
        entry = _entry(root, "Login.tsx")
        result = frontend.trace_frontend_journey(_request(), (entry,), "frontend", root, ("Login.tsx",))
        payload = result.to_dict()
        assert any(step["metadata"].get("http_method") == "POST" for step in payload["steps"])
        assert journey.TRANSITION_TYPE_DISPATCHES in _transition_types(result)
        assert journey.TRANSITION_TYPE_NAVIGATES_TO in _transition_types(result)


def test_direct_js_call_and_unresolved_dynamic_call_gap():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        _write(
            root,
            "flow.ts",
            """
            export function handleLogin() { nextStep(); actions[name]() }
            function nextStep() { return fetch('/api/next') }
            """,
        )
        entry = journey.JourneyEntryPoint("frontend", "flow.ts", journey.ENTRY_POINT_TYPE_EXPLICIT_SYMBOL, "handleLogin", journey.CONFIDENCE_HIGH, 0.95, symbol="handleLogin", origin=journey.ORIGIN_EXPLICIT)
        result = frontend.trace_frontend_journey(_request(), (entry,), "frontend", root, ("flow.ts",))
        assert journey.STEP_TYPE_COMPONENT_METHOD in _types(result)
        assert journey.GAP_REASON_DYNAMIC_CALL_UNRESOLVED in _gap_reasons(result)


def test_trace_depth_cap_is_reported():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        _write(
            root,
            "flow.ts",
            """
            import { loginService } from './auth'
            function handleLogin() { loginService() }
            """,
        )
        entry = journey.JourneyEntryPoint("frontend", "flow.ts", journey.ENTRY_POINT_TYPE_EXPLICIT_SYMBOL, "handleLogin", journey.CONFIDENCE_HIGH, 0.95, symbol="handleLogin", origin=journey.ORIGIN_EXPLICIT)
        result = frontend.trace_frontend_journey(_request(), (entry,), "frontend", root, ("flow.ts",), max_depth=1, max_steps=20, max_transitions=20)
        assert journey.GAP_REASON_STEP_CAP_REACHED in _gap_reasons(result)


def test_frontend_step_cap_is_reported():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        _write(
            root,
            "flow.ts",
            """
            function handleLogin() { setUser(); setProfile(); setReady(); dispatch({ type: 'ok' }); navigate('/done'); fetch('/api/login') }
            """,
        )
        entry = journey.JourneyEntryPoint("frontend", "flow.ts", journey.ENTRY_POINT_TYPE_EXPLICIT_SYMBOL, "handleLogin", journey.CONFIDENCE_HIGH, 0.95, symbol="handleLogin", origin=journey.ORIGIN_EXPLICIT)
        result = frontend.trace_frontend_journey(_request(), (entry,), "frontend", root, ("flow.ts",), max_depth=8, max_steps=3, max_transitions=50)
        payload = result.to_dict()
        codes = {item["code"] for item in payload["diagnostics"]}
        assert payload["summary"]["step_count"] == 3
        assert journey.DIAGNOSTIC_JOURNEY_STEP_CAP_REACHED in codes


def test_frontend_transition_cap_is_reported():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        _write(
            root,
            "flow.ts",
            """
            function handleLogin() { setUser(); setProfile(); setReady(); dispatch({ type: 'ok' }); navigate('/done'); fetch('/api/login') }
            """,
        )
        entry = journey.JourneyEntryPoint("frontend", "flow.ts", journey.ENTRY_POINT_TYPE_EXPLICIT_SYMBOL, "handleLogin", journey.CONFIDENCE_HIGH, 0.95, symbol="handleLogin", origin=journey.ORIGIN_EXPLICIT)
        result = frontend.trace_frontend_journey(_request(), (entry,), "frontend", root, ("flow.ts",), max_depth=8, max_steps=50, max_transitions=3)
        payload = result.to_dict()
        codes = {item["code"] for item in payload["diagnostics"]}
        assert payload["summary"]["transition_count"] == 3
        assert journey.DIAGNOSTIC_JOURNEY_TRANSITION_CAP_REACHED in codes


def test_deterministic_frontend_journey_result():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        _write(root, "Login.tsx", "function handleLogin() { fetch('/api/login') }\n")
        entry = journey.JourneyEntryPoint("frontend", "Login.tsx", journey.ENTRY_POINT_TYPE_EXPLICIT_SYMBOL, "handleLogin", journey.CONFIDENCE_HIGH, 0.95, symbol="handleLogin", origin=journey.ORIGIN_EXPLICIT)
        first = frontend.trace_frontend_journey(_request(), (entry,), "frontend", root, ("Login.tsx",)).to_dict()
        second = frontend.trace_frontend_journey(_request(), (entry,), "frontend", root, ("Login.tsx",)).to_dict()
        assert first == second


TESTS = [
    test_angular_template_to_component_service_and_http_request,
    test_react_handler_to_api_helper_state_dispatch_and_navigation,
    test_direct_js_call_and_unresolved_dynamic_call_gap,
    test_trace_depth_cap_is_reported,
    test_frontend_step_cap_is_reported,
    test_frontend_transition_cap_is_reported,
    test_deterministic_frontend_journey_result,
]
