import tempfile
from pathlib import Path

from agent_export import generate_agent_prompt
from context_budget import build_budget_report, build_budget_summary_rows
from context_pack import build_context_pack
from test_mapping import collect_test_hints, build_test_hints_section, extract_python_test_functions


def _write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_graph(root: Path, files: list[dict]) -> dict:
    return {
        "schema_version": 1,
        "root": str(root),
        "files": files,
        "edges": [],
    }


def _source_file(path: str) -> dict:
    return {
        "path": path,
        "language": "python",
        "classes": [],
        "functions": [],
        "interfaces": [],
        "types": [],
        "enums": [],
        "exports": [],
        "imports": [],
        "external_imports": [],
        "unresolved_imports": [],
        "unresolved_import_details": [],
        "routes": [],
    }


def _test_file(path: str, *, functions: list[dict] | None = None, imports: list[str] | None = None) -> dict:
    return {
        "path": path,
        "language": "python",
        "classes": [],
        "functions": functions or [],
        "interfaces": [],
        "types": [],
        "enums": [],
        "exports": [],
        "imports": imports or [],
        "external_imports": [],
        "unresolved_imports": [],
        "unresolved_import_details": [],
        "routes": [],
    }


def test_extract_python_test_functions_returns_only_top_level_test_functions_and_line_ranges():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        file_path = root / "tests" / "test_sample.py"
        _write_file(
            file_path,
            (
                "def helper():\n"
                "    return True\n\n"
                "def test_alpha():\n"
                "    assert helper()\n\n"
                "async def test_beta(flag):\n"
                "    assert flag\n"
            ),
        )

        result = extract_python_test_functions(file_path)

        assert result["status"] == "ok"
        assert [item["name"] for item in result["functions"]] == ["test_alpha", "test_beta"]
        assert result["functions"][0]["start_line"] == 4
        assert result["functions"][0]["end_line"] == 5
        assert result["functions"][1]["start_line"] == 7
        assert result["functions"][1]["end_line"] == 8


def test_extract_python_test_functions_handles_syntax_errors_safely():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        file_path = root / "tests" / "test_broken.py"
        _write_file(file_path, "def test_broken(:\n    pass\n")

        result = extract_python_test_functions(file_path)

        assert result["status"] == "syntax_error"
        assert result["functions"] == []
        assert result["error"]["type"] == "syntax_error"


def test_collect_test_hints_matches_filename_and_task_terms_conservatively():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_file(
            root / "commands" / "run_command.py",
            "def write_run_command():\n    return None\n",
        )
        _write_file(
            root / "tests" / "test_run_command.py",
            (
                "from commands.run_command import write_run_command\n\n"
                "def test_run_dry_run_shows_plan():\n"
                "    assert write_run_command() is None\n\n"
                "def test_run_selected_file_mode_shows_context_mode_and_selected_files():\n"
                "    assert write_run_command() is None\n"
            ),
        )
        _write_file(
            root / "tests" / "test_run_command_budget.py",
            (
                "from commands.run_command import write_run_command\n\n"
                "def test_run_command_budget_summary():\n"
                "    assert write_run_command() is None\n\n"
                "def test_run_command_budget_limit_is_reported():\n"
                "    assert write_run_command() is None\n"
            ),
        )
        _write_file(
            root / "tests" / "test_run_command_cli.py",
            (
                "from commands.run_command import write_run_command\n\n"
                "def test_run_command_cli_smoke():\n"
                "    assert write_run_command() is None\n"
            ),
        )
        _write_file(
            root / "tests" / "test_run_command_extra.py",
            (
                "from commands.run_command import write_run_command\n\n"
                "def test_run_command_extra_case():\n"
                "    assert write_run_command() is None\n"
            ),
        )

        graph = _make_graph(
            root,
            [
                _source_file("commands/run_command.py"),
                _test_file(
                    "tests/test_run_command.py",
                    imports=["commands.run_command"],
                ),
                _test_file(
                    "tests/test_run_command_budget.py",
                    imports=["commands.run_command"],
                ),
                _test_file(
                    "tests/test_run_command_cli.py",
                    imports=["commands.run_command"],
                ),
                _test_file(
                    "tests/test_run_command_extra.py",
                    imports=["commands.run_command"],
                ),
            ],
        )

        report_one = collect_test_hints(
            graph,
            "fix dry run plan output",
            relevant_entries=[{"file": graph["files"][0]}],
            selected_paths=["commands/run_command.py"],
        )
        report_two = collect_test_hints(
            graph,
            "fix dry run plan output",
            relevant_entries=[{"file": graph["files"][0]}],
            selected_paths=["commands/run_command.py"],
        )

        assert report_one["included_count"] == 3
        assert report_one["included_function_count"] == 5
        assert [item["test_file"] for item in report_one["included"]] == [
            "tests/test_run_command.py",
            "tests/test_run_command_budget.py",
            "tests/test_run_command_cli.py",
        ]
        assert report_one["included"] == report_two["included"]
        assert report_one["skipped_count"] > 0
        section = build_test_hints_section(report_one)
        text = "\n".join(section)
        assert "test_run_dry_run_shows_plan" in text
        assert "test_run_command_budget_summary" in text
        assert "skipped by cap" in text


