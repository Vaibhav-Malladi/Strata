import ast
from pathlib import Path

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


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_MODULES = (
    PROJECT_ROOT / "strata" / "core" / "inventory.py",
    PROJECT_ROOT / "strata" / "core" / "candidates.py",
    PROJECT_ROOT / "strata" / "core" / "candidate_pipeline.py",
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


TESTS = [
    test_candidate_core_modules_avoid_integration_and_parser_dependencies,
    test_candidate_foundation_public_api_imports_are_stable,
]
