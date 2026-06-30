import tempfile
from pathlib import Path

from agent_export import generate_agent_prompt
from context_budget import build_budget_report, build_budget_summary_rows
from context_pack import build_context_pack
import strata.parsers.symbol_slicing as new_symbol_slicing
import symbol_slicing as old_symbol_slicing
from symbol_slicing import (
    build_symbol_snippets,
    build_symbol_snippets_section,
    collect_symbol_hints,
    extract_javascript_symbols,
    extract_python_symbols,
)


def _write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_graph(root: Path, paths: list[str]) -> dict:
    return {
        "schema_version": 1,
        "root": str(root),
        "files": [
            {
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
            for path in paths
        ],
        "edges": [],
    }


def test_new_symbol_slicing_import_matches_legacy_shim():
    assert old_symbol_slicing.extract_python_symbols is new_symbol_slicing.extract_python_symbols
    assert old_symbol_slicing.collect_symbol_hints is new_symbol_slicing.collect_symbol_hints


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


def test_extract_javascript_symbols_finds_functions_typed_arrows_components_hooks_and_methods():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        file_path = root / "LoginPanel.tsx"
        _write_file(
            file_path,
            (
                "export async function saveUser(user: User) {\n"
                "  return user;\n"
                "}\n\n"
                "export const useAuth: AuthHook = async (token: string) => {\n"
                "  return token;\n"
                "};\n\n"
                "export const LoginPanel = (props: Props) => <button />;\n\n"
                "export class UserService {\n"
                "  async login(user: User) {\n"
                "    return user;\n"
                "  }\n"
                "}\n"
            ),
        )

        result = extract_javascript_symbols(file_path)
        symbols = {item["qualname"]: item for item in result["symbols"]}

        assert result["status"] == "ok"
        assert symbols["saveUser"]["kind"] == "function"
        assert symbols["useAuth"]["kind"] == "hook"
        assert symbols["LoginPanel"]["kind"] == "component"
        assert symbols["UserService"]["kind"] == "class"
        assert symbols["UserService.login"]["kind"] == "method"
        assert all(item["confidence"] == "medium" for item in symbols.values())
        assert all(item["confidence_reason"] == "regex" for item in symbols.values())
        assert symbols["useAuth"]["signature"].startswith("(token")


def test_generated_context_includes_approximate_tsx_symbol_confidence():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_file(
            root / "src" / "LoginButton.tsx",
            "export const LoginButton = ({ disabled }: Props) => <button disabled={disabled} />;\n",
        )
        graph = {
            "root": str(root),
            "files": [
                {
                    **_make_graph(root, ["src/LoginButton.tsx"])["files"][0],
                    "path": "src/LoginButton.tsx",
                    "language": "typescript",
                    "functions": [{"name": "LoginButton"}],
                }
            ],
            "edges": [],
        }

        content = build_context_pack(
            graph,
            "fix login button not disabling",
            selected_paths=["src/LoginButton.tsx"],
            budget_value="small",
        )

        assert "## Symbol Hints" in content
        assert "LoginButton" in content
        assert "medium confidence (regex)" in content
        assert "## React Hints" in content


def test_collect_symbol_hints_prefers_selected_file_symbols_and_reports_term_matches():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_file(
            root / "commands" / "run_command.py",
            (
                "def _build_dry_run_rows():\n"
                "    return True\n\n"
                "def _print_plan():\n"
                "    return 'plan'\n\n"
                "def write_run_command():\n"
                "    return None\n\n"
                "def _parse_run_args():\n"
                "    return None\n\n"
                "def _print_guided_summary():\n"
                "    return None\n"
            ),
        )
        _write_file(
            root / "commands" / "apply_command.py",
            (
                "def write_apply_dry_run_command():\n"
                "    return None\n"
            ),
        )

        graph = _make_graph(root, ["commands/run_command.py", "commands/apply_command.py"])
        entries = [
            {
                "file": graph["files"][0],
                "selected_by_user": True,
            },
            {
                "file": graph["files"][1],
            },
        ]

        hints = collect_symbol_hints(
            graph,
            "fix dry run plan output",
            entries,
            selected_paths=["commands/run_command.py"],
        )
        hint_map = {hint["symbol_name"]: hint for hint in hints}
        symbol_names = [hint["symbol_name"] for hint in hints]

        assert symbol_names[:4] == [
            "_build_dry_run_rows",
            "_print_plan",
            "write_run_command",
            "_parse_run_args",
        ]
        assert symbol_names.index("_build_dry_run_rows") < symbol_names.index("write_apply_dry_run_command")
        assert "selected file symbol" in hint_map["_build_dry_run_rows"]["reason"]
        assert "matched task terms" in hint_map["_build_dry_run_rows"]["reason"]
        assert '"dry", "run"' in hint_map["_build_dry_run_rows"]["reason"]
        assert "multi-term match" in hint_map["_build_dry_run_rows"]["reason"]
        assert "matched task term" in hint_map["_print_plan"]["reason"]
        assert '"plan"' in hint_map["_print_plan"]["reason"]
        assert "selected file symbol" in hint_map["_parse_run_args"]["reason"]
        assert "matched task term" in hint_map["_parse_run_args"]["reason"]


def test_collect_symbol_hints_prioritizes_selected_files_over_adjacent_single_term_matches():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_file(
            root / "commands" / "run_command.py",
            (
                "def _print_plan():\n"
                "    return 'selected'\n"
            ),
        )
        _write_file(
            root / "commands" / "plan_helpers.py",
            (
                "def render_plan():\n"
                "    return 'adjacent'\n\n"
                "def summarize_plan():\n"
                "    return 'adjacent'\n"
            ),
        )

        graph = _make_graph(root, ["commands/run_command.py", "commands/plan_helpers.py"])
        entries = [
            {
                "file": graph["files"][0],
                "selected_by_user": True,
            },
            {
                "file": graph["files"][1],
            },
        ]

        hints = collect_symbol_hints(
            graph,
            "plan output",
            entries,
            selected_paths=["commands/run_command.py"],
        )
        symbol_names = [hint["symbol_name"] for hint in hints]

        assert hints[0]["file_path"] == "commands/run_command.py"
        assert symbol_names[0] == "_print_plan"
        assert symbol_names.index("_print_plan") < symbol_names.index("render_plan")
        assert symbol_names.index("_print_plan") < symbol_names.index("summarize_plan")


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
                    "functions": [{"name": "write_run_command"}, {"name": "_build_dry_run_rows"}],
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
        assert report["symbol_hints_count"] <= 8
        assert ("Symbol hints", f"{report['symbol_hints_count']} matched") in rows


def test_collect_symbol_hints_caps_to_a_small_deterministic_set():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_file(
            root / "commands" / "run_command.py",
            (
                "def _build_dry_run_rows():\n"
                "    return True\n\n"
                "def _print_dry_run_plan():\n"
                "    return True\n\n"
                "def write_run_command():\n"
                "    return None\n\n"
                "def _parse_run_args():\n"
                "    return None\n\n"
                "def render_dry_run_plan():\n"
                "    return None\n\n"
                "def summarize_run_plan():\n"
                "    return None\n"
            ),
        )
        _write_file(
            root / "commands" / "apply_command.py",
            (
                "def write_apply_dry_run_command():\n"
                "    return None\n\n"
                "def render_dry_run_plan():\n"
                "    return None\n\n"
                "def summarize_run_plan():\n"
                "    return None\n\n"
                "def print_plan_output():\n"
                "    return None\n\n"
                "def report_run_output():\n"
                "    return None\n"
            ),
        )

        graph = _make_graph(root, ["commands/run_command.py", "commands/apply_command.py"])
        entries = [
            {
                "file": graph["files"][0],
                "selected_by_user": True,
            },
            {
                "file": graph["files"][1],
            },
        ]

        hints_one = collect_symbol_hints(
            graph,
            "fix dry run plan output",
            entries,
            selected_paths=["commands/run_command.py"],
        )
        hints_two = collect_symbol_hints(
            graph,
            "fix dry run plan output",
            entries,
            selected_paths=["commands/run_command.py"],
        )

        assert len(hints_one) == 8
        assert [hint["symbol_name"] for hint in hints_one] == [hint["symbol_name"] for hint in hints_two]
        assert all(hint["file_path"] == "commands/run_command.py" for hint in hints_one[:4])
        assert any(hint["file_path"] == "commands/apply_command.py" for hint in hints_one[4:])


def test_build_symbol_snippets_extracts_non_selected_snippets_and_clamps_ranges():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_file(
            root / "commands" / "run_command.py",
            (
                "def write_run_command():\n"
                "    return None\n"
            ),
        )
        _write_file(
            root / "commands" / "agent_adapters.py",
            (
                "def build_command_dry_run_result():\n"
                "    return {'ok': True}\n"
                "\n"
                "def adapter_supports_dry_run():\n"
                "    return True\n"
            ),
        )

        hints = [
            {
                "file_path": "commands/run_command.py",
                "symbol_name": "write_run_command",
                "kind": "function",
                "start_line": 1,
                "end_line": 2,
                "reason": "selected file symbol",
            },
            {
                "file_path": "commands/agent_adapters.py",
                "symbol_name": "build_command_dry_run_result",
                "kind": "function",
                "start_line": 1,
                "end_line": 999,
                "reason": 'matched task terms "dry", "run"',
            },
        ]

        report = build_symbol_snippets(
            root,
            hints,
            selected_paths=["commands/run_command.py"],
            budget_remaining=5_000,
        )

        assert report["included_count"] == 1
        assert report["skipped_count"] == 1
        assert report["included"][0]["file_path"] == "commands/agent_adapters.py"
        assert report["included"][0]["symbol_name"] == "build_command_dry_run_result"
        assert report["included"][0]["start_line"] == 1
        assert report["included"][0]["end_line"] == 5
        assert "def build_command_dry_run_result" in report["included"][0]["text"]
        assert "commands/run_command.py" not in {snippet["file_path"] for snippet in report["included"]}


def test_build_symbol_snippets_truncates_long_snippets_with_marker():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        body = "\n".join(f"    line_{index} = {index}" for index in range(200))
        _write_file(
            root / "long_snippet.py",
            (
                "def render_long_snippet():\n"
                f"{body}\n"
                "    return line_0\n"
            ),
        )

        report = build_symbol_snippets(
            root,
            [
                {
                    "file_path": "long_snippet.py",
                    "symbol_name": "render_long_snippet",
                    "kind": "function",
                    "start_line": 1,
                    "end_line": 210,
                    "reason": "matched task terms \"render\"",
                }
            ],
            budget_remaining=5_000,
            max_chars_per_snippet=120,
        )

        snippet = report["included"][0]

        assert report["included_count"] == 1
        assert "# ... snippet truncated to fit Strata budget ..." in snippet["text"]
        assert len(snippet["text"]) <= 160


def test_build_symbol_snippets_reports_skipped_reasons_and_caps_list():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_file(
            root / "commands" / "run_command.py",
            (
                "def write_run_command():\n"
                "    return None\n"
            ),
        )
        _write_file(
            root / "commands" / "agent_adapters.py",
            (
                "def build_command_dry_run_result():\n"
                "    return True\n\n"
                "def adapter_supports_dry_run():\n"
                "    return True\n\n"
                "def run_adapter():\n"
                "    return True\n\n"
                "def _dry_run_message():\n"
                "    return True\n\n"
                "def execute_dry_run_command():\n"
                "    return True\n\n"
                "def write_apply_dry_run_command():\n"
                "    return True\n"
            ),
        )

        report = build_symbol_snippets(
            root,
            [
                {
                    "file_path": "commands/run_command.py",
                    "symbol_name": "write_run_command",
                    "kind": "function",
                    "start_line": 1,
                    "end_line": 2,
                    "reason": "selected file symbol",
                },
                {
                    "file_path": "commands/agent_adapters.py",
                    "symbol_name": "build_command_dry_run_result",
                    "kind": "function",
                    "start_line": 1,
                    "end_line": 2,
                    "reason": 'matched task terms "dry", "run"',
                    "priority": 0,
                    "score": 500,
                    "matched_term_count": 2,
                },
                {
                    "file_path": "commands/agent_adapters.py",
                    "symbol_name": "adapter_supports_dry_run",
                    "kind": "function",
                    "start_line": 4,
                    "end_line": 5,
                    "reason": 'matched task terms "dry", "run"',
                    "priority": 1,
                    "score": 450,
                    "matched_term_count": 2,
                },
                {
                    "file_path": "commands/agent_adapters.py",
                    "symbol_name": "run_adapter",
                    "kind": "function",
                    "start_line": 7,
                    "end_line": 8,
                    "reason": 'matched task term "run"',
                    "priority": 2,
                    "score": 400,
                    "matched_term_count": 1,
                },
                {
                    "file_path": "commands/agent_adapters.py",
                    "symbol_name": "_dry_run_message",
                    "kind": "function",
                    "start_line": 10,
                    "end_line": 11,
                    "reason": 'matched task terms "dry", "run"',
                    "priority": 3,
                    "score": 350,
                    "matched_term_count": 2,
                },
                {
                    "file_path": "commands/agent_adapters.py",
                    "symbol_name": "execute_dry_run_command",
                    "kind": "function",
                    "start_line": 13,
                    "end_line": 14,
                    "reason": 'matched task terms "dry", "run"',
                    "priority": 4,
                    "score": 300,
                    "matched_term_count": 2,
                },
                {
                    "file_path": "commands/agent_adapters.py",
                    "symbol_name": "write_apply_dry_run_command",
                    "kind": "function",
                    "start_line": 16,
                    "end_line": 17,
                    "reason": 'matched task terms "dry", "run"',
                    "priority": 5,
                    "score": 250,
                    "matched_term_count": 2,
                },
            ],
            selected_paths=["commands/run_command.py"],
            budget_remaining=10_000,
            max_snippets=2,
        )

        section = build_symbol_snippets_section(report)
        text = "\n".join(section)

        assert report["included_count"] == 2
        assert report["skipped_count"] >= 4
        assert "Skipped snippets:" in text
        assert "selected file" in text
        assert "cap reached" in text
        assert "...and" in text
        assert text.count("Skipped snippets:") >= 1


def test_build_symbol_snippets_includes_fewer_snippets_under_tighter_budget():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_file(
            root / "commands" / "run_command.py",
            (
                "def write_run_command():\n"
                "    return None\n"
            ),
        )

        body = "\n".join(f"    value_{index} = {index}" for index in range(80))
        for name in [
            "agent_adapters.py",
            "execute_command.py",
            "plan_command.py",
            "workflow_command.py",
        ]:
            _write_file(
                root / "commands" / name,
                (
                    "def build_command_dry_run_result():\n"
                    f"{body}\n"
                    "    return value_0\n"
                ),
            )

        hints = [
            {
                "file_path": "commands/run_command.py",
                "symbol_name": "write_run_command",
                "kind": "function",
                "start_line": 1,
                "end_line": 2,
                "reason": "selected file symbol",
            },
        ]

        for index, name in enumerate(
            [
                "commands/agent_adapters.py",
                "commands/execute_command.py",
                "commands/plan_command.py",
                "commands/workflow_command.py",
            ],
            start=1,
        ):
            hints.append(
                {
                    "file_path": name,
                    "symbol_name": "build_command_dry_run_result",
                    "kind": "function",
                    "start_line": 1,
                    "end_line": 82,
                    "reason": 'matched task terms "dry", "run"',
                    "priority": index,
                    "score": 500 - 25 * index,
                    "matched_term_count": 2,
                }
            )

        small_report = build_symbol_snippets(
            root,
            hints,
            selected_paths=["commands/run_command.py"],
            budget_remaining=900,
        )
        large_report = build_symbol_snippets(
            root,
            hints,
            selected_paths=["commands/run_command.py"],
            budget_remaining=10_000,
        )

        assert small_report["included_count"] < large_report["included_count"]
        assert all(snippet["file_path"] != "commands/run_command.py" for snippet in small_report["included"])
        assert all(snippet["file_path"] != "commands/run_command.py" for snippet in large_report["included"])


def test_build_symbol_snippets_skips_generated_secret_and_ignored_paths():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_file(
            root / "src" / "real.py",
            (
                "def keep_me():\n"
                "    return True\n"
            ),
        )

        report = build_symbol_snippets(
            root,
            [
                {
                    "file_path": "src/real.py",
                    "symbol_name": "keep_me",
                    "kind": "function",
                    "start_line": 1,
                    "end_line": 2,
                    "reason": "matched task terms \"keep\"",
                },
                {
                    "file_path": ".aidc/temp.py",
                    "symbol_name": "hidden_symbol",
                    "kind": "function",
                    "start_line": 1,
                    "end_line": 2,
                    "reason": "generated file",
                },
                {
                    "file_path": "credentials.json",
                    "symbol_name": "secret_symbol",
                    "kind": "function",
                    "start_line": 1,
                    "end_line": 2,
                    "reason": "secret file",
                },
                {
                    "file_path": "dist/generated.py",
                    "symbol_name": "generated_symbol",
                    "kind": "function",
                    "start_line": 1,
                    "end_line": 2,
                    "reason": "ignored file",
                },
            ],
            budget_remaining=5_000,
        )

        skipped_reasons = {item["skip_reason"] for item in report["skipped"]}

        assert report["included_count"] == 1
        assert report["included"][0]["file_path"] == "src/real.py"
        assert report["skipped_count"] == 3
        assert "generated or ignored path" in skipped_reasons
        assert "secret-looking path" in skipped_reasons


def test_context_pack_and_agent_prompt_include_symbol_snippets_section():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_file(
            root / "commands" / "run_command.py",
            (
                "def write_run_command():\n"
                "    return None\n"
            ),
        )
        _write_file(
            root / "commands" / "agent_adapters.py",
            (
                "def build_command_dry_run_result():\n"
                "    return {'ok': True}\n\n"
                "def write_apply_dry_run_command():\n"
                "    return None\n"
            ),
        )

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
                    "path": "commands/agent_adapters.py",
                    "language": "python",
                    "classes": [],
                    "functions": [
                        {"name": "build_command_dry_run_result"},
                        {"name": "write_apply_dry_run_command"},
                    ],
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
        rows = build_budget_summary_rows(report)

        assert report["symbol_snippets_count"] >= 1
        assert "commands/run_command.py" in content
        assert "commands/run_command.py" in prompt
        assert "## Symbol Snippets" in content
        assert "## Symbol Snippets" in prompt
        assert "commands/agent_adapters.py" in content
        assert "commands/agent_adapters.py" in prompt
        assert "build_command_dry_run_result" in content
        assert "build_command_dry_run_result" in prompt
        assert "```python" in content
        assert "```python" in prompt
        assert "Lines " in content
        assert "Lines " in prompt
        assert any(label == "Symbol snippets" for label, _ in rows)
        assert any("included" in str(value) for label, value in rows if label == "Symbol snippets")


TESTS = [
    test_new_symbol_slicing_import_matches_legacy_shim,
    test_extract_python_symbols_finds_functions_classes_and_methods,
    test_extract_python_symbols_returns_safe_error_for_syntax_error,
    test_extract_javascript_symbols_finds_functions_typed_arrows_components_hooks_and_methods,
    test_generated_context_includes_approximate_tsx_symbol_confidence,
    test_collect_symbol_hints_prefers_selected_file_symbols_and_reports_term_matches,
    test_collect_symbol_hints_prioritizes_selected_files_over_adjacent_single_term_matches,
    test_symbol_hints_section_survives_tiny_budget_and_selected_files,
    test_collect_symbol_hints_caps_to_a_small_deterministic_set,
    test_build_symbol_snippets_extracts_non_selected_snippets_and_clamps_ranges,
    test_build_symbol_snippets_truncates_long_snippets_with_marker,
    test_build_symbol_snippets_skips_generated_secret_and_ignored_paths,
    test_context_pack_and_agent_prompt_include_symbol_snippets_section,
]
