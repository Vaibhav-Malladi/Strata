from verification_hints import collect_verification_commands


def _project(manager: str, *scripts: str) -> dict:
    return {
        "package_path": "package.json",
        "package_manager": manager,
        "scripts": [{"name": script, "command": script} for script in scripts],
    }


def test_npm_verification_uses_only_available_package_scripts():
    commands = collect_verification_commands(
        {},
        "fix login button",
        [],
        _project("npm", "test", "lint", "build"),
    )

    assert commands == ["npm test", "npm run lint", "npm run build"]
    assert "npm run typecheck" not in commands


def test_pnpm_and_yarn_verification_use_detected_manager_style():
    pnpm = collect_verification_commands(
        {},
        "fix login button",
        [],
        _project("pnpm", "test", "lint", "build"),
    )
    yarn = collect_verification_commands(
        {},
        "fix login button",
        [],
        _project("yarn", "test", "lint", "build"),
    )

    assert pnpm == ["pnpm test", "pnpm lint", "pnpm build"]
    assert yarn == ["yarn test", "yarn lint", "yarn build"]


def test_e2e_is_only_included_when_task_context_calls_for_it():
    project = _project("npm", "test", "e2e")

    normal = collect_verification_commands({}, "fix login button", [], project)
    browser = collect_verification_commands({}, "fix browser e2e login flow", [], project)

    assert "npm run e2e" not in normal
    assert "npm run e2e" in browser


TESTS = [
    test_npm_verification_uses_only_available_package_scripts,
    test_pnpm_and_yarn_verification_use_detected_manager_style,
    test_e2e_is_only_included_when_task_context_calls_for_it,
]
