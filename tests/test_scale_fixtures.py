import json
from pathlib import Path
from unittest.mock import patch

from strata.core.scale_fixtures import (
    BACKEND_FRAMEWORKS_FOR_SCALE,
    SCENARIO_LARGE_FULLSTACK_REPO,
    SCENARIO_MEDIUM_FRONTEND_REPO,
    SCENARIO_SMALL_PYTHON_REPO,
    SCENARIO_VERY_LARGE_ENTERPRISE_WORKSPACE,
    SCALE_FIXTURE_KIND,
    STRESS_SCENARIO_NAMES,
    build_count_only_stress_scenarios,
    build_synthetic_repo_shape,
    evaluate_named_scale_stress_scenario,
    evaluate_scale_stress_scenario,
    generate_synthetic_file_facts,
    generate_synthetic_relationships,
)


def test_synthetic_repo_shape_is_json_ready_and_deterministic():
    first = build_synthetic_repo_shape(
        "sample_scale_repo",
        file_count=100,
        ignored_file_count=10,
        languages=("python", "go"),
    )
    second = build_synthetic_repo_shape(
        "sample_scale_repo",
        file_count=100,
        ignored_file_count=10,
        languages=("python", "go"),
    )

    assert first == second
    assert first == {
        "fixture_kind": SCALE_FIXTURE_KIND,
        "repo_name": "sample_scale_repo",
        "file_count": 100,
        "source_file_count": 90,
        "ignored_file_count": 10,
        "language_counts": {"go": 45, "python": 45},
        "relationship_count": 314,
        "edge_count": 134,
        "candidate_count": 18,
        "estimated_context_tokens": 756,
    }
    assert json.loads(json.dumps(first, allow_nan=False)) == first


def test_file_fact_generation_is_deterministic_despite_repeated_calls():
    shape = build_synthetic_repo_shape(
        "facts_repo",
        file_count=20,
        languages=("python", "typescript"),
    )

    first = generate_synthetic_file_facts(shape, record_count=6, seed="same")
    second = generate_synthetic_file_facts(shape, record_count=6, seed="same")

    assert first == second
    assert first[0] == {
        "path": "src/python/file_00000.py",
        "size": 128,
        "mtime_ns": 1_700_000_000_000_000_000,
        "language": "python",
        "content_hash": first[0]["content_hash"],
    }
    assert len(first[0]["content_hash"]) == 16


def test_file_fact_generation_does_not_create_files():
    shape = build_synthetic_repo_shape(
        "no_files_repo",
        file_count=20,
        languages=("python",),
    )
    before_paths = set(Path("tests/fixtures").rglob("*"))

    facts = generate_synthetic_file_facts(shape, record_count=10)

    after_paths = set(Path("tests/fixtures").rglob("*"))
    assert before_paths == after_paths
    assert len(facts) == 10


def test_count_only_scenarios_include_small_medium_large_and_very_large_shapes():
    scenarios = build_count_only_stress_scenarios()

    assert tuple(scenarios) == STRESS_SCENARIO_NAMES
    assert SCENARIO_SMALL_PYTHON_REPO in scenarios
    assert SCENARIO_MEDIUM_FRONTEND_REPO in scenarios
    assert SCENARIO_LARGE_FULLSTACK_REPO in scenarios
    assert SCENARIO_VERY_LARGE_ENTERPRISE_WORKSPACE in scenarios
    assert scenarios[SCENARIO_SMALL_PYTHON_REPO]["file_count"] < scenarios[SCENARIO_MEDIUM_FRONTEND_REPO]["file_count"]
    assert scenarios[SCENARIO_MEDIUM_FRONTEND_REPO]["file_count"] < scenarios[SCENARIO_LARGE_FULLSTACK_REPO]["file_count"]
    assert scenarios[SCENARIO_LARGE_FULLSTACK_REPO]["file_count"] < scenarios[SCENARIO_VERY_LARGE_ENTERPRISE_WORKSPACE]["file_count"]


def test_at_least_one_scenario_includes_go_language_counts():
    scenarios = build_count_only_stress_scenarios()

    assert any(
        scenario["language_counts"].get("go", 0) > 0
        for scenario in scenarios.values()
    )


def test_synthetic_relationship_generation_is_deterministic():
    shape = build_count_only_stress_scenarios()[SCENARIO_LARGE_FULLSTACK_REPO]

    first = generate_synthetic_relationships(shape, relationship_count=20, seed="same")
    second = generate_synthetic_relationships(shape, relationship_count=20, seed="same")

    assert first == second
    assert first[0]["framework"] == "fastapi"
    assert first[0]["source_path"].endswith(".py")
    assert first[6]["framework"] == "go"
    assert first[6]["source_path"].endswith(".go")


