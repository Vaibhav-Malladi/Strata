import tempfile
from pathlib import Path

from verify import build_verification_markdown, verify_diff, write_verification_report


def test_empty_diff_summary_produces_pass():
    report = verify_diff({"summary": {}})

    assert report["status"] == "PASS"
    assert report["failures"] == []
    assert report["warnings"] == []
    assert report["improvements"] == []
    assert report["recommended_commands"] == [
        "py tests.py",
        "py tests\\run.py",
    ]


def test_unresolved_imports_added_produces_fail():
    report = verify_diff({"summary": {"unresolved_imports_added": 1}})

    assert report["status"] == "FAIL"
    assert any("Unresolved imports added" in item for item in report["failures"])


def test_files_removed_produces_warn():
    report = verify_diff({"summary": {"files_removed": 1}})

    assert report["status"] == "WARN"
    assert any("Files removed" in item for item in report["warnings"])


def test_routes_added_and_removed_produce_warn():
    report = verify_diff({"summary": {"routes_added": 1, "routes_removed": 1}})

    assert report["status"] == "WARN"
    assert any("Routes added" in item for item in report["warnings"])
    assert any("Routes removed" in item for item in report["warnings"])


def test_unresolved_imports_removed_is_listed_as_improvement():
    report = verify_diff({"summary": {"unresolved_imports_removed": 2}})

    assert report["status"] == "PASS"
    assert any(
        "Unresolved imports removed" in item for item in report["improvements"]
    )


def test_malformed_diff_produces_fail_and_does_not_crash():
    report = verify_diff(None)

    assert report["status"] == "FAIL"
    assert report["failures"]
    assert "dictionary" in report["failures"][0].lower()


def test_markdown_includes_required_sections():
    report = verify_diff({"summary": {}})

    markdown = build_verification_markdown(report)

    assert "# Strata Verification Report" in markdown
    assert "Status" in markdown
    assert "Recommended Verification" in markdown


def test_write_verification_report_writes_json_and_markdown():
    report = verify_diff({"summary": {"files_removed": 1}})

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        root.mkdir()

        result = write_verification_report(root, report)

        json_path = Path(result["json_path"])
        markdown_path = Path(result["markdown_path"])

        assert json_path.exists()
        assert markdown_path.exists()
        assert json_path.read_text(encoding="utf-8")
        assert markdown_path.read_text(encoding="utf-8").startswith(
            "# Strata Verification Report"
        )


TESTS = [
    test_empty_diff_summary_produces_pass,
    test_unresolved_imports_added_produces_fail,
    test_files_removed_produces_warn,
    test_routes_added_and_removed_produce_warn,
    test_unresolved_imports_removed_is_listed_as_improvement,
    test_malformed_diff_produces_fail_and_does_not_crash,
    test_markdown_includes_required_sections,
    test_write_verification_report_writes_json_and_markdown,
]
