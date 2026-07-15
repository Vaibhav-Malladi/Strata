from importlib import import_module

from strata.core.backend_relationships import BackendRelationship
from strata.core.flask_routes import infer_flask_routes


flask_routes = import_module("strata.core.flask_routes")


def _payloads(source: str, source_path: str = "app\\views.py") -> list[dict]:
    return [relationship.to_dict() for relationship in infer_flask_routes(source_path, source)]


def test_app_route_literal_path_creates_high_confidence_flask_route():
    payloads = _payloads('@app.route("/items")\ndef list_items():\n    pass\n')

    assert payloads == [
        {
            "framework": "flask",
            "relationship_type": "backend_route",
            "source_path": "app/views.py",
            "target_path": "app/views.py",
            "target_symbol": "list_items",
            "route_path": "/items",
            "http_method": "GET",
            "handler_symbol": "list_items",
            "service_symbol": None,
            "model_symbol": None,
            "confidence": "high",
            "evidence": ["line 1 decorator app.route"],
            "warnings": [],
            "reason": "flask_decorator",
        }
    ]
    assert isinstance(infer_flask_routes("app/views.py", '@app.route("/x")\ndef h():\n    pass\n')[0], BackendRelationship)


def test_blueprint_route_literal_path_creates_one_route():
    payloads = _payloads('@users_bp.route("/users/<user_id>")\ndef user_detail(user_id):\n    pass\n')

    assert len(payloads) == 1
    assert payloads[0]["framework"] == "flask"
    assert payloads[0]["route_path"] == "/users/<user_id>"
    assert payloads[0]["http_method"] == "GET"
    assert payloads[0]["handler_symbol"] == "user_detail"


def test_app_route_with_methods_creates_deterministic_relationships():
    payloads = _payloads(
        '@application.route("/items", methods=["POST", "GET"])\n'
        "def handle_items():\n"
        "    pass\n"
    )

    assert [
        (payload["route_path"], payload["http_method"], payload["handler_symbol"])
        for payload in payloads
    ] == [
        ("/items", "GET", "handle_items"),
        ("/items", "POST", "handle_items"),
    ]
    assert all(payload["evidence"] == ["line 1 decorator application.route"] for payload in payloads)


def test_flask_shortcut_decorators_normalize_http_methods():
    source = "\n\n".join(
        f'@bp.{method}("/{method}")\ndef handle_{method}():\n    pass'
        for method in ("get", "post", "put", "patch", "delete", "options", "head")
    )

    assert [
        (payload["route_path"], payload["http_method"], payload["handler_symbol"])
        for payload in _payloads(source)
    ] == [
        ("/delete", "DELETE", "handle_delete"),
        ("/get", "GET", "handle_get"),
        ("/head", "HEAD", "handle_head"),
        ("/options", "OPTIONS", "handle_options"),
        ("/patch", "PATCH", "handle_patch"),
        ("/post", "POST", "handle_post"),
        ("/put", "PUT", "handle_put"),
    ]


def test_flask_variable_syntax_is_preserved_as_literal_string():
    payloads = _payloads('@blueprint.route("/users/<user_id>")\ndef detail(user_id):\n    pass\n')

    assert payloads[0]["route_path"] == "/users/<user_id>"


def test_dynamic_route_path_is_not_guessed():
    payloads = _payloads('@bp.route(prefix + "/items")\ndef list_items():\n    pass\n')

    assert payloads == []


def test_dynamic_methods_are_not_guessed_and_warn():
    payloads = _payloads('@bp.route("/items", methods=METHODS)\ndef list_items():\n    pass\n')

    assert len(payloads) == 1
    assert payloads[0]["http_method"] == "unknown"
    assert payloads[0]["warnings"] == [
        "Dynamic Flask route methods ignored; only literal method names are supported.",
        "Unsupported Flask route method ignored by HTTP normalizer.",
    ]


def test_syntax_error_does_not_crash_and_returns_empty_result():
    assert infer_flask_routes("app/views.py", "def broken(:\n    pass\n") == []


def test_non_flask_looking_decorators_are_ignored():
    source = (
        '@route("/bare")\n'
        "def bare_handler():\n"
        "    pass\n\n"
        '@api_view(["GET"])\n'
        "def handler():\n"
        "    pass\n\n"
        '@pytest.mark.parametrize("x", [1])\n'
        "def test_handler(x):\n"
        "    pass\n"
    )

    assert _payloads(source) == []


def test_ordering_is_deterministic_by_source_route_method_and_handler():
    source = (
        '@bp.post("/z")\n'
        "def zed():\n"
        "    pass\n\n"
        '@bp.route("/a")\n'
        "def alpha():\n"
        "    pass\n\n"
        '@bp.get("/z")\n'
        "def zed_get():\n"
        "    pass\n"
    )

    assert [
        (payload["route_path"], payload["http_method"], payload["handler_symbol"])
        for payload in _payloads(source)
    ] == [
        ("/a", "GET", "alpha"),
        ("/z", "GET", "zed_get"),
        ("/z", "POST", "zed"),
    ]


def test_evidence_includes_decorator_name_and_line_number():
    payloads = _payloads('\n\n@blueprint.patch("/items/<item_id>")\ndef update_item(item_id):\n    pass\n')

    assert payloads[0]["evidence"] == ["line 3 decorator blueprint.patch"]


def test_no_repo_or_file_scanning_is_exposed():
    public_names = tuple(name for name in dir(flask_routes) if not name.startswith("_"))
    forbidden_words = ("scan", "scanner", "walk_repo", "read_file", "glob")

    assert "infer_flask_routes" in public_names
    assert not [
        name
        for name in public_names
        if any(word in name.lower() for word in forbidden_words)
    ]


def test_docs_say_k4_is_flask_only_and_k5_remains_pending():
    with open(
        "docs/roadmap/backend-intelligence-foundation.md",
        encoding="utf-8",
    ) as handle:
        content = handle.read()

    assert "K4 covers Flask route extraction only" in content
    assert "K5 Django/DRF remains pending" in content


TESTS = [
    test_app_route_literal_path_creates_high_confidence_flask_route,
    test_blueprint_route_literal_path_creates_one_route,
    test_app_route_with_methods_creates_deterministic_relationships,
    test_flask_shortcut_decorators_normalize_http_methods,
    test_flask_variable_syntax_is_preserved_as_literal_string,
    test_dynamic_route_path_is_not_guessed,
    test_dynamic_methods_are_not_guessed_and_warn,
    test_syntax_error_does_not_crash_and_returns_empty_result,
    test_non_flask_looking_decorators_are_ignored,
    test_ordering_is_deterministic_by_source_route_method_and_handler,
    test_evidence_includes_decorator_name_and_line_number,
    test_no_repo_or_file_scanning_is_exposed,
    test_docs_say_k4_is_flask_only_and_k5_remains_pending,
]
