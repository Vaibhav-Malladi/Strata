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


def _assert_terms(text: str, *terms: object) -> None:
    normalized = text.lower()
    missing: list[str] = []

    for term in terms:
        if isinstance(term, (list, tuple, set, frozenset)):
            options = [str(option) for option in term]
            if not any(option.lower() in normalized for option in options):
                missing.append("one of: " + " | ".join(options))
            continue

        value = str(term)
        if value.lower() not in normalized:
            missing.append(value)

    assert not missing, f"Missing expected concept(s): {', '.join(missing)}"


def test_cli_no_args_shows_guided_entrypoint_before_advanced_commands():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)

        exit_code, output = _run_cli(root)

        assert exit_code == 0
        _assert_terms(
            output,
            "strata",
            "new here?",
            "strata start",
            "strata setup",
            "strata run",
            "strata doctor install",
            "connect ai",
            "strata setup --manual",
            "strata setup --ollama",
            "strata setup --http",
            "strata setup --command",
            "strata setup --codex-cli",
            "strata setup --aider",
            "main workflow",
            "current state",
            "next:",
            "advanced:",
            "strata ask",
            "strata review",
            "strata apply",
        )
        assert output.index("New here?") < output.index("Connect AI") < output.index("Main workflow") < output.index("Advanced:")
        assert output.index("strata setup") < output.index("strata ask")
        assert "strata config set api_key_env OPENAI_API_KEY" not in output
        assert "strata run --type <task_type>" not in output


def test_cli_help_lists_main_workflow_first_and_keeps_advanced_reference():
    _, output = capture_output(print_usage)

    _assert_terms(output, "connect ai", "main workflow", "usage:", "advanced commands", "legacy / fallback")
    assert output.index("Connect AI") < output.index("Main workflow") < output.index("Advanced commands") < output.index("Legacy / fallback")
    _assert_terms(
        output,
        "strata start [path]",
        'strata ask "<task>" [path]',
        "strata start",
        "strata setup",
        "strata run",
        "strata setup --manual",
        "strata setup --ollama",
        "strata setup --http",
        "strata help setup",
        "strata help ask",
        "strata help manual",
        "strata review [path]",
        "strata apply [--yes] [--dry-run] [path]",
        "strata config set http_timeout 120",
        "strata apply --dry-run <root>",
        "legacy fallback: use `py cli.py ...`",
        "patch",
        "review",
        "apply",
        "browser ai",
        ".aidc/agent_prompt.md",
    )
    _assert_terms(output, ("chatgpt", "claude", "gemini", "copilot chat"))


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
        _assert_terms(output, "warning:", ("directly", "direct edit"), ".aidc/direct_edit.diff", ".aidc/agent_patch.diff", "git diff")
        assert "next" in output.lower() or "fix" in output.lower()


TESTS = [
    test_cli_no_args_shows_guided_entrypoint_before_advanced_commands,
    test_cli_help_lists_main_workflow_first_and_keeps_advanced_reference,
    test_review_missing_patch_includes_fix_line,
    test_apply_dry_run_missing_patch_includes_fix_line,
    test_ask_command_warning_mentions_direct_edits_and_safety,
]
