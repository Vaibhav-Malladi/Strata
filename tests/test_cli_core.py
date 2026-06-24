import contextlib
import json
import os
import tempfile
import sys
from pathlib import Path

from cli import main as cli_main
from cli import write_graph, show_file
from cli_help import print_usage
from tests.helpers import run_silently, capture_output, change_directory
from workflow_config import default_config, save_config


def _create_cli_core_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)

    (root / "helper.py").write_text(
        "def helper():\n"
        "    return True\n",
        encoding="utf-8",
    )

    (root / "main.py").write_text(
        "import os\n"
        "import helper\n"
        "import missing_module\n\n"
        "def run():\n"
        "    return helper()\n",
        encoding="utf-8",
    )


def _create_patch_file(root: Path, content: str) -> Path:
    patch_path = root / ".aidc" / "agent_patch.diff"
    patch_path.parent.mkdir(parents=True, exist_ok=True)
    patch_path.write_text(content, encoding="utf-8")
    return patch_path


def _write_prompt(root: Path) -> Path:
    prompt_path = root / ".aidc" / "agent_prompt.md"
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text("prompt", encoding="utf-8")
    return prompt_path


def _save_config(root: Path, **overrides) -> None:
    config = default_config()
    config.update(overrides)
    save_config(config, root)


@contextlib.contextmanager
def change_argv(args: list[str]):
    original = sys.argv[:]
    sys.argv = args
    try:
        yield
    finally:
        sys.argv = original


def test_cli_write_graph_creates_output_file():
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir)
        _create_cli_core_repo(repo_root)

        with change_directory(repo_root):
            exit_code = run_silently(write_graph, str(repo_root))

        assert exit_code == 0
        assert (repo_root / ".aidc" / "graph.json").exists()

        with open(repo_root / ".aidc" / "graph.json", "r", encoding="utf-8") as file:
            graph = json.load(file)

        assert graph["schema_version"] == 1
        assert graph["root"] == str(repo_root)
        assert len(graph["files"]) == 2
        assert len(graph["edges"]) == 1

        paths = [file_info["path"] for file_info in graph["files"]]

        assert any(path.endswith("main.py") for path in paths)
        assert any(path.endswith("helper.py") for path in paths)

        main_file = None

        for file_info in graph["files"]:
            if file_info["path"].endswith("main.py"):
                main_file = file_info

        assert main_file is not None
        assert "os" in main_file["external_imports"]
        assert "missing_module" in main_file["unresolved_imports"]
        assert "helper" not in main_file["external_imports"]
        assert "helper" not in main_file["unresolved_imports"]

        edge = graph["edges"][0]

        assert edge["from"].endswith("main.py")
        assert edge["to"].endswith("helper.py")
        assert edge["import"] == "helper"


def test_cli_show_file_finds_saved_file():
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir)
        _create_cli_core_repo(repo_root)

        with change_directory(repo_root):
            run_silently(write_graph, str(repo_root))

            exit_code = run_silently(show_file, str(repo_root / "main.py"))

        assert exit_code == 0


def test_cli_show_file_returns_error_for_missing_file():
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir)
        _create_cli_core_repo(repo_root)

        with change_directory(repo_root):
            run_silently(write_graph, str(repo_root))

            exit_code = run_silently(show_file, "missing.py")

        assert exit_code == 1


def test_cli_show_file_displays_unresolved_import_line_number():
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir)
        _create_cli_core_repo(repo_root)

        with change_directory(repo_root):
            run_silently(write_graph, str(repo_root))

            exit_code, output = capture_output(show_file, str(repo_root / "main.py"))

        assert exit_code == 0
        assert "Warnings" in output
        assert "Unresolved imports found in" in output
        assert "missing_module" in output
        assert "at line" in output
        assert "3" in output


def test_cli_show_file_displays_backend_routes():
    graph = {
        "schema_version": 1,
        "root": ".",
        "files": [
            {
                "path": "api.py",
                "language": "python",
                "imports": [],
                "external_imports": [],
                "unresolved_imports": [],
                "unresolved_import_details": [],
                "classes": [],
                "functions": [],
                "routes": [
                    {
                        "method": "GET",
                        "path": "/health",
                        "line": 1,
                        "source": "@app.get",
                    },
                    {
                        "method": "POST",
                        "path": "/users",
                        "line": 5,
                        "source": "@router.post",
                    },
                ],
            }
        ],
        "edges": [],
    }

    with tempfile.TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir)

        with change_directory(repo_root):
            os.makedirs(".aidc", exist_ok=True)

            with open(".aidc/graph.json", "w", encoding="utf-8") as file:
                json.dump(graph, file)

            exit_code, output = capture_output(show_file, "api.py")

        assert exit_code == 0
        assert "Backend routes" in output
        assert "GET" in output
        assert "/health" in output
        assert "POST" in output
        assert "/users" in output
        assert "@app.get" in output
        assert "@router.post" in output


