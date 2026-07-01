from pathlib import Path
from unittest.mock import patch

from strata.core.candidates import (
    normalize_task_tokens,
    rank_candidates,
    score_candidate,
)
from strata.core.inventory import InventoryRecord


def _record(
    path: str,
    *,
    folder_role: str = "source",
    language: str | None = "typescript",
    extension: str = ".ts",
    is_test: bool = False,
    is_generated: bool = False,
) -> InventoryRecord:
    return InventoryRecord(
        path=path,
        extension=extension,
        size=100,
        mtime=1_700_000_000,
        is_test=is_test,
        is_generated_guess=is_generated,
        folder_role=folder_role,
        language_guess=language,
    )


def test_filename_keyword_match_ranks_above_unrelated_file():
    auth_service = _record("src/services/auth_service.ts")
    unrelated = _record("src/utils/format_date.ts")

    ranked = rank_candidates([unrelated, auth_service], "fix auth service bug")

    assert ranked[0].path == auth_service.path
    assert ranked[0].score > ranked[1].score
    assert any("filename matches task keyword 'auth'" in reason for reason in ranked[0].reasons)


def test_folder_segment_match_contributes_an_explainable_reason():
    result = score_candidate(
        _record("features/checkout/client.ts", folder_role="other"),
        "checkout flow",
    )

    assert result.score > 0
    assert "folder matches task keyword 'checkout' (+3)" in result.reasons


def test_generated_vendor_build_and_minified_records_are_strongly_demoted():
    source = _record("src/auth/client.js", language="javascript", extension=".js")
    cheap_matches = [
        _record(
            "dist/auth/client.js",
            folder_role="generated",
            language="javascript",
            extension=".js",
            is_generated=True,
        ),
        _record(
            "vendor/auth/client.js",
            folder_role="vendor",
            language="javascript",
            extension=".js",
            is_generated=True,
        ),
        _record(
            "build/auth/client.js",
            folder_role="generated",
            language="javascript",
            extension=".js",
            is_generated=True,
        ),
        _record(
            "src/auth/client.min.js",
            language="javascript",
            extension=".js",
            is_generated=True,
        ),
    ]

    source_score = score_candidate(source, "auth client").score
    for record in cheap_matches:
        result = score_candidate(record, "auth client")
        assert result.score < source_score
        assert any("generated or vendor path" in reason for reason in result.reasons)


def test_test_files_are_demoted_for_implementation_tasks():
    implementation = _record("src/checkout.ts")
    test_file = _record(
        "tests/checkout.spec.ts",
        folder_role="test",
        is_test=True,
    )

    ranked = rank_candidates([test_file, implementation], "change checkout flow")

    assert ranked[0].path == implementation.path
    test_result = next(item for item in ranked if item.path == test_file.path)
    assert "test file for implementation task (-12)" in test_result.reasons


def test_test_files_are_boosted_when_task_asks_for_tests():
    implementation = _record("src/checkout.ts")
    test_file = _record(
        "tests/checkout.spec.ts",
        folder_role="test",
        is_test=True,
    )

    ranked = rank_candidates([implementation, test_file], "add tests for checkout")

    assert ranked[0].path == test_file.path
    assert "task asks for tests (+8)" in ranked[0].reasons
    assert "test file for implementation task (-12)" not in ranked[0].reasons


def test_language_and_extension_relevance_are_transparent():
    result = score_candidate(
        _record("src/component.tsx", extension=".tsx"),
        "update typescript tsx component",
    )

    assert "language 'typescript' matches task (+2)" in result.reasons
    assert "extension '.tsx' matches task (+2)" in result.reasons


def test_scoring_does_not_stat_or_open_inventory_paths():
    record = _record("missing/auth_service.ts")

    with (
        patch.object(Path, "open", side_effect=AssertionError("opened candidate")),
        patch.object(Path, "stat", side_effect=AssertionError("statted candidate")),
    ):
        result = score_candidate(record, "auth service")

    assert result.path == record.path
    assert result.score > 0


def test_task_normalization_removes_stopwords_and_duplicates():
    assert normalize_task_tokens("Fix the Auth auth service bug") == ("auth", "service")


TESTS = [
    test_filename_keyword_match_ranks_above_unrelated_file,
    test_folder_segment_match_contributes_an_explainable_reason,
    test_generated_vendor_build_and_minified_records_are_strongly_demoted,
    test_test_files_are_demoted_for_implementation_tasks,
    test_test_files_are_boosted_when_task_asks_for_tests,
    test_language_and_extension_relevance_are_transparent,
    test_scoring_does_not_stat_or_open_inventory_paths,
    test_task_normalization_removes_stopwords_and_duplicates,
]
