from pathlib import Path

from strata.core.candidate_evaluation import EXPECTED_FILE_TIERS, SCHEMA_VERSION
from strata.core.content_probe import DEFAULT_CONTENT_PROBE_CAPS
from strata.core.probe_evaluation import STRATEGIES
from strata.core.probe_pool import (
    DEFAULT_MAX_OBVIOUS,
    DEFAULT_MAX_PER_DIRECTORY,
    DEFAULT_MAX_RESCUE,
    DEFAULT_MAX_TOTAL,
)
from strata.core.probe_scoring import (
    CONFIDENCE_LEVELS as PROBE_CONFIDENCE_LEVELS,
    DEFAULT_PROBE_SCORE_WEIGHTS,
)
from strata.core.stage_report import CONFIDENCE_LEVELS


DOC_PATH = Path(__file__).parents[1] / "docs" / "roadmap" / "candidate-evaluation-quality.md"


def _document() -> str:
    return DOC_PATH.read_text(encoding="utf-8")


def test_final_policy_names_every_part_g_contract_module():
    document = _document()
    modules = (
        "strata.core.candidate_evaluation",
        "strata.core.stage_report",
        "strata.core.candidate_metrics",
        "strata.core.candidate_baseline",
        "strata.core.probe_pool",
        "strata.core.probe_scoring",
        "strata.core.content_probe",
        "strata.core.probe_evaluation",
    )

    assert all(module in document for module in modules)


def test_manifest_tiers_and_comparison_strategies_remain_locked():
    assert SCHEMA_VERSION == 1
    assert EXPECTED_FILE_TIERS == (
        "critical",
        "useful",
        "distractor",
        "irrelevant",
    )
    assert STRATEGIES == ("baseline", "mixed_pool", "mixed_pool_probe")


def test_default_probe_score_weights_match_final_policy():
    weights = DEFAULT_PROBE_SCORE_WEIGHTS

    assert weights.cheap_weight == 0.35
    assert weights.probe_weight == 0.30
    assert weights.structural_weight == 0.20
    assert weights.cost_weight == 0.15
    assert sum(weights.to_dict().values()) == 1.0


def test_stage_and_probe_confidence_contracts_are_identical():
    assert CONFIDENCE_LEVELS == ("unknown", "low", "medium", "high")
    assert PROBE_CONFIDENCE_LEVELS is CONFIDENCE_LEVELS


def test_pool_and_content_probe_defaults_match_final_policy():
    assert (
        DEFAULT_MAX_TOTAL,
        DEFAULT_MAX_OBVIOUS,
        DEFAULT_MAX_RESCUE,
        DEFAULT_MAX_PER_DIRECTORY,
    ) == (40, 20, 20, 5)
    assert DEFAULT_CONTENT_PROBE_CAPS.to_dict() == {
        "max_files": 20,
        "max_bytes_per_file": 4 * 1024,
        "max_total_bytes": 32 * 1024,
        "max_file_size": 256 * 1024,
    }


def test_final_policy_documents_caps_and_confidence_metadata_rule():
    document = _document()

    assert "20 open attempts" in document
    assert "4 KiB per file" in document
    assert "32 KiB total" in document
    assert "256 KiB maximum eligible file size" in document
    assert "Confidence is" in document
    assert "metadata only" in document
    assert "not an additive score" in document


def test_real_repository_validation_is_explicitly_deferred():
    document = _document()

    assert "Real GitHub repository benchmarking is not part of Part G" in document
    assert "after Parts M and N" in document
    assert "after Part P" in document
    assert all(part in document for part in ("Part H", "Part I", "Part J", "Part K"))


TESTS = [
    test_final_policy_names_every_part_g_contract_module,
    test_manifest_tiers_and_comparison_strategies_remain_locked,
    test_default_probe_score_weights_match_final_policy,
    test_stage_and_probe_confidence_contracts_are_identical,
    test_pool_and_content_probe_defaults_match_final_policy,
    test_final_policy_documents_caps_and_confidence_metadata_rule,
    test_real_repository_validation_is_explicitly_deferred,
]
