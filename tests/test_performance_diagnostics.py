import json

from strata.core.incremental_cache import decide_incremental_cache_reuse
from strata.core.performance_budget import (
    MAX_CANDIDATE_FILES,
    MAX_CONTEXT_TOKENS_DEFAULT,
    build_performance_budget_summary,
)
from strata.core.performance_diagnostics import (
    DIAGNOSTIC_CATEGORY_CACHE_REUSE,
    DIAGNOSTIC_CATEGORY_CACHE_STALENESS,
    DIAGNOSTIC_CATEGORY_CANDIDATE_PRESSURE,
    DIAGNOSTIC_CATEGORY_CONTEXT_BUDGET,
    DIAGNOSTIC_CATEGORY_RELATIONSHIP_PRESSURE,
    DIAGNOSTIC_CATEGORY_SYNTHETIC_STRESS,
    DIAGNOSTIC_SEVERITY_FAIL,
    DIAGNOSTIC_SEVERITY_INFO,
    DIAGNOSTIC_SEVERITY_WARN,
    build_performance_diagnostics,
    create_performance_diagnostic,
    render_performance_diagnostics_markdown,
)
from strata.core.relationship_limits import (
    RelationshipLimitProfile,
    apply_relationship_limits,
)
from strata.core.scale_fixtures import (
    SCENARIO_SMALL_PYTHON_REPO,
    SCENARIO_VERY_LARGE_ENTERPRISE_WORKSPACE,
    evaluate_named_scale_stress_scenario,
)


def _relationship(source_path: str) -> dict:
    return {
        "framework": "fastapi",
        "relationship_type": "route_handler",
        "source_path": source_path,
        "target_path": "app/service.py",
        "route_path": "/items",
        "http_method": "GET",
    }


def _cache_hit() -> dict:
    return {
        "reuse": True,
        "status": "hit",
        "reasons": [],
        "warnings": [],
        "changed_counts": {},
    }


def test_diagnostic_record_is_json_ready_and_deterministic():
    diagnostic = create_performance_diagnostic(
        severity=DIAGNOSTIC_SEVERITY_WARN,
        category=DIAGNOSTIC_CATEGORY_CONTEXT_BUDGET,
        code="strict_context_budget_pressure",
        message="Estimated context tokens exceed the strict budget.",
        evidence=[{"estimated_context_tokens": 4500}],
        next_action="Keep context compact.",
    )

    assert diagnostic == {
        "severity": "warn",
        "category": "context_budget",
        "code": "strict_context_budget_pressure",
        "message": "Estimated context tokens exceed the strict budget.",
        "evidence": [{"estimated_context_tokens": 4500}],
        "next_action": "Keep context compact.",
    }
    assert json.loads(json.dumps(diagnostic, allow_nan=False)) == diagnostic


def test_budget_fail_creates_fail_context_budget_diagnostic():
    budget = build_performance_budget_summary(
        file_count=10,
        edge_count=9,
        candidate_count=5,
        relationship_count=20,
        estimated_context_tokens=MAX_CONTEXT_TOKENS_DEFAULT + 1,
    )

    summary = build_performance_diagnostics(budget_summary=budget)

    diagnostic = summary["diagnostics"][0]
    assert summary["status"] == "fail"
    assert diagnostic["severity"] == DIAGNOSTIC_SEVERITY_FAIL
    assert diagnostic["category"] == DIAGNOSTIC_CATEGORY_CONTEXT_BUDGET
    assert diagnostic["code"] == "context_token_budget_exceeded"


def test_candidate_overage_creates_candidate_pressure_warning():
    budget = build_performance_budget_summary(
        file_count=10,
        edge_count=9,
        candidate_count=MAX_CANDIDATE_FILES + 1,
        relationship_count=20,
        estimated_context_tokens=1000,
    )

    summary = build_performance_diagnostics(budget_summary=budget)

    assert summary["status"] == "warn"
    assert summary["diagnostics"][0]["severity"] == DIAGNOSTIC_SEVERITY_WARN
    assert summary["diagnostics"][0]["category"] == DIAGNOSTIC_CATEGORY_CANDIDATE_PRESSURE


