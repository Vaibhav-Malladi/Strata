import ast
import importlib
import importlib.util
from pathlib import Path
import tomllib


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = PROJECT_ROOT / "strata"

PACKAGE_LAYERS = ("core", "parsers", "adapters", "patch", "commands", "utils")
FORBIDDEN_LAYER_IMPORTS = {
    "utils": {"core", "parsers", "adapters", "patch", "commands"},
    "parsers": {"core", "adapters", "patch", "commands"},
    "adapters": {"core", "patch", "commands"},
    "core": {"patch", "commands"},
    "patch": {"commands"},
}

TEMPORARY_LAYER_EXCEPTIONS = {
    ("parsers/symbol_slicing.py", "strata.core.context_matching"),
    ("parsers/symbol_slicing.py", "strata.core.context_efficiency"),
    ("parsers/symbol_slicing.py", "strata.core.selected_context"),
    ("parsers/typescript.py", "strata.core.context_matching"),
}

TEMPORARY_ROOT_IMPORT_ALLOWLIST = {
    "adapters/doctor.py": {"http_adapter_contract", "ollama_adapter"},
    "adapters/export.py": {
        "brief",
        "context_budget",
        "execution_hints",
        "framework_hints",
        "health",
        "selected_context",
        "test_mapper",
        "test_mapping",
        "verification_hints",
    },
    "adapters/http_executor.py": {"patch_contract", "patch_validator"},
    "adapters/ollama.py": {"patch_contract", "patch_validator"},
    "core/brief.py": {"secret_redaction"},
    "core/brief_impact.py": {"impact"},
    "core/context_budget.py": {"context_pack", "test_mapper", "typescript_project"},
    "core/context_pack.py": {"secret_redaction", "typescript_project"},
    "core/selected_context.py": {"snapshot_cache"},
    "utils/config.py": {"agent_adapters", "secret_redaction"},
    "utils/output.py": {"secret_redaction"},
    "utils/shell.py": {"patch_contract", "patch_validator", "secret_redaction"},
}

TEMPORARY_CLI_CORE_IMPORTERS = {
    "commands/agent_prompt_command.py",
    "commands/ask_command.py",
    "commands/brief_command.py",
    "commands/context_command.py",
    "commands/cycles_command.py",
    "commands/diff_command.py",
    "commands/gate_command.py",
    "commands/health_command.py",
    "commands/impact_command.py",
    "commands/map_command.py",
    "commands/preflight_command.py",
    "commands/prepare_command.py",
    "commands/review_command.py",
    "commands/routes_command.py",
    "commands/scan_command.py",
    "commands/show_command.py",
    "commands/snapshot_command.py",
    "commands/start_command.py",
    "commands/status_command.py",
    "commands/tests_for_command.py",
    "commands/verify_command.py",
}

IMPORTANT_ROOT_SHIMS = {
    "cli.py": "strata.commands.cli",
    "strata.py": "strata.cli",
    "cli_core.py": "strata.commands.cli_core",
    "graph.py": "strata.core.graph",
    "python_parser.py": "strata.parsers.python",
    "adapter_doctor.py": "strata.adapters.doctor",
    "patch_contract.py": "strata.patch.contract",
    "fs_utils.py": "strata.utils.paths",
    "commands/gate_command.py": "strata.commands.gate_command",
}


def _parse(path: Path) -> ast.Module:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as error:
        raise AssertionError(f"Architecture check could not parse {path}: {error}") from error


def _imported_modules(path: Path) -> list[str]:
    modules: list[str] = []
    relative_path = path.relative_to(PACKAGE_ROOT)
    package = ".".join(("strata", *relative_path.parent.parts))

    for node in ast.walk(_parse(path)):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                module = importlib.util.resolve_name("." * node.level + module, package)
            if module:
                modules.append(module)

    return modules


def _shim_target(path: Path) -> str | None:
    for node in _parse(path).body:
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        if node.module.startswith("strata.") and any(alias.name == "*" for alias in node.names):
            return node.module
    return None


