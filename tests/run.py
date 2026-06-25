import os
import sys
import traceback

try:  # pragma: no cover - rich progress is exercised indirectly.
    from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn
    from rich.table import Column
except Exception:  # pragma: no cover - fallback when Rich is unavailable.
    BarColumn = None
    Progress = None
    SpinnerColumn = None
    TextColumn = None
    TimeElapsedColumn = None
    TimeRemainingColumn = None
    Column = None

TESTS_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.dirname(TESTS_DIR)

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

if TESTS_DIR not in sys.path:
    sys.path.insert(0, TESTS_DIR)

import test_parser
import test_scanner
import test_graph
import test_gate
import test_gate_command
import test_cli_core
import test_adapter_presets
import test_map_writer
import test_brief
import test_cycles
import test_health
import test_impact
import test_brief_impact
import test_test_mapper
import test_preflight
import test_prepare_command
import test_run_command
import test_apply_command
import test_command_executor
import test_execute_command
import test_direct_edit_safety
import test_adapter_doctor
import test_http_executor
import test_http_adapter_contract
import test_ollama_adapter
import test_doctor_command
import test_patch_applier
import test_workflow_config
import test_workflow_planner
import test_config_command
import test_context_command
import test_context_efficiency
import test_agent_export
import test_agent_adapters
import test_status
import test_context_matching
import test_context_pack
import test_selected_context
import test_snapshot
import test_snapshot_command
import test_patch_contract
import test_patch_validator
import test_patch_create_existing_dry_run
import test_patch_command
import test_secret_redaction
import test_ui
import test_diff_engine
import test_verify
import test_verify_command
import test_diff_command
import test_review_command
import test_guided_workflow_commands
import test_ask_inline_review
import test_guided_entrypoint
import test_test_quality
import test_help_topics
import test_scan_command
import test_repo_summary
import test_setup_command
from tests import test_languages
from tests import test_js_resolution
from tests import test_js_parser
from tests import test_javascript_parser
from tests import test_typescript_parser
from tests import test_multilang_scanner
from tests import test_backend_map
from tests import test_routes
from ui import get_console, is_rich_enabled, print_command_header, print_success


_PLAIN_PROGRESS_INTERVAL = 50
_PROGRESS_LABEL_MAX_WIDTH = 60


TEST_MODULES = [
    test_parser,
    test_scanner,
    test_graph,
    test_gate,
    test_gate_command,
    test_cli_core,
    test_adapter_presets,
    test_map_writer,
    test_brief,
    test_cycles,
    test_health,
    test_impact,
    test_brief_impact,
    test_test_mapper,
    test_preflight,
    test_prepare_command,
    test_run_command,
    test_apply_command,
    test_command_executor,
    test_execute_command,
    test_direct_edit_safety,
    test_adapter_doctor,
    test_http_executor,
    test_http_adapter_contract,
    test_ollama_adapter,
    test_doctor_command,
    test_patch_applier,
    test_workflow_config,
    test_workflow_planner,
    test_config_command,
    test_context_command,
    test_context_efficiency,
    test_agent_export,
    test_agent_adapters,
    test_status,
    test_context_matching,
    test_context_pack,
    test_selected_context,
    test_snapshot,
    test_snapshot_command,
    test_patch_contract,
    test_patch_validator,
    test_patch_create_existing_dry_run,
    test_patch_command,
    test_secret_redaction,
    test_ui,
    test_diff_engine,
    test_verify,
    test_verify_command,
    test_diff_command,
    test_review_command,
    test_guided_workflow_commands,
    test_ask_inline_review,
    test_guided_entrypoint,
    test_test_quality,
    test_help_topics,
    test_scan_command,
    test_repo_summary,
    test_setup_command,
    test_languages,
    test_js_resolution,
    test_js_parser,
    test_javascript_parser,
    test_typescript_parser,
    test_multilang_scanner,
    test_backend_map,
    test_routes,
]


def main():
    total_tests = sum(len(module.TESTS) for module in TEST_MODULES)

    print_command_header("Tests", mode="compact")

    total = _run_tests(total_tests)

    print_success(f"All tests passed. ({total} tests)")


def _run_tests(total_tests: int) -> int:
    if total_tests <= 0:
        return 0

    if _supports_rich_progress():
        return _run_tests_with_rich_progress(total_tests)

    return _run_tests_with_plain_progress(total_tests)


def _supports_rich_progress() -> bool:
    return (
        Progress is not None
        and TextColumn is not None
        and BarColumn is not None
        and TimeElapsedColumn is not None
        and TimeRemainingColumn is not None
        and Column is not None
        and is_rich_enabled()
    )


def _run_tests_with_rich_progress(total_tests: int) -> int:
    console = get_console()
    columns = []

    if SpinnerColumn is not None and not _env_flag("STRATA_NO_SPINNER"):
        columns.append(SpinnerColumn())

    columns.extend(
        [
            TextColumn("[bold cyan]{task.description}", table_column=Column(width=14, no_wrap=True)),
            BarColumn(table_column=Column(min_width=20, ratio=1)),
            TextColumn("{task.completed}/{task.total}", table_column=Column(width=9, no_wrap=True)),
            TimeElapsedColumn(table_column=Column(width=8, no_wrap=True)),
            TimeRemainingColumn(compact=True, table_column=Column(width=8, no_wrap=True)),
            TextColumn(
                "[dim]{task.fields[label]}",
                table_column=Column(ratio=2, min_width=20, max_width=_PROGRESS_LABEL_MAX_WIDTH, overflow="ellipsis"),
            ),
        ]
    )

    total = 0
    with Progress(*columns, console=console, transient=True, refresh_per_second=12, expand=True) as progress:
        task_id = progress.add_task("Running tests", total=total_tests, label="")
        for module in TEST_MODULES:
            module_label = _format_module_label(module)
            for test in module.TESTS:
                test_label = _format_test_label(test)
                progress.update(task_id, label=shorten_test_name(f"{module_label}::{test_label}"))
                try:
                    test()
                except Exception:
                    _print_failure(module_label, test_label)
                    raise
                total += 1
                progress.advance(task_id)

    return total


def _run_tests_with_plain_progress(total_tests: int) -> int:
    total = 0
    next_report = _PLAIN_PROGRESS_INTERVAL

    for module in TEST_MODULES:
        module_label = _format_module_label(module)
        for test in module.TESTS:
            test_label = _format_test_label(test)
            try:
                test()
            except Exception:
                _print_failure(module_label, test_label)
                raise

            total += 1

            if total >= next_report or total == total_tests:
                print(f"Running tests... {total}/{total_tests}")
                while next_report <= total:
                    next_report += _PLAIN_PROGRESS_INTERVAL

    return total


def _print_failure(module_label: str, test_label: str) -> None:
    print(f"Failed test: {module_label}.{test_label}")
    traceback.print_exc()


def _format_module_label(module) -> str:
    return str(getattr(module, "__name__", "module"))


def _format_test_label(test) -> str:
    return str(getattr(test, "__name__", "test"))


def shorten_test_name(name: str, max_width: int = 60) -> str:
    normalized = str(name or "").strip()

    if len(normalized) <= max_width:
        return normalized

    if max_width <= 3:
        return normalized[:max_width]

    if "::" in normalized:
        _, suffix = normalized.rsplit("::", 1)
        if len(suffix) <= max_width - 5:
            return f"...::{suffix}"
        if len(suffix) <= max_width - 3:
            return f"...{suffix}"
        suffix_width = max_width - 3
        return f"...{suffix[-suffix_width:]}"

    suffix_width = max_width - 3
    return f"...{normalized[-suffix_width:]}"


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    main()
