import ast
import json
from importlib import import_module

from strata.core.backend_relationships import BackendRelationship
from strata.core.python_backend_common import (
    PythonBackendEvidence,
    PythonBackendParseResult,
    PythonBackendSymbol,
    build_backend_relationship_from_route_facts,
    build_python_backend_evidence,
    literal_route_path_from_decorator,
    normalize_decorator_name,
    normalize_http_method,
    parse_python_backend_source,
    python_backend_evidence_to_dict,
    python_backend_parse_result_to_dict,
    python_backend_symbol_from_node,
    python_backend_symbol_to_dict,
    python_backend_symbols_from_tree,
)


common = import_module("strata.core.python_backend_common")


def _decorator(source: str) -> ast.AST:
    result = parse_python_backend_source(source, source_path="app/routes.py")
    assert result.tree is not None
    function = result.tree.body[0]
    assert isinstance(function, ast.FunctionDef)
    return function.decorator_list[0]


def _expect_error(error_type, function, *args, contains: str, **kwargs):
    try:
        function(*args, **kwargs)
    except error_type as error:
        assert contains in str(error)
    else:
        raise AssertionError(f"Expected {error_type.__name__}")


def test_valid_python_ast_parse_result_is_deterministic_and_json_ready():
    result = parse_python_backend_source(
        "class UserService:\n    pass\n\ndef get_user():\n    return None\n",
        source_path="app\\routes.py",
    )

    assert isinstance(result, PythonBackendParseResult)
    assert result.ok is True
    assert result.tree is not None
    assert result.to_dict() == {
        "source_path": "app/routes.py",
        "ok": True,
        "body_count": 2,
        "top_level_symbols": ["UserService", "get_user"],
        "warnings": [],
        "errors": [],
    }
    assert python_backend_parse_result_to_dict(result) == result.to_dict()
    assert json.loads(json.dumps(result.to_dict(), allow_nan=False)) == result.to_dict()


def test_syntax_errors_return_safe_failure_shape():
    result = parse_python_backend_source(
        "def broken(:\n    pass\n",
        source_path="app/routes.py",
    )

    assert result.ok is False
    assert result.tree is None
    assert result.to_dict()["warnings"] == ["Python source could not be parsed."]
    assert result.to_dict()["errors"] == ["SyntaxError: invalid syntax at line 1"]


def test_decorator_names_normalize_deterministically():
    examples = {
        '@app.get("/x")\ndef handler():\n    pass\n': "app.get",
        '@router.post("/x")\ndef handler():\n    pass\n': "router.post",
        '@blueprint.route("/x")\ndef handler():\n    pass\n': "blueprint.route",
        '@api_view(["GET"])\ndef handler():\n    pass\n': "api_view",
        '@permission_classes([])\ndef handler():\n    pass\n': "permission_classes",
    }

    assert {
        source: normalize_decorator_name(_decorator(source))
        for source in examples
    } == examples


def test_string_route_paths_are_extracted_only_from_literals():
    positional = literal_route_path_from_decorator(
        _decorator('@router.get("/users/{id}")\ndef handler():\n    pass\n')
    )
    keyword = literal_route_path_from_decorator(
        _decorator('@blueprint.route(rule="/status")\ndef handler():\n    pass\n')
    )

    assert positional.to_dict() == {"route_path": "/users/{id}", "warnings": []}
    assert keyword.to_dict() == {"route_path": "/status", "warnings": []}


def test_dynamic_route_paths_are_ignored_with_warning():
    dynamic = literal_route_path_from_decorator(
        _decorator('@router.get(prefix + "/users")\ndef handler():\n    pass\n')
    )
    formatted = literal_route_path_from_decorator(
        _decorator('@router.get(f"/users/{id}")\ndef handler():\n    pass\n')
    )

    assert dynamic.route_path is None
    assert formatted.route_path is None
    assert dynamic.warnings == (
        "Dynamic route path ignored; only string literals are supported.",
    )
    assert formatted.warnings == dynamic.warnings


def test_http_method_normalization_is_stable():
    assert normalize_http_method("get") == "GET"
    assert normalize_http_method("POST") == "POST"
    assert normalize_http_method("put") == "PUT"
    assert normalize_http_method("patch") == "PATCH"
    assert normalize_http_method("delete") == "DELETE"
    assert normalize_http_method("options") == "OPTIONS"
    assert normalize_http_method("head") == "HEAD"
    assert normalize_http_method("route") == "unknown"
    assert normalize_http_method("route", explicit_any=True) == "ANY"
    assert normalize_http_method("whatever") == "unknown"


