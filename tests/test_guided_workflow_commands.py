import builtins
import contextlib
import sys
import tempfile
from pathlib import Path

from cli import main as cli_main
from cli_help import print_usage
from tests.helpers import capture_output, change_directory
from workflow_config import default_config, save_config


@contextlib.contextmanager
def change_argv(args: list[str]):
    original = sys.argv[:]
    sys.argv = args
    try:
        yield
    finally:
        sys.argv = original


@contextlib.contextmanager
def patched_input(value: str):
    original = builtins.input
    builtins.input = lambda prompt="": value
    try:
        yield
    finally:
        builtins.input = original


def _create_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "main.py").write_text("print('hello')\n", encoding="utf-8")
    (root / "helper.py").write_text("def helper():\n    return True\n", encoding="utf-8")


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


def _run_cli(root: Path, *args: str):
    with change_directory(root):
        with change_argv(["cli.py", *args]):
            return capture_output(cli_main)


def test_help_lists_main_workflow_before_advanced_commands():
    _, output = capture_output(print_usage)

    assert "Connect AI" in output
    assert "Main workflow:" in output
    assert "Advanced commands:" in output
    assert output.index("Connect AI") < output.index("Main workflow:") < output.index("Advanced commands:")
    assert "repo snapshot cache" in output.lower()
    assert "strata start [path]" in output
    assert 'strata ask [--file <path>] "<task>" [path]' in output
    assert "strata start" in output
    assert "strata setup" in output
    assert "strata run" in output
    assert "strata setup --manual" in output
    assert "strata setup --ollama" in output
    assert "strata setup --http" in output
    assert "strata setup --command" in output
    assert "strata setup --codex-cli" in output
    assert "strata setup --aider" in output
    assert "strata scan [path] [--force]" in output
    assert "strata status [path]" in output
    assert "strata doctor install" in output
    assert "strata help setup" in output
    assert "strata help ask" in output
    assert "strata help manual" in output
    assert "strata help scan" in output
    assert "strata help status" in output
    assert "strata review <root>" in output
    assert "strata apply --yes" in output
    assert "Selected-file examples" in output
    assert 'strata ask --file helper.py "fix the greeting"' in output
    assert 'strata run --file app.py --file helper.py "refactor this flow"' in output


def test_start_reports_repo_readiness_and_intelligence():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _save_config(
            root,
            adapter="prompt_file",
            prompt_path=".aidc/agent_prompt.md",
        )
        _write_prompt(root)

        exit_code, output = _run_cli(root, "start")

        assert exit_code == 0
        assert "Start summary" in output
        assert "Reading repository" in output
        assert "Repo map ready" in output
        assert "Snapshot cache" in output
        assert "Full scan" in output
        assert "missing" in output.lower()
        assert "first-time setup" in output.lower()
        assert "Graph" in output
        assert ".aidc/graph.json" in output.replace("\\", "/")
        assert "Files" in output
        assert "Edges" in output
        assert "Repo intelligence" in output
        assert "Repo readiness" in output
        assert "ready" in output
        assert "strata scan" in output.lower()
        assert "focused mode" in output.lower() or "full repo context" in output.lower()
        assert "strata ask \"your task\"" in output
        assert (root / ".aidc" / "graph.json").exists()
        assert (root / ".aidc" / "cache" / "repo_snapshot.json").exists()

        exit_code, output = _run_cli(root, "start")

        assert exit_code == 0
        assert "Snapshot cache" in output
        assert "fresh" in output.lower()
        assert "Changed since snapshot" in output
        assert "Full scan" in output


def test_start_without_config_shows_connect_ai_guidance():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)

        exit_code, output = _run_cli(root, "start")

        assert exit_code == 0
        assert "Connect AI" in output
        assert "Snapshot cache" in output
        assert "Full scan" in output
        assert "focused mode" in output.lower() or "full repo context needs" in output.lower()
        assert "strata scan" in output.lower()
        assert "strata setup" in output
        assert "strata setup --manual" in output
        assert "browser AI" in output
        assert "strata ask \"your task\"" in output


