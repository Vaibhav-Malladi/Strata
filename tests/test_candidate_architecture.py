import ast
import sys
from pathlib import Path

from strata.core.angular_starting_files import (
    AngularStartingFile,
    select_angular_starting_files,
)
from strata.core.frontend_starting_files import (
    FrontendStartingFile,
    FrontendStartingFileSelection,
    FrontendStartingFileSummary,
    FrontendStartingFileSummaryItem,
    select_frontend_starting_files,
    summarize_frontend_starting_files,
)
from strata.core.frontend_frameworks import (
    FrontendFrameworkDetection,
    FrontendFrameworkSignal,
    detect_frontend_frameworks,
)
from strata.core.frontend_roles import (
    FRONTEND_ROLES,
    infer_frontend_role_from_path,
    is_frontend_candidate,
)
from strata.core.candidate_pipeline import (
    CandidateAnalysis,
    CandidateAnalysisSummary,
    analyze_candidates_for_task,
    summarize_candidate_analysis,
)
from strata.core.candidates import (
    CandidateSelection,
    CandidateSummary,
    CandidateValue,
    select_candidates,
    summarize_candidate_selection,
)
from strata.core.inventory import (
    InventoryRecord,
    collect_inventory,
    create_inventory_record,
    iter_inventory_records,
)
from strata.core.react_starting_files import (
    ReactStartingFile,
    select_react_starting_files,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROLES_MODULE = PROJECT_ROOT / "strata" / "core" / "frontend_roles.py"
REACT_STARTING_FILE_MODULE = (
    PROJECT_ROOT / "strata" / "core" / "react_starting_files.py"
)
ANGULAR_STARTING_FILE_MODULE = (
    PROJECT_ROOT / "strata" / "core" / "angular_starting_files.py"
)
FRONTEND_STARTING_FILE_MODULE = (
    PROJECT_ROOT / "strata" / "core" / "frontend_starting_files.py"
)
FRONTEND_FRAMEWORKS_MODULE = (
    PROJECT_ROOT / "strata" / "core" / "frontend_frameworks.py"
)
CANDIDATE_MODULES = (
    PROJECT_ROOT / "strata" / "core" / "inventory.py",
    PROJECT_ROOT / "strata" / "core" / "candidates.py",
    PROJECT_ROOT / "strata" / "core" / "candidate_pipeline.py",
    FRONTEND_ROLES_MODULE,
    REACT_STARTING_FILE_MODULE,
    ANGULAR_STARTING_FILE_MODULE,
    FRONTEND_STARTING_FILE_MODULE,
    FRONTEND_FRAMEWORKS_MODULE,
)
FORBIDDEN_IMPORTS = (
    "strata.adapter",
    "strata.adapters",
    "strata.agent_adapters",
    "strata.cache",
    "strata.cli",
    "strata.commands",
    "strata.context_pack",
    "strata.core.adapters",
    "strata.core.context_pack",
    "strata.core.cache",
    "strata.core.scanner",
    "strata.core.snapshot_cache",
    "strata.core.trace",
    "strata.core.tracing",
    "strata.parsers",
    "strata.patch",
    "strata.scanner",
    "strata.snapshot_cache",
    "strata.trace",
    "strata.tracing",
)
FORBIDDEN_ROOT_IMPORTS = {
    "adapter",
    "adapter_presets",
    "adapters",
    "agent_adapters",
    "cache",
    "cli",
    "commands",
    "context_pack",
    "parsers",
    "patch",
    "scanner",
    "snapshot_cache",
    "trace",
    "tracing",
}
REACT_STARTING_FILE_DEPENDENCIES = {
    "strata.core.candidates",
    "strata.core.frontend_roles",
    "strata.core.inventory",
}
ANGULAR_STARTING_FILE_DEPENDENCIES = {
    "strata.core.candidates",
    "strata.core.frontend_roles",
    "strata.core.inventory",
}
FRONTEND_STARTING_FILE_DEPENDENCIES = {
    "strata.core.angular_starting_files",
    "strata.core.frontend_frameworks",
    "strata.core.inventory",
    "strata.core.react_starting_files",
}
FRONTEND_FRAMEWORK_DEPENDENCIES = {"strata.core.inventory"}


def _imported_modules(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return tuple(modules)


def test_candidate_core_modules_avoid_integration_and_parser_dependencies():
    violations: list[str] = []
    for path in CANDIDATE_MODULES:
        for module in _imported_modules(path):
            root_module = module.split(".", 1)[0]
            if (
                root_module in FORBIDDEN_ROOT_IMPORTS
                or module.startswith(FORBIDDEN_IMPORTS)
            ):
                violations.append(f"{path.name} imports forbidden module {module}")

    assert not violations, "Candidate architecture violations:\n" + "\n".join(violations)


def test_candidate_foundation_public_api_imports_are_stable():
    assert InventoryRecord.__module__ == "strata.core.inventory"
    assert all(
        callable(value)
        for value in (
            create_inventory_record,
            iter_inventory_records,
            collect_inventory,
            select_candidates,
            summarize_candidate_selection,
            analyze_candidates_for_task,
            summarize_candidate_analysis,
        )
    )
    assert CandidateValue.__module__ == "strata.core.candidates"
    assert CandidateSelection.__module__ == "strata.core.candidates"
    assert CandidateSummary.__module__ == "strata.core.candidates"
    assert CandidateAnalysis.__module__ == "strata.core.candidate_pipeline"
    assert CandidateAnalysisSummary.__module__ == "strata.core.candidate_pipeline"
    assert "unknown" in FRONTEND_ROLES
    assert callable(infer_frontend_role_from_path)
    assert callable(is_frontend_candidate)
    assert ReactStartingFile.__module__ == "strata.core.react_starting_files"
    assert callable(select_react_starting_files)
    assert AngularStartingFile.__module__ == "strata.core.angular_starting_files"
    assert callable(select_angular_starting_files)
    assert FrontendStartingFile.__module__ == "strata.core.frontend_starting_files"
    assert FrontendStartingFileSelection.__module__ == (
        "strata.core.frontend_starting_files"
    )
    assert callable(select_frontend_starting_files)
    assert FrontendStartingFileSummary.__module__ == (
        "strata.core.frontend_starting_files"
    )
    assert FrontendStartingFileSummaryItem.__module__ == (
        "strata.core.frontend_starting_files"
    )
    assert callable(summarize_frontend_starting_files)
    assert FrontendFrameworkSignal.__module__ == "strata.core.frontend_frameworks"
    assert FrontendFrameworkDetection.__module__ == "strata.core.frontend_frameworks"
    assert callable(detect_frontend_frameworks)


def test_frontend_roles_use_only_standard_library_dependencies():
    violations = [
        module
        for module in _imported_modules(FRONTEND_ROLES_MODULE)
        if module.split(".", 1)[0] not in sys.stdlib_module_names
    ]

    assert not violations, "Unexpected frontend role imports: " + ", ".join(
        violations
    )


def test_react_starting_files_use_only_intentional_dependencies():
    violations = [
        module
        for module in _imported_modules(REACT_STARTING_FILE_MODULE)
        if module not in REACT_STARTING_FILE_DEPENDENCIES
        and module.split(".", 1)[0] not in sys.stdlib_module_names
    ]

    assert not violations, "Unexpected React starting-file imports: " + ", ".join(
        violations
    )


def test_angular_starting_files_use_only_intentional_dependencies():
    violations = [
        module
        for module in _imported_modules(ANGULAR_STARTING_FILE_MODULE)
        if module not in ANGULAR_STARTING_FILE_DEPENDENCIES
        and module.split(".", 1)[0] not in sys.stdlib_module_names
    ]

    assert not violations, "Unexpected Angular starting-file imports: " + ", ".join(
        violations
    )


def test_frontend_starting_files_use_only_intentional_dependencies():
    violations = [
        module
        for module in _imported_modules(FRONTEND_STARTING_FILE_MODULE)
        if module not in FRONTEND_STARTING_FILE_DEPENDENCIES
        and module.split(".", 1)[0] not in sys.stdlib_module_names
    ]

    assert not violations, "Unexpected frontend starting-file imports: " + ", ".join(
        violations
    )


def test_frontend_frameworks_use_only_intentional_dependencies():
    violations = [
        module
        for module in _imported_modules(FRONTEND_FRAMEWORKS_MODULE)
        if module not in FRONTEND_FRAMEWORK_DEPENDENCIES
        and module.split(".", 1)[0] not in sys.stdlib_module_names
    ]

    assert not violations, "Unexpected frontend framework imports: " + ", ".join(
        violations
    )


TESTS = [
    test_candidate_core_modules_avoid_integration_and_parser_dependencies,
    test_candidate_foundation_public_api_imports_are_stable,
    test_frontend_roles_use_only_standard_library_dependencies,
    test_react_starting_files_use_only_intentional_dependencies,
    test_angular_starting_files_use_only_intentional_dependencies,
    test_frontend_starting_files_use_only_intentional_dependencies,
    test_frontend_frameworks_use_only_intentional_dependencies,
]
