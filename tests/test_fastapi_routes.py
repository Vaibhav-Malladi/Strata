from importlib import import_module

from strata.core.backend_relationships import BackendRelationship
from strata.core.fastapi_routes import infer_fastapi_routes


fastapi_routes = import_module("strata.core.fastapi_routes")


def _payloads(source: str, source_path: str = "app\\api.py") -> list[dict]:
    return [relationship.to_dict() for relationship in infer_fastapi_routes(source_path, source)]


def test_app_get_literal_path_creates_high_confidence_fastapi_route():
    payloads = _payloads('@app.get("/items")\ndef list_items():\n    pass\n')

    assert payloads == [
        {
            "framework": "fastapi",
            "relationship_type": "backend_route",
            "source_path": "app/api.py",
            "target_path": "app/api.py",
            "target_symbol": "list_items",
            "route_path": "/items",
            "http_method": "GET",
            "handler_symbol": "list_items",
            "service_symbol": None,
            "model_symbol": None,
            "confidence": "high",
            "evidence": ["line 1 decorator app.get"],
            "warnings": [],
            "reason": "fastapi_decorator",
        }
    ]
    assert isinstance(infer_fastapi_routes("app/api.py", '@app.get("/x")\ndef h():\n    pass\n')[0], BackendRelationship)


def test_router_post_literal_path_creates_one_route():
    payloads = _payloads('@router.post("/items")\ndef create_item():\n    pass\n')

    assert len(payloads) == 1
    assert payloads[0]["framework"] == "fastapi"
    assert payloads[0]["route_path"] == "/items"
    assert payloads[0]["http_method"] == "POST"
    assert payloads[0]["handler_symbol"] == "create_item"


def test_common_method_decorators_normalize_http_methods():
    source = "\n\n".join(
        f'@api_router.{method}("/{method}")\ndef handle_{method}():\n    pass'
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


def test_api_route_with_methods_creates_deterministic_relationships():
    payloads = _payloads(
        '@app.api_route("/items", methods=["POST", "GET"])\n'
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
    assert all(payload["evidence"] == ["line 1 decorator app.api_route"] for payload in payloads)


def test_api_route_without_methods_uses_any():
    payloads = _payloads('@router.api_route("/items")\ndef handle_items():\n    pass\n')

    assert len(payloads) == 1
    assert payloads[0]["http_method"] == "ANY"
    assert payloads[0]["route_path"] == "/items"


def test_dynamic_route_path_is_not_guessed():
    payloads = _payloads('@router.get(prefix + "/items")\ndef list_items():\n    pass\n')

    assert payloads == []


def test_syntax_error_does_not_crash_and_returns_empty_result():
    assert infer_fastapi_routes("app/api.py", "def broken(:\n    pass\n") == []


def test_non_fastapi_looking_decorators_are_ignored():
    source = (
        '@get("/bare")\n'
        "def bare_handler():\n"
        "    pass\n\n"
        '@permission_classes([])\n'
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
        '@router.post("/z")\n'
        "def zed():\n"
        "    pass\n\n"
        '@router.get("/a")\n'
        "def alpha():\n"
        "    pass\n\n"
        '@router.get("/z")\n'
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
    payloads = _payloads('\n\n@api_router.patch("/items/{item_id}")\ndef update_item():\n    pass\n')

    assert payloads[0]["evidence"] == ["line 3 decorator api_router.patch"]


def test_no_repo_or_file_scanning_is_exposed():
    public_names = tuple(name for name in dir(fastapi_routes) if not name.startswith("_"))
    forbidden_words = ("scan", "scanner", "walk_repo", "read_file", "glob")

    assert "infer_fastapi_routes" in public_names
    assert not [
        name
        for name in public_names
        if any(word in name.lower() for word in forbidden_words)
    ]


def test_docs_say_k3_is_fastapi_only_and_k4_k5_remain_pending():
    with open(
        "docs/roadmap/backend-intelligence-foundation.md",
        encoding="utf-8",
    ) as handle:
        content = handle.read()

    assert "K3 covers FastAPI route extraction only" in content
    assert "K4 Flask and K5 Django/DRF remain pending" in content


TESTS = [
    test_app_get_literal_path_creates_high_confidence_fastapi_route,
    test_router_post_literal_path_creates_one_route,
    test_common_method_decorators_normalize_http_methods,
    test_api_route_with_methods_creates_deterministic_relationships,
    test_api_route_without_methods_uses_any,
    test_dynamic_route_path_is_not_guessed,
    test_syntax_error_does_not_crash_and_returns_empty_result,
    test_non_fastapi_looking_decorators_are_ignored,
    test_ordering_is_deterministic_by_source_route_method_and_handler,
    test_evidence_includes_decorator_name_and_line_number,
    test_no_repo_or_file_scanning_is_exposed,
    test_docs_say_k3_is_fastapi_only_and_k4_k5_remain_pending,
]