def test_start_reports_interrupted_full_scan_marker():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _save_config(
            root,
            adapter="prompt_file",
            prompt_path=".aidc/agent_prompt.md",
        )
        temp_scan = root / ".aidc" / "cache" / "repo_scan.tmp.json"
        temp_scan.parent.mkdir(parents=True, exist_ok=True)
        temp_scan.write_text(
            '{"schema_version":1,"status":"scanning","root":"%s"}' % root.as_posix(),
            encoding="utf-8",
        )

        exit_code, output = _run_cli(root, "start")

        assert exit_code == 0
        assert "interrupted" in output.lower()
        assert "previous scan did not finish" in output.lower()
        assert "full repo context" in output.lower()
        assert "strata scan" in output.lower()


def test_start_reports_stale_snapshot_cache_after_repo_change():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _save_config(
            root,
            adapter="prompt_file",
            prompt_path=".aidc/agent_prompt.md",
        )
        _write_prompt(root)

        exit_code, _ = _run_cli(root, "start")
        assert exit_code == 0

        (root / "main.py").write_text("print('updated')\n", encoding="utf-8")

        exit_code, output = _run_cli(root, "start")

        assert exit_code == 0
        assert "Snapshot cache" in output
        assert "stale" in output.lower()
        assert "Changed since snapshot" in output


def test_ask_prompt_file_manual_mode_writes_prompt_and_recommends_review():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _save_config(
            root,
            adapter="prompt_file",
            prompt_path=".aidc/agent_prompt.md",
        )

        exit_code, output = _run_cli(root, "ask", "fix the login bug")

        assert exit_code == 0
        assert (root / ".aidc" / "agent_prompt.md").exists()
        assert not (root / ".aidc" / "agent_patch.diff").exists()
        assert "Ask prepared" in output
        assert "Full scan" in output
        assert "focused context" in output
        assert "Open `.aidc/agent_prompt.md`" in output
        assert "ChatGPT" in output
        assert ".aidc/agent_patch.diff" in output
        assert "Run `strata review`" in output
        assert "strata apply --dry-run" in output


def test_ask_selected_file_mode_accepts_repeated_file_flags_and_anchors_prompt():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _save_config(
            root,
            adapter="prompt_file",
            prompt_path=".aidc/agent_prompt.md",
        )

        exit_code, output = _run_cli(
            root,
            "ask",
            "--file",
            "helper.py",
            "--file",
            "main.py",
            "fix the greeting",
        )

        prompt_text = (root / ".aidc" / "agent_prompt.md").read_text(encoding="utf-8")

        assert exit_code == 0
        assert "Selected context" in output
        assert "Context mode" in output
        assert "selected files" in output.lower()
        assert "Selected files" in output
        assert "helper.py" in output
        assert "main.py" in output
        assert "selected-file context" in output.lower()
        assert "User-selected files" in prompt_text
        assert "helper.py" in prompt_text
        assert "main.py" in prompt_text


def test_ask_missing_selected_file_is_rejected_with_friendly_error():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)

        exit_code, output = _run_cli(root, "ask", "--file", "missing.py", "fix the greeting")

        assert exit_code == 1
        assert "Selected file does not exist" in output
        assert "Ask failed" in output


def test_ask_selected_directory_is_rejected_with_friendly_error():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        (root / "src").mkdir(parents=True, exist_ok=True)

        exit_code, output = _run_cli(root, "ask", "--file", "src", "fix the greeting")

        assert exit_code == 1
        assert "directory, not a file" in output.lower()
        assert "Ask failed" in output


def test_ask_outside_repo_selected_file_is_rejected_with_friendly_error():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)

        exit_code, output = _run_cli(root, "ask", "--file", "..\\outside.py", "fix the greeting")

        assert exit_code == 1
        assert "outside the repo root" in output.lower()
        assert "Ask failed" in output


def test_ask_ignored_generated_selected_file_is_rejected_with_friendly_error():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        ignored_file = root / ".aidc" / "temp.py"
        ignored_file.parent.mkdir(parents=True, exist_ok=True)
        ignored_file.write_text("print('ignored')\n", encoding="utf-8")

        exit_code, output = _run_cli(root, "ask", "--file", ".aidc/temp.py", "fix the greeting")

        assert exit_code == 1
        assert "ignored or generated" in output.lower()
        assert "Ask failed" in output


