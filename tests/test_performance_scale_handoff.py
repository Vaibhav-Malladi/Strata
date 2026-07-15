from pathlib import Path

from strata.core.incremental_cache import (
    build_incremental_cache_key,
    decide_incremental_cache_reuse,
)
from strata.core.performance_budget import (
    default_performance_budget_profile,
    build_performance_budget_summary,
)
from strata.core.performance_diagnostics import (
    build_performance_diagnostics,
    render_performance_diagnostics_markdown,
)
from strata.core.relationship_limits import apply_relationship_limits
from strata.core.scale_fixtures import evaluate_scale_stress_scenario


DOC_PATH = Path("docs/roadmap/performance-scale-hardening.md")


def _doc() -> str:
    return DOC_PATH.read_text(encoding="utf-8")


def test_part_l_docs_mark_l1_l6_complete():
    content = _doc()

    for item in (
        "L1 Performance budget and benchmark harness - complete",
        "L2 Incremental scan/cache primitives - complete",
        "L3 Bounded relationship extraction - complete",
        "L4 Large repo stress fixtures - complete",
        "L5 Performance diagnostics/reporting - complete",
        "L6 Final scale hardening docs - complete",
    ):
        assert item in content


def test_docs_lock_part_i_token_firewall_ownership():
    content = _doc()

    assert "Part I remains the token firewall" in content
    assert "only layer deciding what enters `strata_context.md`" in content
    assert "context packs" in content
    assert "context artifacts" in content


def test_docs_state_part_l_does_not_increase_default_prompt_context_size():
    content = _doc()

    assert "must not increase default prompt/context size" in content
    assert "does not expand prompt content" in content
    assert "no prompt-size expansion" in content


def test_docs_state_real_repo_uat_is_not_part_of_l():
    content = _doc()

    assert "No real GitHub repo cloning/testing in Part L" in content
    assert "No real repo UAT in L" in content
    assert "real repo UAT remains later product validation" in content


def test_docs_handoff_workspace_intelligence_to_q():
    content = _doc()

    assert "Q owns workspace intelligence" in content
    assert "Q should use L2/L4/L5 principles for workspace-scale safety" in content


def test_docs_handoff_journey_intelligence_to_p():
    content = _doc()

    assert "P owns journey intelligence" in content
    assert "P should use bounded relationship summaries" in content
    assert "not raw unbounded graphs" in content


def test_docs_handoff_adapter_model_workflow_control_to_o():
    content = _doc()

    assert "O owns adapter/model workflow control" in content
    assert "O should respect L1/L3 budgets" in content


def test_docs_handoff_workflow_diagnostics_and_ux_to_m_n():
    content = _doc()

    assert "M owns workflow diagnostics" in content
    assert "M should consume L5 diagnostics" in content
    assert "N owns UX polish" in content
    assert "N should use L5 output for low-noise UX" in content


def test_docs_keep_go_in_scope_and_java_rust_out():
    content = _doc()

    assert "Go remains in scope because it was explicitly reintroduced" in content
    assert "Java/Rust remain out of scope for Part L" in content


def test_docs_state_no_broad_scanner_or_extractor_rewrite_in_l():
    content = _doc()

    assert "No broad scanner/extractor rewrite in L" in content
    assert "does not perform a broad scanner rewrite" in content
    assert "does not add broad CLI workflow diagnostics" in content


def test_docs_state_synthetic_count_only_scale_testing():
    content = _doc()

    assert "synthetic/count-only scale testing" in content
    assert "small generated records" in content
    assert "no real cloned repos" in content


def test_public_l_module_apis_remain_available_by_direct_import():
    assert callable(default_performance_budget_profile)
    assert callable(build_performance_budget_summary)
    assert callable(decide_incremental_cache_reuse)
    assert callable(build_incremental_cache_key)
    assert callable(apply_relationship_limits)
    assert callable(evaluate_scale_stress_scenario)
    assert callable(build_performance_diagnostics)
    assert callable(render_performance_diagnostics_markdown)


def test_guardrail_tests_do_not_require_generated_context_artifacts():
    context_artifacts = [
        Path(".aidc/context"),
        Path(".aidc/strata_context.md"),
        Path(".aidc/context_artifacts"),
    ]

    assert all(not path.exists() for path in context_artifacts)


TESTS = [
    test_part_l_docs_mark_l1_l6_complete,
    test_docs_lock_part_i_token_firewall_ownership,
    test_docs_state_part_l_does_not_increase_default_prompt_context_size,
    test_docs_state_real_repo_uat_is_not_part_of_l,
    test_docs_handoff_workspace_intelligence_to_q,
    test_docs_handoff_journey_intelligence_to_p,
    test_docs_handoff_adapter_model_workflow_control_to_o,
    test_docs_handoff_workflow_diagnostics_and_ux_to_m_n,
    test_docs_keep_go_in_scope_and_java_rust_out,
    test_docs_state_no_broad_scanner_or_extractor_rewrite_in_l,
    test_docs_state_synthetic_count_only_scale_testing,
    test_public_l_module_apis_remain_available_by_direct_import,
    test_guardrail_tests_do_not_require_generated_context_artifacts,
]
