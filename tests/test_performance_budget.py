import json
from pathlib import Path

from strata.core.performance_budget import (
    BUDGET_STATUS_FAIL,
    BUDGET_STATUS_PASS,
    BUDGET_STATUS_WARN,
    DEFAULT_PERFORMANCE_BUDGET_PROFILE,
    LARGE_REPO_FILE_COUNT,
    MAX_CANDIDATE_FILES,
    MAX_CONTEXT_TOKENS_DEFAULT,
    MAX_CONTEXT_TOKENS_STRICT,
    MAX_RELATIONSHIP_RECORDS,
    MAX_SCAN_SECONDS_SOFT,
    MAX_SUMMARY_ITEMS,
    MEDIUM_REPO_FILE_COUNT,
    PERFORMANCE_BUDGET_PROFILE_VERSION,
    REPO_SIZE_LARGE,
    REPO_SIZE_MEDIUM,
    REPO_SIZE_SMALL,
    REPO_SIZE_VERY_LARGE,
    SMALL_REPO_FILE_COUNT,
    build_performance_budget_summary,
    classify_repository_size,
    default_performance_budget_profile,
)
from strata.core.performance_fixtures import build_synthetic_fixture_counts


def test_default_budget_profile_shape_is_stable():
    assert default_performance_budget_profile() == {
        "profile_version": PERFORMANCE_BUDGET_PROFILE_VERSION,
        "profile_name": "default",
        "small_repo_file_count": SMALL_REPO_FILE_COUNT,
        "medium_repo_file_count": MEDIUM_REPO_FILE_COUNT,
        "large_repo_file_count": LARGE_REPO_FILE_COUNT,
        "max_candidate_files": MAX_CANDIDATE_FILES,
        "max_relationship_records": MAX_RELATIONSHIP_RECORDS,
        "max_summary_items": MAX_SUMMARY_ITEMS,
        "max_scan_seconds_soft": MAX_SCAN_SECONDS_SOFT,
        "max_context_tokens_default": MAX_CONTEXT_TOKENS_DEFAULT,
        "max_context_tokens_strict": MAX_CONTEXT_TOKENS_STRICT,
    }
    assert DEFAULT_PERFORMANCE_BUDGET_PROFILE.to_dict() == default_performance_budget_profile()


def test_repo_size_classification_is_deterministic():
    assert classify_repository_size(0) == REPO_SIZE_SMALL
    assert classify_repository_size(SMALL_REPO_FILE_COUNT) == REPO_SIZE_SMALL
    assert classify_repository_size(SMALL_REPO_FILE_COUNT + 1) == REPO_SIZE_MEDIUM
    assert classify_repository_size(MEDIUM_REPO_FILE_COUNT) == REPO_SIZE_MEDIUM
    assert classify_repository_size(MEDIUM_REPO_FILE_COUNT + 1) == REPO_SIZE_LARGE
    assert classify_repository_size(LARGE_REPO_FILE_COUNT) == REPO_SIZE_LARGE
    assert classify_repository_size(LARGE_REPO_FILE_COUNT + 1) == REPO_SIZE_VERY_LARGE


def test_budget_summary_pass_warn_fail_behavior():
    passing = build_performance_budget_summary(
        file_count=10,
        edge_count=9,
        candidate_count=5,
        relationship_count=20,
        estimated_context_tokens=1_000,
    )
    warning = build_performance_budget_summary(
        file_count=10,
        edge_count=9,
        candidate_count=MAX_CANDIDATE_FILES + 1,
        relationship_count=20,
        estimated_context_tokens=1_000,
    )
    failing = build_performance_budget_summary(
        file_count=10,
        edge_count=9,
        candidate_count=5,
        relationship_count=20,
        estimated_context_tokens=MAX_CONTEXT_TOKENS_DEFAULT + 1,
    )

    assert passing["budget_status"] == BUDGET_STATUS_PASS
    assert passing["warnings"] == []
    assert warning["budget_status"] == BUDGET_STATUS_WARN
    assert failing["budget_status"] == BUDGET_STATUS_FAIL


def test_budget_summary_warns_when_candidate_count_exceeds_budget():
    summary = build_performance_budget_summary(
        file_count=10,
        edge_count=9,
        candidate_count=MAX_CANDIDATE_FILES + 1,
        relationship_count=20,
        estimated_context_tokens=1_000,
    )

    assert summary["budget_status"] == BUDGET_STATUS_WARN
    assert summary["warnings"] == [
        f"candidate_count {MAX_CANDIDATE_FILES + 1} exceeds max_candidate_files {MAX_CANDIDATE_FILES}"
    ]