def test_cli_agent_prompt_command_smoke():
    import os
    import subprocess
    import sys
    from pathlib import Path

    cli_path = Path(__file__).resolve().parents[1] / "cli.py"

    with tempfile.TemporaryDirectory() as temp_dir:
        project_root = Path(temp_dir)
        _create_cli_core_repo(project_root)
        output_path = project_root / ".aidc" / "agent_prompt.md"

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"

        result = subprocess.run(
            [
                sys.executable,
                str(cli_path),
                "agent-prompt",
                "add agent prompt command",
                "local",
            ],
            cwd=project_root,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        assert result.returncode == 0, result.stderr
        assert "Strata" in result.stdout
        assert "Agent prompt complete" in result.stdout
        assert "Task" in result.stdout
        assert "add agent prompt command" in result.stdout
        assert "Agent" in result.stdout
        assert "local" in result.stdout
        assert ".aidc/agent_prompt.md" in result.stdout.replace("\\", "/")
        assert output_path.exists()


def test_cli_status_command_smoke():
    import os
    import subprocess
    import sys
    from pathlib import Path

    cli_path = Path(__file__).resolve().parents[1] / "cli.py"

    with tempfile.TemporaryDirectory() as temp_dir:
        project_root = Path(temp_dir)
        _create_cli_core_repo(project_root)

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"

        result = subprocess.run(
            [
                sys.executable,
                str(cli_path),
                "status",
            ],
            cwd=project_root,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        assert result.returncode == 0, result.stderr
        assert "Strata" in result.stdout
        assert "Strata status" in result.stdout
        assert "Root" in result.stdout
        assert "State" in result.stdout
        assert "Missing" in result.stdout
        assert "Stale" in result.stdout
        assert "# Strata Status" in result.stdout
        assert "## Generated Files" in result.stdout
        assert "## Missing Outputs" in result.stdout
        assert "## Recommended Actions" in result.stdout


def test_cli_patch_command_smoke():
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir) / "repo"
        repo_root.mkdir()
        _create_patch_file(
            repo_root,
            "diff --git a/main.py b/main.py\n+print('hello')\n",
        )

        with change_argv(["cli.py", "patch", str(repo_root)]):
            exit_code, output = capture_output(cli_main)

        assert exit_code == 0
        assert "Patch inspect" in output
        assert ".aidc" in output.replace("\\", "/")
        assert "ready" in output
        assert "diff --git" not in output


def test_cli_apply_dry_run_command_smoke():
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir)

        with change_argv(["cli.py", "apply", "--dry-run"]):
            with change_directory(repo_root):
                exit_code, output = capture_output(cli_main)

        assert exit_code == 1
        assert "Apply dry-run" in output
        assert "missing" in output
        assert "Patch file not found." in output
        assert not (repo_root / ".aidc").exists()


def test_cli_execute_command_dispatches():
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir)
        _create_repo(repo_root)
        _save_config(
            repo_root,
            adapter="prompt_file",
            prompt_path=".aidc/agent_prompt.md",
        )
        _write_prompt(repo_root)

        with change_directory(repo_root):
            with change_argv(["cli.py", "execute"]):
                exit_code, output = capture_output(cli_main)

        assert exit_code == 1
        assert "Execute adapter" in output
        assert "Status" in output
        assert "Adapter" in output
        assert "Prompt" in output
        assert "Patch" in output
        assert "Command" in output
        assert "Timeout seconds" in output
        assert "Executes command" in output
        assert "Applies patch" in output
        assert "Message" in output


