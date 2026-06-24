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


def test_help_usage_mentions_all_ai_modes_and_beginner_topics():
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
    assert 'strata review' in output
    assert 'strata apply --dry-run' in output
    assert 'strata apply' in output
    assert 'strata run "<task>"' in output
    assert 'strata help setup' in output
    assert 'strata help ask' in output
    assert 'strata help manual' in output


def test_help_setup_topic_is_beginner_friendly():
    exit_code, output = _run_cli("help", "setup")

    assert exit_code == 0
    assert "Setup chooses how Strata talks to AI." in output
    assert "strata setup" in output
    assert "strata setup --manual" in output
    assert "strata setup --ollama" in output
    assert "strata setup --codex-cli" in output
    assert "strata setup --aider" in output
    assert "strata setup --command" in output
    assert "strata setup --http" in output
    assert "strata setup --show" in output
    assert "strata doctor adapter" in output
    assert output.count("Local-first repository intelligence for AI-assisted coding") == 0


def test_help_manual_topic_is_step_by_step():
    exit_code, output = _run_cli("help", "manual")

    assert exit_code == 0
    assert "Manual/browser AI is the safest first-time mode." in output
    assert "No API key or local model required." in output
    assert ".aidc/agent_prompt.md" in output
    assert "ChatGPT" in output or "Claude" in output or "Gemini" in output
    assert "unified diff" in output
    assert ".aidc/agent_patch.diff" in output
    assert "strata review" in output
    assert "strata apply --dry-run" in output
    assert "strata apply" in output
    assert "strata gate" in output
    assert output.count("Local-first repository intelligence for AI-assisted coding") == 0


def test_help_ollama_topic_is_step_by_step():
    exit_code, output = _run_cli("help", "ollama")

    assert exit_code == 0
    assert "Ollama must be running" in output
    assert "ollama list" in output
    assert "qwen2.5-coder:14b" in output
    assert "strata setup --ollama" in output
    assert "strata config set model" in output
    assert "strata doctor adapter" in output
    assert "strata ask" in output
    assert "strata review" in output
    assert "strata apply --dry-run" in output
    assert "strata apply" in output
    assert output.count("Local-first repository intelligence for AI-assisted coding") == 0


def test_help_command_topic_mentions_patch_first_workflow():
    exit_code, output = _run_cli("help", "command")

    assert exit_code == 0
    assert "Codex CLI" in output
    assert "Aider" in output
    assert "custom script" in output
    assert ".aidc/agent_prompt.md" in output
    assert ".aidc/direct_edit.diff" in output
    assert "git diff" in output
    assert "strata setup --codex-cli" in output
    assert "strata setup --aider" in output
    assert "strata setup --command" in output
    assert 'strata config set command "<your command here>"' in output


def test_help_http_topic_mentions_api_configuration():
    exit_code, output = _run_cli("help", "http")

    assert exit_code == 0
    assert "OpenAI-compatible HTTP API" in output
    assert "strata setup --http" in output
    assert "base_url" in output
    assert "api_key_env" in output
    assert "model" in output
    assert "strata doctor adapter" in output


def test_help_ask_topic_mentions_setup_and_next_steps():
    exit_code, output = _run_cli("help", "ask")

    assert exit_code == 0
    assert "Ask prepares context" in output
    assert "strata setup" in output
    assert "configured AI mode" in output
    assert "does not apply changes directly" in output
    assert ".aidc/agent_patch.diff" in output
    assert "strata review" in output
    assert "strata apply --dry-run" in output
    assert "strata apply" in output
    assert output.count("Local-first repository intelligence for AI-assisted coding") == 0


def test_help_review_topic_mentions_patch_validation():
    exit_code, output = _run_cli("help", "review")

    assert exit_code == 0
    assert "Review inspects `.aidc/agent_patch.diff`" in output
    assert "Patch validity" in output
    assert "Patch targets" in output
    assert "Review is read-only" in output
    assert "strata apply --dry-run" in output


def test_help_apply_topic_mentions_dry_run_tests_and_gate():
    exit_code, output = _run_cli("help", "apply")

    assert exit_code == 0
    assert "Apply is the point where files may change." in output
    assert "strata apply --dry-run" in output
    assert "strata apply" in output
    assert "project tests" in output
    assert "strata gate" in output
    assert "Do not commit until tests pass" in output


def test_help_run_topic_mentions_fast_confirmation():
    exit_code, output = _run_cli("help", "run")

    assert exit_code == 0
    assert "Run is the guided one-command flow" in output
    assert "strata run \"fix bug\"" in output
    assert "strata apply" in output
    assert "strata run --fast \"fix bug\"" in output
    assert "Strata never commits or pushes automatically" in output


def test_help_gate_topic_mentions_reports_and_tests():
    exit_code, output = _run_cli("help", "gate")

    assert exit_code == 0
    assert "Gate is the final validation summary." in output
    assert ".aidc/gate_report.md" in output
    assert ".aidc/gate_report.json" in output
    assert "Gate does not replace your project tests" in output
    assert "Run project tests before commit" in output


def test_help_start_topic_mentions_beginner_entrypoint():
    exit_code, output = _run_cli("help", "start")

    assert exit_code == 0
    assert "Start is the beginner entrypoint" in output
    assert "installed in a project" in output
    assert "Scan the repository" in output
    assert "setup, ask, review, apply, and gate" in output


def test_help_browser_alias_routes_to_manual():
    exit_code, output = _run_cli("help", "browser")

    assert exit_code == 0
    assert "Manual/browser AI is the safest first-time mode." in output
    assert output.count("Local-first repository intelligence for AI-assisted coding") == 0


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
    test_help_ask_topic_mentions_setup_and_next_steps,
    test_help_review_topic_mentions_patch_validation,
    test_help_apply_topic_mentions_dry_run_tests_and_gate,
    test_help_run_topic_mentions_fast_confirmation,
    test_help_gate_topic_mentions_reports_and_tests,
    test_help_start_topic_mentions_beginner_entrypoint,
    test_help_browser_alias_routes_to_manual,
    test_help_unknown_topic_returns_nonzero_and_suggests_help,
]
