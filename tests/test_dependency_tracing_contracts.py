from pathlib import Path

from strata.core.dependency_priority import (
    DEFAULT_MAX_DEPTH,
    DEFAULT_MAX_EDGES,
    DEFAULT_MAX_ESTIMATED_COST,
    DEFAULT_MAX_FILES,
)
from strata.core.dependency_trace_runner import DEFAULT_MAX_SEED_FILES
from strata.core.dependency_tracing import PRIORITIES


DOC_PATH = Path(__file__).parents[1] / "docs/roadmap/priority-dependency-tracing.md"


def _document() -> str:
    return DOC_PATH.read_text(encoding="utf-8")


def test_final_policy_names_every_part_h_public_module():
    document = _document()
    modules = (
        "strata.core.dependency_tracing",
        "strata.core.python_dependency_edges",
        "strata.core.js_ts_dependency_edges",
        "strata.core.dependency_trace_runner",
        "strata.core.dependency_traversal",
        "strata.core.dependency_priority",
        "strata.core.dependency_trace_evaluation",
    )

    assert all(module in document for module in modules)


def test_documented_priority_and_caps_match_runtime_policy():
    document = _document()

    assert PRIORITIES == ("critical", "high", "medium", "low")
    assert "critical > high > medium > low" in document
    assert DEFAULT_MAX_SEED_FILES == 20
    assert "default maximum\nis `20` seed files" in document
    assert (DEFAULT_MAX_DEPTH, DEFAULT_MAX_FILES, DEFAULT_MAX_EDGES) == (2, 40, 100)
    assert DEFAULT_MAX_ESTIMATED_COST == 100.0
    for value in ("maximum depth: `2`", "maximum visited files: `40`", "maximum edges: `100`", "maximum estimated cost: `100.0`"):
        assert value in document


def test_js_ts_resolution_and_confidence_boundaries_are_locked():
    document = _document()

    assert "Resolution is relative-only" in document
    assert "no `node_modules` traversal" in document
    assert "no installed-package or bare\npackage resolution" in document
    assert "Confidence is metadata only" in document
    assert "not an additive score" in document


def test_evaluation_rule_and_stage_measurement_are_documented():
    document = _document()

    assert "The conclusion rule requires" in document
    assert "rather than forcing a positive\nresult" in document
    assert "strata.core.stage_report.StageReport" in document
    assert "bytes read, and files touched" in document


def test_part_i_handoff_and_deferred_boundaries_are_explicit():
    document = _document()

    assert "## Part I Handoff" in document
    assert "DependencyTraversalReport.to_dict()" in document
    assert "visited_files" in document and "file_depths" in document
    assert "There is no CLI/product wiring yet" in document
    assert "no candidate behavior changes" in document
    assert "Real\nGitHub repository benchmarking is not part of Part H" in document


TESTS = [
    test_final_policy_names_every_part_h_public_module,
    test_documented_priority_and_caps_match_runtime_policy,
    test_js_ts_resolution_and_confidence_boundaries_are_locked,
    test_evaluation_rule_and_stage_measurement_are_documented,
    test_part_i_handoff_and_deferred_boundaries_are_explicit,
]
