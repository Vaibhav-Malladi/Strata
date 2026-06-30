import tempfile
import os
from pathlib import Path

import diff_engine as old_diff_engine
import strata.core.diff_engine as new_diff_engine

from diff_engine import (
    build_diff_markdown,
    compare_graphs,
    extract_symbol_surface,
    extract_unresolved_imports,
    normalize_edges,
    normalize_file_map,
    normalize_routes,
    write_diff_report,
)


def test_diff_engine_module_compatibility():
    assert old_diff_engine.compare_graphs is new_diff_engine.compare_graphs
    assert old_diff_engine.build_diff_markdown is new_diff_engine.build_diff_markdown
    assert old_diff_engine.write_diff_report is new_diff_engine.write_diff_report


def old_graph() -> dict:
    return {
        "schema_version": 1,
        "root": "old",
        "files": [
            {
                "path": "src/app.py",
                "language": "python",
                "imports": [],
                "external_imports": [],
                "unresolved_imports": ["old_missing"],
                "unresolved_import_details": [
                    {"name": "old_missing", "line": 4},
                ],
                "classes": [{"name": "OldApp"}],
                "functions": [{"name": "run"}],
                "interfaces": [],
                "types": [],
                "enums": [],
                "exports": ["run"],
            },
            {
                "path": "src/keep.py",
                "language": "python",
                "imports": [],
                "external_imports": [],
                "unresolved_imports": [],
                "unresolved_import_details": [],
                "classes": [{"name": "Keep"}],
                "functions": [{"name": "shared"}, {"name": "old_only"}],
                "interfaces": [],
                "types": [],
                "enums": [],
                "exports": [],
            },
        ],
        "edges": [
            {
                "from": "src/app.py",
                "to": "src/keep.py",
                "type": "imports",
                "import": "keep",
            }
        ],
    }


def new_graph() -> dict:
    return {
        "schema_version": 1,
        "root": "new",
        "files": [
            {
                "path": "src/keep.py",
                "language": "python",
                "imports": [],
                "external_imports": [],
                "unresolved_imports": ["new_missing"],
                "unresolved_import_details": [
                    {"name": "new_missing", "line": 6},
                ],
                "classes": [{"name": "Keep"}],
                "functions": [{"name": "shared"}, {"name": "new_only"}],
                "interfaces": [],
                "types": [],
                "enums": [],
                "exports": [],
            },
            {
                "path": "src/new.py",
                "language": "python",
                "imports": [],
                "external_imports": [],
                "unresolved_imports": [],
                "unresolved_import_details": [],
                "classes": [{"name": "NewThing"}],
                "functions": [{"name": "build"}],
                "interfaces": [],
                "types": [],
                "enums": [],
                "exports": ["build"],
            },
        ],
        "edges": [
            {
                "from": "src/keep.py",
                "to": "src/new.py",
                "type": "imports",
                "import": "new",
            }
        ],
    }


def old_routes_data() -> dict:
    return {
        "routes": [
            {"method": "GET", "path": "/health", "file": "src/app.py"},
        ]
    }


def new_routes_data() -> dict:
    return {
        "routes": [
            {"method": "GET", "path": "/health", "file": "src/app.py"},
            {"method": "POST", "path": "/users", "file": "src/new.py"},
        ]
    }


def test_normalize_file_map_returns_path_keyed_mapping():
    mapping = normalize_file_map(old_graph())

    assert sorted(mapping) == [
        os.path.normpath("src/app.py"),
        os.path.normpath("src/keep.py"),
    ]


def test_normalize_edges_returns_hashable_signatures():
    edges = normalize_edges(old_graph())

    assert (
        os.path.normpath("src/app.py"),
        os.path.normpath("src/keep.py"),
        "keep",
    ) in edges


def test_extract_unresolved_imports_returns_sorted_lists():
    unresolved = extract_unresolved_imports(old_graph())

    assert unresolved == {os.path.normpath("src/app.py"): ["old_missing"]}


