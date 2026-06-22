from cli import show_cycles
from cycles import find_cycles, has_cycles, format_cycles
from scanner import scan_repo
from tests.helpers import capture_output


def test_find_cycles_returns_empty_for_tmp_repo():
    graph = scan_repo("tmp_repo")
    cycles = find_cycles(graph)

    assert cycles == []
    assert has_cycles(graph) is False
    assert format_cycles(cycles) == "No circular dependencies found."


def test_find_cycles_detects_simple_cycle():
    graph = {
        "schema_version": 1,
        "root": "cycle_repo",
        "files": [],
        "edges": [
            {
                "from": "a.py",
                "to": "b.py",
                "type": "imports",
                "import": "b",
            },
            {
                "from": "b.py",
                "to": "a.py",
                "type": "imports",
                "import": "a",
            },
        ],
    }

    cycles = find_cycles(graph)

    assert has_cycles(graph) is True
    assert len(cycles) == 1
    assert cycles[0][0] == cycles[0][-1]
    assert "a.py" in cycles[0]
    assert "b.py" in cycles[0]


def test_format_cycles_displays_cycle_chain():
    cycles = [["a.py", "b.py", "a.py"]]
    output = format_cycles(cycles)

    assert "Cycle 1:" in output
    assert "a.py -> b.py -> a.py" in output


def test_cli_show_cycles_returns_success_for_no_cycles():
    exit_code, output = capture_output(show_cycles, "tmp_repo")

    assert exit_code == 0
    assert "Cycle check complete" in output
    assert "Cycles" in output
    assert "none" in output


def test_cli_show_cycles_returns_error_for_cycle_graph():
    graph = {
        "schema_version": 1,
        "root": "cycle_repo",
        "files": [],
        "edges": [
            {
                "from": "a.py",
                "to": "b.py",
                "type": "imports",
                "import": "b",
            },
            {
                "from": "b.py",
                "to": "a.py",
                "type": "imports",
                "import": "a",
            },
        ],
    }

    cycles = find_cycles(graph)
    output = format_cycles(cycles)

    assert cycles
    assert "Cycle 1:" in output
    assert "a.py" in output
    assert "b.py" in output


TESTS = [
    test_find_cycles_returns_empty_for_tmp_repo,
    test_find_cycles_detects_simple_cycle,
    test_format_cycles_displays_cycle_chain,
    test_cli_show_cycles_returns_success_for_no_cycles,
    test_cli_show_cycles_returns_error_for_cycle_graph,
]