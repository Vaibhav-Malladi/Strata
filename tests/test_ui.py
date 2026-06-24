from __future__ import annotations

import contextlib
import os
from types import SimpleNamespace

from tests.helpers import capture_output
import tests.run as test_runner
from ui import (
    build_banner,
    color,
    get_console,
    print_next_steps,
    render_banner,
    render_command_header,
    render_kv_table,
    render_lifecycle,
    render_next_steps,
    render_status_card,
    render_wordmark,
    strip_ansi,
    status_spinner,
)


@contextlib.contextmanager
def _forced_env(**updates):
    original = {key: os.environ.get(key) for key in updates}
    try:
        for key, value in updates.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_render_wordmark_includes_title_and_tagline_without_ansi():
    with _forced_env(STRATA_PLAIN="1", STRATA_NO_COLOR="1", CI=None):
        wordmark = render_wordmark()

    assert "Strata" in wordmark
    assert "Local-first repository intelligence for AI-assisted coding" in wordmark
    assert "\x1b[" not in wordmark


def test_render_banner_defaults_to_wordmark():
    with _forced_env(STRATA_PLAIN="1", STRATA_NO_COLOR="1", CI=None):
        banner = render_banner()

    assert "Strata" in banner
    assert "Local-first repository intelligence for AI-assisted coding" in banner


def test_build_banner_defaults_to_compact_title_panel():
    with _forced_env(STRATA_PLAIN="1", STRATA_NO_COLOR="1", CI=None):
        banner = build_banner()

    assert "Strata" in banner
    assert "Local-first repository intelligence for AI-assisted coding" not in banner


def test_render_command_header_compact_shows_command_and_subtitle():
    with _forced_env(STRATA_PLAIN="1", STRATA_NO_COLOR="1", CI=None):
        header = render_command_header("Doctor", "Adapter checks", mode="compact")

    assert "Strata" in header
    assert "Doctor" in header
    assert "Adapter checks" in header


def test_render_kv_table_aligns_keys_and_values():
    with _forced_env(STRATA_PLAIN="1", STRATA_NO_COLOR="1", CI=None):
        table = render_kv_table(
            [
                ("Status", "PASS"),
                ("Output", ".aidc/gate_report.md"),
                ("Mode", 3),
            ]
        )

    lines = table.splitlines()

    assert len(lines) == 3
    assert "Status" in lines[0]
    assert "PASS" in lines[0]
    assert "Output" in lines[1]
    assert ".aidc/gate_report.md" in lines[1]
    assert "Mode" in lines[2]
    assert "3" in lines[2]
    assert lines[0].index("PASS") == lines[1].index(".aidc/gate_report.md") == lines[2].index("3")


def test_render_status_card_includes_status_and_rows():
    with _forced_env(STRATA_PLAIN="1", STRATA_NO_COLOR="1", CI=None):
        card = render_status_card(
            "Adapter doctor",
            [
                ("Adapter", "command"),
                ("Prompt", ".aidc/agent_prompt.md"),
            ],
            status="READY",
        )

    assert "Adapter doctor" in card
    assert "Status" in card
    assert "READY" in card
    assert "Adapter" in card
    assert "command" in card
    assert "Prompt" in card
    assert ".aidc/agent_prompt.md" in card


def test_render_lifecycle_includes_numbered_steps():
    with _forced_env(STRATA_PLAIN="1", STRATA_NO_COLOR="1", CI=None):
        lifecycle = render_lifecycle(
            "Lifecycle",
            [
                "Check adapter readiness",
                "Run configured adapter",
                "Inspect generated patch",
            ],
        )

    assert "Lifecycle" in lifecycle
    assert "1." in lifecycle
    assert "2." in lifecycle
    assert "3." in lifecycle
    assert "Check adapter readiness" in lifecycle
    assert "Run configured adapter" in lifecycle
    assert "Inspect generated patch" in lifecycle


def test_color_disabled_returns_plain_text():
    assert color("hello", "red", enabled=False) == "hello"


def test_color_respects_no_color_env():
    with _forced_env(NO_COLOR="1", STRATA_NO_COLOR=None, STRATA_PLAIN=None, CI=None):
        assert color("hello", "red") == "hello"

    with _forced_env(STRATA_NO_COLOR="1", NO_COLOR=None, STRATA_PLAIN=None, CI=None):
        assert color("hello", "red") == "hello"