def test_synthetic_relationships_cover_python_js_ts_and_go_backend_frameworks():
    shape = build_count_only_stress_scenarios()[SCENARIO_LARGE_FULLSTACK_REPO]
    relationships = generate_synthetic_relationships(
        shape,
        relationship_count=len(BACKEND_FRAMEWORKS_FOR_SCALE),
    )

    frameworks = {relationship["framework"] for relationship in relationships}
    source_paths = [relationship["source_path"] for relationship in relationships]

    assert frameworks == set(BACKEND_FRAMEWORKS_FOR_SCALE)
    assert any(path.endswith(".py") for path in source_paths)
    assert any(path.endswith(".ts") for path in source_paths)
    assert any(path.endswith(".go") for path in source_paths)


def test_stress_evaluation_combines_budget_cache_and_relationship_limits():
    shape = build_count_only_stress_scenarios()[SCENARIO_MEDIUM_FRONTEND_REPO]

    result = evaluate_scale_stress_scenario(
        shape,
        file_fact_limit=12,
        relationship_record_limit=20,
    )

    assert result["scenario"]["repo_name"] == SCENARIO_MEDIUM_FRONTEND_REPO
    assert "budget_status" in result["budget_summary"]
    assert len(result["cache_metadata_summary"]["cache_key"]) == 64
    assert result["cache_metadata_summary"]["file_fact_count"] == 12
    assert result["relationship_limit_summary"]["total_input_count"] == 20
    assert result["status"] in {"pass", "warn", "fail"}
    assert json.loads(json.dumps(result, allow_nan=False)) == result


def test_very_large_scenario_warns_or_fails_without_huge_fixtures():
    result = evaluate_named_scale_stress_scenario(
        SCENARIO_VERY_LARGE_ENTERPRISE_WORKSPACE,
        file_fact_limit=16,
        relationship_record_limit=260,
    )

    assert result["status"] in {"warn", "fail"}
    assert result["budget_summary"]["budget_status"] == "fail"
    assert result["cache_metadata_summary"]["file_fact_count"] == 16
    assert result["relationship_limit_summary"]["total_input_count"] == 260
    assert result["relationship_limit_summary"]["dropped_relationships_count"] > 0


def test_small_scenario_passes():
    result = evaluate_named_scale_stress_scenario(
        SCENARIO_SMALL_PYTHON_REPO,
        file_fact_limit=10,
        relationship_record_limit=20,
    )

    assert result["status"] == "pass"
    assert result["budget_summary"]["budget_status"] == "pass"
    assert result["relationship_limit_summary"]["status"] == "pass"
    assert result["warnings"] == []


def test_no_extractor_functions_are_invoked():
    shape = build_count_only_stress_scenarios()[SCENARIO_SMALL_PYTHON_REPO]

    with patch(
        "strata.core.backend_relationships.create_backend_relationship",
        side_effect=AssertionError("extractor-style helper invoked"),
    ):
        result = evaluate_scale_stress_scenario(
            shape,
            file_fact_limit=5,
            relationship_record_limit=5,
        )

    assert result["relationship_limit_summary"]["total_input_count"] == 5


def test_no_real_repo_paths_or_internet_dependencies():
    scenarios = build_count_only_stress_scenarios()
    facts = generate_synthetic_file_facts(
        scenarios[SCENARIO_LARGE_FULLSTACK_REPO],
        record_count=12,
    )
    relationships = generate_synthetic_relationships(
        scenarios[SCENARIO_LARGE_FULLSTACK_REPO],
        relationship_count=12,
    )

    all_paths = [fact["path"] for fact in facts]
    all_paths.extend(relationship["source_path"] for relationship in relationships)
    assert all(not Path(path).is_absolute() for path in all_paths)
    assert all("github.com" not in json.dumps(item) for item in [scenarios, facts, relationships])


def test_docs_say_l4_is_synthetic_count_only_and_no_real_repo_uat():
    content = Path("docs/roadmap/performance-scale-hardening.md").read_text(
        encoding="utf-8",
    )

    assert "L4 implemented" in content
    assert "synthetic count-only" in content
    assert "small generated records" in content
    assert "real cloned GitHub repo testing is not part of L4" in content
    assert "do not increase default prompt/context size" in content


TESTS = [
    test_synthetic_repo_shape_is_json_ready_and_deterministic,
    test_file_fact_generation_is_deterministic_despite_repeated_calls,
    test_file_fact_generation_does_not_create_files,
    test_count_only_scenarios_include_small_medium_large_and_very_large_shapes,
    test_at_least_one_scenario_includes_go_language_counts,
    test_synthetic_relationship_generation_is_deterministic,
    test_synthetic_relationships_cover_python_js_ts_and_go_backend_frameworks,
    test_stress_evaluation_combines_budget_cache_and_relationship_limits,
    test_very_large_scenario_warns_or_fails_without_huge_fixtures,
    test_small_scenario_passes,
    test_no_extractor_functions_are_invoked,
    test_no_real_repo_paths_or_internet_dependencies,
    test_docs_say_l4_is_synthetic_count_only_and_no_real_repo_uat,
]
