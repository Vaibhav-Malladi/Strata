import contextlib
import tempfile
from pathlib import Path

import commands.run_command as run_command_module
from commands.run_command import write_run_command
from workflow_config import default_config, save_config
import tests.run as test_runner
from tests.helpers import capture_output, change_directory


def _create_run_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)

    (root / "helper.py").write_text(
        "def helper():\n"
        "    return True\n",
        encoding="utf-8",
    )

    (root / "main.py").write_text(
        "import helper\n\n"
        "def run():\n"
        "    return helper()\n",
        encoding="utf-8",
    )


def _save_run_config(root: Path, **overrides) -> None:
    config = default_config()
    config.update(overrides)
    save_config(config, root)


@contextlib.contextmanager
def _patched_load_config(config: dict):
    original = run_command_module.load_config
    run_command_module.load_config = lambda root: config
    try:
        yield
    finally:
        run_command_module.load_config = original


@contextlib.contextmanager
def patched_input(value: str):
    original = run_command_module.input

    def _fake_input(prompt: str = "") -> str:
        print(prompt, end="")
        return value

    run_command_module.input = _fake_input
    try:
        yield
    finally:
        run_command_module.input = original


def _create_patch_file(root: Path, content: str) -> Path:
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


def test_run_dry_run_does_not_create_aidc():
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir)
        _create_run_repo(repo_root)

        exit_code, output = capture_output(
            write_run_command,
            str(repo_root),
            "--dry-run",
            "fix helper bug",
        )

        assert exit_code == 0
        assert not (repo_root / ".aidc").exists()
        assert "dry-run" in output
        assert "Executes AI" in output
        assert "no" in output


def test_run_dry_run_command_adapter_shows_command_without_execution():
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir)
        _create_run_repo(repo_root)
        config = {
            "mode": "auto",
            "agent": "custom",
            "adapter": "command",
            "command": "my-ai --prompt .aidc/agent_prompt.md",
            "prompt_path": ".aidc/agent_prompt.md",
            "auto_snapshot": True,
            "auto_verify": True,
            "require_gate_pass_before_commit": True,
        }

        with _patched_load_config(config):
            exit_code, output = capture_output(
                write_run_command,
                str(repo_root),
                "--dry-run",
                "fix bug",
            )

        assert exit_code == 0
        assert "command" in output
        assert "my-ai --prompt .aidc/agent_prompt.md" in output
        assert "Executes command" in output
        assert "Executes AI" in output
        assert "no" in output
        assert not (repo_root / ".aidc").exists()


def test_run_dry_run_command_adapter_missing_command_returns_nonzero():
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir)
        _create_run_repo(repo_root)
        config = {
            "mode": "auto",
            "agent": "custom",
            "adapter": "command",
            "command": None,
            "prompt_path": ".aidc/agent_prompt.md",
            "auto_snapshot": True,
            "auto_verify": True,
            "require_gate_pass_before_commit": True,
        }

        with _patched_load_config(config):
            exit_code, output = capture_output(
                write_run_command,
                str(repo_root),
                "--dry-run",
                "fix bug",
            )

        assert exit_code == 1
        assert "non-empty string command" in output
        assert not (repo_root / ".aidc").exists()


def test_run_dry_run_prompt_file_still_works():
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir)
        _create_run_repo(repo_root)
        config = default_config()
        config["adapter"] = "prompt_file"
        config["prompt_path"] = ".aidc/agent_prompt.md"

        with _patched_load_config(config):
            exit_code, output = capture_output(
                write_run_command,
                str(repo_root),
                "--dry-run",
                "fix helper bug",
            )

        assert exit_code == 0
        assert "prompt_file" in output
        assert "Executes AI" in output
        assert "no" in output
        assert not (repo_root / ".aidc").exists()


def test_run_dry_run_shows_plan():
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir)
        _create_run_repo(repo_root)

        exit_code, output = capture_output(
            write_run_command,
            str(repo_root),
            "--dry-run",
            "fix broken helper import",
        )

        assert exit_code == 0
        assert "bugfix" in output
        assert "Steps" in output
        assert "scan -> context -> preflight -> agent_prompt -> snapshot -> adapter -> diff -> verify -> gate" in output


def test_run_dry_run_accepts_flag_after_task():
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir)
        _create_run_repo(repo_root)

        exit_code, output = capture_output(
            write_run_command,
            str(repo_root),
            "fix broken helper import",
            "--dry-run",
        )

        assert exit_code == 0
        assert "dry-run" in output
        assert "bugfix" in output


def test_run_dry_run_respects_explicit_type():
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir)
        _create_run_repo(repo_root)

        exit_code, output = capture_output(
            write_run_command,
            str(repo_root),
            "--dry-run",
            "--type",
            "docs",
            "do something",
        )

        assert exit_code == 0
        assert "docs" in output
        assert "Task type" in output


