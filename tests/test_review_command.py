import contextlib
import sys
import tempfile
from pathlib import Path

from cli import main as cli_main
from cli_core import build_graph
from routes import collect_routes
from snapshot import write_snapshot
from tests.helpers import capture_output, change_directory
from workflow_config import config_path, save_config


@contextlib.contextmanager
def change_argv(args: list[str]):
    original = sys.argv[:]
    sys.argv = args
    try:
        yield
    finally:
        sys.argv = original


def _create_review_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)

    (root / "helper.py").write_text(
        "def helper():\n"
        "    return True\n",
        encoding="utf-8",
    )

    (root / "main.py").write_text(
        "import helper\n\n"
        "def run():\n"
        "    return helper.helper()\n",
        encoding="utf-8",
    )


def _run_review_cli(root: Path, *args: str):
    with change_directory(root):
        with change_argv(["cli.py", "review", *args]):
            return capture_output(cli_main)


def _create_snapshot(root: Path) -> None:
    with change_directory(root):
        graph = build_graph(".")

    assert graph is not None
    write_snapshot(root, graph, collect_routes(graph))


def test_review_without_config_uses_defaults_and_runs_verify():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        _create_review_repo(root)
        _create_snapshot(root)

        exit_code, output = _run_review_cli(root)
        normalized_output = output.replace("\\", "/")

        assert exit_code == 0
        assert "Strata" in output
        assert "Review complete" in output
        assert "PASS" in output
        assert "Verify" in output
        assert (root / ".aidc" / "diff_report.md").exists()
        assert (root / ".aidc" / "diff_report.json").exists()
        assert (root / ".aidc" / "verification_report.md").exists()
        assert (root / ".aidc" / "verification_report.json").exists()
        assert (root / ".aidc" / "gate_report.md").exists()
        assert (root / ".aidc" / "gate_report.json").exists()
        assert not config_path(root).exists()
        assert ".aidc/diff_report.md" in normalized_output


def test_review_respects_auto_verify_false():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        _create_review_repo(root)
        save_config({"auto_verify": False}, root)
        _create_snapshot(root)

        exit_code, output = _run_review_cli(root, str(root))

        assert exit_code == 0
        assert "Verify" in output
        assert "skipped" in output
        assert (root / ".aidc" / "diff_report.md").exists()
        assert (root / ".aidc" / "diff_report.json").exists()
        assert (root / ".aidc" / "gate_report.md").exists()
        assert (root / ".aidc" / "gate_report.json").exists()
        assert not (root / ".aidc" / "verification_report.md").exists()
        assert not (root / ".aidc" / "verification_report.json").exists()


def test_review_missing_snapshot_returns_nonzero():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        _create_review_repo(root)

        exit_code, output = _run_review_cli(root)

        assert exit_code != 0
        assert "snapshot" in output.lower()
        assert "PASS" not in output


def test_review_gate_failure_returns_nonzero():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        _create_review_repo(root)
        _create_snapshot(root)

        (root / "main.py").write_text(
            "import missing_module\n\n"
            "def run():\n"
            "    return 1\n",
            encoding="utf-8",
        )

        exit_code, output = _run_review_cli(root)

        assert exit_code != 0
        assert "FAIL" in output or "error" in output.lower()
        assert (root / ".aidc" / "gate_report.md").exists()
        assert (root / ".aidc" / "gate_report.json").exists()


def test_review_too_many_args_returns_nonzero():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        _create_review_repo(root)

        exit_code, output = _run_review_cli(root, str(root), "extra")

        assert exit_code == 1
        assert "Usage" in output


def test_review_invalid_config_returns_nonzero():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        _create_review_repo(root)
        _create_snapshot(root)

        path = config_path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        original = '{"mode": "banana"'
        path.write_text(original, encoding="utf-8")

        exit_code, output = _run_review_cli(root)

        assert exit_code != 0
        assert "error" in output.lower()
        assert path.read_text(encoding="utf-8") == original


def test_review_does_not_stack_multiple_banners():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        _create_review_repo(root)
        _create_snapshot(root)

        exit_code, output = _run_review_cli(root)

        assert exit_code == 0
        assert output.count("Local-first repository intelligence") == 1


def test_help_mentions_review():
    from cli_help import print_usage

    _, output = capture_output(print_usage)

    assert "strata review" in output
    assert "strata review <root>" in output


TESTS = [
    test_review_without_config_uses_defaults_and_runs_verify,
    test_review_respects_auto_verify_false,
    test_review_missing_snapshot_returns_nonzero,
    test_review_gate_failure_returns_nonzero,
    test_review_too_many_args_returns_nonzero,
    test_review_invalid_config_returns_nonzero,
    test_review_does_not_stack_multiple_banners,
    test_help_mentions_review,
]