def test_relationship_drops_create_relationship_pressure_warning():
    relationship_summary = apply_relationship_limits(
        [_relationship("b.py"), _relationship("a.py")],
        profile=RelationshipLimitProfile(
            max_total_relationships=1,
            max_summary_payload_relationships=10,
        ),
    )

    summary = build_performance_diagnostics(
        relationship_limit_summary=relationship_summary,
    )

    assert summary["status"] == "warn"
    assert summary["diagnostics"][0]["category"] == DIAGNOSTIC_CATEGORY_RELATIONSHIP_PRESSURE
    assert summary["diagnostics"][0]["code"] == "relationship_records_dropped"


def test_cache_hit_creates_cache_reuse_info_diagnostic():
    summary = build_performance_diagnostics(cache_decision=_cache_hit())

    assert summary["status"] == "pass"
    assert summary["diagnostics"][0]["severity"] == DIAGNOSTIC_SEVERITY_INFO
    assert summary["diagnostics"][0]["category"] == DIAGNOSTIC_CATEGORY_CACHE_REUSE


def test_cache_stale_or_invalid_creates_cache_staleness_warning():
    stale = {
        "reuse": False,
        "status": "stale",
        "reasons": ["input_fingerprint_changed"],
        "warnings": [],
        "changed_counts": {},
    }
    invalid = {
        "reuse": False,
        "status": "invalid",
        "reasons": ["malformed_cache_metadata"],
        "warnings": ["bad metadata"],
        "changed_counts": {},
    }

    stale_summary = build_performance_diagnostics(cache_decision=stale)
    invalid_summary = build_performance_diagnostics(cache_decision=invalid)

    assert stale_summary["diagnostics"][0]["category"] == DIAGNOSTIC_CATEGORY_CACHE_STALENESS
    assert invalid_summary["diagnostics"][0]["category"] == DIAGNOSTIC_CATEGORY_CACHE_STALENESS
    assert stale_summary["status"] == "warn"
    assert invalid_summary["status"] == "warn"


def test_stress_warn_or_fail_creates_synthetic_stress_diagnostic():
    stress = evaluate_named_scale_stress_scenario(
        SCENARIO_VERY_LARGE_ENTERPRISE_WORKSPACE,
        file_fact_limit=8,
        relationship_record_limit=260,
    )

    summary = build_performance_diagnostics(stress_evaluation=stress)

    assert summary["status"] == "fail"
    assert summary["diagnostics"][0]["category"] == DIAGNOSTIC_CATEGORY_SYNTHETIC_STRESS
    assert summary["diagnostics"][0]["severity"] == DIAGNOSTIC_SEVERITY_FAIL


def test_summary_status_escalates_pass_warn_fail_deterministically():
    passing = build_performance_diagnostics(cache_decision=_cache_hit())
    warning = build_performance_diagnostics(
        cache_decision={
            "reuse": False,
            "status": "miss",
            "reasons": ["missing_cache"],
            "warnings": [],
            "changed_counts": {},
        }
    )
    failing = build_performance_diagnostics(
        budget_summary=build_performance_budget_summary(
            file_count=10,
            edge_count=9,
            candidate_count=5,
            relationship_count=20,
            estimated_context_tokens=MAX_CONTEXT_TOKENS_DEFAULT + 1,
        )
    )

    assert passing["status"] == "pass"
    assert warning["status"] == "warn"
    assert failing["status"] == "fail"


def test_diagnostics_and_evidence_are_truncated_by_caps():
    budget = build_performance_budget_summary(
        file_count=10,
        edge_count=9,
        candidate_count=MAX_CANDIDATE_FILES + 1,
        relationship_count=20,
        estimated_context_tokens=MAX_CONTEXT_TOKENS_DEFAULT + 1,
    )
    relationship_summary = apply_relationship_limits(
        [_relationship("a.py"), _relationship("b.py")],
        profile=RelationshipLimitProfile(
            max_total_relationships=1,
            max_summary_payload_relationships=10,
        ),
    )

    summary = build_performance_diagnostics(
        budget_summary=budget,
        cache_decision={
            "reuse": False,
            "status": "stale",
            "reasons": ["one", "two", "three"],
            "warnings": [],
            "changed_counts": {},
        },
        relationship_limit_summary=relationship_summary,
        stress_evaluation=evaluate_named_scale_stress_scenario(
            SCENARIO_VERY_LARGE_ENTERPRISE_WORKSPACE,
            file_fact_limit=4,
            relationship_record_limit=5,
        ),
        max_diagnostics=2,
        max_top_risks=1,
        max_next_actions=1,
        max_evidence_items=1,
    )

    assert summary["truncated"] is True
    assert len(summary["diagnostics"]) == 2
    assert len(summary["top_risks"]) == 1
    assert len(summary["next_actions"]) == 1
    assert all(len(diagnostic["evidence"]) <= 1 for diagnostic in summary["diagnostics"])


