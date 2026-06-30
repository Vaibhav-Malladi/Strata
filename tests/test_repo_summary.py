import repo_summary as old_repo_summary
import strata.core.repo_summary as new_repo_summary
from repo_summary import summarize_graph


def _empty_frontend_buckets() -> dict:
    return {
        "components": [],
        "services": [],
        "modules": [],
        "routes": [],
    }


def test_core_repo_summary_import_matches_compatibility_shim():
    assert old_repo_summary.summarize_graph is new_repo_summary.summarize_graph


def _make_file(path: str, language: str, **overrides) -> dict:
    file_info = {
        "path": path,
        "language": language,
        "imports": [],
        "external_imports": [],
        "unresolved_imports": [],
        "path_alias_imports": [],
        "classes": [],
        "functions": [],
        "components": [],
        "hooks": [],
        "framework": "",
        "frameworks": [],
        "angular": _empty_frontend_buckets(),
    }
    file_info.update(overrides)

    angular = file_info.get("angular")
    if not isinstance(angular, dict):
        file_info["angular"] = _empty_frontend_buckets()

    return file_info


def _python_graph() -> dict:
    return {
        "schema_version": 1,
        "root": "sample",
        "files": [
            _make_file(
                "src/app.py",
                "python",
                imports=["os"],
                external_imports=["os"],
                functions=[{"name": "run"}],
                classes=[{"name": "App"}],
            ),
            _make_file(
                "src/helper.py",
                "python",
                functions=[{"name": "helper"}],
            ),
        ],
        "edges": [
            {
                "from": "src/app.py",
                "to": "src/helper.py",
                "type": "imports",
                "import": "helper",
            }
        ],
    }


def _js_ts_graph() -> dict:
    return {
        "schema_version": 1,
        "root": "sample",
        "files": [
            _make_file("src/app.ts", "typescript"),
            _make_file("src/legacy.js", "javascript"),
        ],
        "edges": [],
    }


def _frontend_graph() -> dict:
    return {
        "schema_version": 1,
        "root": "sample",
        "files": [
            _make_file(
                "src/App.tsx",
                "typescript",
                framework="react",
                frameworks=["react"],
                imports=["react", "@/components/Button", "@my/shared", "./local", "missing-lib"],
                external_imports=["react"],
                path_alias_imports=["@/components/Button"],
                unresolved_imports=["missing-lib"],
                components=[{"name": "App"}],
                hooks=[{"name": "useState"}],
            ),
            _make_file(
                "src/components/Button.jsx",
                "javascript",
                framework="react",
                frameworks=["react"],
                components=[{"name": "Button"}],
            ),
            _make_file(
                "src/app.component.ts",
                "typescript",
                framework="angular",
                frameworks=["angular"],
                angular={
                    "components": [{"name": "AppComponent"}],
                    "services": [],
                    "modules": [{"name": "AppModule"}],
                    "routes": [{"name": "home", "path": "home"}],
                },
            ),
            _make_file(
                "src/user.service.ts",
                "typescript",
                framework="angular",
                frameworks=["angular"],
                angular={
                    "components": [],
                    "services": [{"name": "UserService"}],
                    "modules": [],
                    "routes": [],
                },
            ),
            _make_file(
                "src/local.ts",
                "typescript",
            ),
            _make_file(
                "packages/shared/src/index.ts",
                "typescript",
                classes=[{"name": "Shared"}],
            ),
        ],
        "edges": [
            {
                "from": "src/App.tsx",
                "to": "src/components/Button.jsx",
                "type": "imports",
                "import": "@/components/Button",
            },
            {
                "from": "src/App.tsx",
                "to": "packages/shared/src/index.ts",
                "type": "imports",
                "import": "@my/shared",
            },
            {
                "from": "src/App.tsx",
                "to": "src/local.ts",
                "type": "imports",
                "import": "./local",
            },
            {
                "from": "src/app.component.ts",
                "to": "src/user.service.ts",
                "type": "imports",
                "import": "./user.service",
            },
        ],
    }


