from importlib import import_module

from strata.core.backend_relationships import BackendRelationship
from strata.core.nestjs_routes import infer_nestjs_routes


nestjs_routes = import_module("strata.core.nestjs_routes")


def _payloads(source: str, source_path: str = "src\\users.controller.ts") -> list[dict]:
    return [relationship.to_dict() for relationship in infer_nestjs_routes(source_path, source)]


def test_controller_and_get_combine_route_path():
    source = (
        '@Controller("users")\n'
        "export class UsersController {\n"
        '  @Get(":id")\n'
        "  findOne() {}\n"
        "}\n"
    )
    payloads = _payloads(source)

    assert payloads == [
        {
            "framework": "nestjs",
            "relationship_type": "backend_route",
            "source_path": "src/users.controller.ts",
            "target_path": "src/users.controller.ts",
            "target_symbol": "findOne",
            "route_path": "/users/:id",
            "http_method": "GET",
            "handler_symbol": "findOne",
            "service_symbol": None,
            "model_symbol": None,
            "confidence": "high",
            "evidence": ["line 3 decorator Get"],
            "warnings": [],
            "reason": "nestjs_controller_route",
        }
    ]
    assert isinstance(infer_nestjs_routes("src/users.controller.ts", source)[0], BackendRelationship)


def test_post_put_patch_delete_methods_normalize():
    source = (
        '@Controller("items")\n'
        "class ItemsController {\n"
        '  @Post()\n  create() {}\n'
        '  @Put(":id")\n  replace() {}\n'
        '  @Patch(":id")\n  update() {}\n'
        '  @Delete(":id")\n  remove() {}\n'
        "}\n"
    )

    assert [
        (payload["route_path"], payload["http_method"], payload["handler_symbol"])
        for payload in _payloads(source)
    ] == [
        ("/items", "POST", "create"),
        ("/items/:id", "PUT", "replace"),
        ("/items/:id", "PATCH", "update"),
        ("/items/:id", "DELETE", "remove"),
    ]


def test_empty_controller_or_method_path_is_deterministic():
    source = (
        "@Controller()\n"
        "class HealthController {\n"
        '  @Get("health")\n  health() {}\n'
        "  @Head()\n  rootHead() {}\n"
        "}\n"
    )

    assert [
        (payload["route_path"], payload["http_method"], payload["handler_symbol"])
        for payload in _payloads(source)
    ] == [
        ("/", "HEAD", "rootHead"),
        ("/health", "GET", "health"),
    ]


def test_dynamic_controller_or_method_paths_are_not_guessed():
    dynamic_controller = (
        "@Controller(prefix)\n"
        "class UsersController {\n"
        '  @Get(":id")\n  findOne() {}\n'
        "}\n"
    )
    dynamic_method = (
        '@Controller("users")\n'
        "class UsersController {\n"
        "  @Get(routeName)\n  findOne() {}\n"
        "}\n"
    )

    assert _payloads(dynamic_controller) == []
    assert _payloads(dynamic_method) == []


def test_syntax_like_parse_failures_do_not_crash():
    assert infer_nestjs_routes("src/broken.ts", "@Controller('x')\nclass Broken {\n") == []


def test_non_nest_decorators_are_ignored():
    source = (
        '@Injectable()\n'
        "class Service {}\n"
        '@Controller("users")\n'
        "class UsersController {\n"
        "  @UseGuards(AuthGuard)\n"
        "  guarded() {}\n"
        "}\n"
    )

    assert _payloads(source) == []


def test_deterministic_ordering():
    source = (
        '@Controller("z")\n'
        "class ZController {\n"
        '  @Post("b")\n  postB() {}\n'
        '  @Get("a")\n  getA() {}\n'
        "}\n"
    )

    assert [
        (payload["route_path"], payload["http_method"], payload["handler_symbol"])
        for payload in _payloads(source)
    ] == [
        ("/z/a", "GET", "getA"),
        ("/z/b", "POST", "postB"),
    ]


def test_no_repo_or_file_scanning_is_exposed():
    public_names = tuple(name for name in dir(nestjs_routes) if not name.startswith("_"))
    forbidden_words = ("scan", "scanner", "walk_repo", "read_file", "glob")

    assert "infer_nestjs_routes" in public_names
    assert not [
        name
        for name in public_names
        if any(word in name.lower() for word in forbidden_words)
    ]


TESTS = [
    test_controller_and_get_combine_route_path,
    test_post_put_patch_delete_methods_normalize,
    test_empty_controller_or_method_path_is_deterministic,
    test_dynamic_controller_or_method_paths_are_not_guessed,
    test_syntax_like_parse_failures_do_not_crash,
    test_non_nest_decorators_are_ignored,
    test_deterministic_ordering,
    test_no_repo_or_file_scanning_is_exposed,
]
