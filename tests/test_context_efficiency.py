import contextlib
import os
import tempfile
from pathlib import Path

from commands.context_command import write_context
from context_efficiency import compute_context_efficiency, estimate_tokens
from tests.helpers import capture_output


@contextlib.contextmanager
def change_directory(path: Path):
    original = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(original)


def _create_repo(root: Path) -> None:
    (root / "main.py").write_text(
        "def main():\n"
        "    return 'hello'\n",
        encoding="utf-8",
    )
    (root / "helper.py").write_text(
        "def helper():\n"
        "    return True\n",
        encoding="utf-8",
    )


def test_estimate_tokens_returns_zero_for_empty_text():
    assert estimate_tokens("") == 0


def test_estimate_tokens_rounds_up_for_exact_quarter_blocks():
    assert estimate_tokens("abcd") == 2


def test_estimate_tokens_rounds_up_for_partial_quarter_blocks():
    assert estimate_tokens("abcde") == 2


def test_compute_context_efficiency_returns_zero_reduction_when_baseline_is_zero():
    metrics = compute_context_efficiency(0, 12)

    assert metrics["full_source_tokens"] == 0
    assert metrics["focused_context_tokens"] == 4
    assert metrics["reduction_percent"] == 0


def test_compute_context_efficiency_returns_zero_reduction_when_focused_is_larger():
    metrics = compute_context_efficiency(8, 12)

    assert metrics["full_source_tokens"] == 3
    assert metrics["focused_context_tokens"] == 4
    assert metrics["reduction_percent"] == 0


def test_compute_context_efficiency_calculates_normal_reduction_percent():
    metrics = compute_context_efficiency(16, 8)

    assert metrics["full_source_tokens"] == 5
    assert metrics["focused_context_tokens"] == 3
    assert metrics["reduction_percent"] == 40


def test_write_context_outputs_context_efficiency_section():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        root.mkdir(parents=True, exist_ok=True)
        _create_repo(root)

        with change_directory(root):
            exit_code, output = capture_output(write_context, str(root), "improve main helper flow")

        assert exit_code == 0
        assert "Context Efficiency" in output
        assert "Source files scanned" in output
        assert "Files included" in output
        assert "Full source estimate" in output
        assert "Strata context estimate" in output
        assert "Estimated context reduction" in output
        assert "Actual AI token usage may vary by adapter." in output


TESTS = [
    test_estimate_tokens_returns_zero_for_empty_text,
    test_estimate_tokens_rounds_up_for_exact_quarter_blocks,
    test_estimate_tokens_rounds_up_for_partial_quarter_blocks,
    test_compute_context_efficiency_returns_zero_reduction_when_baseline_is_zero,
    test_compute_context_efficiency_returns_zero_reduction_when_focused_is_larger,
    test_compute_context_efficiency_calculates_normal_reduction_percent,
    test_write_context_outputs_context_efficiency_section,
]
