from pathlib import Path

from ui import (
    build_banner,
    build_kv_table,
    build_section,
    format_error,
    format_path,
    format_status,
    format_success,
    format_warning,
)


def test_build_banner_contains_expected_text():
    banner = build_banner()

    assert "Strata" in banner
    assert "Local-first" in banner
    assert "AI-assisted coding" in banner


def test_build_section_contains_title_and_separator():
    section = build_section("Project Summary")

    assert "Project Summary" in section
    assert "─" in section
    assert section.splitlines()[1] == "─" * len("Project Summary")


def test_build_kv_table_preserves_rows_and_alignment():
    table = build_kv_table(
        [
            ("Status", "PASS"),
            ("Output", Path(".aidc/gate_report.md")),
            ("Mode", 3),
        ]
    )

    lines = table.splitlines()

    assert len(lines) == 3
    assert "Status" in lines[0]
    assert "PASS" in lines[0]
    assert "Output" in lines[1]
    assert ".aidc" in lines[1]
    assert "Mode" in lines[2]
    assert "3" in lines[2]
    assert lines[0].index("PASS") == lines[1].index(".aidc") == lines[2].index("3")
    assert all(line == line.rstrip() for line in lines)


def test_build_kv_table_returns_empty_string_for_empty_rows():
    assert build_kv_table([]) == ""


def test_format_status_normalizes_known_values():
    assert format_status("PASS") == "✓ PASS"
    assert format_status("pass") == "✓ PASS"
    assert format_status("WARN") == "⚠ WARN"
    assert format_status("warning") == "⚠ WARN"
    assert format_status("FAIL") == "✕ FAIL"
    assert format_status("error") == "✕ FAIL"


def test_format_status_leaves_unknown_values_uppercased():
    assert format_status("  pending review  ") == "PENDING REVIEW"


def test_message_formatters_include_symbols_and_text():
    assert format_success("done") == "✓ done"
    assert format_warning("careful") == "⚠ careful"
    assert format_error("broken") == "✕ broken"


def test_format_path_accepts_string_and_path_without_existing_file():
    missing_path = "does/not/exist.txt"
    path_obj = Path("also/missing.txt")

    assert format_path(missing_path) == missing_path
    assert format_path(path_obj) == str(path_obj)


TESTS = [
    test_build_banner_contains_expected_text,
    test_build_section_contains_title_and_separator,
    test_build_kv_table_preserves_rows_and_alignment,
    test_build_kv_table_returns_empty_string_for_empty_rows,
    test_format_status_normalizes_known_values,
    test_format_status_leaves_unknown_values_uppercased,
    test_message_formatters_include_symbols_and_text,
    test_format_path_accepts_string_and_path_without_existing_file,
]
