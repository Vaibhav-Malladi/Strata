import tempfile
from pathlib import Path

import execution_hints as old_execution_hints
import strata.core.execution_hints as new_execution_hints
from context_pack import build_context_pack
from execution_hints import collect_execution_path_hints
from framework_hints import collect_angular_hints, collect_react_hints


def _file(path: str, language: str = "python", **extra) -> dict:
    item = {
        "path": path,
        "language": language,
        "classes": [],
        "functions": [],
        "imports": [],
        "external_imports": [],
        "unresolved_imports": [],
        "unresolved_import_details": [],
        "routes": [],
    }
    item.update(extra)
    return item


def test_core_execution_hints_import_matches_compatibility_shim():
    assert (
        old_execution_hints.collect_execution_path_hints
        is new_execution_hints.collect_execution_path_hints
    )


def _write(root: Path, path: str, content: str = "") -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def test_python_execution_hints_prioritize_selected_command_and_import_path():
    graph = {
        "root": ".",
        "files": [
            _file("cli.py"),
            _file(
                "commands/run_command.py",
                functions=[{"name": "write_run_command"}],
            ),
            _file("agent_adapters.py"),
        ],
        "edges": [
            {
                "from": "cli.py",
                "to": "commands/run_command.py",
                "type": "imports",
                "import": "commands.run_command",
            },
            {
                "from": "commands/run_command.py",
                "to": "agent_adapters.py",
                "type": "imports",
                "import": "agent_adapters",
            },
        ],
    }
    relevant = [
        {
            "file": graph["files"][1],
            "selected_by_user": True,
        },
        {"file": graph["files"][0]},
    ]

    hints = collect_execution_path_hints(graph, relevant)

    assert "commands/run_command.py" in hints[0]
    assert any("likely the command handler for `strata run`" in hint for hint in hints)
    assert any("agent_adapters.py" in hint and "via import" in hint for hint in hints)


def test_react_execution_hints_reference_test_without_repeating_react_section():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        source = "src/components/LoginButton.tsx"
        test = "src/components/LoginButton.test.tsx"
        _write(root, source, "export function LoginButton() { return <button />; }\n")
        _write(root, test)
        graph = {
            "root": str(root),
            "files": [
                _file(source, "typescript", functions=[{"name": "LoginButton"}]),
                _file(test, "typescript"),
            ],
            "edges": [],
        }
        relevant = [{"file": graph["files"][0]}]
        react_hints = collect_react_hints(
            graph,
            "fix login button not disabling",
            relevant,
        )
        hints = collect_execution_path_hints(
            graph,
            relevant,
            react_hints=react_hints,
        )
        content = build_context_pack(
            graph,
            "fix login button not disabling",
            selected_paths=[source],
            budget_value="small",
        )

        assert any(source in hint and test in hint for hint in hints)
        execution_section = content.split("## Execution Path Hints", 1)[1].split("## ", 1)[0]
        assert test in execution_section
        assert "medium confidence" not in execution_section


def test_angular_execution_hints_use_convention_wording_for_file_family():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        paths = [
            "src/app/login/login.component.ts",
            "src/app/login/login.component.html",
            "src/app/login/login.component.scss",
            "src/app/login/login.component.spec.ts",
        ]
        for path in paths:
            _write(root, path)
        graph = {
            "root": str(root),
            "files": [_file(paths[0], "typescript")],
            "edges": [],
        }
        relevant = [{"file": graph["files"][0]}]
        angular_hints = collect_angular_hints(
            graph,
            relevant,
            "fix login component validation",
        )

        hints = collect_execution_path_hints(
            graph,
            relevant,
            angular_hints=angular_hints,
        )

        assert any("template" in hint and "by convention" in hint for hint in hints)
        assert any("style" in hint and "by convention" in hint for hint in hints)
        assert any("likely covered" in hint and paths[3] in hint for hint in hints)


TESTS = [
    test_core_execution_hints_import_matches_compatibility_shim,
    test_python_execution_hints_prioritize_selected_command_and_import_path,
    test_react_execution_hints_reference_test_without_repeating_react_section,
    test_angular_execution_hints_use_convention_wording_for_file_family,
]