def test_normalize_routes_handles_dict_payloads():
    routes = normalize_routes(new_routes_data())

    assert ("GET", "/health", os.path.normpath("src/app.py")) in routes
    assert ("POST", "/users", os.path.normpath("src/new.py")) in routes


def test_extract_symbol_surface_returns_sorted_categories():
    surface = extract_symbol_surface(old_graph()["files"][0])

    assert surface["classes"] == ["OldApp"]
    assert surface["functions"] == ["run"]
    assert surface["exports"] == ["run"]


def test_compare_graphs_detects_file_edge_route_import_and_symbol_changes():
    diff = compare_graphs(
        old_graph(),
        new_graph(),
        old_routes_data(),
        new_routes_data(),
    )

    assert diff["files_added"] == [os.path.normpath("src/new.py")]
    assert diff["files_removed"] == [os.path.normpath("src/app.py")]
    assert diff["files_kept"] == [os.path.normpath("src/keep.py")]
    assert (
        os.path.normpath("src/keep.py"),
        os.path.normpath("src/new.py"),
        "new",
    ) in diff["edges_added"]
    assert (
        os.path.normpath("src/app.py"),
        os.path.normpath("src/keep.py"),
        "keep",
    ) in diff["edges_removed"]
    assert (
        "POST",
        "/users",
        os.path.normpath("src/new.py"),
    ) in diff["routes_added"]
    assert diff["summary"]["files_added"] == 1
    assert diff["summary"]["files_removed"] == 1
    assert diff["summary"]["edges_added"] == 1
    assert diff["summary"]["edges_removed"] == 1
    assert diff["summary"]["routes_added"] == 1
    assert diff["summary"]["routes_removed"] == 0
    assert diff["summary"]["unresolved_imports_added"] == 1
    assert diff["summary"]["unresolved_imports_removed"] == 1
    assert diff["summary"]["symbols_added"] > 0
    assert diff["summary"]["symbols_removed"] > 0


def test_build_diff_markdown_includes_required_sections():
    diff = compare_graphs(old_graph(), new_graph(), old_routes_data(), new_routes_data())

    markdown = build_diff_markdown(diff)

    assert "# Strata Structural Diff" in markdown
    assert "## Summary" in markdown
    assert "## Files Added" in markdown
    assert "## Files Removed" in markdown
    assert "## Dependency Edges Added" in markdown
    assert "## Dependency Edges Removed" in markdown
    assert "## Backend Routes Added" in markdown
    assert "## Backend Routes Removed" in markdown
    assert "## Unresolved Imports Added" in markdown
    assert "## Unresolved Imports Removed" in markdown
    assert "## Symbols Added" in markdown
    assert "## Symbols Removed" in markdown


def test_build_diff_markdown_says_none_for_empty_sections():
    empty_diff = compare_graphs({"files": [], "edges": []}, {"files": [], "edges": []})

    markdown = build_diff_markdown(empty_diff)

    assert "None." in markdown


def test_write_diff_report_writes_json_and_markdown():
    diff = compare_graphs(old_graph(), new_graph(), old_routes_data(), new_routes_data())

    with tempfile.TemporaryDirectory() as temp_dir:
        result = write_diff_report(Path(temp_dir), diff)

        json_path = Path(result["json_path"])
        markdown_path = Path(result["markdown_path"])

        assert json_path.exists()
        assert markdown_path.exists()
        assert json_path.read_text(encoding="utf-8")
        assert markdown_path.read_text(encoding="utf-8").startswith("# Strata Structural Diff")


TESTS = [
    test_diff_engine_module_compatibility,
    test_normalize_file_map_returns_path_keyed_mapping,
    test_normalize_edges_returns_hashable_signatures,
    test_extract_unresolved_imports_returns_sorted_lists,
    test_normalize_routes_handles_dict_payloads,
    test_extract_symbol_surface_returns_sorted_categories,
    test_compare_graphs_detects_file_edge_route_import_and_symbol_changes,
    test_build_diff_markdown_includes_required_sections,
    test_build_diff_markdown_says_none_for_empty_sections,
    test_write_diff_report_writes_json_and_markdown,
]
