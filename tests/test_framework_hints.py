import tempfile
from pathlib import Path

import framework_hints as old_framework_hints
import strata.core.framework_hints as new_framework_hints
from agent_export import generate_agent_prompt
from context_budget import build_budget_report
from context_pack import build_context_pack, rank_relevant_files
from framework_hints import (
    build_angular_hints_section,
    build_react_hints_section,
    collect_angular_hints,
    collect_react_hints,
)


def test_core_framework_hints_import_matches_compatibility_shim():
    assert old_framework_hints.collect_react_hints is new_framework_hints.collect_react_hints


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
            _file("src/components/login-button.tsx", functions=[{"name": "LoginButton"}]),
            _file("src/components/LoginButton.test.tsx", functions=[{"name": "LoginButton"}]),
            _file("src/components/LoginForm.tsx", functions=[{"name": "LoginForm"}]),
            _file("src/hooks/useAuth.ts", functions=[{"name": "useAuth"}]),
            _file("src/hooks/useLogin.ts", functions=[{"name": "useLogin"}]),
            _file("src/services/auth.service.ts", classes=[{"name": "AuthService"}]),
        ],
        "edges": [],
    }

    login_ranked = rank_relevant_files(graph, "fix login button not disabling")
    hook_ranked = rank_relevant_files(graph, "update auth hook state handling")

    assert login_ranked[0]["file"]["path"] == "src/components/LoginButton.tsx"
    assert login_ranked.index(next(item for item in login_ranked if item["file"]["path"].endswith("LoginButton.tsx"))) < login_ranked.index(
        next(item for item in login_ranked if item["file"]["path"].endswith("LoginButton.test.tsx"))
    )
    assert hook_ranked[0]["file"]["path"] == "src/hooks/useAuth.ts"


def test_react_component_family_includes_tests_styles_and_tailwind_without_test_component():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        paths = [
            "src/components/LoginButton.tsx",
            "src/components/LoginButton.test.tsx",
            "src/components/LoginButton.module.css",
            "src/hooks/useLogin.ts",
        ]
        _write(
            root / paths[0],
            'export function LoginButton() { return <button className="flex rounded bg-blue-600">Login</button>; }\n',
        )
        for path in paths[1:]:
            _write(root / path, "")

        graph = {
            "root": str(root),
            "files": [_file(paths[0]), _file(paths[1]), _file(paths[3])],
            "edges": [],
        }
        relevant = [{"file": file_info} for file_info in graph["files"]]
        hints = collect_react_hints(graph, "fix login button not disabling", relevant)
        section = "\n".join(build_react_hints_section(hints))

        assert [hint["path"] for hint in hints] == ["src/components/LoginButton.tsx"]
        assert hints[0]["tests"] == ["src/components/LoginButton.test.tsx"]
        assert hints[0]["styles"] == ["src/components/LoginButton.module.css"]
        assert hints[0]["hooks"] == ["src/hooks/useLogin.ts"]
        assert hints[0]["styling"] == "Tailwind (detected via class usage)"
        assert "LoginButton.test.tsx` - component" not in section
        assert "medium confidence (convention)" in section


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


def test_react_hints_are_capped_for_many_components():
    files = [
        _file(f"src/components/LoginButton{index}.tsx")
        for index in range(8)
    ]
    graph = {"root": ".", "files": files, "edges": []}
    relevant = [{"file": file_info} for file_info in files]

    hints = collect_react_hints(graph, "fix login button", relevant)

    assert len(hints) == 4


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
        graph = {"root": str(root), "files": [_file(paths[0])], "edges": []}
        relevant = [{"file": graph["files"][0]}]

        hints = collect_angular_hints(graph, relevant, "update user profile component")
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


def test_angular_service_guard_relationships_and_compact_output_cap():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        source_paths = [
            "src/app/auth/auth.service.ts",
            "src/app/auth/auth.guard.ts",
        ]
        component_paths = [
            f"src/app/item-{index}/item-{index}.component.ts"
            for index in range(8)
        ]
        for path in [
            *source_paths,
            "src/app/auth/auth.service.spec.ts",
            "src/app/auth/auth.guard.spec.ts",
            *component_paths,
        ]:
            _write(root / path, "")

        graph = {
            "root": str(root),
            "files": [_file(path) for path in [*source_paths, *component_paths]],
            "edges": [],
        }
        relevant = [{"file": file_info} for file_info in graph["files"]]

        hints = collect_angular_hints(graph, relevant, "update auth access")
        section = "\n".join(build_angular_hints_section(hints))

        assert len(hints) == 5
        service = next(hint for hint in hints if hint["kind"] == "service")
        guard = next(hint for hint in hints if hint["kind"] == "guard")
        assert service["tests"] == ["src/app/auth/auth.service.spec.ts"]
        assert guard["tests"] == ["src/app/auth/auth.guard.spec.ts"]
        assert "medium confidence (convention); matched `auth`" in section


def test_angular_component_source_ranks_above_template_and_style():
    graph = {
        "root": ".",
        "files": [
            _file("src/app/profile/profile.component.ts"),
            _file("src/app/profile/profile.component.html", language="html"),
            _file("src/app/profile/profile.component.scss", language="scss"),
        ],
        "edges": [],
    }

    ranked = rank_relevant_files(graph, "fix profile component validation")

    assert ranked[0]["file"]["path"] == "src/app/profile/profile.component.ts"


def test_react_component_source_ranks_above_style_unless_style_is_requested():
    graph = {
        "root": ".",
        "files": [
            _file("src/components/LoginButton.tsx"),
            _file("src/components/LoginButton.module.css", language="css"),
        ],
        "edges": [],
    }

    normal_ranked = rank_relevant_files(graph, "fix login button not disabling")
    style_ranked = rank_relevant_files(graph, "fix login button styles")

    assert normal_ranked[0]["file"]["path"] == "src/components/LoginButton.tsx"
    assert style_ranked[0]["file"]["path"] == "src/components/LoginButton.module.css"


TESTS = [
    test_core_framework_hints_import_matches_compatibility_shim,
    test_react_starting_file_ranking_prefers_direct_component_and_hook_matches,
    test_react_component_family_includes_tests_styles_and_tailwind_without_test_component,
    test_react_hints_exclude_test_and_spec_components,
    test_react_hints_are_capped_for_many_components,
    test_angular_file_family_and_generated_sections_only_appear_when_found,
    test_angular_service_guard_relationships_and_compact_output_cap,
    test_angular_component_source_ranks_above_template_and_style,
    test_react_component_source_ranks_above_style_unless_style_is_requested,
]