def test_ask_command_missing_adapter_shows_setup_guidance():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)

        _save_config(
            root,
            adapter="command",
            command=None,
            prompt_path=".aidc/agent_prompt.md",
        )

        exit_code, output = _run_cli(root, "ask", "fix the login bug")

        assert exit_code == 1
        assert "No AI adapter is configured yet." in output
        assert "Connect AI" in output
        assert "Full scan" in output
        assert "focused context" in output
        assert "strata setup" in output
        assert "strata setup --manual" in output
        assert "ChatGPT" in output
        assert ".aidc/agent_patch.diff" in output
        assert "strata review" in output


def test_ask_repo_wide_task_warns_when_full_scan_missing():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _save_config(
            root,
            adapter="prompt_file",
            prompt_path=".aidc/agent_prompt.md",
        )

        exit_code, output = _run_cli(root, "ask", "repo-wide refactor")

        assert exit_code == 0
        assert "focused context" in output
        assert "full scan" in output.lower()
        assert "strata scan" in output.lower()


def test_review_without_patch_gives_clear_next_step():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)

        exit_code, output = _run_cli(root, "review")

        assert exit_code == 1
        assert "No AI patch found." in output
        assert 'Run `strata ask "your task"` first.' in output
        assert "snapshot" in output.lower()


def test_apply_dry_run_still_works():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _create_patch_file(
            root,
            (
                "diff --git a/main.py b/main.py\n"
                "--- a/main.py\n"
                "+++ b/main.py\n"
                "@@ -1 +1 @@\n"
                "-print('hello')\n"
                "+print('goodbye')\n"
            ),
        )

        exit_code, output = _run_cli(root, "apply", "--dry-run")

        assert exit_code == 0
        assert "Apply dry-run" in output
        assert "Applies patch" in output
        assert "no" in output


def test_existing_advanced_commands_still_route():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _save_config(
            root,
            adapter="prompt_file",
            prompt_path=".aidc/agent_prompt.md",
        )
        _write_prompt(root)

        exit_code, output = _run_cli(root, "doctor", "adapter")

        assert exit_code == 0
        assert "Adapter doctor" in output
        assert "Prompt" in output
        assert "Patch" in output


def test_apply_success_mentions_no_commit_or_push():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _create_patch_file(
            root,
            (
                "diff --git a/main.py b/main.py\n"
                "--- a/main.py\n"
                "+++ b/main.py\n"
                "@@ -1 +1 @@\n"
                "-print('hello')\n"
                "+print('goodbye')\n"
            ),
        )

        exit_code, output = _run_cli(root, "apply", "--yes")

        assert exit_code == 0
        assert "Apply complete" in output
        assert "Patch applied successfully." in output
        assert "Strata did not commit or push anything." in output


def test_apply_defaults_to_no_without_yes_flag():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _write_prompt(root)
        (root / "main.py").write_text("print('hello')\n", encoding="utf-8")
        _create_patch_file(
            root,
            (
                "diff --git a/main.py b/main.py\n"
                "--- a/main.py\n"
                "+++ b/main.py\n"
                "@@ -1 +1 @@\n"
                "-print('hello')\n"
                "+print('goodbye')\n"
            ),
        )

        with patched_input(""):
            exit_code, output = _run_cli(root, "apply")

        assert exit_code == 1
        assert "Patch not applied." in output
        assert (root / "main.py").read_text(encoding="utf-8") == "print('hello')\n"


TESTS = [
    test_help_lists_main_workflow_before_advanced_commands,
    test_start_reports_repo_readiness_and_intelligence,
    test_start_without_config_shows_connect_ai_guidance,
    test_ask_prompt_file_manual_mode_writes_prompt_and_recommends_review,
    test_ask_selected_file_mode_accepts_repeated_file_flags_and_anchors_prompt,
    test_ask_missing_selected_file_is_rejected_with_friendly_error,
    test_ask_selected_directory_is_rejected_with_friendly_error,
    test_ask_outside_repo_selected_file_is_rejected_with_friendly_error,
    test_ask_ignored_generated_selected_file_is_rejected_with_friendly_error,
    test_ask_command_missing_adapter_shows_setup_guidance,
    test_ask_repo_wide_task_warns_when_full_scan_missing,
    test_review_without_patch_gives_clear_next_step,
    test_apply_dry_run_still_works,
    test_existing_advanced_commands_still_route,
    test_apply_success_mentions_no_commit_or_push,
    test_apply_defaults_to_no_without_yes_flag,
]
