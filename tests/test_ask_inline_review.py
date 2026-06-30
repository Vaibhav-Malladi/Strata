import contextlib
import re
import sys
import tempfile
from pathlib import Path

import commands.ask_command as old_ask_command
import strata.commands.ask_command as new_ask_command
from cli import main as cli_main
from tests.helpers import capture_output, change_directory
from workflow_config import default_config, save_config


ask_command_module = new_ask_command


@contextlib.contextmanager
def change_argv(args: list[str]):
    original = sys.argv[:]
    sys.argv = args
    try:
        yield
    finally:
        sys.argv = original


def test_new_ask_command_import_matches_legacy_shim():
    assert new_ask_command.write_ask_command is old_ask_command.write_ask_command


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
        _assert_terms(output, "prompt", "open `.aidc/agent_prompt.md`", ".aidc/agent_patch.diff", "save it to `.aidc/agent_patch.diff`")
        _assert_terms(output, ("chatgpt", "claude", "gemini", "copilot chat"))
        assert "inline review" not in output
        assert "patch status" not in output
        _assert_terms(output, "next", "strata review")


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
        _assert_terms(
            output,
            "warning:",
            ("directly", "direct edit"),
            "inline review",
            "patch status",
            "ready",
            "validation",
            "passed",
            "dry-run",
            "files changed",
            "targets",
            "main.py",
            "next",
            "strata review",
            "strata apply",
        )


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
        _assert_terms(output, "inline review", "patch status")


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
        _assert_terms(output, "patch status")
        assert re.search(r"Patch status\s+.*missing", output)
        _assert_terms(output, "fix", ".aidc/agent_patch.diff", "next", "strata review")
        assert 'run `strata ask "your task"` again' in output.lower()


def test_ask_selected_file_mode_warns_when_stale_patch_exists():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _configure_command_adapter(root)
        _write_patch(
            root,
            (
                "diff --git a/tests/test_patch_applier.py b/tests/test_patch_applier.py\n"
                "--- a/tests/test_patch_applier.py\n"
                "+++ b/tests/test_patch_applier.py\n"
                "@@ -1 +1 @@\n"
                "-print('old')\n"
                "+print('new')\n"
            ),
        )

        original_execute = ask_command_module.execute_command_adapter

        def _fake_execute_command_adapter(_root, **_kwargs):
            return {
                "status": "patch_missing",
                "patch_status": "missing",
                "patch_valid": False,
                "patch_path": ".aidc/agent_patch.diff",
                "targets": [],
                "message": "No patch written for this run.",
                "stdout": "",
                "stderr": "",
                "warnings": [],
                "errors": [],
            }

        ask_command_module.execute_command_adapter = _fake_execute_command_adapter
        try:
            exit_code, output = _run_cli(root, "ask", "--file", "helper.py", "fix the greeting")
        finally:
            ask_command_module.execute_command_adapter = original_execute

        assert exit_code == 0
        _assert_terms(output, "selected context", "context mode", "selected files", "helper.py")
        _assert_terms(output, "existing patch file found before ask")


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
        _assert_terms(output, "patch status")
        assert re.search(r"Patch status\s+.*invalid", output)
        _assert_terms(output, "validation")
        assert re.search(r"Validation\s+.*invalid", output)
        _assert_terms(output, "dry-run")
        assert re.search(r"Dry-run\s+.*not run", output)
        _assert_terms(output, "fix", "valid unified diff", "next")
        assert 'run `strata ask "your task"` again' in output.lower()


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
        _assert_terms(output, "no ai adapter is configured yet", "connect ai", "strata setup", "strata setup --manual", ".aidc/agent_prompt.md", ".aidc/agent_patch.diff", "strata review", "strata apply --dry-run")
        assert "chatgpt" in output.lower() or "claude" in output.lower() or "gemini" in output.lower()


TESTS = [
    test_new_ask_command_import_matches_legacy_shim,
    test_ask_prompt_file_manual_mode_stays_manual_and_recommends_review,
    test_ask_ready_patch_shows_inline_review_fields_and_warning,
    test_ask_does_not_apply_the_patch,
    test_ask_missing_patch_shows_fix_and_next_guidance,
    test_ask_selected_file_mode_warns_when_stale_patch_exists,
    test_ask_invalid_patch_shows_fix_and_next_guidance,
    test_ask_missing_command_adapter_shows_setup_guidance_and_returns_nonzero,
]
