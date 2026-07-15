from importlib import import_module

from strata.core.backend_relationships import BackendRelationship
from strata.core.express_routes import infer_express_routes


express_routes = import_module("strata.core.express_routes")


def _payloads(source: str, source_path: str = "src\\routes.ts") -> list[dict]:
    return [relationship.to_dict() for relationship in infer_express_routes(source_path, source)]


def test_app_get_literal_path_creates_high_confidence_route():
    payloads = _payloads('app.get("/items", listItems);\n')

    assert payloads == [
        {
            "framework": "express",
            "relationship_type": "backend_route",
            "source_path": "src/routes.ts",
            "target_path": "src/routes.ts",
            "target_symbol": "listItems",
            "route_path": "/items",
            "http_method": "GET",
            "handler_symbol": "listItems",
            "service_symbol": None,
            "model_symbol": None,
            "confidence": "high",
            "evidence": ["line 1 call app.get"],
            "warnings": [],
            "reason": "express_route_call",
        }
    ]
    assert isinstance(infer_express_routes("src/routes.ts", 'app.get("/x", h);')[0], BackendRelationship)


def test_router_post_literal_path_creates_one_route():
    payloads = _payloads('router.post("/items", controller.createItem);\n')

    assert payloads[0]["route_path"] == "/items"
    assert payloads[0]["http_method"] == "POST"
    assert payloads[0]["handler_symbol"] == "controller.createItem"


def test_all_common_http_methods_normalize():
    source = "\n".join(
        f'app.{method}("/{method}", handle{method});'
        for method in ("get", "post", "put", "patch", "delete", "options", "head")
    )

    assert [
        (payload["route_path"], payload["http_method"])
        for payload in _payloads(source)
    ] == [
        ("/delete", "DELETE"),
        ("/get", "GET"),
        ("/head", "HEAD"),
        ("/options", "OPTIONS"),
        ("/patch", "PATCH"),
        ("/post", "POST"),
        ("/put", "PUT"),
    ]


def test_router_route_chain_creates_deterministic_relationships():
    payloads = _payloads('router.route("/items").post(createItem).get(listItems);\n')

    assert [
        (payload["route_path"], payload["http_method"], payload["handler_symbol"], payload["reason"])
        for payload in payloads
    ] == [
        ("/items", "GET", "listItems", "express_chained_route"),
        ("/items", "POST", "createItem", "express_chained_route"),
    ]


def test_dynamic_route_path_is_ignored():
    assert _payloads("app.get(`/items/${id}`, handler);\n") == []
    assert _payloads("app.get(prefix + '/items', handler);\n") == []


def test_handler_symbol_is_captured_for_simple_identifiers_members_and_functions():
    source = (
        'app.get("/a", listItems);\n'
        'app.get("/b", controller.listItems);\n'
        'app.get("/c", async function inlineItems(req, res) {});\n'
    )

    assert [
        (payload["route_path"], payload["handler_symbol"])
        for payload in _payloads(source)
    ] == [
        ("/a", "listItems"),
        ("/b", "controller.listItems"),
        ("/c", "inlineItems"),
    ]


def test_non_express_looking_calls_are_ignored():
    assert _payloads('client.get("/items", handler);\nget("/bare", handler);\n') == []


def test_deterministic_ordering():
    source = 'router.post("/z", zed);\nrouter.get("/a", alpha);\nrouter.get("/z", zedGet);\n'

    assert [
        (payload["route_path"], payload["http_method"], payload["handler_symbol"])
        for payload in _payloads(source)
    ] == [
        ("/a", "GET", "alpha"),
        ("/z", "GET", "zedGet"),
        ("/z", "POST", "zed"),
    ]


def test_no_repo_or_file_scanning_is_exposed():
    public_names = tuple(name for name in dir(express_routes) if not name.startswith("_"))
    forbidden_words = ("scan", "scanner", "walk_repo", "read_file", "glob")

    assert "infer_express_routes" in public_names
    assert not [
        name
        for name in public_names
        if any(word in name.lower() for word in forbidden_words)
    ]


TESTS = [
    test_app_get_literal_path_creates_high_confidence_route,
    test_router_post_literal_path_creates_one_route,
    test_all_common_http_methods_normalize,
    test_router_route_chain_creates_deterministic_relationships,
    test_dynamic_route_path_is_ignored,
    test_handler_symbol_is_captured_for_simple_identifiers_members_and_functions,
    test_non_express_looking_calls_are_ignored,
    test_deterministic_ordering,
    test_no_repo_or_file_scanning_is_exposed,
]
