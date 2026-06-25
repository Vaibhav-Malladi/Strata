import json
from pathlib import Path


SCRIPT_NAMES = ("dev", "start", "build", "test", "lint", "typecheck", "preview", "e2e")
SCRIPT_LIMIT = 8
COMMAND_LIMIT = 100
DEPENDENCY_LIMIT = 8

FRAMEWORK_TOOLING = (
    (("react", "react-dom"), "React"),
    (("next",), "Next.js"),
    (("vite", "@vitejs/plugin-react"), "Vite"),
    (("@angular/core", "@angular/cli"), "Angular"),
    (("typescript",), "TypeScript"),
    (("tailwindcss",), "Tailwind CSS"),
    (("react-router", "react-router-dom"), "React Router"),
    (("@tanstack/react-query",), "React Query"),
    (("redux", "@reduxjs/toolkit"), "Redux"),
    (("zustand",), "Zustand"),
    (("eslint",), "ESLint"),
)
TEST_TOOLING = (
    (("vitest",), "Vitest"),
    (("jest",), "Jest"),
    (("cypress",), "Cypress"),
    (("@playwright/test", "playwright"), "Playwright"),
    (
        (
            "@testing-library/react",
            "@testing-library/angular",
            "@testing-library/jest-dom",
            "@testing-library/user-event",
        ),
        "Testing Library",
    ),
)
KEY_DEPENDENCIES = (
    "react",
    "react-dom",
    "next",
    "@angular/core",
    "react-router",
    "react-router-dom",
    "@tanstack/react-query",
    "redux",
    "@reduxjs/toolkit",
    "zustand",
)
LOCKFILES = (
    ("pnpm-lock.yaml", "pnpm"),
    ("yarn.lock", "yarn"),
    ("package-lock.json", "npm"),
    ("npm-shrinkwrap.json", "npm"),
    ("bun.lockb", "bun"),
)


def collect_javascript_project_hints(graph: dict) -> dict:
    """Read compact, high-signal JavaScript package metadata."""

    root = Path(str((graph or {}).get("root") or "."))
    for relative_path in _package_json_paths(graph):
        package_path = root / Path(relative_path)
        if not package_path.is_file():
            continue
        try:
            payload = json.loads(package_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue

        dependencies = _dependency_groups(payload)
        dependency_names = set().union(*dependencies.values())
        scripts = _collect_scripts(payload.get("scripts"))
        package_type = str(payload.get("type") or "").strip().lower()
        if package_type not in {"module", "commonjs"}:
            package_type = ""

        return {
            "package_path": relative_path,
            "package_manager": _detect_package_manager(package_path.parent, payload),
            "package_type": package_type,
            "scripts": scripts,
            "script_count": len(scripts),
            "framework_tooling": _detected_labels(dependency_names, FRAMEWORK_TOOLING),
            "key_dependencies": [
                name
                for name in KEY_DEPENDENCIES
                if name in dependencies["dependencies"]
            ][:DEPENDENCY_LIMIT],
            "test_tooling": _detected_labels(dependency_names, TEST_TOOLING),
        }

    return {
        "package_path": "",
        "package_manager": "",
        "package_type": "",
        "scripts": [],
        "script_count": 0,
        "framework_tooling": [],
        "key_dependencies": [],
        "test_tooling": [],
    }


def build_javascript_project_hints_section(report: dict | None) -> list[str]:
    report = report or {}
    if not report.get("package_path"):
        return []

    lines = ["## JavaScript Project Hints", ""]
    lines.append(f"- package manager: {report.get('package_manager') or 'unknown'}")
    if report.get("package_type"):
        lines.append(f"- package type: {report['package_type']}")
    if report.get("framework_tooling"):
        lines.append(f"- framework/tooling: {', '.join(report['framework_tooling'])}")
    if report.get("scripts"):
        lines.append("- scripts:")
        for script in report["scripts"]:
            command = str(script.get("command") or "")
            suffix = f": `{command}`" if command else ""
            lines.append(f"  - {script.get('name', '<unknown>')}{suffix}")
    if report.get("key_dependencies"):
        lines.append(f"- key dependencies: {', '.join(report['key_dependencies'])}")
    if report.get("test_tooling"):
        lines.append(f"- test tooling: {', '.join(report['test_tooling'])}")
    lines.append("")
    return lines


def _package_json_paths(graph: dict) -> list[str]:
    paths = []
    for file_info in (graph or {}).get("files", []):
        path = str(file_info.get("path", "")).replace("\\", "/").strip()
        if Path(path).name.lower() == "package.json":
            paths.append(path)
    if "package.json" not in paths:
        paths.append("package.json")
    return sorted(set(paths), key=lambda path: (path.count("/"), path))


def _dependency_groups(payload: dict) -> dict[str, set[str]]:
    groups = {}
    for key in ("dependencies", "devDependencies", "peerDependencies"):
        value = payload.get(key)
        groups[key] = (
            {str(name) for name in value if str(name).strip()}
            if isinstance(value, dict)
            else set()
        )
    return groups


def _collect_scripts(value) -> list[dict]:
    if not isinstance(value, dict):
        return []

    scripts = []
    for name in SCRIPT_NAMES:
        if name not in value:
            continue
        command = str(value.get(name) or "").strip()
        scripts.append(
            {
                "name": name,
                "command": command if len(command) <= COMMAND_LIMIT else "",
            }
        )
    return scripts[:SCRIPT_LIMIT]


def _detect_package_manager(package_dir: Path, payload: dict) -> str:
    declared = str(payload.get("packageManager") or "").strip().lower()
    for manager in ("pnpm", "yarn", "npm", "bun"):
        if declared == manager or declared.startswith(f"{manager}@"):
            return manager

    for filename, manager in LOCKFILES:
        if (package_dir / filename).is_file():
            return manager
    return "unknown"


def _detected_labels(
    dependency_names: set[str],
    definitions: tuple[tuple[tuple[str, ...], str], ...],
) -> list[str]:
    return [
        label
        for package_names, label in definitions
        if any(name in dependency_names for name in package_names)
    ][:DEPENDENCY_LIMIT]
