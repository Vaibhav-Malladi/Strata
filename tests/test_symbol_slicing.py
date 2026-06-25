import tempfile
from pathlib import Path

from context_budget import build_budget_report, build_budget_summary_rows
from context_pack import build_context_pack
from agent_export import generate_agent_prompt
from symbol_slicing import collect_symbol_hints, extract_python_symbols


def _write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_graph(root: Path) -> dict:
    return {
        "schema_version": 1,
        "root": str(root),
        "files": [
            {
                "path": "commands/run_command.py",
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
        ],
        "edges": [],
    }


def test_extract_python_symbols_finds_functions_classes_and_methods():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        file_path = root / "sample.py"
        _write_file(
            file_path,
            (
                "def top_level(flag, value=1):\n"
                "    return value if flag else 0\n\n"
                "class Runner:\n"
                "    def execute(self, dry_run=False):\n"
                "        return dry_run\n"
            ),
        )

        result = extract_python_symbols(file_path)
        symbols = result["symbols"]

        assert result["status"] == "ok"
        assert {symbol["kind"] for symbol in symbols} == {"function", "class", "method"}
        assert any(symbol["name"] == "top_level" for symbol in symbols)
        assert any(symbol["name"] == "Runner" for symbol in symbols)
        assert any(symbol["qualname"] == "Runner.execute" for symbol in symbols)
        assert any(symbol["start_line"] > 0 for symbol in symbols)
        assert any(symbol["end_line"] >= symbol["start_line"] for symbol in symbols)
        assert any(symbol["signature"].startswith("(flag") for symbol in symbols if symbol["name"] == "top_level")


def test_extract_python_symbols_returns_safe_error_for_syntax_error():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        file_path = root / "broken.py"
        _write_file(file_path, "def broken(:\n    pass\n")

        result = extract_python_symbols(file_path)

        assert result["status"] == "syntax_error"
        assert result["symbols"] == []
        assert result["error"]["type"] == "syntax_error"


def test_collect_symbol_hints_matches_task_terms_and_selected_files():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_file(
            root / "commands" / "run_command.py",
            (
                "def dry_run_helper():\n"
                "    return True\n\n"
                "def _print_plan():\n"
                "    return 'plan'\n\n"
                "class RunCommand:\n"
                "    def execute(self):\n"
                "        return None\n"
            ),
        )

        graph = _make_graph(root)
        entries = [
            {
                "file": graph["files"][0],
                "score": 100,
                "matched_terms": [],
                "confidence": "high",
                "selected_by_user": True,
            }
        ]

        hints = collect_symbol_hints(
            graph,
            "fix dry run plan output",
            entries,
            selected_paths=["commands/run_command.py"],
        )

        hint_text = "\n".join(
            f"{hint['file_path']}::{hint['symbol_name']} {hint['reason']}"
            for hint in hints
        )

        assert hints
        assert "commands/run_command.py::_print_plan" in hint_text
        assert "task term match" in hint_text or "class/method name match" in hint_text
        assert "dry_run_helper" in hint_text


def test_symbol_hints_section_survives_tiny_budget_and_selected_files():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_file(
            root / "commands" / "run_command.py",
            (
                "def dry_run_helper():\n"
                "    return True\n\n"
                "def _print_plan():\n"
                "    return 'plan'\n\n"
                "class RunCommand:\n"
                "    def execute(self):\n"
                "        return None\n"
            ),
        )
        _write_file(root / "helper.py", "def helper():\n    return True\n")

        graph = {
            "schema_version": 1,
            "root": str(root),
            "files": [
                {
                    "path": "commands/run_command.py",
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
                },
                {
                    "path": "helper.py",
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
                },
            ],
            "edges": [],
        }

        report = build_budget_report(
            graph,
            "fix dry run plan output",
            selected_paths=["commands/run_command.py"],
            budget_value="tiny",
        )
        content = build_context_pack(
            graph,
            "fix dry run plan output",
            selected_paths=["commands/run_command.py"],
            budget_value="tiny",
        )
        prompt = generate_agent_prompt(
            graph,
            "fix dry run plan output",
            "generic",
            selected_paths=["commands/run_command.py"],
            budget_value="tiny",
        )
        rows = build_budget_summary_rows(report)

        assert "commands/run_command.py" in content
        assert "Symbol Hints" in content
        assert "Symbol Hints" in prompt
        assert "commands/run_command.py" in prompt
        assert "_print_plan" in content or "_print_plan" in prompt
        assert report["symbol_hints_count"] > 0
        assert ("Symbol hints", f"{report['symbol_hints_count']} matched") in rows


TESTS = [
    test_extract_python_symbols_finds_functions_classes_and_methods,
    test_extract_python_symbols_returns_safe_error_for_syntax_error,
    test_collect_symbol_hints_matches_task_terms_and_selected_files,
    test_symbol_hints_section_survives_tiny_budget_and_selected_files,
]
