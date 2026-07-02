import ast
import sys
from pathlib import Path

from strata.core.angular_starting_files import (
    AngularStartingFile,
    select_angular_starting_files,
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
ANGULAR_STARTING_FILE_MODULE = (
    PROJECT_ROOT / "strata" / "core" / "angular_starting_files.py"
)
CANDIDATE_MODULES = (
    PROJECT_ROOT / "strata" / "core" / "inventory.py",
    PROJECT_ROOT / "strata" / "core" / "candidates.py",
    PROJECT_ROOT / "strata" / "core" / "candidate_pipeline.py",
    PROJECT_ROOT / "strata" / "core" / "react_starting_files.py",
    ANGULAR_STARTING_FILE_MODULE,
)
FORBIDDEN_IMPORTS = (
    "strata.adapters",
    "strata.cli",
    "strata.commands",
    "strata.core.context_pack",
    "strata.core.scanner",
    "strata.parsers",
    "strata.patch",
)
FORBIDDEN_ROOT_IMPORTS = {
    "adapters",
    "cli",
    "commands",
    "context_pack",
    "parsers",
    "patch",
    "scanner",
}
ANGULAR_STARTING_FILE_DEPENDENCIES = {
    "strata.core.candidates",
    "strata.core.frontend_roles",
    "strata.core.inventory",
}


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
    assert ReactStartingFile.__module__ == "strata.core.react_starting_files"
    assert callable(select_react_starting_files)
    assert AngularStartingFile.__module__ == "strata.core.angular_starting_files"
    assert callable(select_angular_starting_files)


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


TESTS = [
    test_candidate_core_modules_avoid_integration_and_parser_dependencies,
    test_candidate_foundation_public_api_imports_are_stable,
    test_angular_starting_files_use_only_intentional_dependencies,
]
