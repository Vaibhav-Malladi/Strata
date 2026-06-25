from agent_export import generate_agent_prompt
from context_budget import BudgetParseError, build_budget_report, build_budget_summary_rows, parse_budget_value
from context_pack import build_context_pack
from context_efficiency import estimate_tokens


def make_file(path: str, **overrides) -> dict:
    file_info = {
        "path": path,
        "language": overrides.pop("language", "typescript"),
        "classes": overrides.pop("classes", []),
        "functions": overrides.pop("functions", []),
        "interfaces": overrides.pop("interfaces", []),
        "types": overrides.pop("types", []),
        "enums": overrides.pop("enums", []),
        "exports": overrides.pop("exports", []),
        "imports": overrides.pop("imports", []),
        "external_imports": overrides.pop("external_imports", []),
        "unresolved_imports": overrides.pop("unresolved_imports", []),
        "unresolved_import_details": overrides.pop("unresolved_import_details", []),
        "routes": overrides.pop("routes", []),
    }
    file_info.update(overrides)
    return file_info


def fake_graph() -> dict:
    return {
        "schema_version": 1,
        "root": "sample",
        "files": [
            make_file("src/pages/Home.tsx"),
            make_file("src/components/Header.tsx"),
            make_file("src/components/Footer.tsx"),
        ],
        "edges": [],
    }


def _assert_terms(text: str, *terms: str) -> None:
    normalized = text.lower()
    missing = [term for term in terms if term.lower() not in normalized]
    assert not missing, f"Missing expected concept(s): {', '.join(missing)}"


def test_parse_budget_value_supports_presets():
    assert parse_budget_value("tiny")["target_tokens"] == 2000
    assert parse_budget_value("small")["target_tokens"] == 4000
    assert parse_budget_value("medium")["target_tokens"] == 8000
    assert parse_budget_value("large")["target_tokens"] == 16000


def test_parse_budget_value_supports_numeric_values():
    parsed = parse_budget_value("1234")

    assert parsed["name"] == "1234"
    assert parsed["target_tokens"] == 1234


def test_parse_budget_value_rejects_invalid_values():
    try:
        parse_budget_value("banana")
    except BudgetParseError as error:
        message = str(error).lower()
        assert "tiny" in message
        assert "small" in message
        assert "medium" in message
        assert "large" in message
    else:
        raise AssertionError("Expected BudgetParseError for invalid budget value")


def test_selected_file_remains_included_under_tiny_budget():
    graph = fake_graph()

    report = build_budget_report(
        graph,
        "home page is broken",
        selected_paths=["src/components/Header.tsx"],
        budget_value="tiny",
    )

    included_paths = [entry["file"]["path"] for entry in report["included_entries"]]

    assert "src/components/Header.tsx" in included_paths
    assert report["selected_over_budget"] is False


def test_budget_sections_appear_and_excluded_context_is_reported():
    graph = fake_graph()

    report = build_budget_report(
        graph,
        "home page is broken",
        selected_paths=["src/components/Header.tsx"],
        budget_value="1",
    )
    content = build_context_pack(
        graph,
        "home page is broken",
        selected_paths=["src/components/Header.tsx"],
        budget_value="1",
    )
    prompt = generate_agent_prompt(
        graph,
        "home page is broken",
        "generic",
        selected_paths=["src/components/Header.tsx"],
        budget_value="1",
    )

    included_paths = [entry["file"]["path"] for entry in report["included_entries"]]

    assert "src/components/Header.tsx" in included_paths
    assert report["selected_over_budget"] is True
    assert report["excluded_entries"]
    _assert_terms(
        content,
        "Structured Intent",
        "Change Boundary",
        "Context Budget",
        "Included Context",
        "Excluded Context",
    )
    _assert_terms(
        prompt,
        "Structured Intent",
        "Change Boundary",
        "Context Budget",
        "Included Context",
        "Excluded Context",
    )


def test_budget_summary_prefers_rendered_context_content_estimate():
    graph = fake_graph()
    content = build_context_pack(
        graph,
        "home page is broken",
        budget_value="small",
    )
    report = build_budget_report(
        graph,
        "home page is broken",
        budget_value="small",
    )
    report["budgeted_context_tokens"] = estimate_tokens(content)

    rows = build_budget_summary_rows(report)

    assert ("Budgeted generated content estimate", f"~{report['budgeted_context_tokens']:,}") in rows
    assert report["budgeted_context_tokens"] > report["estimated_context_tokens"]


TESTS = [
    test_parse_budget_value_supports_presets,
    test_parse_budget_value_supports_numeric_values,
    test_parse_budget_value_rejects_invalid_values,
    test_selected_file_remains_included_under_tiny_budget,
    test_budget_sections_appear_and_excluded_context_is_reported,
    test_budget_summary_prefers_rendered_context_content_estimate,
]
