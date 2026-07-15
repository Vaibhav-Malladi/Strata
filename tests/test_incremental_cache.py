import json

from strata.core.incremental_cache import (
    CACHE_STATUS_HIT,
    CACHE_STATUS_INVALID,
    CACHE_STATUS_STALE,
    INCREMENTAL_CACHE_SCHEMA_VERSION,
    INVALIDATION_CACHE_TOO_OLD,
    INVALIDATION_FILE_COUNT_CHANGED,
    INVALIDATION_INPUT_FINGERPRINT_CHANGED,
    INVALIDATION_MALFORMED_CACHE_METADATA,
    INVALIDATION_ROOT_CHANGED,
    INVALIDATION_SCHEMA_MISMATCH,
    INVALIDATION_SCAN_OPTIONS_CHANGED,
    build_incremental_cache_key,
    build_incremental_cache_metadata,
    decide_incremental_cache_reuse,
    fingerprint_scan_inputs,
    is_cache_metadata_expired,
    summarize_incremental_cache_diagnostics,
)


def _records():
    return [
        {
            "path": "src/app.py",
            "size": 100,
            "mtime_ns": 1_000,
            "language": "python",
        },
        {
            "path": "web/app.ts",
            "size": 200,
            "mtime_ns": 2_000,
            "content_hash": "abc123",
            "language": "typescript",
        },
        {
            "path": "cmd/server.go",
            "size": 300,
            "modified_at": "2026-07-15T12:00:00+00:00",
            "language": "go",
        },
    ]


def _metadata(**overrides):
    values = {
        "root_fingerprint": "repo-root",
        "scan_options": {"include_tests": True, "languages": ["python", "typescript", "go"]},
        "input_records": _records(),
        "created_at": 100,
        "ignored_file_count": 2,
        "strata_version": "0.3.3",
    }
    values.update(overrides)
    return build_incremental_cache_metadata(**values)


def test_file_input_fingerprinting_is_deterministic_despite_input_order():
    first = fingerprint_scan_inputs(_records())
    second = fingerprint_scan_inputs(tuple(reversed(_records())))

    assert first == second
    assert first["record_count"] == 3
    assert [record["path"] for record in first["records"]] == [
        "cmd/server.go",
        "src/app.py",
        "web/app.ts",
    ]


def test_path_normalization_is_deterministic():
    fingerprint = fingerprint_scan_inputs(
        [
            {"path": "src\\app.py", "size": 10, "language": "Python"},
            {"path": "web\\components\\Button.tsx", "size": 20, "language": "TypeScript"},
        ]
    )

    assert [record["path"] for record in fingerprint["records"]] == [
        "src/app.py",
        "web/components/Button.tsx",
    ]
    assert [record["language"] for record in fingerprint["records"]] == [
        "python",
        "typescript",
    ]


def test_cache_key_is_stable_for_identical_metadata():
    first = _metadata()
    second = _metadata(input_records=tuple(reversed(_records())))

    assert first == second
    assert build_incremental_cache_key(first) == build_incremental_cache_key(second)


def test_cache_key_changes_when_scan_options_change():
    first = _metadata(scan_options={"include_tests": True})
    second = _metadata(scan_options={"include_tests": False})

    assert first["scan_options_fingerprint"] != second["scan_options_fingerprint"]
    assert build_incremental_cache_key(first) != build_incremental_cache_key(second)


def test_cache_reuse_returns_hit_when_metadata_matches():
    previous = _metadata()
    current = _metadata()

    decision = decide_incremental_cache_reuse(previous, current)

    assert decision == {
        "reuse": True,
        "status": CACHE_STATUS_HIT,
        "reasons": [],
        "warnings": [],
        "changed_counts": {},
    }


def test_cache_reuse_returns_stale_when_schema_changes():
    previous = _metadata()
    current = dict(_metadata())
    current["schema_version"] = INCREMENTAL_CACHE_SCHEMA_VERSION + 1

    decision = decide_incremental_cache_reuse(previous, current)

    assert decision["reuse"] is False
    assert decision["status"] == CACHE_STATUS_STALE
    assert decision["reasons"] == [INVALIDATION_SCHEMA_MISMATCH]


def test_cache_reuse_returns_stale_when_cache_version_changes():
    previous = _metadata()
    current = dict(_metadata())
    current["cache_version"] = "incremental-cache-v2"

    decision = decide_incremental_cache_reuse(previous, current)

    assert decision["reuse"] is False
    assert decision["status"] == CACHE_STATUS_STALE
    assert decision["reasons"] == [INVALIDATION_SCHEMA_MISMATCH]


def test_cache_reuse_returns_stale_when_root_changes():
    decision = decide_incremental_cache_reuse(
        _metadata(root_fingerprint="root-a"),
        _metadata(root_fingerprint="root-b"),
    )

    assert decision["reuse"] is False
    assert decision["status"] == CACHE_STATUS_STALE
    assert decision["reasons"] == [INVALIDATION_ROOT_CHANGED]