def test_strip_ansi_removes_escape_sequences():
    assert strip_ansi("\x1b[31mhello\x1b[0m") == "hello"


def test_status_spinner_noops_in_plain_mode():
    with _forced_env(STRATA_PLAIN="1", STRATA_NO_COLOR="1", STRATA_NO_SPINNER="1", CI=None):
        _, output = capture_output(_exercise_spinner_success)

    assert output == ""


def test_status_spinner_force_mode_uses_real_console():
    with _forced_env(STRATA_PLAIN="1", STRATA_NO_COLOR="1", STRATA_NO_SPINNER=None, STRATA_FORCE_SPINNER="1", CI=None):
        console = get_console(force_spinner=True)

    assert console.__class__.__name__ != "_FallbackConsole"


def test_status_spinner_context_exits_cleanly_on_success():
    with _forced_env(STRATA_PLAIN="1", STRATA_NO_COLOR="1", STRATA_NO_SPINNER="1", CI=None):
        _, output = capture_output(_exercise_spinner_success)

    assert output == ""


def test_status_spinner_context_exits_cleanly_on_exception():
    with _forced_env(STRATA_PLAIN="1", STRATA_NO_COLOR="1", STRATA_NO_SPINNER="1", CI=None):
        _, output = capture_output(_exercise_spinner_exception)

    assert output == ""


def test_render_next_steps_includes_commands():
    with _forced_env(STRATA_PLAIN="1", STRATA_NO_COLOR="1", CI=None):
        steps = render_next_steps(["strata patch", "strata apply --dry-run", "strata apply"])

    assert "Next steps" in steps
    assert "strata patch" in steps
    assert "strata apply --dry-run" in steps
    assert "strata apply" in steps


def test_print_next_steps_smoke():
    with _forced_env(STRATA_PLAIN="1", STRATA_NO_COLOR="1", CI=None):
        _, output = capture_output(print_next_steps, ["strata patch"])

    assert "strata patch" in output


def test_rich_import_works():
    import rich

    assert rich.__name__ == "rich"


def test_render_helpers_handle_none_values():
    with _forced_env(STRATA_PLAIN="1", STRATA_NO_COLOR="1", CI=None):
        card = render_status_card("None check", [("Prompt", None), ("Patch", None)])

    assert "None check" in card
    assert "-" in card

    fake_tests = [lambda: None for _ in range(52)]
    fake_module = SimpleNamespace(__name__="test_fake_module", TESTS=fake_tests)
    original_modules = test_runner.TEST_MODULES

    try:
        test_runner.TEST_MODULES = [fake_module]
        with _forced_env(STRATA_PLAIN="1", STRATA_NO_COLOR="1", CI=None):
            _, output = capture_output(test_runner.main)
    finally:
        test_runner.TEST_MODULES = original_modules

    assert "Strata" in output
    assert "Running tests... 50/52" in output
    assert "Running tests... 52/52" in output
    assert "All tests passed. (52 tests)" in output
    assert "\x1b[" not in output
    assert "test_fake_module" not in output


def _exercise_spinner_success():
    with status_spinner("Working") as spinner:
        spinner.update("Still working")


def _exercise_spinner_exception():
    try:
        with status_spinner("Working") as spinner:
            spinner.update("Still working")
            raise RuntimeError("boom")
    except RuntimeError:
        pass


TESTS = [
    test_render_wordmark_includes_title_and_tagline_without_ansi,
    test_render_banner_defaults_to_wordmark,
    test_build_banner_defaults_to_compact_title_panel,
    test_render_command_header_compact_shows_command_and_subtitle,
    test_render_kv_table_aligns_keys_and_values,
    test_render_status_card_includes_status_and_rows,
    test_render_lifecycle_includes_numbered_steps,
    test_color_disabled_returns_plain_text,
    test_color_respects_no_color_env,
    test_strip_ansi_removes_escape_sequences,
    test_status_spinner_noops_in_plain_mode,
    test_status_spinner_force_mode_uses_real_console,
    test_status_spinner_context_exits_cleanly_on_success,
    test_status_spinner_context_exits_cleanly_on_exception,
    test_render_next_steps_includes_commands,
    test_print_next_steps_smoke,
    test_rich_import_works,
    test_render_helpers_handle_none_values,
]