def test_run_dry_run_accepts_type_after_task():
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir)
        _create_run_repo(repo_root)

        exit_code, output = capture_output(
            write_run_command,
            str(repo_root),
            "do something",
            "--type",
            "docs",
            "--dry-run",
        )

        assert exit_code == 0
        assert "docs" in output


def test_run_dry_run_respects_auto_snapshot_false():
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir)
        _create_run_repo(repo_root)
        _save_run_config(repo_root, auto_snapshot=False)

        exit_code, output = capture_output(
            write_run_command,
            str(repo_root),
            "--dry-run",
            "fix broken helper import",
        )

        assert exit_code == 0
        assert "-> snapshot ->" not in output.replace("\n", " ")


def test_run_dry_run_respects_auto_verify_false():
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir)
        _create_run_repo(repo_root)
        _save_run_config(repo_root, auto_verify=False)

        exit_code, output = capture_output(
            write_run_command,
            str(repo_root),
            "--dry-run",
            "fix broken helper import",
        )

        assert exit_code == 0
        assert "-> verify ->" not in output.replace("\n", " ")


def test_run_normal_prompt_file_shows_review_summary_and_next_apply():
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir)
        _create_run_repo(repo_root)
        _save_run_config(
            repo_root,
            adapter="prompt_file",
            prompt_path=".aidc/agent_prompt.md",
        )
        _create_patch_file(repo_root, _valid_patch_text())

        with change_directory(repo_root):
            exit_code, output = capture_output(
                write_run_command,
                str(repo_root),
                "fix helper bug",
            )

        assert exit_code == 0
        assert (repo_root / ".aidc" / "agent_prompt.md").exists()
        assert (repo_root / ".aidc" / "agent_patch.diff").exists()
        assert "Run summary" in output
        assert "Patch status" in output
        assert "Validation" in output
        assert "Dry-run" in output
        assert "Files changed" in output
        assert "Targets" in output
        assert "Next:" in output
        assert "Full scan" in output
        assert "focused context" in output
        assert "strata apply" in output
        assert "Local-first repository intelligence for AI-assisted coding" not in output
        assert (repo_root / "main.py").read_text(encoding="utf-8") == (
            "import helper\n\n"
            "def run():\n"
            "    return helper()\n"
        )


def test_run_selected_file_mode_shows_context_mode_and_selected_files():
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir)
        _create_run_repo(repo_root)
        _save_run_config(
            repo_root,
            adapter="prompt_file",
            prompt_path=".aidc/agent_prompt.md",
        )
        _create_patch_file(repo_root, _valid_patch_text())

        with change_directory(repo_root):
            exit_code, output = capture_output(
                write_run_command,
                str(repo_root),
                "--file",
                "helper.py",
                "refactor helper flow",
            )

        assert exit_code == 0
        assert "Context mode" in output
        assert "selected files" in output.lower()
        assert "Selected files" in output
        assert "helper.py" in output
        assert "selected-file context" in output.lower()
        assert (repo_root / ".aidc" / "agent_prompt.md").exists()


def test_run_normal_no_patch_gives_fix_guidance():
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir)
        _create_run_repo(repo_root)
        _save_run_config(
            repo_root,
            adapter="prompt_file",
            prompt_path=".aidc/agent_prompt.md",
        )

        with change_directory(repo_root):
            exit_code, output = capture_output(
                write_run_command,
                str(repo_root),
                "fix helper bug",
            )

        assert exit_code == 1
        assert "Fix:" in output
        assert "inspect .aidc/agent_patch.diff" in output
        assert "run strata review" in output


def test_run_repo_wide_task_warns_when_full_scan_missing():
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir)
        _create_run_repo(repo_root)
        _save_run_config(
            repo_root,
            adapter="prompt_file",
            prompt_path=".aidc/agent_prompt.md",
        )

        with change_directory(repo_root):
            exit_code, output = capture_output(
                write_run_command,
                str(repo_root),
                "repo-wide refactor",
            )

        assert exit_code == 1
        assert "focused context" in output
        assert "full scan" in output.lower()
        assert "strata scan" in output.lower()


def test_run_fast_decline_does_not_apply():
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir)
        _create_run_repo(repo_root)
        _save_run_config(
            repo_root,
            adapter="prompt_file",
            prompt_path=".aidc/agent_prompt.md",
        )
        _create_patch_file(repo_root, _valid_patch_text())

        with change_directory(repo_root):
            with patched_input(""):
                exit_code, output = capture_output(
                    write_run_command,
                    str(repo_root),
                    "--fast",
                    "fix helper bug",
                )

        assert exit_code == 0
        assert "Apply this patch now? [y/N]:" in output
        assert "Next:" in output
        assert "strata apply" in output
        assert (repo_root / "main.py").read_text(encoding="utf-8") == (
            "import helper\n\n"
            "def run():\n"
            "    return helper()\n"
        )


