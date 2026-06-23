import contextlib
import os
import tempfile
from pathlib import Path

from commands.snapshot_command import write_snapshot_command
from tests.helpers import capture_output


@contextlib.contextmanager
def change_directory(path: Path):
    original = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(original)


def create_snapshot_repo(root: Path, with_routes: bool = False) -> None:
    (root / "src").mkdir(parents=True, exist_ok=True)

    route_block = '@app.get("/health")\n' if with_routes else ""

    (root / "src" / "main.py").write_text(
        "from src.helper import helper\n\n"
        f"{route_block}"
        "def run():\n"
        "    return helper()\n",
        encoding="utf-8",
    )

    (root / "src" / "helper.py").write_text(
        "def helper():\n"
        "    return True\n",
        encoding="utf-8",
    )


def test_snapshot_command_writes_timestamped_snapshot_directory():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        root.mkdir()
        create_snapshot_repo(root, with_routes=True)

        with change_directory(root):
            exit_code, output = capture_output(write_snapshot_command, ".")

        snapshot_dir = root / ".aidc" / "snapshots"
        latest_path = snapshot_dir / "latest.txt"
        latest_timestamp = latest_path.read_text(encoding="utf-8")
        created_dir = snapshot_dir / latest_timestamp

        assert exit_code == 0
        assert created_dir.exists()
        assert (created_dir / "graph.json").exists()
        assert (created_dir / "routes.json").exists()
        assert (created_dir / "summary.md").exists()
        assert latest_path.exists()
        assert "Snapshot created" in output
        assert "Status" in output
        assert "complete" in output


def test_snapshot_command_latest_points_to_created_snapshot():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        root.mkdir()
        create_snapshot_repo(root)

        with change_directory(root):
            exit_code, _ = capture_output(write_snapshot_command, ".")

        snapshot_root = root / ".aidc" / "snapshots"
        latest_timestamp = (snapshot_root / "latest.txt").read_text(encoding="utf-8")

        assert exit_code == 0
        assert (snapshot_root / latest_timestamp).exists()


def test_snapshot_command_rejects_missing_root_without_crashing():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "missing"

        exit_code, output = capture_output(write_snapshot_command, str(root))

        assert exit_code == 1
        assert "Scan failed" in output
        assert "path does not exist" in output


def test_snapshot_command_works_with_no_backend_routes():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        root.mkdir()
        create_snapshot_repo(root, with_routes=False)

        with change_directory(root):
            exit_code, output = capture_output(write_snapshot_command, ".")

        latest_timestamp = (root / ".aidc" / "snapshots" / "latest.txt").read_text(
            encoding="utf-8"
        )
        snapshot_dir = root / ".aidc" / "snapshots" / latest_timestamp
        routes_json = (snapshot_dir / "routes.json").read_text(encoding="utf-8")

        assert exit_code == 0
        assert "Routes" in output
        assert "0" in output
        assert '"routes": []' in routes_json


TESTS = [
    test_snapshot_command_writes_timestamped_snapshot_directory,
    test_snapshot_command_latest_points_to_created_snapshot,
    test_snapshot_command_rejects_missing_root_without_crashing,
    test_snapshot_command_works_with_no_backend_routes,
]
