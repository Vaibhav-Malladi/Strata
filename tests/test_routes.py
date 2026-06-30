import json
import tempfile
from pathlib import Path
import commands.routes_command as old_routes_command
import strata.commands.routes_command as new_routes_command
from commands.routes_command import write_routes

import routes as old_routes
import strata.core.routes as new_routes
from routes import (
    collect_routes,
    find_duplicate_routes,
    generate_routes_report,
    route_files_with_unresolved_imports,
    write_routes_json,
    write_routes_report,
)
from tests.helpers import capture_output, change_directory


def test_routes_core_import_matches_compatibility_shim():
    assert old_routes.collect_routes is new_routes.collect_routes


def test_new_routes_command_import_matches_legacy_shim():
    assert new_routes_command.write_routes is old_routes_command.write_routes


def route_test_graph() -> dict:
    return {
        "schema_version": 1,
        "root": "sample",
        "files": [
            {
                "path": "api.py",
                "language": "python",
                "imports": [],
                "external_imports": [],
                "unresolved_imports": [],
                "unresolved_import_details": [],
                "classes": [],
                "functions": [],
                "routes": [
                    {
                        "method": "GET",
                        "path": "/health",
                        "line": 1,
                        "source": "@app.get",
                    },
                    {
                        "method": "POST",
                        "path": "/users",
                        "line": 5,
                        "source": "@router.post",
                    },
                ],
            },
            {
                "path": "routes/user.routes.ts",
                "language": "typescript",
                "imports": [],
                "external_imports": [],
                "unresolved_imports": ["../db/client"],
                "unresolved_import_details": [
                    {
                        "name": "../db/client",
                        "line": 2,
                    }
                ],
                "classes": [],
                "functions": [],
                "routes": [
                    {
                        "method": "POST",
                        "path": "/users",
                        "line": 8,
                        "source": "router.post",
                    },
                    {
                        "method": "PUT",
                        "path": "/users/:id",
                        "line": 12,
                        "source": "router.put",
                    },
                ],
            },
        ],
        "edges": [],
    }


def test_collect_routes_returns_all_backend_routes():
    graph = route_test_graph()

    routes = collect_routes(graph)

    assert len(routes) == 4

    signatures = [
        (route["method"], route["path"], route["file"])
        for route in routes
    ]

    assert ("GET", "/health", "api.py") in signatures
    assert ("POST", "/users", "api.py") in signatures
    assert ("POST", "/users", "routes/user.routes.ts") in signatures
    assert ("PUT", "/users/:id", "routes/user.routes.ts") in signatures


def test_find_duplicate_routes_reports_same_method_and_path():
    graph = route_test_graph()
    routes = collect_routes(graph)

    duplicates = find_duplicate_routes(routes)

    assert len(duplicates) == 1
    assert duplicates[0]["method"] == "POST"
    assert duplicates[0]["path"] == "/users"
    assert len(duplicates[0]["locations"]) == 2


def test_route_files_with_unresolved_imports_are_reported():
    graph = route_test_graph()

    risks = route_files_with_unresolved_imports(graph)

    assert len(risks) == 1
    assert risks[0]["file"] == "routes/user.routes.ts"
    assert risks[0]["unresolved_imports"][0]["name"] == "../db/client"


def test_generate_routes_report_includes_routes_and_warnings():
    graph = route_test_graph()

    content = generate_routes_report(graph)

    assert "# Route Map" in content
    assert "- Backend routes: `4`" in content
    assert "- Duplicate route warnings: `1`" in content
    assert "- Route files with unresolved imports: `1`" in content
    assert "| `GET` | `/health` | `api.py:1` | `@app.get` | `python` |" in content
    assert "| `POST` | `/users` | `api.py:5` | `@router.post` | `python` |" in content
    assert "| `POST` | `/users` | `routes/user.routes.ts:8` | `router.post` | `typescript` |" in content
    assert "- Duplicate route `POST /users` found in:" in content
    assert "`../db/client` at line `2`" in content
    assert "## AI Notes" in content


def test_write_routes_report_and_json_create_files():
    graph = route_test_graph()

    with tempfile.TemporaryDirectory() as temp_dir:
        report_path = Path(temp_dir) / "routes.md"
        json_path = Path(temp_dir) / "routes.json"

        write_routes_report(graph, str(report_path))
        write_routes_json(graph, str(json_path))

        assert report_path.exists()
        assert json_path.exists()

        payload = json.loads(json_path.read_text(encoding="utf-8"))

        assert payload["route_count"] == 4
        assert len(payload["routes"]) == 4
        assert len(payload["duplicate_routes"]) == 1
        assert len(payload["route_import_risks"]) == 1

def test_cli_write_routes_creates_route_outputs():
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        api_path = temp_root / "api.py"
        api_path.write_text(
            '@app.get("/health")\n'
            'def health_check():\n'
            '    pass\n',
            encoding="utf-8",
        )

        with change_directory(temp_root):
            exit_code, output = capture_output(write_routes, temp_dir)

        assert exit_code == 0
        assert (temp_root / ".aidc" / "routes.md").exists()
        assert (temp_root / ".aidc" / "routes.json").exists()
        normalized_output = output.replace("\\", "/")

        assert "Strata" in output
        assert "Routes complete" in output
        assert "Markdown" in output
        assert ".aidc/routes.md" in normalized_output
        assert ".aidc/routes.json" in normalized_output
        assert "Root" in output
        assert "Routes" in output
        assert "Duplicate warnings" in output
        assert "Import risks" in output

        content = (temp_root / ".aidc" / "routes.md").read_text(encoding="utf-8")
        payload = json.loads((temp_root / ".aidc" / "routes.json").read_text(encoding="utf-8"))

        assert "# Route Map" in content
        assert "- Backend routes: `1`" in content
        assert "| `GET` | `/health` |" in content
        assert payload["route_count"] == 1
        assert payload["routes"][0]["method"] == "GET"
        assert payload["routes"][0]["path"] == "/health"

TESTS = [
    test_routes_core_import_matches_compatibility_shim,
    test_new_routes_command_import_matches_legacy_shim,
    test_collect_routes_returns_all_backend_routes,
    test_find_duplicate_routes_reports_same_method_and_path,
    test_route_files_with_unresolved_imports_are_reported,
    test_generate_routes_report_includes_routes_and_warnings,
    test_write_routes_report_and_json_create_files,
    test_cli_write_routes_creates_route_outputs,
]
