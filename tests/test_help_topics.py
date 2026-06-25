import contextlib
import sys

from cli import main as cli_main
from cli_help import print_usage
from tests.helpers import capture_output


@contextlib.contextmanager
def change_argv(args: list[str]):
    original = sys.argv[:]
    sys.argv = args
    try:
        yield
    finally:
        sys.argv = original


def _run_cli(*args: str):
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


def test_help_usage_mentions_all_ai_modes_and_beginner_topics():
    _, output = capture_output(print_usage)

    _assert_terms(
        output,
        "connect ai",
        "strata setup",
        "strata setup ai",
        "strata setup ai --check",
        "strata setup --manual",
        "strata setup --ollama",
        "strata setup --http",
        "strata setup --command",
        "strata setup --codex-cli",
        "strata setup --aider",
        'strata ask [--file <reference>]... "<task>" [path]',
        "strata scan [path] [--force]",
        "strata status [path]",
        "strata review",
        "strata apply --dry-run",
        "strata apply",
        'strata run [--file <reference>]... "<task>"',
        "strata doctor install",
        "strata help setup",
        "strata help ask",
        "strata help manual",
        "strata help scan",
        "strata help status",
        "strata help context",
        "strata help prepare",
        "Selected-file examples",
        'strata ask --file LoginForm "fix validation"',
        'strata run --file run_command "fix dry run output" --dry-run',
        'strata ask --file run_command --file ask_command "compare these flows"',
        'strata ask --budget small "fix validation"',
        'strata run --budget small --dry-run "fix validation"',
        'strata context --budget 3000 "fix validation"',
        'strata prepare --budget small "fix validation"',
    )


def test_help_setup_topic_is_beginner_friendly():
    exit_code, output = _run_cli("help", "setup")

    assert exit_code == 0
    _assert_terms(
        output,
        "setup",
        "ai",
        "strata setup",
        "strata setup ai",
        "strata setup ai --check",
        "strata setup --manual",
        "strata setup --ollama",
        "strata setup --codex-cli",
        "strata setup --aider",
        "strata setup --command",
        "strata setup --http",
        "strata setup --show",
        "strata doctor adapter",
        "user environment",
    )


def test_help_manual_topic_is_step_by_step():
    exit_code, output = _run_cli("help", "manual")

    assert exit_code == 0
    _assert_terms(
        output,
        "manual",
        "browser",
        "safest",
        "api key",
        "local model",
        ".aidc/agent_prompt.md",
        ".aidc/agent_patch.diff",
        "strata review",
        "strata apply --dry-run",
        "strata apply",
        "strata gate",
    )
    _assert_terms(output, ("chatgpt", "claude", "gemini", "copilot chat"))


def test_help_ollama_topic_is_step_by_step():
    exit_code, output = _run_cli("help", "ollama")

    assert exit_code == 0
    _assert_terms(
        output,
        "ollama",
        "must be running",
        "exact model tag",
        "ollama list",
        "qwen2.5-coder:14b",
        "strata setup --ollama",
        "strata config set model",
        "strata doctor adapter",
        "strata ask",
        "strata review",
        "strata apply --dry-run",
        "strata apply",
    )


def test_help_command_topic_mentions_patch_first_workflow():
    exit_code, output = _run_cli("help", "command")

    assert exit_code == 0
    _assert_terms(
        output,
        "codex cli",
        "aider",
        "custom script",
        ".aidc/agent_prompt.md",
        ".aidc/direct_edit.diff",
        "git diff",
        "strata setup --codex-cli",
        "strata setup --aider",
        "strata setup --command",
        'strata config set command "<your command here>"',
    )
    _assert_terms(output, ("prompt", "patch-first", "direct edit"))


def test_help_http_topic_mentions_api_configuration():
    exit_code, output = _run_cli("help", "http")

    assert exit_code == 0
    _assert_terms(
        output,
        "openai-compatible http api",
        "strata setup ai",
        "strata setup ai --check",
        "strata setup --http",
        "base_url",
        "api_key_env",
        "model",
        "strata doctor adapter",
    )
    _assert_terms(output, "hardcode")


def test_help_doctor_topic_mentions_install_diagnostics():
    exit_code, output = _run_cli("help", "doctor")

    assert exit_code == 0
    _assert_terms(
        output,
        "install",
        "path",
        "adapter setup",
        "strata doctor install",
        "python executable",
        'shutil.which("strata")',
        "windows tips",
        "pip",
        "-e",
        "py -m strata",
        "strata doctor adapter",
        "found or missing",
        "setup ai",
    )


def test_help_install_alias_routes_to_doctor_topic():
    exit_code, output = _run_cli("help", "install")

    assert exit_code == 0
    _assert_terms(output, "install", "path", "adapter setup", "strata doctor install")


