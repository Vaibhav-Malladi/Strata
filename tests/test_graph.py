from graph import validate_graph
from scanner import scan_repo


def test_validate_scanned_graph():
    result = scan_repo(".")
    problems = validate_graph(result)

    assert problems == []


def test_validate_graph_requires_schema_version():
    graph = {
        "root": "tmp_repo",
        "files": [],
        "edges": [],
    }

    problems = validate_graph(graph)

    assert "graph is missing schema_version" in problems


def test_validate_graph_rejects_wrong_schema_version():
    graph = {
        "schema_version": 999,
        "root": "tmp_repo",
        "files": [],
        "edges": [],
    }

    problems = validate_graph(graph)

    assert "graph schema_version must be 1" in problems


TESTS = [
    test_validate_scanned_graph,
    test_validate_graph_requires_schema_version,
    test_validate_graph_rejects_wrong_schema_version,
]