import json
from pathlib import Path, PurePosixPath
from unittest.mock import patch

from strata.core.candidate_evaluation import load_candidate_evaluation_manifest
from strata.core.inventory import InventoryRecord, collect_inventory
from strata.core.probe_pool import build_probe_pool


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "candidate_quality"


def _record(
    path: str,
    *,
    size: int = 1,
    mtime: float = 1.0,
) -> InventoryRecord:
    suffix = PurePosixPath(path).suffix
    return InventoryRecord(
        path=path,
        extension=suffix,
        size=size,
        mtime=mtime,
        is_test=False,
        is_generated_guess=False,
        folder_role="source",
        language_guess=None,
    )


def _entry(pool, path: str):
    return next(entry for entry in pool.entries if entry.path == path)


def test_probe_pool_ordering_is_deterministic():
    records = [
        _record("src/utils.ts"),
        _record("package.json"),
        _record("src/auth/service.ts"),
        _record("src/auth/model.ts"),
    ]
    obvious = ["src/auth/model.ts"]

    forward = build_probe_pool(records, "fix auth service", obvious)
    reverse = build_probe_pool(reversed(records), "fix auth service", obvious)

    assert forward.to_dict() == reverse.to_dict()


def test_obvious_candidates_are_included_in_engine_order():
    records = [_record("src/first.py"), _record("src/second.py")]

    pool = build_probe_pool(
        records,
        "unrelated task",
        ["src/second.py", "src/first.py"],
    )

    assert [entry.path for entry in pool.entries[:2]] == [
        "src/second.py",
        "src/first.py",
    ]
    assert pool.entries[0].from_obvious is True
    assert pool.entries[0].obvious_rank == 1


def test_generic_low_score_file_can_enter_through_rescue_lane():
    pool = build_probe_pool(
        [_record("src/helpers.py", size=1_000_000, mtime=0.0)],
        "repair session expiry",
        [],
    )

    entry = _entry(pool, "src/helpers.py")
    assert entry.from_obvious is False
    assert entry.from_rescue is True
    assert "generic_name" in entry.sources


def test_rescue_lane_is_independent_of_candidate_score_inputs():
    records = [
        _record("src/utils.ts", size=1, mtime=1.0),
        _record("lib/helpers.py", size=999_999, mtime=999.0),
    ]

    pool = build_probe_pool(records, "repair opaque behavior", [])

    assert {entry.path for entry in pool.entries} == {
        "lib/helpers.py",
        "src/utils.ts",
    }
    assert all(entry.from_rescue for entry in pool.entries)


def test_framework_config_and_adjacent_files_enter_rescue_lane():
    pool = build_probe_pool(
        [
            _record("package.json"),
            _record("src/main.ts"),
            _record("src/deep/feature.ts"),
        ],
        "repair startup",
        [],
    )

    assert "framework_config" in _entry(pool, "package.json").sources
    assert "framework_adjacent" in _entry(pool, "src/main.ts").sources


def test_role_relevant_files_enter_rescue_lane():
    pool = build_probe_pool(
        [_record("src/network/request.ts"), _record("src/model.ts")],
        "repair API request retries",
        [],
    )

    assert "role_relevant" in _entry(pool, "src/network/request.ts").sources


def test_task_matching_folder_segments_enter_rescue_lane():
    pool = build_probe_pool(
        [_record("src/auth/opaque.data"), _record("src/other/plain.data")],
        "repair auth expiry",
        [],
    )

    assert "task_folder" in _entry(pool, "src/auth/opaque.data").sources


def test_total_and_lane_caps_are_respected():
    obvious_records = [_record(f"misc/dir{index}/opaque.bin") for index in range(4)]
    rescue_records = [_record(f"src/dir{index}/utils.ts") for index in range(6)]
    records = [*obvious_records, *rescue_records]
    obvious = [record.path for record in obvious_records]

    pool = build_probe_pool(
        records,
        "repair behavior",
        obvious,
        max_total=3,
        max_obvious=2,
        max_rescue=2,
        max_per_directory=3,
    )

    assert len(pool.entries) == 3
    assert sum(entry.from_obvious for entry in pool.entries) <= 2
    assert sum(entry.from_rescue for entry in pool.entries) <= 2
    assert pool.truncated is True


def test_per_directory_cap_is_respected():
    records = [
        _record("src/feature/api.ts"),
        _record("src/feature/service.ts"),
        _record("src/feature/utils.ts"),
        _record("lib/helpers.py"),
    ]

    pool = build_probe_pool(
        records,
        "repair behavior",
        [],
        max_per_directory=1,
    )
    directories = [PurePosixPath(entry.path).parent for entry in pool.entries]

    assert directories.count(PurePosixPath("src/feature")) == 1
    assert PurePosixPath("lib") in directories


def test_duplicate_lane_paths_merge_sources_and_reasons():
    pool = build_probe_pool(
        [_record("src/api.ts")],
        "repair API request",
        ["src/api.ts", ".\\src\\api.ts"],
    )

    assert len(pool.entries) == 1
    entry = pool.entries[0]
    assert entry.from_obvious is True
    assert entry.from_rescue is True
    assert entry.sources[0] == "obvious"
    assert "generic_name" in entry.sources
    assert len(entry.reasons) == len(set(entry.reasons))


def test_probe_pool_builder_does_not_read_or_stat_files():
    records = [_record("src/auth/service.ts"), _record("package.json")]

    with (
        patch("builtins.open", side_effect=AssertionError("opened file")),
        patch.object(Path, "read_text", side_effect=AssertionError("read file")),
        patch.object(Path, "stat", side_effect=AssertionError("statted file")),
    ):
        pool = build_probe_pool(records, "fix auth service", [])

    assert pool.entries


def test_probe_pool_works_with_g3_fixture_inventory():
    manifest_path = FIXTURE_ROOT / "messy_python" / "manifest.json"
    manifest = load_candidate_evaluation_manifest(manifest_path)
    fixture_repo = manifest_path.parent / "repo"
    records = collect_inventory(fixture_repo)

    pool = build_probe_pool(
        records,
        manifest.tasks[0].task_text,
        ["app/auth/service.py"],
    )

    assert _entry(pool, "app/auth/service.py").from_obvious is True
    assert _entry(pool, "app/auth/api.py").from_rescue is True
    assert json.loads(json.dumps(pool.to_dict())) == pool.to_dict()


TESTS = [
    test_probe_pool_ordering_is_deterministic,
    test_obvious_candidates_are_included_in_engine_order,
    test_generic_low_score_file_can_enter_through_rescue_lane,
    test_rescue_lane_is_independent_of_candidate_score_inputs,
    test_framework_config_and_adjacent_files_enter_rescue_lane,
    test_role_relevant_files_enter_rescue_lane,
    test_task_matching_folder_segments_enter_rescue_lane,
    test_total_and_lane_caps_are_respected,
    test_per_directory_cap_is_respected,
    test_duplicate_lane_paths_merge_sources_and_reasons,
    test_probe_pool_builder_does_not_read_or_stat_files,
    test_probe_pool_works_with_g3_fixture_inventory,
]