def test_help_ask_topic_mentions_setup_and_next_steps():
    exit_code, output = _run_cli("help", "ask")

    assert exit_code == 0
    _assert_terms(
        output,
        "ask",
        "context",
        "strata setup",
        "ai",
        "apply",
        ".aidc/agent_patch.diff",
        "strata review",
        "strata apply --dry-run",
        "strata apply",
        "selected-file context",
        "--file LoginForm",
        "run_command",
        "ask_command",
        "--budget small",
        "--budget 3000",
    )


def test_help_review_topic_mentions_patch_validation():
    exit_code, output = _run_cli("help", "review")

    assert exit_code == 0
    _assert_terms(output, "review", "patch", "valid", "targets", "read-only", "strata apply --dry-run")


def test_help_apply_topic_mentions_dry_run_tests_and_gate():
    exit_code, output = _run_cli("help", "apply")

    assert exit_code == 0
    _assert_terms(output, "apply", "files", "strata apply --dry-run", "strata apply", "tests", "strata gate", "commit")


def test_help_run_topic_mentions_fast_confirmation():
    exit_code, output = _run_cli("help", "run")

    assert exit_code == 0
    _assert_terms(
        output,
        "strata run",
        "patch",
        "review",
        "--fast",
        "apply",
        "commit",
        "push",
        "auto",
        "selected-file context",
        "--file loginform",
        "run_command",
        "--budget small",
    )
    _assert_terms(output, ("confirm", "confirmation"))


def test_help_context_topic_mentions_budget_examples():
    exit_code, output = _run_cli("help", "context")

    assert exit_code == 0
    _assert_terms(
        output,
        "context",
        "budgeted summary",
        "--budget 3000",
        "--budget small",
        ".aidc/context_pack.md",
    )


def test_help_prepare_topic_mentions_budget_examples():
    exit_code, output = _run_cli("help", "prepare")

    assert exit_code == 0
    _assert_terms(
        output,
        "prepare",
        ".aidc/context_pack.md",
        ".aidc/agent_prompt.md",
        "--budget small",
        "generated prompt content estimate",
    )


def test_help_gate_topic_mentions_reports_and_tests():
    exit_code, output = _run_cli("help", "gate")

    assert exit_code == 0
    _assert_terms(output, "gate", "validation", ".aidc/gate_report.md", ".aidc/gate_report.json", "tests", "commit")


def test_help_start_topic_mentions_beginner_entrypoint():
    exit_code, output = _run_cli("help", "start")

    assert exit_code == 0
    _assert_terms(output, "beginner", "entrypoint", "scan", "snapshot cache", "setup", "ask", "review", "apply", "gate", "strata doctor install", "focused mode", "--force")


def test_help_scan_topic_mentions_scan_states_and_force():
    exit_code, output = _run_cli("help", "scan")

    assert exit_code == 0
    _assert_terms(
        output,
        "scan",
        "focused mode",
        "fresh",
        "stale",
        "interrupted",
        "strata scan",
        "strata scan --force",
        "temp marker",
    )


def test_help_status_topic_mentions_scan_readiness():
    exit_code, output = _run_cli("help", "status")

    assert exit_code == 0
    _assert_terms(
        output,
        "status",
        "fresh",
        "stale",
        "interrupted",
        "missing",
        "focused mode",
        "strata scan",
    )


def test_help_browser_alias_routes_to_manual():
    exit_code, output = _run_cli("help", "browser")

    assert exit_code == 0
    _assert_terms(output, "manual", "browser", "safest")


def test_help_unknown_topic_returns_nonzero_and_suggests_help():
    exit_code, output = _run_cli("help", "bogus-topic")

    assert exit_code == 1
    assert "Unknown help topic: bogus-topic" in output
    assert "Try `strata help` for available commands." in output


TESTS = [
    test_help_usage_mentions_all_ai_modes_and_beginner_topics,
    test_help_setup_topic_is_beginner_friendly,
    test_help_manual_topic_is_step_by_step,
    test_help_ollama_topic_is_step_by_step,
    test_help_command_topic_mentions_patch_first_workflow,
    test_help_http_topic_mentions_api_configuration,
    test_help_doctor_topic_mentions_install_diagnostics,
    test_help_install_alias_routes_to_doctor_topic,
    test_help_ask_topic_mentions_setup_and_next_steps,
    test_help_review_topic_mentions_patch_validation,
    test_help_apply_topic_mentions_dry_run_tests_and_gate,
    test_help_run_topic_mentions_fast_confirmation,
    test_help_context_topic_mentions_budget_examples,
    test_help_prepare_topic_mentions_budget_examples,
    test_help_gate_topic_mentions_reports_and_tests,
    test_help_start_topic_mentions_beginner_entrypoint,
    test_help_scan_topic_mentions_scan_states_and_force,
    test_help_status_topic_mentions_scan_readiness,
    test_help_browser_alias_routes_to_manual,
    test_help_unknown_topic_returns_nonzero_and_suggests_help,
]