def test_cache_reuse_returns_stale_when_input_fingerprints_change():
    changed_records = _records()
    changed_records[0] = dict(changed_records[0])
    changed_records[0]["size"] = changed_records[0]["size"] + 1

    decision = decide_incremental_cache_reuse(
        _metadata(input_records=_records()),
        _metadata(input_records=changed_records),
    )

    assert decision["reuse"] is False
    assert decision["status"] == CACHE_STATUS_STALE
    assert decision["reasons"] == [INVALIDATION_INPUT_FINGERPRINT_CHANGED]


def test_cache_reuse_returns_stale_when_file_count_changes():
    previous = _metadata(ignored_file_count=1)
    current = _metadata(ignored_file_count=3)

    decision = decide_incremental_cache_reuse(previous, current)

    assert decision["reuse"] is False
    assert decision["status"] == CACHE_STATUS_STALE
    assert decision["reasons"] == [INVALIDATION_FILE_COUNT_CHANGED]
    assert decision["changed_counts"]["file_count"] == {
        "previous": 4,
        "current": 6,
        "delta": 2,
    }


def test_cache_reuse_reports_scan_option_changes():
    decision = decide_incremental_cache_reuse(
        _metadata(scan_options={"include_tests": True}),
        _metadata(scan_options={"include_tests": False}),
    )

    assert decision["status"] == CACHE_STATUS_STALE
    assert decision["reasons"] == [INVALIDATION_SCAN_OPTIONS_CHANGED]


def test_ttl_expiry_is_based_only_on_supplied_timestamps():
    assert is_cache_metadata_expired(
        created_at=100,
        current_time=160,
        max_age_seconds=60,
    ) is False
    assert is_cache_metadata_expired(
        created_at=100,
        current_time=161,
        max_age_seconds=60,
    ) is True

    decision = decide_incremental_cache_reuse(
        _metadata(created_at=100),
        _metadata(created_at=100),
        current_time=161,
        max_age_seconds=60,
    )

    assert decision["status"] == CACHE_STATUS_STALE
    assert decision["reasons"] == [INVALIDATION_CACHE_TOO_OLD]


def test_malformed_metadata_returns_invalid_decision_not_crash():
    malformed = {"schema_version": 1}

    decision = decide_incremental_cache_reuse(malformed, _metadata())

    assert decision["reuse"] is False
    assert decision["status"] == CACHE_STATUS_INVALID
    assert decision["reasons"] == [INVALIDATION_MALFORMED_CACHE_METADATA]
    assert decision["warnings"]


def test_diagnostics_summary_is_json_ready():
    metadata = _metadata()
    decision = decide_incremental_cache_reuse(metadata, metadata)
    summary = summarize_incremental_cache_diagnostics(metadata, decision)

    assert summary == {
        "status": CACHE_STATUS_HIT,
        "reuse": True,
        "reason_count": 0,
        "reasons": [],
        "warning_count": 0,
        "warnings": [],
        "schema_version": 1,
        "cache_version": "incremental-cache-v1",
        "file_count": 5,
        "source_file_count": 3,
        "ignored_file_count": 2,
        "language_counts": {
            "go": 1,
            "python": 1,
            "typescript": 1,
        },
    }
    assert json.loads(json.dumps(summary, allow_nan=False)) == summary


def test_docs_say_l2_is_primitives_only_without_scanner_rewrite():
    with open("docs/roadmap/performance-scale-hardening.md", encoding="utf-8") as handle:
        content = handle.read()

    assert "L1 complete" in content
    assert "L2 implemented" in content
    assert "safe cache reuse primitives" in content
    assert "does not yet perform broad scanner integration" in content
    assert "token firewall" in content


TESTS = [
    test_file_input_fingerprinting_is_deterministic_despite_input_order,
    test_path_normalization_is_deterministic,
    test_cache_key_is_stable_for_identical_metadata,
    test_cache_key_changes_when_scan_options_change,
    test_cache_reuse_returns_hit_when_metadata_matches,
    test_cache_reuse_returns_stale_when_schema_changes,
    test_cache_reuse_returns_stale_when_cache_version_changes,
    test_cache_reuse_returns_stale_when_root_changes,
    test_cache_reuse_returns_stale_when_input_fingerprints_change,
    test_cache_reuse_returns_stale_when_file_count_changes,
    test_cache_reuse_reports_scan_option_changes,
    test_ttl_expiry_is_based_only_on_supplied_timestamps,
    test_malformed_metadata_returns_invalid_decision_not_crash,
    test_diagnostics_summary_is_json_ready,
    test_docs_say_l2_is_primitives_only_without_scanner_rewrite,
]