def _import_graph() -> dict:
    return {
        "schema_version": 1,
        "root": "sample",
        "files": [
            _make_file(
                "src/App.tsx",
                "typescript",
                imports=["react", "@/components/Button", "@my/shared", "./local", "missing-lib"],
                external_imports=["react"],
                path_alias_imports=["@/components/Button"],
                unresolved_imports=["missing-lib"],
            )
        ],
        "edges": [
            {
                "from": "src/App.tsx",
                "to": "src/components/Button.tsx",
                "type": "imports",
                "import": "@/components/Button",
            },
            {
                "from": "src/App.tsx",
                "to": "packages/shared/src/index.ts",
                "type": "imports",
                "import": "@my/shared",
            },
            {
                "from": "src/App.tsx",
                "to": "src/local.ts",
                "type": "imports",
                "import": "./local",
            },
        ],
    }


def test_empty_graph_summary_works():
    summary = summarize_graph({})

    assert summary == {
        "languages": {},
        "frameworks": {},
        "symbols": {
            "functions": 0,
            "classes": 0,
            "components": 0,
            "hooks": 0,
            "angular_components": 0,
            "angular_services": 0,
            "angular_modules": 0,
            "angular_routes": 0,
        },
        "imports": {
            "resolved_edges": 0,
            "unresolved": 0,
            "external": 0,
            "path_alias": 0,
            "workspace": 0,
        },
        "top_files": [],
    }


def test_python_language_count_works():
    summary = summarize_graph(_python_graph())

    assert summary["languages"] == {"python": 2}


def test_typescript_and_javascript_language_count_works():
    summary = summarize_graph(_js_ts_graph())

    assert summary["languages"] == {
        "javascript": 1,
        "typescript": 1,
    }


def test_react_framework_count_works():
    summary = summarize_graph(_frontend_graph())

    assert summary["frameworks"]["react"] == 2


def test_angular_framework_count_works():
    summary = summarize_graph(_frontend_graph())

    assert summary["frameworks"]["angular"] == 2


def test_components_count_works():
    summary = summarize_graph(_frontend_graph())

    assert summary["symbols"]["components"] == 2


def test_hooks_count_works():
    summary = summarize_graph(_frontend_graph())

    assert summary["symbols"]["hooks"] == 1


def test_angular_service_module_and_route_counts_work():
    summary = summarize_graph(_frontend_graph())

    assert summary["symbols"]["angular_components"] == 1
    assert summary["symbols"]["angular_services"] == 1
    assert summary["symbols"]["angular_modules"] == 1
    assert summary["symbols"]["angular_routes"] == 1


def test_import_edge_counts_work():
    summary = summarize_graph(_import_graph())

    assert summary["imports"]["resolved_edges"] == 3
    assert summary["imports"]["external"] == 1
    assert summary["imports"]["path_alias"] == 1
    assert summary["imports"]["workspace"] == 1


def test_unresolved_import_counts_work():
    summary = summarize_graph(_import_graph())

    assert summary["imports"]["unresolved"] == 1


def test_missing_fields_do_not_crash():
    summary = summarize_graph(
        {
            "files": [
                None,
                {},
                {
                    "language": "python",
                    "imports": "helper",
                },
            ],
            "edges": None,
        }
    )

    assert summary["languages"] == {"python": 1}
    assert summary["imports"]["resolved_edges"] == 0
    assert isinstance(summary["top_files"], list)


def test_fresh_deterministic_dict_and_list_behavior():
    graph = _frontend_graph()

    first = summarize_graph(graph)
    second = summarize_graph(graph)

    first["languages"]["python"] = 99
    first["top_files"][0]["path"] = "changed"

    assert second["languages"].get("python", 0) != 99
    assert second["top_files"][0]["path"] != "changed"
    assert first["top_files"] is not second["top_files"]
    assert first["symbols"] is not second["symbols"]


TESTS = [
    test_core_repo_summary_import_matches_compatibility_shim,
    test_empty_graph_summary_works,
    test_python_language_count_works,
    test_typescript_and_javascript_language_count_works,
    test_react_framework_count_works,
    test_angular_framework_count_works,
    test_components_count_works,
    test_hooks_count_works,
    test_angular_service_module_and_route_counts_work,
    test_import_edge_counts_work,
    test_unresolved_import_counts_work,
    test_missing_fields_do_not_crash,
    test_fresh_deterministic_dict_and_list_behavior,
]
