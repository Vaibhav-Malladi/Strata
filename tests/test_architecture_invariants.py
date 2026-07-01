import ast
import importlib
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
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

MIGRATED_ROOT_SHIMS = (
    # CLI and command infrastructure.
    ("cli.py", "strata.commands.cli"),
    ("cli_core.py", "strata.commands.cli_core"),
    ("cli_help.py", "strata.commands.cli_help"),
    ("cli_ui.py", "strata.commands.cli_ui"),
    ("help_topics.py", "strata.commands.help_topics"),
    ("strata.py", "strata.cli"),
    # Utilities.
    ("command_executor.py", "strata.utils.shell"),
    ("fs_utils.py", "strata.utils.paths"),
    ("secret_redaction.py", "strata.utils.secrets"),
    ("ui.py", "strata.utils.output"),
    ("workflow_config.py", "strata.utils.config"),
    # Parsers.
    ("javascript_project.py", "strata.parsers.javascript_project"),
    ("js_parser.py", "strata.parsers.javascript"),
    ("js_resolution.py", "strata.parsers.js_resolution"),
    ("languages.py", "strata.parsers.languages"),
    ("python_parser.py", "strata.parsers.python"),
    ("symbol_slicing.py", "strata.parsers.symbol_slicing"),
    ("typescript_project.py", "strata.parsers.typescript"),
    # Adapters.
    ("adapter_doctor.py", "strata.adapters.doctor"),
    ("adapter_presets.py", "strata.adapters.presets"),
    ("agent_adapters.py", "strata.adapters.agent_adapters"),
    ("agent_export.py", "strata.adapters.export"),
    ("http_adapter_contract.py", "strata.adapters.http_contract"),
    ("http_executor.py", "strata.adapters.http_executor"),
    ("ollama_adapter.py", "strata.adapters.ollama"),
    # Patch handling.
    ("patch_applier.py", "strata.patch.applier"),
    ("patch_contract.py", "strata.patch.contract"),
    ("patch_validator.py", "strata.patch.validator"),
    # Core repository intelligence.
    ("brief.py", "strata.core.brief"),
    ("brief_impact.py", "strata.core.brief_impact"),
    ("context_budget.py", "strata.core.context_budget"),
    ("context_efficiency.py", "strata.core.context_efficiency"),
    ("context_matching.py", "strata.core.context_matching"),
    ("context_pack.py", "strata.core.context_pack"),
    ("cycles.py", "strata.core.cycles"),
    ("diff_engine.py", "strata.core.diff_engine"),
    ("direct_edit.py", "strata.core.direct_edit"),
    ("execution_hints.py", "strata.core.execution_hints"),
    ("framework_hints.py", "strata.core.framework_hints"),
    ("full_scan.py", "strata.core.full_scan"),
    ("gate.py", "strata.core.gate"),
    ("graph.py", "strata.core.graph"),
    ("health.py", "strata.core.health"),
    ("impact.py", "strata.core.impact"),
    ("map_writer.py", "strata.core.map_writer"),
    ("preflight.py", "strata.core.preflight"),
    ("repo_ignore.py", "strata.core.repo_ignore"),
    ("repo_summary.py", "strata.core.repo_summary"),
    ("routes.py", "strata.core.routes"),
    ("scanner.py", "strata.core.scanner"),
    ("selected_context.py", "strata.core.selected_context"),
    ("snapshot.py", "strata.core.snapshot"),
    ("snapshot_cache.py", "strata.core.snapshot_cache"),
    ("status.py", "strata.core.status"),
    ("test_mapper.py", "strata.core.test_mapper"),
    ("test_mapping.py", "strata.core.test_mapping"),
    ("verification_hints.py", "strata.core.verification_hints"),
    ("verify.py", "strata.core.verify"),
    ("workflow_planner.py", "strata.core.workflow_planner"),
)

INTENTIONAL_ROOT_NON_SHIMS = {"tests.py"}

PACKAGE_SMOKE_MODULES = (
    "strata.cli",
    "strata.commands.cli",
    "strata.commands.cli_core",
    "strata.core.scanner",
    "strata.core.context_pack",
    "strata.core.gate",
    "strata.patch.applier",
    "strata.parsers.python",
    "strata.parsers.javascript",
    "strata.adapters.ollama",
    "strata.utils.config",
)


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
    shims = {Path(relative_path).stem: target for relative_path, target in MIGRATED_ROOT_SHIMS}

    for path in (PROJECT_ROOT / "commands").glob("*.py"):
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
            if root_name in allowed:
                continue
            violations.append(
                f"{relative_path} imports root shim {root_name}; use {migrated_modules[root_name]}"
            )

    assert not violations, "New imports through root compatibility shims:\n" + "\n".join(violations)


def test_migrated_root_shim_inventory_is_complete_small_and_correct():
    violations: list[str] = []

    inventory_files = {relative_path for relative_path, _ in MIGRATED_ROOT_SHIMS}
    actual_root_files = {path.name for path in PROJECT_ROOT.glob("*.py")}
    unexpected_files = sorted(actual_root_files - inventory_files - INTENTIONAL_ROOT_NON_SHIMS)
    missing_non_shims = sorted(INTENTIONAL_ROOT_NON_SHIMS - actual_root_files)

    if unexpected_files:
        violations.append("Unclassified root Python files: " + ", ".join(unexpected_files))
    if missing_non_shims:
        violations.append("Missing intentional root files: " + ", ".join(missing_non_shims))

    for relative_path, expected_target in MIGRATED_ROOT_SHIMS:
        path = PROJECT_ROOT / relative_path
        implementation_path = PROJECT_ROOT / (expected_target.replace(".", "/") + ".py")
        if not path.is_file():
            violations.append(f"Missing compatibility shim: {relative_path}")
            continue
        if not implementation_path.is_file():
            violations.append(
                f"Missing packaged implementation for {relative_path}: {implementation_path.relative_to(PROJECT_ROOT)}"
            )

        significant_lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        target = _shim_target(path)
        if len(significant_lines) > 3:
            violations.append(f"Compatibility shim is too large: {relative_path}")
        if target != expected_target:
            violations.append(
                f"{relative_path} must contain 'from {expected_target} import *'; found {target!r}"
            )

    assert not violations, "Invalid root compatibility shims:\n" + "\n".join(violations)


def test_representative_package_modules_import():
    failures: list[str] = []

    for module_name in PACKAGE_SMOKE_MODULES:
        try:
            importlib.import_module(module_name)
        except Exception as error:
            failures.append(f"{module_name}: {type(error).__name__}: {error}")

    assert not failures, "Package smoke import failures:\n" + "\n".join(failures)


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


def test_python_module_entrypoint_help_smoke():
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    result = subprocess.run(
        [sys.executable, "-m", "strata", "--help"],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, f"python -m strata --help failed:\n{result.stderr}"
    assert "Strata" in result.stdout, "python -m strata --help produced no Strata help output"


TESTS = [
    test_required_package_directories_exist,
    test_package_layering_has_no_new_violations,
    test_package_modules_avoid_new_root_compatibility_imports,
    test_migrated_root_shim_inventory_is_complete_small_and_correct,
    test_representative_package_modules_import,
    test_packaged_cli_entrypoints_are_wired_correctly,
    test_python_module_entrypoint_help_smoke,
]
