from importlib import import_module

from strata.core.backend_relationships import BackendRelationship
from strata.core.go_routes import infer_go_routes


go_routes = import_module("strata.core.go_routes")


def _payloads(source: str, source_path: str = "cmd\\api\\main.go") -> list[dict]:
    return [relationship.to_dict() for relationship in infer_go_routes(source_path, source)]


def test_http_handle_func_literal_path_creates_any_go_route():
    payloads = _payloads('http.HandleFunc("/items", listItems)\n')

    assert payloads == [
        {
            "framework": "go",
            "relationship_type": "backend_route",
            "source_path": "cmd/api/main.go",
            "target_path": "cmd/api/main.go",
            "target_symbol": "listItems",
            "route_path": "/items",
            "http_method": "ANY",
            "handler_symbol": "listItems",
            "service_symbol": None,
            "model_symbol": None,
            "confidence": "high",
            "evidence": ["line 1 call http.HandleFunc"],
            "warnings": [],
            "reason": "go_http_handle",
        }
    ]
    assert isinstance(infer_go_routes("cmd/api/main.go", 'http.HandleFunc("/x", h)\n')[0], BackendRelationship)


def test_http_handle_literal_path_creates_route():
    payloads = _payloads('http.Handle("/items", handler)\n')

    assert payloads[0]["http_method"] == "ANY"
    assert payloads[0]["handler_symbol"] == "handler"
    assert payloads[0]["evidence"] == ["line 1 call http.Handle"]


def test_mux_handle_func_with_methods_creates_deterministic_relationships():
    payloads = _payloads('router.HandleFunc("/items/{id}", getItem).Methods("POST", "GET")\n')

    assert [
        (payload["route_path"], payload["http_method"], payload["handler_symbol"], payload["reason"])
        for payload in payloads
    ] == [
        ("/items/{id}", "GET", "getItem", "go_mux_methods"),
        ("/items/{id}", "POST", "getItem", "go_mux_methods"),
    ]


def test_methods_path_handler_func_pattern_is_supported():
    payloads = _payloads('r.Methods("POST").Path("/items").HandlerFunc(createItem)\n')

    assert payloads[0]["route_path"] == "/items"
    assert payloads[0]["http_method"] == "POST"
    assert payloads[0]["handler_symbol"] == "createItem"


def test_chi_style_methods_create_method_aware_routes():
    source = "\n".join(
        [
            'r.Get("/items", listItems)',
            'r.Post("/items", createItem)',
            'r.Put("/items/{id}", updateItem)',
            'r.Patch("/items/{id}", patchItem)',
            'r.Delete("/items/{id}", deleteItem)',
        ]
    )

    assert [
        (payload["route_path"], payload["http_method"], payload["handler_symbol"])
        for payload in _payloads(source)
    ] == [
        ("/items", "GET", "listItems"),
        ("/items", "POST", "createItem"),
        ("/items/{id}", "PUT", "updateItem"),
        ("/items/{id}", "PATCH", "patchItem"),
        ("/items/{id}", "DELETE", "deleteItem"),
    ]


def test_dynamic_route_path_is_ignored():
    assert _payloads('http.HandleFunc(routePath, listItems)\n') == []


def test_handler_symbol_captures_member_selectors():
    payloads = _payloads('mux.HandleFunc("/items", handler.List)\n')

    assert payloads[0]["handler_symbol"] == "handler.List"
    assert payloads[0]["confidence"] == "medium"


def test_non_route_go_calls_are_ignored():
    assert _payloads('fmt.Println("/items")\nclient.Get("/items")\n') == []


def test_deterministic_ordering_by_route_method_handler():
    source = 'r.Post("/z", zed)\nr.Get("/a", alpha)\nr.Get("/z", zedGet)\n'

    assert [
        (payload["route_path"], payload["http_method"], payload["handler_symbol"])
        for payload in _payloads(source)
    ] == [
        ("/a", "GET", "alpha"),
        ("/z", "GET", "zedGet"),
        ("/z", "POST", "zed"),
    ]


def test_evidence_includes_pattern_and_line_number():
    payloads = _payloads('\n\nr.Delete("/items/{id}", deleteItem)\n')

    assert payloads[0]["evidence"] == ["line 3 call r.Delete"]


def test_no_repo_or_file_scanning_is_exposed():
    public_names = tuple(name for name in dir(go_routes) if not name.startswith("_"))
    forbidden_words = ("scan", "scanner", "walk_repo", "read_file", "glob")

    assert "infer_go_routes" in public_names
    assert not [
        name
        for name in public_names
        if any(word in name.lower() for word in forbidden_words)
    ]


TESTS = [
    test_http_handle_func_literal_path_creates_any_go_route,
    test_http_handle_literal_path_creates_route,
    test_mux_handle_func_with_methods_creates_deterministic_relationships,
    test_methods_path_handler_func_pattern_is_supported,
    test_chi_style_methods_create_method_aware_routes,
    test_dynamic_route_path_is_ignored,
    test_handler_symbol_captures_member_selectors,
    test_non_route_go_calls_are_ignored,
    test_deterministic_ordering_by_route_method_handler,
    test_evidence_includes_pattern_and_line_number,
    test_no_repo_or_file_scanning_is_exposed,
]
