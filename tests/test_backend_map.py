from map_writer import generate_project_map


def test_project_map_includes_backend_routes_section():
    graph = {
        "schema_version": 1,
        "root": "sample",
        "files": [
            {
                "path": "api.py",
                "language": "python",
                "imports": [],
                "external_imports": [],
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
                "framework": "angular",
                "imports": [],
                "external_imports": [],
                "unresolved_import_details": [],
                "classes": [],
                "functions": [],
                "routes": [
                    {
                        "method": "PUT",
                        "path": "/users/:id",
                        "line": 8,
                        "source": "router.put",
                    },
                ],
            },
        ],
        "edges": [],
    }

    content = generate_project_map(graph)

    assert "## Backend Routes" in content
    assert "- Backend routes: `3`" in content
    assert "| `GET` | `/health` | `api.py:1` | `@app.get` |" in content
    assert "| `POST` | `/users` | `api.py:5` | `@router.post` |" in content
    assert "| `PUT` | `/users/:id` | `routes/user.routes.ts:8` | `router.put` |" in content


def test_project_map_includes_routes_under_each_file():
    graph = {
        "schema_version": 1,
        "root": "sample",
        "files": [
            {
                "path": "server.js",
                "language": "javascript",
                "imports": [],
                "external_imports": [],
                "unresolved_import_details": [],
                "classes": [],
                "functions": [],
                "routes": [
                    {
                        "method": "GET",
                        "path": "/health",
                        "line": 3,
                        "source": "app.get",
                    },
                ],
            },
        ],
        "edges": [],
    }

    content = generate_project_map(graph)

    assert "### `server.js`" in content
    assert "- Routes: `GET /health` at line `3`" in content


TESTS = [
    test_project_map_includes_backend_routes_section,
    test_project_map_includes_routes_under_each_file,
]