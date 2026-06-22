from brief import generate_task_brief, score_relevant_files
from brief_impact import generate_impact_notes
from scanner import scan_repo


def test_generate_impact_notes_includes_main_section():
    graph = scan_repo("tmp_repo")
    relevant_files = score_relevant_files(graph, "change helper behavior")

    content = generate_impact_notes(graph, relevant_files[:2])

    assert "## Impact Notes" in content
    assert "Risk level" in content
    assert "Summary" in content
    assert "Direct dependents" in content
    assert "Direct dependencies" in content
    assert "Transitive dependents" in content


def test_generate_impact_notes_reports_helper_dependency_impact():
    graph = scan_repo("tmp_repo")
    relevant_files = score_relevant_files(graph, "change helper behavior")

    content = generate_impact_notes(graph, relevant_files[:2])

    assert "helper.py" in content
    assert "main.py" in content
    assert "medium" in content


def test_generate_task_brief_includes_impact_notes():
    graph = scan_repo("tmp_repo")
    content = generate_task_brief(graph, "change helper behavior")

    assert "## Impact Notes" in content
    assert "Risk level" in content
    assert "Direct dependents" in content
    assert "Direct dependencies" in content


TESTS = [
    test_generate_impact_notes_includes_main_section,
    test_generate_impact_notes_reports_helper_dependency_impact,
    test_generate_task_brief_includes_impact_notes,
]