def test_markdown_renderer_is_deterministic_and_concise():
    summary = build_performance_diagnostics(
        budget_summary=build_performance_budget_summary(
            file_count=10,
            edge_count=9,
            candidate_count=MAX_CANDIDATE_FILES + 1,
            relationship_count=20,
            estimated_context_tokens=1000,
        ),
        cache_decision=_cache_hit(),
    )

    first = render_performance_diagnostics_markdown(summary)
    second = render_performance_diagnostics_markdown(summary)

    assert first == second
    assert first.startswith("# Strata Performance Diagnostics")
    assert "## Top Risks" in first
    assert len(first.splitlines()) < 60


def test_markdown_does_not_dump_raw_huge_payloads():
    huge_payload = {"status": "warn", "scenario": {"repo_name": "huge", "file_count": 1}, "warnings": ["x" * 1000]}
    summary = build_performance_diagnostics(stress_evaluation=huge_payload)
    markdown = render_performance_diagnostics_markdown(summary)

    assert "x" * 200 not in markdown
    assert "source_summaries" not in markdown


def test_empty_inputs_produce_no_risk_summary_deterministically():
    summary = build_performance_diagnostics()

    assert summary["status"] == "pass"
    assert summary["diagnostics"][0]["code"] == "no_scale_risks"
    assert summary["top_risks"] == ["No warn/fail scale risks reported."]


def test_output_is_json_ready():
    summary = build_performance_diagnostics(
        stress_evaluation=evaluate_named_scale_stress_scenario(
            SCENARIO_SMALL_PYTHON_REPO,
            file_fact_limit=4,
            relationship_record_limit=4,
        ),
    )

    assert json.loads(json.dumps(summary, allow_nan=False)) == summary


def test_cache_decision_from_l2_helper_is_supported():
    decision = decide_incremental_cache_reuse(
        None,
        {
            "schema_version": 1,
            "cache_version": "incremental-cache-v1",
            "root_fingerprint": "root",
            "scan_options_fingerprint": "options",
            "file_count": 0,
            "source_file_count": 0,
            "ignored_file_count": 0,
            "created_at": 1,
            "strata_version": None,
            "language_counts": {},
            "input_fingerprints": {
                "schema_version": 1,
                "record_count": 0,
                "digest": "digest",
                "records": [],
            },
        },
    )

    summary = build_performance_diagnostics(cache_decision=decision)

    assert summary["status"] == "warn"
    assert summary["diagnostics"][0]["category"] == DIAGNOSTIC_CATEGORY_CACHE_STALENESS


def test_docs_say_l5_is_reporting_only_and_m_n_own_commands():
    with open("docs/roadmap/performance-scale-hardening.md", encoding="utf-8") as handle:
        content = handle.read()

    assert "L5 implemented" in content
    assert "concise reports" in content
    assert "does not add broad CLI workflow diagnostics" in content
    assert "M owns workflow diagnostics" in content
    assert "N owns UX polish" in content
    assert "no prompt-size expansion" in content


TESTS = [
    test_diagnostic_record_is_json_ready_and_deterministic,
    test_budget_fail_creates_fail_context_budget_diagnostic,
    test_candidate_overage_creates_candidate_pressure_warning,
    test_relationship_drops_create_relationship_pressure_warning,
    test_cache_hit_creates_cache_reuse_info_diagnostic,
    test_cache_stale_or_invalid_creates_cache_staleness_warning,
    test_stress_warn_or_fail_creates_synthetic_stress_diagnostic,
    test_summary_status_escalates_pass_warn_fail_deterministically,
    test_diagnostics_and_evidence_are_truncated_by_caps,
    test_markdown_renderer_is_deterministic_and_concise,
    test_markdown_does_not_dump_raw_huge_payloads,
    test_empty_inputs_produce_no_risk_summary_deterministically,
    test_output_is_json_ready,
    test_cache_decision_from_l2_helper_is_supported,
    test_docs_say_l5_is_reporting_only_and_m_n_own_commands,
]
