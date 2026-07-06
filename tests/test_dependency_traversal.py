import ast
import json
import tempfile
from pathlib import Path

from strata.core.dependency_traversal import (
    DEFAULT_MAX_DEPTH,
    DEFAULT_MAX_EDGES,
    DEFAULT_MAX_ESTIMATED_COST,
    DEFAULT_MAX_FILES,
    traverse_dependencies,
)


def _write(root: Path, relative_path: str, content: str = "") -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_one_hop_traversal_reaches_target():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "a.py", "import b\n")
        _write(root, "b.py", "")

        report = traverse_dependencies(root, ("a.py",), max_depth=1)

        assert report.visited_files == ("a.py", "b.py")
        assert report.file_depths == {"a.py": 0, "b.py": 1}
        assert [(edge.source_file, edge.target_file) for edge in report.edges] == [
            ("a.py", "b.py")
        ]


def test_multi_hop_traversal_reaches_depth_cap():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "a.py", "import b\n")
        _write(root, "b.py", "import c\n")
        _write(root, "c.py", "")

        report = traverse_dependencies(root, ("a.py",), max_depth=2)

        assert report.visited_files == ("a.py", "b.py", "c.py")
        assert report.file_depths["c.py"] == 2
        assert len(report.edges) == 2


def test_max_depth_stops_deeper_files_and_reads():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "a.py", "import b\n")
        _write(root, "b.py", "import c\n")
        _write(root, "c.py", "")

        report = traverse_dependencies(root, ("a.py",), max_depth=1)

        assert report.visited_files == ("a.py", "b.py")
        assert all(edge.target_file != "c.py" for edge in report.edges)
        assert report.stage_report.files_touched == 1


def test_max_files_cap_is_respected_with_path_tie_breaking():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "seed.py", "import zed\nimport alpha\n")
        _write(root, "alpha.py", "")
        _write(root, "zed.py", "")

        report = traverse_dependencies(root, ("seed.py",), max_files=2)

        assert report.visited_files == ("seed.py", "alpha.py")
        assert "max_files cap reached: zed.py" in report.skipped_items


def test_max_edges_cap_is_respected():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "seed.py", "import alpha\nimport zed\n")
        _write(root, "alpha.py", "")
        _write(root, "zed.py", "")

        report = traverse_dependencies(root, ("seed.py",), max_edges=1)

        assert len(report.edges) == 1
        assert report.edges[0].target_file == "alpha.py"
        assert "max_edges cap reached" in report.skipped_items


def test_estimated_cost_cap_stops_before_over_budget_edge():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "seed.py", "import alpha\nimport zed\n")
        _write(root, "alpha.py", "")
        _write(root, "zed.py", "")

        report = traverse_dependencies(
            root,
            ("seed.py",),
            max_estimated_cost=1.0,
        )

        assert len(report.edges) == 1
        assert report.stage_report.metrics["estimated_edge_cost"] == 1.0
        assert "max_estimated_cost cap reached" in report.skipped_items


def test_external_unresolved_and_unsupported_inputs_are_skipped():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(
            root,
            "app.ts",
            "import React from 'react'\nimport './missing'\n",
        )
        _write(root, "notes.txt", "")

        report = traverse_dependencies(root, ("app.ts", "notes.txt"))

        assert report.edges == ()
        assert any("react" in item for item in report.skipped_items)
        assert any("./missing" in item for item in report.skipped_items)
        assert any("notes.txt" in item for item in report.skipped_items)


def test_priority_controls_frontier_before_path_order():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(
            root,
            "seed.ts",
            "const low = import('./alpha')\nimport './zed'\n",
        )
        _write(root, "alpha.ts", "")
        _write(root, "zed.ts", "")

        report = traverse_dependencies(root, ("seed.ts",), max_files=2)

        assert report.visited_files == ("seed.ts", "zed.ts")
        assert report.edges[0].priority == "medium"


def test_duplicate_edges_files_and_cycles_are_bounded():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "a.py", "import b\nimport b\n")
        _write(root, "b.py", "import a\n")

        report = traverse_dependencies(root, ("a.py",), max_depth=10)

        assert report.visited_files == ("a.py", "b.py")
        assert len(report.edges) == 2
        assert len(set(report.edges)) == 2


def test_stage_report_contains_files_edges_cost_and_skips():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "a.py", "import b\nimport external\n")
        _write(root, "b.py", "")

        report = traverse_dependencies(root, ("a.py",), max_depth=1)
        stage = report.stage_report

        assert stage.outputs["visited_file_count"] == 2
        assert stage.outputs["edge_count"] == 1
        assert stage.files_touched == 1
        assert stage.metrics["estimated_edge_cost"] == 1.0
        assert stage.skipped_items == report.skipped_items


def test_output_is_deterministic_and_json_ready():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "a.js", "import './b'\n")
        _write(root, "b.js", "")

        first = traverse_dependencies(root, ("a.js",)).to_dict()
        second = traverse_dependencies(root, ("a.js",)).to_dict()

        assert first == second
        assert json.loads(json.dumps(first, allow_nan=False)) == first


def test_confidence_is_metadata_not_traversal_score():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(
            root,
            "seed.ts",
            "const low = import('./alpha')\nimport './zed'\n",
        )
        _write(root, "alpha.ts", "")
        _write(root, "zed.ts", "")

        report = traverse_dependencies(root, ("seed.ts",), max_files=2)

        assert report.visited_files[1] == "zed.ts"
        assert set(report.stage_report.metrics) == {"estimated_edge_cost"}


def test_target_is_not_read_when_file_cap_blocks_frontier():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        target = _write(root, "target.py", "raise RuntimeError('do not read')\n")
        _write(root, "seed.py", "import target\n")
        original_open = Path.open

        def guarded_open(path, *args, **kwargs):
            if path.resolve() == target.resolve():
                raise AssertionError("blocked frontier target was read")
            return original_open(path, *args, **kwargs)

        Path.open = guarded_open
        try:
            report = traverse_dependencies(root, ("seed.py",), max_files=1)
        finally:
            Path.open = original_open

        assert report.visited_files == ("seed.py",)
        assert report.edges[0].target_file == "target.py"


def test_defaults_and_module_dependencies_remain_bounded():
    assert (DEFAULT_MAX_DEPTH, DEFAULT_MAX_FILES, DEFAULT_MAX_EDGES) == (2, 40, 100)
    assert DEFAULT_MAX_ESTIMATED_COST == 100.0

    module_path = Path(__file__).parents[1] / "strata/core/dependency_traversal.py"
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert not any("cli" in module or "command" in module for module in imported)


TESTS = [
    test_one_hop_traversal_reaches_target,
    test_multi_hop_traversal_reaches_depth_cap,
    test_max_depth_stops_deeper_files_and_reads,
    test_max_files_cap_is_respected_with_path_tie_breaking,
    test_max_edges_cap_is_respected,
    test_estimated_cost_cap_stops_before_over_budget_edge,
    test_external_unresolved_and_unsupported_inputs_are_skipped,
    test_priority_controls_frontier_before_path_order,
    test_duplicate_edges_files_and_cycles_are_bounded,
    test_stage_report_contains_files_edges_cost_and_skips,
    test_output_is_deterministic_and_json_ready,
    test_confidence_is_metadata_not_traversal_score,
    test_target_is_not_read_when_file_cap_blocks_frontier,
    test_defaults_and_module_dependencies_remain_bounded,
]
