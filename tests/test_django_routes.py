from importlib import import_module

from strata.core.backend_relationships import BackendRelationship
from strata.core.django_routes import infer_django_routes


django_routes = import_module("strata.core.django_routes")


def _payloads(source: str, source_path: str = "app\\urls.py") -> list[dict]:
    return [relationship.to_dict() for relationship in infer_django_routes(source_path, source)]


def test_path_literal_route_creates_relationship():
    payloads = _payloads('urlpatterns = [path("items/", views.items)]\n')

    assert payloads == [
        {
            "framework": "django",
            "relationship_type": "backend_route",
            "source_path": "app/urls.py",
            "target_path": "app/urls.py",
            "target_symbol": "views.items",
            "route_path": "items/",
            "http_method": "ANY",
            "handler_symbol": "views.items",
            "service_symbol": None,
            "model_symbol": None,
            "confidence": "high",
            "evidence": ["line 1 call path"],
            "warnings": [],
            "reason": "django_urlpattern",
        }
    ]
    assert isinstance(infer_django_routes("app/urls.py", 'urlpatterns = [path("x/", views.x)]')[0], BackendRelationship)


def test_re_path_literal_route_creates_relationship():
    payloads = _payloads('urlpatterns = [re_path(r"^items/$", views.items)]\n')

    assert payloads[0]["framework"] == "django"
    assert payloads[0]["route_path"] == "^items/$"
    assert payloads[0]["handler_symbol"] == "views.items"
    assert payloads[0]["evidence"] == ["line 1 call re_path"]


def test_include_literal_prefix_is_handled_conservatively():
    payloads = _payloads('urlpatterns = [path("api/", include("app.urls"))]\n')

    assert payloads[0]["route_path"] == "api/"
    assert payloads[0]["target_symbol"] == "app.urls"
    assert payloads[0]["confidence"] == "low"
    assert payloads[0]["warnings"] == ["Django include target is not resolved across files."]


def test_api_view_methods_create_route_handler_relationships():
    source = '@api_view(["POST", "GET"])\ndef items(request):\n    pass\n'
    payloads = _payloads(source, source_path="app/views.py")

    assert [
        (payload["relationship_type"], payload["http_method"], payload["handler_symbol"])
        for payload in payloads
    ] == [
        ("route_handler", "GET", "items"),
        ("route_handler", "POST", "items"),
    ]
    assert all(payload["framework"] == "django_rest_framework" for payload in payloads)
    assert all(payload["route_path"] is None for payload in payloads)
    assert all(payload["evidence"] == ["line 1 decorator api_view"] for payload in payloads)


def test_dynamic_paths_are_not_guessed():
    assert _payloads('urlpatterns = [path(prefix + "items/", views.items)]\n') == []


def test_syntax_errors_do_not_crash():
    assert infer_django_routes("app/urls.py", "urlpatterns = [path(\n") == []


def test_non_django_calls_are_ignored():
    assert _payloads('other("items/", views.items)\nnot_path("x", y)\n') == []


def test_deterministic_ordering():
    source = (
        'urlpatterns = [path("z/", views.z), path("a/", views.a)]\n'
        '@api_view(["DELETE"])\n'
        "def delete_item(request):\n"
        "    pass\n"
    )

    assert [
        (payload["route_path"], payload["http_method"], payload["handler_symbol"])
        for payload in _payloads(source)
    ] == [
        (None, "DELETE", "delete_item"),
        ("a/", "ANY", "views.a"),
        ("z/", "ANY", "views.z"),
    ]


def test_evidence_includes_call_or_decorator_and_line_number():
    source = '\nurlpatterns = [url(r"^items/$", views.items)]\n\n@api_view(["GET"])\ndef items(request):\n    pass\n'
    payloads = _payloads(source)

    assert [payload["evidence"][0] for payload in payloads] == [
        "line 4 decorator api_view",
        "line 2 call url",
    ]


def test_router_register_literal_prefix_is_medium_confidence():
    payloads = _payloads('router.register("users", UserViewSet)\n')

    assert payloads[0]["framework"] == "django_rest_framework"
    assert payloads[0]["route_path"] == "users"
    assert payloads[0]["handler_symbol"] == "UserViewSet"
    assert payloads[0]["confidence"] == "medium"
    assert payloads[0]["reason"] == "drf_router_register"


def test_drf_class_based_hints_are_route_handlers_only():
    payloads = _payloads("class UserAPIView(APIView):\n    pass\n", source_path="app/views.py")

    assert payloads[0]["framework"] == "django_rest_framework"
    assert payloads[0]["relationship_type"] == "route_handler"
    assert payloads[0]["route_path"] is None
    assert payloads[0]["http_method"] == "ANY"
    assert payloads[0]["handler_symbol"] == "UserAPIView"
    assert payloads[0]["confidence"] == "medium"
    assert payloads[0]["reason"] == "drf_class_view"


def test_docs_say_k5_k6_k7_are_source_text_only_and_go_is_pending():
    with open(
        "docs/roadmap/backend-intelligence-foundation.md",
        encoding="utf-8",
    ) as handle:
        content = handle.read()

    assert "K5-K7 infer routes only from supplied source text" in content
    assert "K8/K9 Go backend work remains pending" in content


TESTS = [
    test_path_literal_route_creates_relationship,
    test_re_path_literal_route_creates_relationship,
    test_include_literal_prefix_is_handled_conservatively,
    test_api_view_methods_create_route_handler_relationships,
    test_dynamic_paths_are_not_guessed,
    test_syntax_errors_do_not_crash,
    test_non_django_calls_are_ignored,
    test_deterministic_ordering,
    test_evidence_includes_call_or_decorator_and_line_number,
    test_router_register_literal_prefix_is_medium_confidence,
    test_drf_class_based_hints_are_route_handlers_only,
    test_docs_say_k5_k6_k7_are_source_text_only_and_go_is_pending,
]