def test_budget_summary_warns_when_relationship_count_exceeds_budget():
    summary = build_performance_budget_summary(
        file_count=10,
        edge_count=9,
        candidate_count=5,
        relationship_count=MAX_RELATIONSHIP_RECORDS + 1,
        estimated_context_tokens=1_000,
    )

    assert summary["budget_status"] == BUDGET_STATUS_WARN
    assert summary["warnings"] == [
        "relationship_count "
        f"{MAX_RELATIONSHIP_RECORDS + 1} exceeds max_relationship_records "
        f"{MAX_RELATIONSHIP_RECORDS}"
    ]


def test_budget_summary_warns_and_fails_for_strict_and_default_context_tokens():
    strict_warning = build_performance_budget_summary(
        file_count=10,
        edge_count=9,
        candidate_count=5,
        relationship_count=20,
        estimated_context_tokens=MAX_CONTEXT_TOKENS_STRICT + 1,
    )
    default_failure = build_performance_budget_summary(
        file_count=10,
        edge_count=9,
        candidate_count=5,
        relationship_count=20,
        estimated_context_tokens=MAX_CONTEXT_TOKENS_DEFAULT + 1,
    )

    assert strict_warning["budget_status"] == BUDGET_STATUS_WARN
    assert strict_warning["warnings"] == [
        "estimated_context_tokens "
        f"{MAX_CONTEXT_TOKENS_STRICT + 1} exceeds max_context_tokens_strict "
        f"{MAX_CONTEXT_TOKENS_STRICT}"
    ]
    assert default_failure["budget_status"] == BUDGET_STATUS_FAIL
    assert default_failure["warnings"][-1] == (
        "estimated_context_tokens "
        f"{MAX_CONTEXT_TOKENS_DEFAULT + 1} exceeds max_context_tokens_default "
        f"{MAX_CONTEXT_TOKENS_DEFAULT}"
    )


def test_budget_summary_is_json_ready_and_deterministic():
    first = build_performance_budget_summary(
        file_count=101,
        edge_count=200,
        candidate_count=50,
        relationship_count=100,
        estimated_context_tokens=2_000,
    )
    second = build_performance_budget_summary(
        file_count=101,
        edge_count=200,
        candidate_count=50,
        relationship_count=100,
        estimated_context_tokens=2_000,
    )

    assert list(first) == [
        "file_count",
        "edge_count",
        "candidate_count",
        "relationship_count",
        "estimated_context_tokens",
        "repo_size_class",
        "budget_status",
        "warnings",
    ]
    assert first == second
    assert json.loads(json.dumps(first, allow_nan=False)) == first


def test_synthetic_fixture_counts_do_not_create_thousands_of_files():
    before_paths = set(Path("tests/fixtures").rglob("*"))
    counts = build_synthetic_fixture_counts(10_000)
    after_paths = set(Path("tests/fixtures").rglob("*"))

    assert before_paths == after_paths
    assert counts["fixture_kind"] == "synthetic_counts_only"
    assert counts["file_count"] == 10_000
    assert counts["language_counts"] == {
        "python": 2_500,
        "javascript": 2_500,
        "typescript": 2_500,
        "go": 2_500,
    }
    assert counts["candidate_count"] == 2_000
    assert counts["relationship_count"] > counts["file_count"]


def test_docs_mention_l1_measurement_only_and_no_real_repo_uat():
    content = Path("docs/roadmap/performance-scale-hardening.md").read_text(
        encoding="utf-8",
    )

    assert "L1 is measurement and harness only" in content
    assert "does not clone real repositories" in content
    assert "add real-repo UAT" in content
    for item in ("L1", "L2", "L3", "L4", "L5", "L6"):
        assert item in content


TESTS = [
    test_default_budget_profile_shape_is_stable,
    test_repo_size_classification_is_deterministic,
    test_budget_summary_pass_warn_fail_behavior,
    test_budget_summary_warns_when_candidate_count_exceeds_budget,
    test_budget_summary_warns_when_relationship_count_exceeds_budget,
    test_budget_summary_warns_and_fails_for_strict_and_default_context_tokens,
    test_budget_summary_is_json_ready_and_deterministic,
    test_synthetic_fixture_counts_do_not_create_thousands_of_files,
    test_docs_mention_l1_measurement_only_and_no_real_repo_uat,
]
