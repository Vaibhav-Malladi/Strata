from strata.core.go_backend_common import (
    extract_go_handler_symbol,
    extract_go_http_methods,
    go_evidence,
    go_string_literal,
    normalize_go_source_path,
    parse_go_backend_source,
)


def test_source_path_normalization_is_deterministic():
    assert normalize_go_source_path("cmd\\api\\main.go") == "cmd/api/main.go"


def test_function_symbols_are_extracted_conservatively():
    result = parse_go_backend_source(
        "cmd/api/main.go",
        "func listItems(w http.ResponseWriter, r *http.Request) {}\n"
        "var notAFunction = true\n",
    )

    assert result.to_dict() == {
        "source_path": "cmd/api/main.go",
        "line_count": 2,
        "functions": [
            {"name": "listItems", "receiver": None, "line_number": 1},
        ],
        "warnings": [],
    }


def test_method_receiver_functions_are_extracted_conservatively():
    result = parse_go_backend_source(
        "cmd/api/main.go",
        "func (h *Handler) GetItem(w http.ResponseWriter, r *http.Request) {}\n",
    )

    assert result.functions[0].to_dict() == {
        "name": "GetItem",
        "receiver": "Handler",
        "line_number": 1,
    }


def test_string_literal_helper_accepts_only_literals():
    assert go_string_literal('"/items/{id}"') == "/items/{id}"
    assert go_string_literal('"/escaped/\\"name\\""') == '/escaped/"name"'
    assert go_string_literal("routePath") is None
    assert go_string_literal('fmt.Sprintf("/%s", id)') is None


def test_handler_symbols_extract_from_simple_go_calls():
    assert extract_go_handler_symbol("listItems") == "listItems"
    assert extract_go_handler_symbol("h.ListItems") == "h.ListItems"
    assert extract_go_handler_symbol("handler.List") == "handler.List"
    assert extract_go_handler_symbol("func(w http.ResponseWriter) {}") is None


def test_method_extraction_uses_only_explicit_method_literals():
    assert extract_go_http_methods('"GET", "POST"') == ("GET", "POST")
    assert extract_go_http_methods("methodName") == ()
    assert extract_go_http_methods('"BREW"') == ()


def test_evidence_is_stable():
    assert go_evidence(12, "http.HandleFunc") == "line 12 call http.HandleFunc"


TESTS = [
    test_source_path_normalization_is_deterministic,
    test_function_symbols_are_extracted_conservatively,
    test_method_receiver_functions_are_extracted_conservatively,
    test_string_literal_helper_accepts_only_literals,
    test_handler_symbols_extract_from_simple_go_calls,
    test_method_extraction_uses_only_explicit_method_literals,
    test_evidence_is_stable,
]