def test_cli_run_command_smoke():
    import os
    import subprocess
    import sys
    from pathlib import Path

    cli_path = Path(__file__).resolve().parents[1] / "cli.py"

    with tempfile.TemporaryDirectory() as temp_dir:
        project_root = Path(temp_dir)
        _create_cli_core_repo(project_root)

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"

        result = subprocess.run(
            [
                sys.executable,
                str(cli_path),
                "run",
                "--dry-run",
                "fix broken helper import",
            ],
            cwd=project_root,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        assert result.returncode == 0, result.stderr
        assert "Run plan" in result.stdout
        assert "dry-run" in result.stdout
        assert "bugfix" in result.stdout


def test_cli_help_prefers_strata_commands():
    _, output = capture_output(print_usage)

    assert "Connect AI" in output
    assert "strata setup" in output
    assert "strata setup --manual" in output
    assert "strata setup --ollama" in output
    assert "strata setup --http" in output
    assert "strata setup --command" in output
    assert "strata setup --codex-cli" in output
    assert "strata setup --aider" in output
    assert 'strata ask "fix bug"' in output
    assert "For step-by-step help, run `strata help setup`, `strata help ask`, or `strata help manual`." in output
    assert "strata scan [path]" in output
    assert "strata gate <root>" in output
    assert "strata setup" in output
    assert "strata setup --manual" in output
    assert "strata setup --aider" in output
    assert "strata setup --codex-cli" in output
    assert "strata setup --ollama" in output
    assert "strata config [root]" in output
    assert "strata config init [root]" in output
    assert "strata config set <key> <value> [root]" in output
    assert "strata config set command_timeout_seconds 120" in output
    assert "strata config set http_timeout_seconds 120" in output
    assert "strata config set http_timeout 120" in output
    assert "strata config set base_url http://localhost:1234/v1" in output
    assert "strata config set api_key_env OPENAI_API_KEY" in output
    assert "strata patch [root]" in output
    assert 'strata prepare "<task>"' in output
    assert 'strata prepare "<task>" <root>' in output
    assert 'strata run "<task>"' in output
    assert 'strata run --dry-run "<task>"' in output
    assert "strata apply --dry-run" in output
    assert "strata apply --dry-run <root>" in output
    assert "strata execute" in output
    assert "strata execute <root>" in output
    assert "strata doctor adapter" in output
    assert "strata doctor adapter <root>" in output
    assert "strata review" in output
    assert "strata review <root>" in output
    assert output.index("Connect AI") < output.index("Main workflow")
    assert "Run `strata setup` to choose how Strata talks to AI." in output
    assert "`strata setup --manual`" in output
    assert "`strata setup --ollama`" in output
    assert "`strata setup --http`" in output
    assert "Then run `strata ask \"fix bug\"`, `strata review`, `strata apply --dry-run`, and `strata apply`." in output
    assert "For step-by-step help, run `strata help setup`, `strata help ask`, or `strata help manual`." in output
    assert (
        "Prepare context, request a patch, review it, and end with `strata apply` as the next step."
        in output
    )
    assert "Legacy fallback: use `py cli.py ...`" in output
    assert "py cli.py scan [path]" not in output


def test_cli_setup_rejects_conflicting_flags():
    with change_argv(["cli.py", "setup", "--manual", "--ollama"]):
        exit_code, output = capture_output(cli_main)

    assert exit_code == 1
    assert "Usage:" in output
    assert "strata setup --manual" in output


def test_editable_install_imports_command_executor_from_clean_cwd():
    import subprocess

    with tempfile.TemporaryDirectory() as temp_dir:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import command_executor; print(command_executor.__file__)",
            ],
            cwd=temp_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    assert result.returncode == 0, result.stderr
    assert "command_executor.py" in result.stdout.replace("\\", "/")


def test_cli_doctor_adapter_dispatches():
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir)
        _create_cli_core_repo(repo_root)
        aidc_dir = repo_root / ".aidc"
        aidc_dir.mkdir(parents=True, exist_ok=True)
        (aidc_dir / "config.json").write_text(
            json.dumps(
                {
                    "mode": "hybrid",
                    "agent": "codex",
                    "adapter": "prompt_file",
                    "prompt_path": ".aidc/agent_prompt.md",
                    "model": None,
                    "command": None,
                    "auto_snapshot": True,
                    "auto_verify": True,
                    "require_gate_pass_before_commit": True,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (aidc_dir / "agent_prompt.md").write_text("prompt", encoding="utf-8")

        with change_directory(repo_root):
            with change_argv(["cli.py", "doctor", "adapter"]):
                exit_code, output = capture_output(cli_main)

        assert exit_code == 0
        assert "Adapter doctor" in output
        assert "Status" in output
        assert "Adapter" in output
        assert "Prompt" in output
        assert "Patch" in output
        assert "Message" in output
        assert "Command timeout" in output
        assert "Base URL" in output
        assert "API key env" in output
        assert "HTTP timeout seconds" in output


TESTS = [
    test_cli_write_graph_creates_output_file,
    test_cli_show_file_finds_saved_file,
    test_cli_show_file_returns_error_for_missing_file,
    test_cli_show_file_displays_unresolved_import_line_number,
    test_cli_show_file_displays_backend_routes,
    test_cli_agent_prompt_command_smoke,
    test_cli_status_command_smoke,
    test_cli_patch_command_smoke,
    test_cli_apply_dry_run_command_smoke,
    test_cli_run_command_smoke,
    test_cli_help_prefers_strata_commands,
    test_cli_setup_rejects_conflicting_flags,
    test_editable_install_imports_command_executor_from_clean_cwd,
    test_cli_doctor_adapter_dispatches,
]
