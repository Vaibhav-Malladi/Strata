import tempfile
from pathlib import Path

from agent_export import generate_agent_prompt
from context_budget import build_budget_report
from context_pack import build_context_pack, rank_relevant_files
from framework_hints import collect_angular_hints, collect_react_hints


def _write(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _file(path: str, language: str = "typescript", **extra) -> dict:
    item = {
        "path": path,
        "language": language,
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
    item.update(extra)
    return item


def test_react_starting_file_ranking_prefers_direct_component_and_hook_matches():
    graph = {
        "root": ".",
        "files": [
            _file("src/components/LoginButton.tsx", functions=[{"name": "LoginButton"}]),
            _file("src/components/LoginForm.tsx", functions=[{"name": "LoginForm"}]),
            _file("src/hooks/useLogin.ts", functions=[{"name": "useLogin"}]),
            _file("src/services/auth.service.ts", classes=[{"name": "AuthService"}]),
        ],
        "edges": [],
    }

    login_ranked = rank_relevant_files(graph, "fix login button not disabling")
    hook_ranked = rank_relevant_files(graph, "update auth hook state handling")

    assert login_ranked[0]["file"]["path"] == "src/components/LoginButton.tsx"
    assert hook_ranked[0]["file"]["path"] == "src/hooks/useLogin.ts"


def test_react_hints_exclude_test_and_spec_components():
    paths = [
        "src/LoginButton.tsx",
        "src/LoginButton.test.tsx",
        "src/LoginButton.spec.tsx",
        "src/LoginButton.test.jsx",
        "src/LoginButton.spec.jsx",
    ]
    graph = {"root": ".", "files": [_file(path) for path in paths], "edges": []}
    relevant = [{"file": file_info} for file_info in graph["files"]]

    hints = collect_react_hints(graph, "fix login button", relevant)

    assert [hint["path"] for hint in hints] == ["src/LoginButton.tsx"]


def test_angular_file_family_and_generated_sections_only_appear_when_found():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        paths = [
            "src/app/user/user-profile.component.ts",
            "src/app/user/user-profile.component.html",
            "src/app/user/user-profile.component.scss",
            "src/app/user/user-profile.component.spec.ts",
        ]
        for path in paths:
            _write(root / path, "export class UserProfileComponent {}\n")
        graph = {"root": str(root), "files": [_file(path) for path in paths], "edges": []}
        relevant = [{"file": graph["files"][0]}]

        hints = collect_angular_hints(graph, relevant)
        report = build_budget_report(graph, "update user profile component", budget_value="small")
        context = build_context_pack(graph, "update user profile component", budget_value="small")
        prompt = generate_agent_prompt(graph, "update user profile component", budget_value="small")

        assert hints[0]["template"].endswith(".component.html")
        assert hints[0]["styles"][0].endswith(".component.scss")
        assert hints[0]["tests"][0].endswith(".component.spec.ts")
        assert report["angular_hints_count"] >= 1
        assert "## Angular Hints" in context
        assert "## Angular Hints" in prompt
        assert "## TypeScript Project Hints" not in context
        assert "## Declaration Hints" not in context


TESTS = [
    test_react_starting_file_ranking_prefers_direct_component_and_hook_matches,
    test_react_hints_exclude_test_and_spec_components,
    test_angular_file_family_and_generated_sections_only_appear_when_found,
]
