import json
import tempfile
from pathlib import Path

from agent_export import generate_agent_prompt
from context_budget import build_budget_report, build_budget_summary_rows
from context_pack import build_context_pack
from javascript_project import (
    build_javascript_project_hints_section,
    collect_javascript_project_hints,
)


def _write(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _graph(root: Path) -> dict:
    return {
        "root": str(root),
        "files": [{"path": "src/LoginButton.tsx", "language": "typescript"}],
        "edges": [],
    }


def test_javascript_project_hints_are_compact_and_integrated():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        payload = {
            "type": "module",
            "scripts": {
                "dev": "vite",
                "build": "vite build",
                "test": "vitest",
                "lint": "eslint .",
                "release": "ignored-script",
            },
            "dependencies": {
                "react": "^19.0.0",
                "react-dom": "^19.0.0",
                "@tanstack/react-query": "^5.0.0",
                "low-signal-package": "^1.0.0",
            },
            "devDependencies": {
                "typescript": "^5.0.0",
                "vite": "^7.0.0",
                "vitest": "^3.0.0",
                "@testing-library/react": "^16.0.0",
                "tailwindcss": "^4.0.0",
                "eslint": "^9.0.0",
            },
        }
        _write(root / "package.json", json.dumps(payload))
        _write(root / "package-lock.json")
        _write(
            root / "tsconfig.json",
            '{"compilerOptions":{"baseUrl":"src","paths":{"@components/*":["components/*"]}}}',
        )
        _write(
            root / "src" / "types" / "login.d.ts",
            "export function login(user: string): Promise<boolean>;\n",
        )
        graph = _graph(root)
        graph["files"].append(
            {"path": "src/types/login.d.ts", "language": "typescript"}
        )

        hints = collect_javascript_project_hints(graph)
        section = "\n".join(build_javascript_project_hints_section(hints))
        report = build_budget_report(graph, "fix login button", budget_value="small")
        context = build_context_pack(graph, "fix login button", budget_value="small")
        prompt = generate_agent_prompt(graph, "fix login button", budget_value="small")
        rows = build_budget_summary_rows(report)

        assert hints["package_manager"] == "npm"
        assert hints["package_type"] == "module"
        assert [script["name"] for script in hints["scripts"]] == ["dev", "build", "test", "lint"]
        assert hints["framework_tooling"] == [
            "React",
            "Vite",
            "TypeScript",
            "Tailwind CSS",
            "React Query",
            "ESLint",
        ]
        assert hints["key_dependencies"] == ["react", "react-dom", "@tanstack/react-query"]
        assert hints["test_tooling"] == ["Vitest", "Testing Library"]
        assert "low-signal-package" not in section
        assert "ignored-script" not in section
        for generated in (context, prompt):
            assert "## TypeScript Project Hints" in generated
            assert "## JavaScript Project Hints" in generated
            assert "## Declaration Hints" in generated
            assert "package manager: npm" in generated
            assert "dev: `vite`" in generated
            assert "test tooling: Vitest, Testing Library" in generated
            assert generated.index("## TypeScript Project Hints") < generated.index(
                "## JavaScript Project Hints"
            )
            assert generated.index("## JavaScript Project Hints") < generated.index(
                "## Declaration Hints"
            )
        assert ("Project hints", "1 alias, package.json found") in rows


def test_package_manager_lockfile_detection():
    for lockfile, expected in (
        ("pnpm-lock.yaml", "pnpm"),
        ("yarn.lock", "yarn"),
        ("package-lock.json", "npm"),
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write(root / "package.json", "{}")
            _write(root / lockfile)

            hints = collect_javascript_project_hints(_graph(root))

            assert hints["package_manager"] == expected


def test_javascript_project_hints_suppress_empty_and_noisy_output():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        graph = _graph(root)

        assert build_javascript_project_hints_section(
            collect_javascript_project_hints(graph)
        ) == []
        assert "## JavaScript Project Hints" not in build_context_pack(
            graph,
            "fix login button",
            budget_value="small",
        )

        dependencies = {f"package-{index}": "1.0.0" for index in range(100)}
        dependencies["react"] = "19.0.0"
        _write(root / "package.json", json.dumps({"dependencies": dependencies}))
        section = "\n".join(
            build_javascript_project_hints_section(
                collect_javascript_project_hints(graph)
            )
        )

        assert "React" in section
        assert "package-99" not in section
        assert len(section.splitlines()) < 10


def test_javascript_project_budget_summary_pluralizes_scripts():
    singular = build_budget_summary_rows(
        {
            "budget": {},
            "included_entries": [],
            "excluded_entries": [],
            "javascript_project_found": True,
            "javascript_script_count": 1,
            "javascript_project_hints": {
                "package_path": "package.json",
                "package_manager": "npm",
                "framework_tooling": ["React", "Vite"],
            },
        }
    )
    plural = build_budget_summary_rows(
        {
            "budget": {},
            "included_entries": [],
            "excluded_entries": [],
            "javascript_project_found": True,
            "javascript_script_count": 4,
            "javascript_project_hints": {
                "package_path": "package.json",
                "package_manager": "npm",
                "framework_tooling": ["React", "Vite"],
            },
        }
    )

    assert ("JS project hints", "npm, React, Vite; 1 script found") in singular
    assert ("JS project hints", "npm, React, Vite; 4 scripts found") in plural


TESTS = [
    test_javascript_project_hints_are_compact_and_integrated,
    test_package_manager_lockfile_detection,
    test_javascript_project_hints_suppress_empty_and_noisy_output,
    test_javascript_project_budget_summary_pluralizes_scripts,
]
