import json

from strata.core.internal_library_resolution import (
    CLASSIFICATIONS,
    SOURCE_AVAILABILITIES,
    VERSION_CONFIDENCE_AFFECTS_RANKING,
    InternalLibraryResolution,
    LibraryResolutionEvidence,
    LibraryResolutionSafety,
    LibraryVersionMetadata,
    dedupe_resolution_results,
    normalize_package_name,
    sort_resolution_results,
    validate_classification,
    validate_source_availability,
)


def _resolution(**overrides):
    values = {
        "library_name": "@company/master-library/button",
        "classification": "resolved_repo_source",
        "source_availability": "source_available",
    }
    values.update(overrides)
    return InternalLibraryResolution(**values)


def _expect_error(error_type, function, *args, contains, **kwargs):
    try:
        function(*args, **kwargs)
    except error_type as error:
        assert contains in str(error)
    else:
        raise AssertionError(f"Expected {error_type.__name__}")


def test_all_classifications_are_accepted_and_invalid_value_is_rejected():
    assert len(CLASSIFICATIONS) == 9
    for value in CLASSIFICATIONS:
        assert validate_classification(value) == value
    _expect_error(ValueError, validate_classification, "resolved_zip", contains="classification")


def test_all_source_availability_values_are_accepted_and_invalid_is_rejected():
    assert SOURCE_AVAILABILITIES == (
        "source_available",
        "declaration_only",
        "zip_reference_only",
        "metadata_only",
        "unavailable",
        "unknown",
    )
    for value in SOURCE_AVAILABILITIES:
        assert validate_source_availability(value) == value
    _expect_error(ValueError, validate_source_availability, "partial", contains="source_availability")


def test_package_names_are_normalized_without_filesystem_lookup():
    assert normalize_package_name("@angular/material/dialog") == "@angular/material"
    assert normalize_package_name("master-library/button") == "master-library"
    assert _resolution().library_name == "@company/master-library"


def test_unknown_version_and_version_metadata_are_preserved():
    assert _resolution().version.to_dict() == {
        "version": None,
        "version_source": None,
        "version_confidence": "unknown",
    }
    version = LibraryVersionMetadata("3.2.1", "package.json", "medium")
    assert _resolution(version=version).to_dict()["version"] == {
        "version": "3.2.1",
        "version_source": "package.json",
        "version_confidence": "medium",
    }


def test_evidence_and_safety_sequences_serialize_deterministically():
    result = _resolution(
        evidence=LibraryResolutionEvidence(
            import_paths=("@company/master-library/z", "@company/master-library/a"),
            declaration_paths=("types\\z.d.ts", "types/a.d.ts", "types/a.d.ts"),
        ),
        safety=LibraryResolutionSafety(
            files_inspected=2,
            bytes_read=64,
            skipped_items=("zip extraction disabled", "alias unavailable"),
            warnings=("metadata incomplete", "archive unreadable"),
        ),
    )
    payload = result.to_dict()
    assert payload["evidence"]["declaration_paths"] == ["types/a.d.ts", "types/z.d.ts"]
    assert payload["safety"]["skipped_items"] == ["alias unavailable", "zip extraction disabled"]
    assert payload["safety"]["warnings"] == ["archive unreadable", "metadata incomplete"]
    assert json.loads(json.dumps(payload, allow_nan=False)) == payload


def test_duplicate_results_are_deduped_and_sorted_deterministically():
    alpha = _resolution(
        library_name="alpha",
        evidence=LibraryResolutionEvidence(import_paths=("alpha/button",)),
    )
    alpha_other_import = _resolution(
        library_name="alpha",
        evidence=LibraryResolutionEvidence(import_paths=("alpha/dialog",)),
    )
    zeta = _resolution(library_name="zeta")
    merged = dedupe_resolution_results((zeta, alpha_other_import, alpha, zeta))
    assert tuple(item.library_name for item in merged) == ("alpha", "zeta")
    assert merged[0].evidence.import_paths == ("alpha/button", "alpha/dialog")


def test_version_confidence_does_not_affect_sorting_or_ranking():
    assert VERSION_CONFIDENCE_AFFECTS_RANKING is False
    alpha = _resolution(
        library_name="alpha", version=LibraryVersionMetadata(version_confidence="high")
    )
    zeta = _resolution(
        library_name="zeta", version=LibraryVersionMetadata(version_confidence="low")
    )
    assert tuple(item.library_name for item in sort_resolution_results((zeta, alpha))) == (
        "alpha",
        "zeta",
    )


def test_contract_helpers_do_not_access_the_filesystem():
    import os

    original_scandir = os.scandir
    os.scandir = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("scan"))
    try:
        result = _resolution(
            evidence=LibraryResolutionEvidence(import_paths=("@company/master-library",))
        )
        assert dedupe_resolution_results((result, result)) == (result,)
    finally:
        os.scandir = original_scandir


TESTS = [
    test_all_classifications_are_accepted_and_invalid_value_is_rejected,
    test_all_source_availability_values_are_accepted_and_invalid_is_rejected,
    test_package_names_are_normalized_without_filesystem_lookup,
    test_unknown_version_and_version_metadata_are_preserved,
    test_evidence_and_safety_sequences_serialize_deterministically,
    test_duplicate_results_are_deduped_and_sorted_deterministically,
    test_version_confidence_does_not_affect_sorting_or_ranking,
    test_contract_helpers_do_not_access_the_filesystem,
]
