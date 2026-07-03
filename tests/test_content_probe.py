import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from strata.core.candidate_evaluation import load_candidate_evaluation_manifest
from strata.core.content_probe import ContentProbeCaps, probe_content
from strata.core.inventory import collect_inventory
from strata.core.probe_pool import build_probe_pool
from strata.core.probe_scoring import score_probe_entry


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "candidate_quality"


def _write(root: Path, relative_path: str, content: str | bytes) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


def test_max_files_cap_is_respected():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        for name in ("a.py", "b.py", "c.py"):
            _write(root, name, "def auth_service():\n    pass\n")

        result = probe_content(
            root,
            ["a.py", "b.py", "c.py"],
            "fix auth service",
            caps=ContentProbeCaps(max_files=1),
        )

    assert result.files[0].skipped_reason is None
    assert [item.skipped_reason for item in result.files[1:]] == [
        "max_files_cap",
        "max_files_cap",
    ]


def test_max_bytes_per_file_cap_is_respected():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "service.py", "auth service " * 20)

        result = probe_content(
            root,
            ["service.py"],
            "fix auth service",
            caps=ContentProbeCaps(max_bytes_per_file=12),
        )

    assert result.files[0].bytes_read == 12
    assert result.stage_report.bytes_read == 12
    assert "window_truncated" in result.files[0].signals


def test_max_total_bytes_cap_is_respected():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        for name in ("a.py", "b.py", "c.py"):
            _write(root, name, "authentication service")

        result = probe_content(
            root,
            ["a.py", "b.py", "c.py"],
            "authentication service",
            caps=ContentProbeCaps(
                max_files=3,
                max_bytes_per_file=8,
                max_total_bytes=10,
            ),
        )

    assert [item.bytes_read for item in result.files] == [8, 2, 0]
    assert result.files[2].skipped_reason == "max_total_bytes_cap"
    assert result.stage_report.bytes_read == 10


def test_oversized_files_are_skipped_deterministically():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "large.py", "123456")

        result = probe_content(
            root,
            ["large.py"],
            "fix large service",
            caps=ContentProbeCaps(max_file_size=5),
        )

    assert result.files[0].skipped_reason == "file_too_large"
    assert result.files[0].bytes_read == 0


def test_missing_files_are_skipped_deterministically():
    with tempfile.TemporaryDirectory() as temp_dir:
        result = probe_content(
            temp_dir,
            ["missing.py"],
            "fix missing service",
        )

    assert result.files[0].skipped_reason == "missing_file"
    assert result.stage_report.skipped_items == ("missing.py: missing_file",)


def test_binary_files_are_skipped_safely_and_bytes_are_measured():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "binary.bin", b"auth\x00service")

        result = probe_content(root, ["binary.bin"], "fix auth service")

    assert result.files[0].skipped_reason == "binary_content"
    assert result.files[0].probe_relevance == 0.0
    assert result.stage_report.bytes_read == len(b"auth\x00service")


def test_bytes_read_and_files_touched_are_measured():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "service.py", "def service():\n    pass\n")

        result = probe_content(
            root,
            ["service.py", "missing.py"],
            "fix service",
        )

    assert result.stage_report.bytes_read == result.files[0].bytes_read
    assert result.stage_report.files_touched == 2
    assert result.stage_report.outputs["probed_files"] == 1
    assert result.stage_report.outputs["skipped_files"] == 1


def test_optional_clock_records_elapsed_milliseconds():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "service.py", "def service():\n    pass\n")
        readings = iter((1_000_000, 3_500_000))

        result = probe_content(
            root,
            ["service.py"],
            "fix service",
            clock_ns=lambda: next(readings),
        )

    assert result.stage_report.elapsed_ms == 2.5


def test_probe_evidence_and_output_are_deterministic():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(
            root,
            "auth.py",
            "# authentication service\nimport token\ndef refresh_auth():\n    pass\n",
        )

        first = probe_content(root, ["auth.py"], "fix authentication service")
        second = probe_content(root, ["auth.py"], "fix authentication service")

    assert first.to_dict() == second.to_dict()
    assert first.files[0].evidence == (
        "task terms in content: authentication, service",
        "contains import or export declaration",
        "contains class or function signature",
    )


def test_probe_relevance_is_normalized_and_confidence_is_metadata_only():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "service.py", "def auth_service():\n    pass\n")

        probe = probe_content(root, ["service.py"], "fix auth service").files[0]

    assert 0.0 <= probe.probe_relevance <= 1.0
    with_confidence = score_probe_entry(
        probe.path,
        cheap_relevance=0.5,
        probe_relevance=probe.probe_relevance,
        structural_relevance=0.5,
        normalized_cost=0.5,
        confidence=probe.confidence,
    )
    unknown_confidence = score_probe_entry(
        probe.path,
        cheap_relevance=0.5,
        probe_relevance=probe.probe_relevance,
        structural_relevance=0.5,
        normalized_cost=0.5,
        confidence="unknown",
    )
    assert with_confidence.final_score == unknown_confidence.final_score


def test_no_path_outside_supplied_root_can_be_read():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        root.mkdir()
        _write(Path(temp_dir), "outside.py", "secret")

        with patch.object(
            Path,
            "open",
            side_effect=AssertionError("opened a path outside root"),
        ):
            try:
                probe_content(root, ["../outside.py"], "fix secret")
            except ValueError as error:
                assert "must not escape" in str(error)
            else:
                raise AssertionError("Expected unsafe path rejection")


def test_probe_works_with_g3_fixture_and_g6_pool():
    manifest_path = FIXTURE_ROOT / "messy_python" / "manifest.json"
    manifest = load_candidate_evaluation_manifest(manifest_path)
    task = manifest.tasks[0]
    fixture_repo = manifest_path.parent / "repo"
    records = collect_inventory(fixture_repo)
    pool = build_probe_pool(records, task.task_text, ["app/auth/service.py"])

    result = probe_content(
        fixture_repo,
        pool,
        task.task_text,
        caps=ContentProbeCaps(max_files=3),
    )

    assert result.files
    assert result.stage_report.outputs["probed_files"] == 3
    assert all(0.0 <= item.probe_relevance <= 1.0 for item in result.files)


def test_probe_result_is_json_serializable_without_custom_encoders():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "service.py", "def service():\n    pass\n")
        payload = probe_content(root, ["service.py"], "fix service").to_dict()

    serialized = json.dumps(payload, allow_nan=False)

    assert json.loads(serialized) == payload


TESTS = [
    test_max_files_cap_is_respected,
    test_max_bytes_per_file_cap_is_respected,
    test_max_total_bytes_cap_is_respected,
    test_oversized_files_are_skipped_deterministically,
    test_missing_files_are_skipped_deterministically,
    test_binary_files_are_skipped_safely_and_bytes_are_measured,
    test_bytes_read_and_files_touched_are_measured,
    test_optional_clock_records_elapsed_milliseconds,
    test_probe_evidence_and_output_are_deterministic,
    test_probe_relevance_is_normalized_and_confidence_is_metadata_only,
    test_no_path_outside_supplied_root_can_be_read,
    test_probe_works_with_g3_fixture_and_g6_pool,
    test_probe_result_is_json_serializable_without_custom_encoders,
]
