from cli import show_cycles
import cycles as old_cycles
import strata.core.cycles as new_cycles
from cycles import find_cycles, has_cycles, format_cycles
from scanner import scan_repo
from tests.helpers import capture_output, change_directory, temporary_repo


def test_cycles_core_import_matches_compatibility_shim():
    assert old_cycles.find_cycles is new_cycles.find_cycles


def test_find_cycles_returns_empty_for_repo_without_cycles():
    with temporary_repo(
        {
            "helper.py": "def helper():\n    return True\n",
            "main.py": "import helper\n",
        }
    ) as root:
        graph = scan_repo(str(root))

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
    with temporary_repo(
        {
            "helper.py": "def helper():\n    return True\n",
            "main.py": "import helper\n",
        }
    ) as root:
        with change_directory(root):
            exit_code, output = capture_output(show_cycles, str(root))

    assert exit_code == 0
    assert "Strata" in output
    assert "Cycles complete" in output
    assert "Root" in output
    assert "Graph" in output
    assert ".aidc/graph.json" in output.replace("\\", "/")
    assert "Files" in output
    assert "Edges" in output
    assert "Cycles" in output
    assert "0" in output


def test_cli_show_cycles_returns_error_for_cycle_graph():
    with temporary_repo(
        {
            "a.py": "import b\n",
            "b.py": "import a\n",
        }
    ) as root:
        with change_directory(root):
            exit_code, output = capture_output(show_cycles, str(root))

    assert exit_code == 1
    assert "Strata" in output
    assert "Circular dependencies found" in output
    assert "Root" in output
    assert "Graph" in output
    assert ".aidc/graph.json" in output.replace("\\", "/")
    assert "Cycles" in output
    assert "1" in output
    assert "Cycle 1:" in output


TESTS = [
    test_cycles_core_import_matches_compatibility_shim,
    test_find_cycles_returns_empty_for_repo_without_cycles,
    test_find_cycles_detects_simple_cycle,
    test_format_cycles_displays_cycle_chain,
    test_cli_show_cycles_returns_success_for_no_cycles,
    test_cli_show_cycles_returns_error_for_cycle_graph,
]
