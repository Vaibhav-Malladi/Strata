import brief_impact as old_brief_impact
import strata.core.brief_impact as new_brief_impact
from brief import generate_task_brief, score_relevant_files
from brief_impact import generate_impact_notes


def test_core_brief_impact_import_matches_compatibility_shim():
    assert old_brief_impact.generate_impact_notes is new_brief_impact.generate_impact_notes


def brief_impact_graph() -> dict:
    return {
        "schema_version": 1,
        "root": "sample-root",
        "files": [
            {
                "path": "helper.py",
                "language": "python",
                "classes": [],
                "functions": [{"name": "help_me"}],
                "imports": [],
                "external_imports": [],
                "unresolved_imports": [],
                "unresolved_import_details": [],
            },
            {
                "path": "main.py",
                "language": "python",
                "classes": [],
                "functions": [{"name": "run"}],
                "imports": ["helper"],
                "external_imports": [],
                "unresolved_imports": [],
                "unresolved_import_details": [],
            },
        ],
        "edges": [
            {
                "from": "main.py",
                "to": "helper.py",
                "type": "imports",
                "import": "helper",
            }
        ],
    }


def test_generate_impact_notes_includes_main_section():
    graph = brief_impact_graph()
    relevant_files = score_relevant_files(graph, "change helper behavior")

    content = generate_impact_notes(graph, relevant_files[:2])

    assert "## Impact Notes" in content
    assert "Risk level" in content
    assert "Summary" in content
    assert "Direct dependents" in content
    assert "Direct dependencies" in content
    assert "Transitive dependents" in content


def test_generate_impact_notes_reports_helper_dependency_impact():
    graph = brief_impact_graph()
    relevant_files = score_relevant_files(graph, "change helper behavior")

    content = generate_impact_notes(graph, relevant_files[:2])

    assert "helper.py" in content
    assert "main.py" in content
    assert "medium" in content


def test_generate_task_brief_includes_impact_notes():
    graph = brief_impact_graph()
    content = generate_task_brief(graph, "change helper behavior")

    assert "## Impact Notes" in content
    assert "Risk level" in content
    assert "Direct dependents" in content
    assert "Direct dependencies" in content


TESTS = [
    test_core_brief_impact_import_matches_compatibility_shim,
    test_generate_impact_notes_includes_main_section,
    test_generate_impact_notes_reports_helper_dependency_impact,
    test_generate_task_brief_includes_impact_notes,
]
