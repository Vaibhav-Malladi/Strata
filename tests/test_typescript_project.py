import tempfile
from pathlib import Path

import strata.parsers.typescript as new_ts_project
import typescript_project as old_ts_project
from typescript_project import (
    build_declaration_hints_section,
    build_typescript_project_hints_section,
    collect_declaration_hints,
    collect_typescript_project_hints,
)
from agent_export import generate_agent_prompt
from context_budget import build_budget_summary_rows
from context_pack import build_context_pack


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _graph(root: Path, paths: list[str]) -> dict:
    return {
        "root": str(root),
        "files": [{"path": path, "language": "typescript"} for path in paths],
        "edges": [],
    }


def test_new_typescript_project_import_matches_legacy_shim():
    assert old_ts_project.collect_typescript_project_hints is new_ts_project.collect_typescript_project_hints
    assert old_ts_project.collect_declaration_hints is new_ts_project.collect_declaration_hints


def test_typescript_project_aliases_and_declarations_are_compact_and_confident():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(
            root / "tsconfig.json",
            '{"compilerOptions":{"baseUrl":"src","paths":{"@services/*":["app/services/*"],"@shared/*":["app/shared/*"]}}}',
        )
        _write(
            root / "src" / "types" / "api.d.ts",
            (
                "export interface User {\n"
                "  login(token: string): Promise<boolean>;\n"
                "}\n"
                "export function login(user: User): Promise<User>;\n"
                "export type UserId = string;\n"
            ),
        )
        graph = _graph(root, ["tsconfig.json", "src/types/api.d.ts"])

        project = collect_typescript_project_hints(graph)
        declarations = collect_declaration_hints(graph, "fix user login")
        project_text = "\n".join(build_typescript_project_hints_section(project))
        declaration_text = "\n".join(build_declaration_hints_section(declarations))

        assert project["base_url"] == "src"
        assert project["alias_count"] == 2
        assert "@services/*" in project_text
        assert any(item["name"] == "User" for item in declarations)
        assert any(item["name"] == "login" for item in declarations)
        assert all(item["confidence"] == "high" for item in declarations)
        assert all(item["confidence_reason"] == "declaration" for item in declarations)
        assert "Declaration Hints" in declaration_text

        context = build_context_pack(graph, "fix user login", budget_value="small")
        prompt = generate_agent_prompt(graph, "fix user login", budget_value="small")
        for generated in (context, prompt):
            assert "## TypeScript Project Hints" in generated
            assert "## Declaration Hints" in generated
            assert "@services/*" in generated
            assert "high confidence" in generated


def test_project_hint_summary_pluralizes_alias_cleanly():
    singular = build_budget_summary_rows(
        {
            "budget": {},
            "included_entries": [],
            "excluded_entries": [],
            "typescript_alias_count": 1,
        }
    )
    plural = build_budget_summary_rows(
        {
            "budget": {},
            "included_entries": [],
            "excluded_entries": [],
            "typescript_alias_count": 3,
        }
    )

    assert ("Project hints", "1 alias found") in singular
    assert ("Project hints", "3 aliases found") in plural


TESTS = [
    test_new_typescript_project_import_matches_legacy_shim,
    test_typescript_project_aliases_and_declarations_are_compact_and_confident,
    test_project_hint_summary_pluralizes_alias_cleanly,
]
