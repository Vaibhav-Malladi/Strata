import contextlib
import sys
import tempfile
from pathlib import Path

import commands.ask_command as ask_command_module
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


def _create_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "main.py").write_text("print('hello')\n", encoding="utf-8")
    (root / "helper.py").write_text("def helper():\n    return True\n", encoding="utf-8")


def _write_prompt(root: Path) -> None:
    prompt_path = root / ".aidc" / "agent_prompt.md"
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text("prompt", encoding="utf-8")


def _save_config(root: Path, **overrides) -> None:
    config = default_config()
    config.update(overrides)
    save_config(config, root)


def _run_cli(root: Path, *args: str):
    with change_directory(root):
        with change_argv(["cli.py", *args]):
            return capture_output(cli_main)


def test_cli_no_args_shows_guided_entrypoint_before_advanced_commands():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)

        exit_code, output = _run_cli(root)

        assert exit_code == 0
        assert "Strata" in output
        assert output.count("Local-first repository intelligence for AI-assisted coding") == 1
        assert "Main workflow" in output
        assert "Current state" in output
        assert "Next:" in output
        assert "Advanced:" in output
        assert "strata start" in output
        assert "strata ask" in output
        assert "strata review" in output
        assert "strata apply" in output
        assert output.index("Main workflow") < output.index("Advanced:")
        assert "strata config set api_key_env OPENAI_API_KEY" not in output
        assert "strata run --type <task_type>" not in output


def test_cli_help_lists_main_workflow_first_and_keeps_advanced_reference():
    _, output = capture_output(print_usage)

    assert "Main workflow" in output
    assert "Usage:" in output
    assert "Advanced commands" in output
    assert "Legacy / fallback" in output
    assert output.index("Main workflow") < output.index("Advanced commands") < output.index("Legacy / fallback")
    assert "strata start [path]" in output
    assert 'strata ask "<task>" [path]' in output
    assert "strata review [path]" in output
    assert "strata apply [--yes] [--dry-run] [path]" in output
    assert "strata setup --aider" in output
    assert "strata setup --codex-cli" in output
    assert "strata config set http_timeout 120" in output
    assert "strata apply --dry-run <root>" in output
    assert "Legacy fallback: use `py cli.py ...`" in output
    assert "Run the configured command adapter and produce .aidc/agent_patch.diff." in output
    assert (
        "Build a workflow plan, prepare artifacts, and route through the configured adapter without executing commands automatically."
        in output
    )
    assert "Run the configured command adapter and produce .aidc/agent_patch.diff.\n  Build" not in output
    assert "Build a workflow plan, prepare artifacts, and route through the configured adapter without executing commands automatically.\nLegacy" not in output


def test_review_missing_patch_includes_fix_line():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)

        exit_code, output = _run_cli(root, "review")

        assert exit_code == 1
        assert "No AI patch found." in output
        assert "Fix" in output
        assert 'Run `strata ask "your task"` first.' in output


def test_apply_dry_run_missing_patch_includes_fix_line():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        exit_code, output = _run_cli(root, "apply", "--dry-run")

        assert exit_code == 1
        assert "Apply dry-run" in output
        assert "Fix" in output
        assert 'Run `strata ask "your task"` first.' in output
        assert "Patch file not found." in output


def test_ask_command_warning_mentions_direct_edits_and_safety():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _write_prompt(root)
        _save_config(
            root,
            mode="hybrid",
            agent="codex",
            adapter="aider",
            command="aider --message-file .aidc/agent_prompt.md",
            prompt_path=".aidc/agent_prompt.md",
        )

        original_execute = ask_command_module.execute_command_adapter

        def _fake_execute_command_adapter(*_args, **_kwargs):
            return {
                "status": "patch_ready",
                "patch_status": "ready",
                "patch_valid": True,
                "patch_path": ".aidc/agent_patch.diff",
                "targets": ["main.py"],
                "message": "Patch ready.",
                "stdout": "",
                "stderr": "",
                "warnings": [],
                "errors": [],
            }

        ask_command_module.execute_command_adapter = _fake_execute_command_adapter
        try:
            exit_code, output = _run_cli(root, "ask", "fix the login bug")
        finally:
            ask_command_module.execute_command_adapter = original_execute

        assert exit_code in {0, 1}
        assert "Warning:" in output
        assert "This adapter may edit files directly." in output
        assert "Strata will write `.aidc/direct_edit.diff` if no patch is produced." in output
        assert ".aidc/agent_patch.diff" in output
        assert ".aidc/direct_edit.diff" in output
        assert "git diff" in output
        assert "Next" in output or "Fix" in output


TESTS = [
    test_cli_no_args_shows_guided_entrypoint_before_advanced_commands,
    test_cli_help_lists_main_workflow_first_and_keeps_advanced_reference,
    test_review_missing_patch_includes_fix_line,
    test_apply_dry_run_missing_patch_includes_fix_line,
    test_ask_command_warning_mentions_direct_edits_and_safety,
]
