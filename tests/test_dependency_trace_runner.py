import json
import tempfile
from pathlib import Path

from strata.core.dependency_trace_runner import run_dependency_trace


def _write(root: Path, relative_path: str, content: str = "") -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_python_seed_dispatches_to_python_extractor():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "app.py", "import helper\n")
        _write(root, "helper.py", "")

        report = run_dependency_trace(root, ("app.py",))

        assert [(edge.source_file, edge.target_file) for edge in report.edges] == [
            ("app.py", "helper.py")
        ]


def test_js_ts_seed_dispatches_to_js_ts_extractor():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "src/app.ts", "import './helper'\n")
        _write(root, "src/helper.ts", "")

        report = run_dependency_trace(root, ("src/app.ts",))

        assert report.edges[0].target_file == "src/helper.ts"


def test_mixed_seed_list_returns_merged_edges():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "app.py", "import helper\n")
        _write(root, "helper.py", "")
        _write(root, "web/app.ts", "export * from './helper'\n")
        _write(root, "web/helper.ts", "")

        report = run_dependency_trace(root, ("web/app.ts", "app.py"))

        assert report.seed_files == ("app.py", "web/app.ts")
        assert {(edge.source_file, edge.target_file) for edge in report.edges} == {
            ("app.py", "helper.py"),
            ("web/app.ts", "web/helper.ts"),
        }


def test_duplicate_seed_files_are_normalized_and_deduplicated():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        content = "import helper\n"
        source = _write(root, "app.py", content)
        _write(root, "helper.py", "")

        report = run_dependency_trace(root, ("app.py", "./app.py", "app.py"))

        assert report.seed_files == ("app.py",)
        assert report.stage_report.outputs["inspected_seed_count"] == 1
        assert report.stage_report.bytes_read == source.stat().st_size


def test_unsupported_and_policy_excluded_extensions_are_skipped():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "README.md", "import ignored\n")
        _write(root, "app.ts", "")

        report = run_dependency_trace(
            root,
            ("README.md", "app.ts"),
            supported_extensions=(".py",),
        )

        assert report.edges == ()
        assert report.skipped_items == (
            "unsupported seed extension: README.md",
            "unsupported seed extension: app.ts",
        )


def test_missing_seed_file_is_skipped_deterministically():
    with tempfile.TemporaryDirectory() as temp_dir:
        report = run_dependency_trace(temp_dir, ("missing.py",))

        assert report.skipped_items == ("missing seed file: missing.py",)
        assert report.stage_report.files_touched == 0


def test_unsafe_and_escaping_seed_paths_are_skipped():
    with tempfile.TemporaryDirectory() as temp_dir:
        absolute = str((Path(temp_dir) / "outside.py").resolve())

        report = run_dependency_trace(temp_dir, ("../outside.py", absolute))

        assert report.seed_files == ()
        assert len(report.skipped_items) == 2
        assert all(item.startswith("unsafe seed path:") for item in report.skipped_items)


def test_max_seed_cap_uses_normalized_deterministic_order():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "a.py", "")
        _write(root, "b.py", "")

        report = run_dependency_trace(root, ("b.py", "a.py"), max_seed_files=1)

        assert report.seed_files == ("a.py",)
        assert report.skipped_items == ("seed cap exceeded: b.py",)
        assert report.stage_report.files_touched == 1


def test_duplicate_edges_are_merged():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "app.py", "import helper\nimport helper\n")
        _write(root, "helper.py", "")

        report = run_dependency_trace(root, ("app.py",))

        assert len(report.edges) == 1
        assert report.stage_report.outputs["edge_count"] == 1


def test_stage_report_aggregates_cost_files_and_skips():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        source = "import helper\n"
        source_path = _write(root, "app.py", source)
        _write(root, "helper.py", "")
        _write(root, "notes.txt", "")

        report = run_dependency_trace(
            root,
            ("app.py", "missing.ts", "notes.txt"),
        )
        stage = report.stage_report

        assert stage.files_touched == 1
        assert stage.bytes_read == source_path.stat().st_size
        assert stage.metrics["estimated_edge_cost"] == 1.0
        assert stage.outputs == {
            "edge_count": 1,
            "inspected_seed_count": 1,
            "selected_seed_count": 3,
        }
        assert len(stage.skipped_items) == 2


def test_output_is_json_ready():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "app.js", "import './helper'\n")
        _write(root, "helper.js", "")

        payload = run_dependency_trace(root, ("app.js",)).to_dict()

        assert json.loads(json.dumps(payload, allow_nan=False)) == payload


def test_trace_does_not_recurse_from_discovered_targets():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "a.py", "import b\n")
        _write(root, "b.py", "import c\n")
        _write(root, "c.py", "")

        report = run_dependency_trace(root, ("a.py",))

        assert [(edge.source_file, edge.target_file) for edge in report.edges] == [
            ("a.py", "b.py")
        ]
        assert report.stage_report.files_touched == 1


def test_target_files_are_not_read_or_executed():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        marker = root / "executed.txt"
        source = _write(root, "app.py", "import dangerous\n")
        target = _write(
            root,
            "dangerous.py",
            f"from pathlib import Path\nPath({str(marker)!r}).write_text('bad')\n",
        )
        original_open = Path.open

        def guarded_open(path, *args, **kwargs):
            if path.resolve() == target.resolve():
                raise AssertionError("target content was read")
            return original_open(path, *args, **kwargs)

        Path.open = guarded_open
        try:
            report = run_dependency_trace(root, (source.relative_to(root),))
        finally:
            Path.open = original_open

        assert report.edges[0].target_file == "dangerous.py"
        assert not marker.exists()


TESTS = [
    test_python_seed_dispatches_to_python_extractor,
    test_js_ts_seed_dispatches_to_js_ts_extractor,
    test_mixed_seed_list_returns_merged_edges,
    test_duplicate_seed_files_are_normalized_and_deduplicated,
    test_unsupported_and_policy_excluded_extensions_are_skipped,
    test_missing_seed_file_is_skipped_deterministically,
    test_unsafe_and_escaping_seed_paths_are_skipped,
    test_max_seed_cap_uses_normalized_deterministic_order,
    test_duplicate_edges_are_merged,
    test_stage_report_aggregates_cost_files_and_skips,
    test_output_is_json_ready,
    test_trace_does_not_recurse_from_discovered_targets,
    test_target_files_are_not_read_or_executed,
]