def test_function_and_class_symbol_helpers_are_deterministic():
    result = parse_python_backend_source(
        "async def get_user():\n    pass\n\n"
        "class BillingService:\n    pass\n\n"
        "class AccountModel:\n    pass\n\n"
        "class PlainThing:\n    pass\n",
        source_path="app/routes.py",
    )

    symbols = python_backend_symbols_from_tree(result.tree)
    assert [symbol.to_dict() for symbol in symbols] == [
        {
            "name": "get_user",
            "symbol_type": "function",
            "candidate_kind": "handler",
            "line_number": 1,
        },
        {
            "name": "BillingService",
            "symbol_type": "class",
            "candidate_kind": "service",
            "line_number": 4,
        },
        {
            "name": "AccountModel",
            "symbol_type": "class",
            "candidate_kind": "model",
            "line_number": 7,
        },
        {
            "name": "PlainThing",
            "symbol_type": "class",
            "candidate_kind": "unknown",
            "line_number": 10,
        },
    ]
    assert isinstance(symbols[0], PythonBackendSymbol)
    assert python_backend_symbol_to_dict(symbols[0]) == symbols[0].to_dict()

    assert python_backend_symbol_from_node(ast.Pass()) is None


def test_evidence_includes_line_numbers_and_decorator_details():
    source = '@app.get("/x")\ndef handler():\n    pass\n'
    result = parse_python_backend_source(source, source_path="app/routes.py")
    assert result.tree is not None
    function = result.tree.body[0]
    assert isinstance(function, ast.FunctionDef)

    evidence = build_python_backend_evidence(
        source_path="app/routes.py",
        node=function,
        decorator=function.decorator_list[0],
        source=source,
    )

    assert isinstance(evidence, PythonBackendEvidence)
    assert evidence.to_dict() == {
        "source_path": "app/routes.py",
        "line_number": 1,
        "decorator_name": "app.get",
        "decorator_text": 'app.get("/x")',
        "warnings": [],
    }
    assert python_backend_evidence_to_dict(evidence) == evidence.to_dict()


def test_helper_can_create_backend_relationship_from_explicit_route_facts():
    relationship = build_backend_relationship_from_route_facts(
        source_path="app/routes.py",
        framework="generic_backend",
        route_path="/users",
        http_method="get",
        handler_symbol="list_users",
        confidence="medium",
        evidence=("app/routes.py:12 decorator app.get",),
        reason="explicit facts supplied by caller",
    )

    assert isinstance(relationship, BackendRelationship)
    assert relationship.to_dict() == {
        "framework": "generic_backend",
        "relationship_type": "route_handler",
        "source_path": "app/routes.py",
        "target_path": None,
        "target_symbol": None,
        "route_path": "/users",
        "http_method": "GET",
        "handler_symbol": "list_users",
        "service_symbol": None,
        "model_symbol": None,
        "confidence": "medium",
        "evidence": ["app/routes.py:12 decorator app.get"],
        "warnings": [],
        "reason": "explicit facts supplied by caller",
    }


def test_no_framework_specific_extraction_apis_are_exposed_yet():
    public_names = tuple(name for name in dir(common) if not name.startswith("_"))
    forbidden_words = (
        "fastapi",
        "flask",
        "django",
        "drf",
        "express",
        "nestjs",
        "go_http",
        "scanner",
        "detector",
    )

    assert not [
        name
        for name in public_names
        if any(word in name.lower() for word in forbidden_words)
    ]


def test_docs_say_k2_is_common_python_backend_infrastructure_only():
    with open(
        "docs/roadmap/backend-intelligence-foundation.md",
        encoding="utf-8",
    ) as handle:
        content = handle.read()

    assert "K2 is common Python backend infrastructure only" in content
    assert "does not detect FastAPI, Flask, Django, or DRF routes" in content


def test_invalid_inputs_are_rejected_without_guessing():
    _expect_error(TypeError, parse_python_backend_source, None, contains="source")
    _expect_error(TypeError, normalize_http_method, 3, contains="method")
    _expect_error(
        ValueError,
        build_backend_relationship_from_route_facts,
        source_path="app/routes.py",
        framework="rails",
        contains="framework",
    )


TESTS = [
    test_valid_python_ast_parse_result_is_deterministic_and_json_ready,
    test_syntax_errors_return_safe_failure_shape,
    test_decorator_names_normalize_deterministically,
    test_string_route_paths_are_extracted_only_from_literals,
    test_dynamic_route_paths_are_ignored_with_warning,
    test_http_method_normalization_is_stable,
    test_function_and_class_symbol_helpers_are_deterministic,
    test_evidence_includes_line_numbers_and_decorator_details,
    test_helper_can_create_backend_relationship_from_explicit_route_facts,
    test_no_framework_specific_extraction_apis_are_exposed_yet,
    test_docs_say_k2_is_common_python_backend_infrastructure_only,
    test_invalid_inputs_are_rejected_without_guessing,
]
