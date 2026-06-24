import contextlib
import re
import sys
import tempfile
from pathlib import Path

import commands.ask_command as ask_command_module
from cli import main as cli_main
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


def _save_config(root: Path, **overrides) -> None:
    config = default_config()
    config.update(overrides)
    save_config(config, root)


def _run_cli(root: Path, *args: str):
    with change_directory(root):
        with change_argv(["cli.py", *args]):
            return capture_output(cli_main)


def _write_patch(root: Path, content: str) -> Path:
    patch_path = root / ".aidc" / "agent_patch.diff"
    patch_path.parent.mkdir(parents=True, exist_ok=True)
    patch_path.write_text(content, encoding="utf-8")
    return patch_path


def _valid_patch_text() -> str:
    return (
        "diff --git a/main.py b/main.py\n"
        "--- a/main.py\n"
        "+++ b/main.py\n"
        "@@ -1 +1 @@\n"
        "-print('hello')\n"
        "+print('goodbye')\n"
    )


def _configure_command_adapter(root: Path) -> None:
    _save_config(
        root,
        mode="hybrid",
        agent="codex",
        adapter="command",
        command="fake-ai",
        prompt_path=".aidc/agent_prompt.md",
    )


def test_ask_prompt_file_manual_mode_stays_manual_and_recommends_review():
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
        assert "Prompt" in output
        assert "Open `.aidc/agent_prompt.md`" in output
        assert "ChatGPT" in output
        assert "Claude" in output
        assert "Gemini" in output
        assert ".aidc/agent_patch.diff" in output
        assert "Save it to `.aidc/agent_patch.diff`" in output
        assert "Inline review" not in output
        assert "Patch status" not in output
        assert "Next: Save the AI patch to `.aidc/agent_patch.diff`, then run `strata review`." in output


def test_ask_ready_patch_shows_inline_review_fields_and_warning():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _configure_command_adapter(root)
        _write_patch(root, _valid_patch_text())

        original_execute = ask_command_module.execute_command_adapter

        def _fake_execute_command_adapter(_root, **_kwargs):
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

        assert exit_code == 0
        assert "Warning:" in output
        assert "This adapter may edit files directly." in output
        assert "Inline review" in output
        assert "Patch status" in output
        assert "ready" in output
        assert "Validation" in output
        assert "passed" in output
        assert "Dry-run" in output
        assert "Files changed" in output
        assert "1" in output
        assert "Targets" in output
        assert "main.py" in output
        assert "Next" in output
        assert "strata review" in output
        assert "strata apply" in output


def test_ask_does_not_apply_the_patch():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _configure_command_adapter(root)
        _write_patch(root, _valid_patch_text())

        original_execute = ask_command_module.execute_command_adapter

        def _fake_execute_command_adapter(_root, **_kwargs):
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

        assert exit_code == 0
        assert (root / "main.py").read_text(encoding="utf-8") == "print('hello')\n"
        assert "Inline review" in output
        assert "Patch status" in output


def test_ask_missing_patch_shows_fix_and_next_guidance():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _configure_command_adapter(root)

        original_execute = ask_command_module.execute_command_adapter

        def _fake_execute_command_adapter(_root, **_kwargs):
            return {
                "status": "patch_ready",
                "patch_status": "missing",
                "patch_valid": False,
                "patch_path": ".aidc/agent_patch.diff",
                "targets": [],
                "message": "No patch written.",
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

        assert exit_code == 1
        assert "Patch status" in output
        assert re.search(r"Patch status\s+.*missing", output)
        assert "Fix" in output
        assert ".aidc/agent_patch.diff" in output
        assert "Next" in output
        assert 'Run `strata ask "your task"` again' in output
        assert "strata review" in output


def test_ask_invalid_patch_shows_fix_and_next_guidance():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _configure_command_adapter(root)
        _write_patch(root, "this is not a diff\n")

        original_execute = ask_command_module.execute_command_adapter

        def _fake_execute_command_adapter(_root, **_kwargs):
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

        assert exit_code == 1
        assert "Patch status" in output
        assert re.search(r"Patch status\s+.*invalid", output)
        assert "Validation" in output
        assert re.search(r"Validation\s+.*invalid", output)
        assert "Dry-run" in output
        assert re.search(r"Dry-run\s+.*not run", output)
        assert "Fix" in output
        assert "valid unified diff" in output
        assert "Next" in output
        assert 'Run `strata ask "your task"` again' in output


def test_ask_missing_command_adapter_shows_setup_guidance_and_returns_nonzero():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _save_config(
            root,
            mode="hybrid",
            agent="codex",
            adapter="command",
            command=None,
            prompt_path=".aidc/agent_prompt.md",
        )

        exit_code, output = _run_cli(root, "ask", "fix the login bug")

        assert exit_code == 1
        assert "No AI adapter is configured yet." in output
        assert "Connect AI" in output
        assert "strata setup" in output
        assert "strata setup --manual" in output
        assert "ChatGPT" in output
        assert ".aidc/agent_prompt.md" in output
        assert ".aidc/agent_patch.diff" in output
        assert "strata review" in output
        assert "strata apply --dry-run" in output


TESTS = [
    test_ask_prompt_file_manual_mode_stays_manual_and_recommends_review,
    test_ask_ready_patch_shows_inline_review_fields_and_warning,
    test_ask_does_not_apply_the_patch,
    test_ask_missing_patch_shows_fix_and_next_guidance,
    test_ask_invalid_patch_shows_fix_and_next_guidance,
    test_ask_missing_command_adapter_shows_setup_guidance_and_returns_nonzero,
]