def test_run_fast_yes_applies_and_prints_next_steps():
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir)
        _create_run_repo(repo_root)
        (repo_root / "main.py").write_text(
            "def run():\n"
            "    return 'old'\n",
            encoding="utf-8",
        )
        _save_run_config(
            repo_root,
            adapter="prompt_file",
            prompt_path=".aidc/agent_prompt.md",
        )
        _create_patch_file(
            repo_root,
            (
                "diff --git a/main.py b/main.py\n"
                "--- a/main.py\n"
                "+++ b/main.py\n"
                "@@ -1,2 +1,2 @@\n"
                " def run():\n"
                "-    return 'old'\n"
                "+    return 'new'\n"
            ),
        )

        with change_directory(repo_root):
            with patched_input("y"):
                exit_code, output = capture_output(
                    write_run_command,
                    str(repo_root),
                    "--fast",
                    "fix helper bug",
                )

        assert exit_code == 0
        assert "Apply this patch now? [y/N]:" in output
        assert "Apply complete" in output
        assert "Next:" in output
        assert "run your project tests" in output
        assert "strata gate" in output
        assert (repo_root / "main.py").read_text(encoding="utf-8") == (
            "def run():\n"
            "    return 'new'\n"
        )


def test_run_invalid_type_returns_nonzero():
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir)
        _create_run_repo(repo_root)

        exit_code, output = capture_output(
            write_run_command,
            str(repo_root),
            "--type",
            "banana",
            "do something",
        )

        assert exit_code == 1
        assert "Unknown task type" in output


def test_run_missing_task_returns_nonzero():
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir)
        _create_run_repo(repo_root)

        exit_code, output = capture_output(write_run_command, str(repo_root))

        assert exit_code == 1
        assert "Usage: strata run" in output


def test_run_too_many_args_returns_nonzero():
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir)
        _create_run_repo(repo_root)

        exit_code, output = capture_output(
            write_run_command,
            str(repo_root),
            "task",
            "root",
            "extra",
        )

        assert exit_code == 1
        assert "Usage: strata run" in output


def test_run_outputs_single_banner():
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir)
        _create_run_repo(repo_root)
        _save_run_config(
            repo_root,
            adapter="prompt_file",
            prompt_path=".aidc/agent_prompt.md",
        )
        _create_patch_file(repo_root, _valid_patch_text())

        with change_directory(repo_root):
            exit_code, output = capture_output(
                write_run_command,
                str(repo_root),
                "fix helper bug",
            )

        assert exit_code == 0
        assert "Strata" in output
        assert "Local-first repository intelligence for AI-assisted coding" not in output


def test_shorten_test_name_keeps_short_names_unchanged():
    name = "tests.test_run_command::test_run_dry_run_does_not_create_aidc"

    assert test_runner.shorten_test_name(name, max_width=80) == name


def test_shorten_test_name_prefers_suffix_for_long_names():
    name = "tests/test_http_executor.py::test_successful_patch_with_very_long_name"

    shortened = test_runner.shorten_test_name(name, max_width=60)

    assert shortened.startswith("...")
    assert shortened.endswith("::test_successful_patch_with_very_long_name")
    assert len(shortened) <= 60


def test_shorten_test_name_truncates_when_suffix_is_still_too_long():
    name = "tests/test_http_executor.py::test_successful_patch_with_a_really_really_really_long_suffix_name"

    shortened = test_runner.shorten_test_name(name, max_width=40)

    assert shortened.startswith("...")
    assert len(shortened) <= 40
    assert "suffix_name" in shortened


TESTS = [
    test_run_dry_run_does_not_create_aidc,
    test_run_dry_run_command_adapter_shows_command_without_execution,
    test_run_dry_run_command_adapter_missing_command_returns_nonzero,
    test_run_dry_run_prompt_file_still_works,
    test_run_dry_run_shows_plan,
    test_run_dry_run_accepts_flag_after_task,
    test_run_dry_run_respects_explicit_type,
    test_run_dry_run_accepts_type_after_task,
    test_run_dry_run_respects_auto_snapshot_false,
    test_run_dry_run_respects_auto_verify_false,
    test_run_normal_prompt_file_shows_review_summary_and_next_apply,
    test_run_selected_file_mode_shows_context_mode_and_selected_files,
    test_run_normal_no_patch_gives_fix_guidance,
    test_run_repo_wide_task_warns_when_full_scan_missing,
    test_run_fast_decline_does_not_apply,
    test_run_fast_yes_applies_and_prints_next_steps,
    test_run_invalid_type_returns_nonzero,
    test_run_missing_task_returns_nonzero,
    test_run_too_many_args_returns_nonzero,
    test_run_outputs_single_banner,
    test_shorten_test_name_keeps_short_names_unchanged,
    test_shorten_test_name_prefers_suffix_for_long_names,
    test_shorten_test_name_truncates_when_suffix_is_still_too_long,
]
