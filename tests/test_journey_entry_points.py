import tempfile
from pathlib import Path

import strata.utils.journey_entry_points as entry_points
import strata.utils.user_journey as journey


def _write(root: Path, path: str, content: str) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _request(**overrides):
    data = {
        "task": "Trace Login",
        "ui_hints": ("Login",),
        "route_hints": ("/login",),
        "starting_symbols": ("handleLogin",),
    }
    data.update(overrides)
    return journey.JourneyRequest(**data)


def _detect(root: Path, paths, request=None, **kwargs):
    return entry_points.detect_journey_entry_points(request or _request(), "frontend", root, paths, **kwargs).to_dict()


def _codes(payload):
    return {item["code"] for item in payload["diagnostics"]}


def test_angular_button_click_submit_and_router_link_entries():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        _write(
            root,
            "src/app/login.component.html",
            """
            <button (click)="handleLogin()">Login</button>
            <form (submit)="submitLogin()"></form>
            <a routerLink="/login">Login</a>
            """,
        )
        payload = _detect(root, ("src/app/login.component.html",), _request(starting_symbols=("handleLogin", "submitLogin")))
        types = {item["entry_point_type"] for item in payload["entry_points"]}
        assert journey.ENTRY_POINT_TYPE_BUTTON in types
        assert journey.ENTRY_POINT_TYPE_FORM in types
        assert journey.ENTRY_POINT_TYPE_ROUTE in types
        assert payload["entry_points"][0]["confidence"] == journey.CONFIDENCE_HIGH


def test_react_button_form_and_route_entries():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        _write(
            root,
            "src/Login.tsx",
            """
            export function Login() {
              return <form onSubmit={submitLogin}><button onClick={handleLogin}>Login</button><Route path="/login" /></form>
            }
            """,
        )
        payload = _detect(root, ("src/Login.tsx",), _request(starting_symbols=("handleLogin", "submitLogin")))
        symbols = {item["symbol"] for item in payload["entry_points"]}
        labels = {item["display_label"] for item in payload["entry_points"]}
        assert "handleLogin" in symbols
        assert "submitLogin" in symbols
        assert "/login" in labels


def test_explicit_path_symbol_and_message_event_entries():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        _write(root, "src/host.ts", "export function iframeReady() {}\nwindow.addEventListener('message', iframeReady)\n")
        request = journey.JourneyRequest(
            task="Trace iframe READY message",
            starting_paths=("src/host.ts",),
            starting_symbols=("iframeReady",),
            ui_hints=("message",),
        )
        payload = _detect(root, ("src/host.ts",), request)
        types = {item["entry_point_type"] for item in payload["entry_points"]}
        assert journey.ENTRY_POINT_TYPE_EXPLICIT_PATH in types
        assert journey.ENTRY_POINT_TYPE_EXPLICIT_SYMBOL in types
        assert journey.ENTRY_POINT_TYPE_MESSAGE_EVENT in types


def test_ambiguous_ui_dynamic_binding_caps_and_ordering():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        _write(root, "a.html", '<button (click)="one()">Login</button><a [routerLink]="target">Login</a>')
        _write(root, "b.html", '<button (click)="two()">Login</button>')
        first = _detect(root, ("b.html", "a.html"), _request(starting_symbols=("one", "two")), max_entry_points=2)
        second = _detect(root, ("a.html", "b.html"), _request(starting_symbols=("one", "two")), max_entry_points=2)
        assert first["entry_points"] == second["entry_points"]
        assert journey.DIAGNOSTIC_ENTRY_DYNAMIC_BINDING_UNRESOLVED in _codes(first)
        assert journey.DIAGNOSTIC_ENTRY_SYMBOL_AMBIGUOUS in _codes(first)
        assert journey.DIAGNOSTIC_ENTRY_CAP_REACHED in _codes(first)


def test_selected_path_safety_missing_and_unsupported_files():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        _write(root, "README.md", "# no")
        payload = _detect(root, ("../outside.html", "missing.html", "README.md"), _request())
        codes = _codes(payload)
        assert journey.DIAGNOSTIC_ENTRY_SELECTED_PATH_INVALID in codes
        assert journey.DIAGNOSTIC_ENTRY_SELECTED_PATH_MISSING in codes
        assert journey.DIAGNOSTIC_ENTRY_UNSUPPORTED_FILE in codes


def test_no_recursive_scan_only_selected_files():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        _write(root, "selected.html", "<button>Other</button>")
        _write(root, "nested/login.html", "<button>Login</button>")
        payload = _detect(root, ("selected.html",), _request())
        assert payload["summary"]["file_count"] == 1
        assert payload["entry_points"] == []


TESTS = [
    test_angular_button_click_submit_and_router_link_entries,
    test_react_button_form_and_route_entries,
    test_explicit_path_symbol_and_message_event_entries,
    test_ambiguous_ui_dynamic_binding_caps_and_ordering,
    test_selected_path_safety_missing_and_unsupported_files,
    test_no_recursive_scan_only_selected_files,
]