def _migrated_root_modules() -> dict[str, str]:
    shims: dict[str, str] = {}
    candidates = list(PROJECT_ROOT.glob("*.py")) + list((PROJECT_ROOT / "commands").glob("*.py"))

    for path in candidates:
        target = _shim_target(path)
        if target:
            shims[path.stem] = target

    return shims


def test_required_package_directories_exist():
    missing = [str(PACKAGE_ROOT / layer) for layer in PACKAGE_LAYERS if not (PACKAGE_ROOT / layer).is_dir()]
    assert PACKAGE_ROOT.is_dir(), f"Missing product package directory: {PACKAGE_ROOT}"
    assert not missing, "Missing package layer directories: " + ", ".join(missing)


def test_package_layering_has_no_new_violations():
    violations: list[str] = []

    for source_layer, forbidden_layers in FORBIDDEN_LAYER_IMPORTS.items():
        for path in sorted((PACKAGE_ROOT / source_layer).rglob("*.py")):
            relative_path = path.relative_to(PACKAGE_ROOT).as_posix()
            for module in _imported_modules(path):
                parts = module.split(".")
                imported_layer = parts[1] if len(parts) > 1 and parts[0] == "strata" else None
                if imported_layer not in forbidden_layers:
                    continue
                if (relative_path, module) in TEMPORARY_LAYER_EXCEPTIONS:
                    continue
                violations.append(f"{relative_path} imports forbidden layer module {module}")

    assert not violations, "Package layering violations:\n" + "\n".join(violations)


def test_package_modules_avoid_new_root_compatibility_imports():
    migrated_modules = _migrated_root_modules()
    violations: list[str] = []

    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        relative_path = path.relative_to(PACKAGE_ROOT).as_posix()
        allowed = TEMPORARY_ROOT_IMPORT_ALLOWLIST.get(relative_path, set())

        for module in _imported_modules(path):
            if module not in migrated_modules:
                continue
            root_name = module
            if root_name == "cli_core" and relative_path in TEMPORARY_CLI_CORE_IMPORTERS:
                continue
            if root_name in allowed:
                continue
            violations.append(
                f"{relative_path} imports root shim {root_name}; use {migrated_modules[root_name]}"
            )

    assert not violations, "New imports through root compatibility shims:\n" + "\n".join(violations)


def test_important_root_compatibility_shims_are_small_and_correct():
    violations: list[str] = []

    for relative_path, expected_target in IMPORTANT_ROOT_SHIMS.items():
        path = PROJECT_ROOT / relative_path
        if not path.is_file():
            violations.append(f"Missing compatibility shim: {relative_path}")
            continue

        significant_lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        target = _shim_target(path)
        if len(significant_lines) > 3:
            violations.append(f"Compatibility shim is too large: {relative_path}")
        if target != expected_target:
            violations.append(
                f"{relative_path} must contain 'from {expected_target} import *'; found {target!r}"
            )

    assert not violations, "Invalid root compatibility shims:\n" + "\n".join(violations)


def test_packaged_cli_entrypoints_are_wired_correctly():
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as file:
        pyproject = tomllib.load(file)

    assert pyproject["project"]["scripts"]["strata"] == "strata.cli:main"

    main_modules = _imported_modules(PACKAGE_ROOT / "__main__.py")
    assert "strata.cli" in main_modules, "strata/__main__.py must import main from strata.cli"
    assert "cli" not in main_modules, "strata/__main__.py must not import the root cli shim"

    packaged_cli = importlib.import_module("strata.cli")
    command_cli = importlib.import_module("strata.commands.cli")
    assert packaged_cli.main is command_cli.main


TESTS = [
    test_required_package_directories_exist,
    test_package_layering_has_no_new_violations,
    test_package_modules_avoid_new_root_compatibility_imports,
    test_important_root_compatibility_shims_are_small_and_correct,
    test_packaged_cli_entrypoints_are_wired_correctly,
]