def test_collect_test_hints_maps_selected_context_to_test_fixture():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_file(
            root / "selected_context.py",
            "def resolve_one_file_reference():\n    return None\n",
        )
        _write_file(
            root / "tests" / "test_selected_context.py",
            (
                "from selected_context import resolve_one_file_reference\n\n"
                "def test_resolve_file_reference_supports_exact_and_smart_matches():\n"
                "    assert resolve_one_file_reference() is None\n\n"
                "def test_resolve_file_references_resolves_each_flag_independently():\n"
                "    assert resolve_one_file_reference() is None\n"
            ),
        )

        graph = _make_graph(
            root,
            [
                _source_file("selected_context.py"),
                _test_file(
                    "tests/test_selected_context.py",
                    imports=["selected_context"],
                ),
            ],
        )
        report = collect_test_hints(
            graph,
            "selected file context",
            relevant_entries=[{"file": graph["files"][0]}],
            selected_paths=["selected_context.py"],
        )
        section = build_test_hints_section(report)
        text = "\n".join(section)

        assert report["included_count"] == 1
        assert report["included_function_count"] == 2
        assert report["included"][0]["test_file"] == "tests/test_selected_context.py"
        assert report["included"][0]["source_path"] == "selected_context.py"
        assert "test_resolve_file_reference_supports_exact_and_smart_matches" in text


def test_context_pack_and_agent_prompt_include_test_hints_section():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_file(
            root / "commands" / "run_command.py",
            "def write_run_command():\n    return None\n",
        )
        _write_file(
            root / "tests" / "test_run_command.py",
            (
                "from commands.run_command import write_run_command\n\n"
                "def test_run_dry_run_shows_plan():\n"
                "    assert write_run_command() is None\n"
            ),
        )

        graph = _make_graph(
            root,
            [
                _source_file("commands/run_command.py"),
                _test_file(
                    "tests/test_run_command.py",
                    imports=["commands.run_command"],
                ),
            ],
        )

        report = build_budget_report(
            graph,
            "fix dry run plan output",
            selected_paths=["commands/run_command.py"],
            budget_value="small",
        )
        content = build_context_pack(
            graph,
            "fix dry run plan output",
            selected_paths=["commands/run_command.py"],
            budget_value="small",
        )
        prompt = generate_agent_prompt(
            graph,
            "fix dry run plan output",
            "generic",
            selected_paths=["commands/run_command.py"],
            budget_value="small",
        )

        assert report["test_hints_count"] == 1
        assert report["test_hints_function_count"] == 1
        assert "## Test Hints" in content
        assert "## Test Hints" in prompt
        assert "tests/test_run_command.py" in content
        assert "tests/test_run_command.py" in prompt
        assert "test_run_dry_run_shows_plan" in content
        assert "test_run_dry_run_shows_plan" in prompt


def test_budget_summary_reports_test_hint_counts():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_file(
            root / "commands" / "run_command.py",
            "def write_run_command():\n    return None\n",
        )
        _write_file(
            root / "tests" / "test_run_command.py",
            (
                "from commands.run_command import write_run_command\n\n"
                "def test_run_dry_run_shows_plan():\n"
                "    assert write_run_command() is None\n"
            ),
        )

        graph = _make_graph(
            root,
            [
                _source_file("commands/run_command.py"),
                _test_file(
                    "tests/test_run_command.py",
                    imports=["commands.run_command"],
                ),
            ],
        )
        report = build_budget_report(
            graph,
            "fix dry run plan output",
            selected_paths=["commands/run_command.py"],
            budget_value="small",
        )
        rows = build_budget_summary_rows(report)

        assert ("Test hints", "1 test / 1 file") in rows


TESTS = [
    test_extract_python_test_functions_returns_only_top_level_test_functions_and_line_ranges,
    test_extract_python_test_functions_handles_syntax_errors_safely,
    test_collect_test_hints_matches_filename_and_task_terms_conservatively,
    test_collect_test_hints_maps_selected_context_to_test_fixture,
    test_context_pack_and_agent_prompt_include_test_hints_section,
    test_budget_summary_reports_test_hint_counts,
]
