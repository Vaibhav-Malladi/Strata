import json
import tempfile
from pathlib import Path

from strata.core.candidate_evaluation import (
    CandidateEvaluationManifestError,
    ExpectedFileTier,
    load_candidate_evaluation_manifest,
    validate_candidate_evaluation_manifest,
)


def _valid_manifest() -> dict:
    return {
        "schema_version": 1,
        "tasks": [
            {
                "id": "react-auth-form",
                "task": "Fix validation in the sign-in form",
                "fixture_path": "fixtures/react-auth",
                "tags": {
                    "stacks": ["frontend"],
                    "languages": ["typescript"],
                    "frameworks": ["react"],
                },
                "expected_files": {
                    "critical": [
                        {
                            "path": "src/components/SignInForm.tsx",
                            "note": "Owns the validation behavior.",
                        }
                    ],
                    "useful": [{"path": "src/lib/validation.ts"}],
                    "distractor": [{"path": "src/components/ProfileForm.tsx"}],
                    "irrelevant": [],
                },
            }
        ],
    }


def _expect_manifest_error(payload: object, contains: str) -> None:
    try:
        validate_candidate_evaluation_manifest(payload)
    except CandidateEvaluationManifestError as error:
        assert contains in str(error)
    else:
        raise AssertionError("Expected CandidateEvaluationManifestError")


def test_valid_candidate_evaluation_manifest_loads_successfully():
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "manifest.json"
        path.write_text(json.dumps(_valid_manifest()), encoding="utf-8")

        manifest = load_candidate_evaluation_manifest(path)

    assert manifest.schema_version == 1
    assert len(manifest.tasks) == 1
    task = manifest.tasks[0]
    assert task.task_id == "react-auth-form"
    assert task.task_text == "Fix validation in the sign-in form"
    assert task.fixture_path == "fixtures/react-auth"
    assert task.tags.frameworks == ("react",)
    assert task.expected_files.for_tier(ExpectedFileTier.CRITICAL)[0].note == (
        "Owns the validation behavior."
    )


def test_required_manifest_and_task_fields_are_enforced():
    payload = _valid_manifest()
    del payload["schema_version"]
    _expect_manifest_error(payload, "manifest: missing required field(s): schema_version")

    payload = _valid_manifest()
    del payload["tasks"][0]["task"]
    _expect_manifest_error(payload, "manifest.tasks[0]: missing required field(s): task")


def test_missing_and_invalid_expected_file_tiers_are_rejected():
    payload = _valid_manifest()
    del payload["tasks"][0]["expected_files"]["distractor"]
    _expect_manifest_error(payload, "missing required field(s): distractor")

    payload = _valid_manifest()
    payload["tasks"][0]["expected_files"]["important"] = []
    _expect_manifest_error(payload, "unexpected field(s): important")


def test_malformed_expected_file_entries_are_rejected():
    malformed_entries = (
        "src/components/SignInForm.tsx",
        {},
        {"path": 7},
        {"path": "src/form.tsx", "note": ""},
        {"path": "src/form.tsx", "note": None},
        {"path": "src/form.tsx", "reason": "critical"},
    )
    for entry in malformed_entries:
        payload = _valid_manifest()
        payload["tasks"][0]["expected_files"]["critical"] = [entry]
        _expect_manifest_error(payload, "manifest.tasks[0].expected_files.critical[0]")


def test_duplicate_expected_files_across_tiers_are_rejected():
    payload = _valid_manifest()
    payload["tasks"][0]["expected_files"]["irrelevant"] = [
        {"path": "src/lib/validation.ts"}
    ]

    _expect_manifest_error(payload, "already listed in useful")


def test_all_expected_file_tiers_may_be_empty():
    payload = _valid_manifest()
    expected_files = payload["tasks"][0]["expected_files"]
    for tier in expected_files:
        expected_files[tier] = []

    manifest = validate_candidate_evaluation_manifest(payload)

    task = manifest.tasks[0]
    assert task.expected_files.critical == ()
    assert task.expected_files.useful == ()
    assert task.expected_files.distractor == ()
    assert task.expected_files.irrelevant == ()


def test_fixture_and_expected_file_paths_must_be_safe_relative_paths():
    unsafe_paths = (
        "../outside.py",
        "src/../../outside.py",
        "/absolute.py",
        "C:/absolute.py",
        "src\\windows.py",
        "src//not-normalized.py",
    )
    for unsafe_path in unsafe_paths:
        payload = _valid_manifest()
        payload["tasks"][0]["expected_files"]["critical"] = [
            {"path": unsafe_path}
        ]
        _expect_manifest_error(payload, ".expected_files.critical[0].path")

    payload = _valid_manifest()
    payload["tasks"][0]["fixture_path"] = "../fixtures/react-auth"
    _expect_manifest_error(payload, "manifest.tasks[0].fixture_path")

    payload = _valid_manifest()
    payload["tasks"][0]["fixture_path"] = "."
    manifest = validate_candidate_evaluation_manifest(payload)
    assert manifest.tasks[0].fixture_path == "."


def test_duplicate_task_ids_are_rejected():
    payload = _valid_manifest()
    payload["tasks"].append(dict(payload["tasks"][0]))

    _expect_manifest_error(payload, "duplicate task id 'react-auth-form'")


TESTS = [
    test_valid_candidate_evaluation_manifest_loads_successfully,
    test_required_manifest_and_task_fields_are_enforced,
    test_missing_and_invalid_expected_file_tiers_are_rejected,
    test_malformed_expected_file_entries_are_rejected,
    test_duplicate_expected_files_across_tiers_are_rejected,
    test_all_expected_file_tiers_may_be_empty,
    test_fixture_and_expected_file_paths_must_be_safe_relative_paths,
    test_duplicate_task_ids_are_rejected,
]
