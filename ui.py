from __future__ import annotations

from contextlib import contextmanager
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Sequence

APP_NAME = "Strata"
TAGLINE = "Local-first repository intelligence for AI-assisted coding"

_SUCCESS_SYMBOL = "✓"
_WARNING_SYMBOL = "!"
_ERROR_SYMBOL = "✗"
_INFO_SYMBOL = "•"
_RUNNING_SYMBOL = "…"
_ARROW = "→"
_SEPARATOR = "─"

_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_TRUE_VALUES = {"1", "true", "yes", "on"}

_WORDMARK_LINES = [
    "███████╗████████╗██████╗  █████╗ ████████╗ █████╗",
    "██╔════╝╚══██╔══╝██╔══██╗██╔══██╗╚══██╔══╝██╔══██╗",
    "███████╗   ██║   ██████╔╝███████║   ██║   ███████║",
    "╚════██║   ██║   ██╔══██╗██╔══██║   ██║   ██╔══██║",
    "███████║   ██║   ██║  ██║██║  ██║   ██║   ██║  ██║",
    "╚══════╝   ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═╝",
]

try:  # pragma: no cover - exercised indirectly when Rich is available.
    from rich import box
    from rich.align import Align
    from rich.console import Console
    from rich.panel import Panel
    from rich.rule import Rule
    from rich.table import Table
    from rich.text import Text
except Exception:  # pragma: no cover - fallback when Rich is unavailable.
    box = None
    Align = None
    Console = None
    Panel = None
    Rule = None
    Table = None
    Text = None


def supports_ansi(stream=None) -> bool:
    stream = sys.stdout if stream is None else stream

    if not hasattr(stream, "isatty"):
        return False

    try:
        if not stream.isatty():
            return False
    except Exception:
        return False

    if os.environ.get("TERM", "").strip().lower() == "dumb":
        return False

    return True


def use_color(stream=None) -> bool:
    if _env_flag("STRATA_PLAIN") or _env_flag("STRATA_NO_COLOR") or _env_flag("NO_COLOR") or _env_flag("CI"):
        return False

    return supports_ansi(stream)


def _supports_unicode_output(stream=None) -> bool:
    stream = sys.stdout if stream is None else stream
    encoding = getattr(stream, "encoding", None)

    if not encoding:
        return True

    normalized = str(encoding).strip().lower().replace("_", "-")
    return normalized.startswith("utf-") or normalized == "cp65001"


def is_rich_enabled(stream=None) -> bool:
    if Console is None or Panel is None or Table is None or Text is None or Align is None or box is None:
        return False

    if _env_flag("STRATA_PLAIN") or _env_flag("CI"):
        return False

    if not _supports_unicode_output(stream):
        return False

    return supports_ansi(stream)


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def color(text: str, style: str, enabled: bool | None = None) -> str:
    if enabled is None:
        enabled = use_color()

    if not enabled:
        return text

    styles = {
        "bold": "1",
        "dim": "2",
        "red": "31",
        "green": "32",
        "yellow": "33",
        "blue": "34",
        "magenta": "35",
        "cyan": "36",
        "white": "37",
        "bright_black": "90",
    }

    codes = [styles[token] for token in style.split() if token in styles]

    if not codes:
        return text

    return f"\033[{';'.join(codes)}m{text}\033[0m"


def symbol(name: str) -> str:
    normalized = str(name or "").strip().lower()

    if _supports_unicode_output():
        symbols = {
            "success": _SUCCESS_SYMBOL,
            "done": _SUCCESS_SYMBOL,
            "pass": _SUCCESS_SYMBOL,
            "ready": _SUCCESS_SYMBOL,
            "ok": _SUCCESS_SYMBOL,
            "failure": _ERROR_SYMBOL,
            "fail": _ERROR_SYMBOL,
            "error": _ERROR_SYMBOL,
            "warn": _WARNING_SYMBOL,
            "warning": _WARNING_SYMBOL,
            "info": _INFO_SYMBOL,
            "running": _RUNNING_SYMBOL,
            "pending": _INFO_SYMBOL,
            "skipped": "-",
        }
    else:
        symbols = {
            "success": "+",
            "done": "+",
            "pass": "+",
            "ready": "+",
            "ok": "+",
            "failure": "x",
            "fail": "x",
            "error": "x",
            "warn": "!",
            "warning": "!",
            "info": "i",
            "running": ">",
            "pending": "i",
            "skipped": "-",
        }

    return symbols.get(normalized, normalized[:1] if normalized else "")


def render_wordmark() -> str:
    return _render_wordmark(subtitle=None, compact=False)


def print_wordmark(subtitle: str | None = None, compact: bool = False) -> None:
    print(_render_wordmark(subtitle=subtitle, compact=compact))


def render_banner(title: str = APP_NAME, subtitle: str | None = None, compact: bool = False) -> str:
    if compact:
        return _render_banner_text(title, subtitle)

    if title == APP_NAME and subtitle is None:
        return render_wordmark()

    return _render_banner_text(title, subtitle)


def render_section(title: str) -> str:
    if is_rich_enabled():
        return _render_rich(_build_section_renderable(title))

    separator_char = _SEPARATOR if _supports_unicode_output() else "-"
    separator = separator_char * max(len(strip_ansi(title)), 1)
    return f"{title}\n{separator}"


def render_kv_table(rows: list[tuple[str, object]] | Sequence[tuple[str, object]]) -> str:
    normalized_rows = [_normalize_row(row) for row in rows]

    if not normalized_rows:
        return ""

    if is_rich_enabled():
        return _render_rich(_build_kv_table_renderable(normalized_rows))

    label_width = max(len(strip_ansi(label)) for label, _ in normalized_rows)
    return "\n".join(f"{label.ljust(label_width)}  {value}" for label, value in normalized_rows)


def render_status_card(
    title: str,
    rows: list[tuple[str, object]] | Sequence[tuple[str, object]],
    status: str | None = None,
) -> str:
    return render_result_panel(title, status or "", rows)


def render_next_steps(steps: list[str] | Sequence[str]) -> str:
    normalized_steps = [str(step).strip() for step in steps if str(step).strip()]

    if not normalized_steps:
        return ""

    if is_rich_enabled():
        return _render_rich(_build_next_steps_renderable(normalized_steps))

    arrow = _ARROW if _supports_unicode_output() else "->"
    lines = [render_section("Next steps")]
    lines.extend(f"{arrow} {step}" for step in normalized_steps)
    return "\n".join(lines)


def render_step(name: str, status: str, detail: str | None = None) -> str:
    text = f"{symbol(status)} {name}"

    if detail:
        text = f"{text} - {detail}"

    return text


def render_command_header(command_name: str, subtitle: str | None = None, mode: str = "normal") -> str:
    if mode == "compact":
        heading = command_name.strip() or APP_NAME
        if subtitle:
            heading = f"{heading}  {subtitle.strip()}"

        return _render_wordmark(subtitle=heading, compact=True)

    header = _render_wordmark(subtitle=subtitle, compact=False)

    if command_name:
        header = f"{header}\n{render_divider(command_name)}"

    return header


def render_lifecycle(title: str, steps: Sequence[str]) -> str:
    normalized_steps = [str(step).strip() for step in steps if str(step).strip()]

    if is_rich_enabled():
        return _render_rich(_build_lifecycle_renderable(title, normalized_steps))

    lines = [render_section(title)]
    lines.extend(f"{index}. {step}" for index, step in enumerate(normalized_steps, start=1))
    return "\n".join(lines)


def render_result_panel(
    title: str,
    status: str,
    rows: list[tuple[str, object]] | Sequence[tuple[str, object]],
    next_steps: list[str] | Sequence[str] | None = None,
) -> str:
    normalized_rows = [_normalize_row(row) for row in rows]
    status_text = _stringify(status)

    if status_text:
        normalized_rows = [("Status", status_text), *normalized_rows]

    if is_rich_enabled():
        parts = [_render_rich(_build_result_panel_renderable(title, normalized_rows, status_text))]
        if next_steps:
            footer = render_footer_hint("\n".join(f"{_ARROW} {step}" for step in next_steps))
            if footer:
                parts.append(footer)
        return "\n".join(part for part in parts if part)

    parts = [render_section(title), render_kv_table(normalized_rows)]
    if next_steps:
        footer = render_footer_hint("\n".join(f"{_ARROW} {step}" for step in next_steps))
        if footer:
            parts.append(footer)
    return "\n".join(part for part in parts if part)


def render_metric_row(label: str, value: object, style: str | None = None) -> str:
    normalized_label = _stringify(label)
    normalized_value = _stringify(value)

    if is_rich_enabled():
        return _render_rich(_build_metric_row_renderable(normalized_label, normalized_value, style))

    return f"{normalized_label:<18} {normalized_value}"


def render_divider(label: str | None = None) -> str:
    if is_rich_enabled() and Rule is not None:
        return _render_rich(Rule(label or "", style="cyan" if use_color() else None))

    if label:
        separator_char = _SEPARATOR if _supports_unicode_output() else "-"
        separator = separator_char * max(3, 36 - len(strip_ansi(label)))
        return f"{label} {separator}"

    separator_char = _SEPARATOR if _supports_unicode_output() else "-"
    return separator_char * 36


def render_footer_hint(text: str) -> str:
    normalized = str(text or "").strip()

    if not normalized:
        return ""

    if is_rich_enabled():
        return _render_rich(_build_footer_hint_renderable(normalized))

    return normalized


def print_banner(title: str = APP_NAME, subtitle: str | None = None, compact: bool = True) -> None:
    print(render_banner(title, subtitle, compact=compact))


def print_section(title: str) -> None:
    print(render_section(title))


def print_kv_table(title: str, rows: list[tuple[str, object]] | Sequence[tuple[str, object]]) -> None:
    print(render_result_panel(title, "", rows))


def print_status_card(
    title: str,
    rows: list[tuple[str, object]] | Sequence[tuple[str, object]],
    status: str | None = None,
) -> None:
    print(render_status_card(title, rows, status=status))


def print_next_steps(steps: list[str] | Sequence[str]) -> None:
    output = render_next_steps(list(steps))

    if output:
        print(output)


def print_error(message: str) -> None:
    print(format_error(message))


def print_warning(message: str) -> None:
    print(format_warning(message))


def print_success(message: str) -> None:
    print(format_success(message))


def print_command_header(command_name: str, subtitle: str | None = None, mode: str = "normal") -> None:
    print(render_command_header(command_name, subtitle=subtitle, mode=mode))


def print_lifecycle(title: str, steps: Sequence[str]) -> None:
    print(render_lifecycle(title, steps))


def print_result_panel(
    title: str,
    status: str,
    rows: list[tuple[str, object]] | Sequence[tuple[str, object]],
    next_steps: list[str] | Sequence[str] | None = None,
) -> None:
    print(render_result_panel(title, status, rows, next_steps=next_steps))


def print_metric_row(label: str, value: object, style: str | None = None) -> None:
    print(render_metric_row(label, value, style=style))


def print_divider(label: str | None = None) -> None:
    print(render_divider(label))


def print_footer_hint(text: str) -> None:
    print(render_footer_hint(text))


@contextmanager
def status_spinner(message: str, enabled: bool | None = None, stream=None):
    stream = sys.stdout if stream is None else stream
    should_enable = _status_enabled(enabled, stream)

    if not should_enable:
        yield _NullSpinner()
        return

    console = get_console(stream, force_spinner=_env_flag("STRATA_FORCE_SPINNER"))

    with console.status(message, spinner="dots") as status:
        yield _ConsoleSpinner(status)


class Spinner:
    def __init__(self, message: str, enabled: bool | None = None, stream=None):
        self._message = message
        self._enabled = enabled
        self._stream = stream
        self._spinner = None

    def __enter__(self):
        self._context = status_spinner(self._message, enabled=self._enabled, stream=self._stream)
        self._spinner = self._context.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb):
        return self._context.__exit__(exc_type, exc, tb)

    def update(self, message: str) -> None:
        if self._spinner is not None:
            self._spinner.update(message)


def get_console(stream=None, force_spinner: bool = False):
    stream = sys.stdout if stream is None else stream

    if Console is None:
        return _FallbackConsole(stream)

    rich_enabled = is_rich_enabled(stream)
    if not rich_enabled and not force_spinner:
        return _FallbackConsole(stream)

    color_system = "standard" if use_color(stream) else None
    width = shutil.get_terminal_size(fallback=(88, 20)).columns if supports_ansi(stream) else 88

    return Console(
        file=stream,
        force_terminal=True,
        color_system=color_system,
        width=width,
        highlight=False,
        legacy_windows=False,
    )


def build_banner() -> str:
    return render_banner(compact=True)


def build_section(title: str) -> str:
    return render_section(title)


def build_kv_table(rows: Sequence[tuple[str, object]]) -> str:
    return render_kv_table(list(rows))


def format_status(status: str) -> str:
    normalized = str(status or "").strip()

    if not normalized:
        return ""

    upper = normalized.upper()

    if upper == "PASS":
        return f"{symbol('pass')} PASS"

    if upper in {"WARN", "WARNING"}:
        return f"{symbol('warn')} WARN"

    if upper in {"FAIL", "ERROR"}:
        return f"{symbol('fail')} FAIL"

    if upper == "READY":
        return f"{symbol('ready')} READY"

    return upper


def format_success(message: str) -> str:
    return f"{symbol('success')} {message}"


def format_warning(message: str) -> str:
    return f"{symbol('warning')} {message}"


def format_error(message: str) -> str:
    return f"{symbol('error')} {message}"


def format_path(path: str | Path) -> str:
    return str(path)


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUE_VALUES


def _status_style(status: str | None) -> str:
    normalized = _stringify(status).lower()

    if any(token in normalized for token in ("fail", "error", "invalid", "failed")):
        return "red"

    if any(token in normalized for token in ("warn", "empty", "missing", "manual", "skip", "dry run", "not ready")):
        return "yellow"

    if any(token in normalized for token in ("pass", "ready", "valid", "applied", "done")):
        return "green"

    return "cyan"


def _status_enabled(enabled: bool | None, stream) -> bool:
    if enabled is False:
        return False

    if _env_flag("STRATA_NO_SPINNER"):
        return False

    if _env_flag("STRATA_FORCE_SPINNER"):
        return Console is not None

    if _env_flag("STRATA_PLAIN") or _env_flag("CI"):
        return False

    return supports_ansi(stream) and Console is not None


def _normalize_row(row: tuple[str, object]) -> tuple[str, object]:
    label, value = row
    return _stringify(label), _stringify(value)


def _stringify(value: object) -> str:
    if value is None:
        return "-"

    text = str(value).replace("\r\n", "\n").replace("\r", "\n").strip()

    if not text:
        return "-"

    if "\n" in text:
        compact = " | ".join(part.strip() for part in text.split("\n") if part.strip())
        return compact or "-"

    return text


def _render_rich(renderable) -> str:
    console = get_console()

    if isinstance(console, _FallbackConsole):
        return ""

    with console.capture() as capture:
        console.print(renderable)

    return capture.get().rstrip()


def _render_wordmark(subtitle: str | None, compact: bool) -> str:
    if compact:
        line = APP_NAME if subtitle is None else f"{APP_NAME}  {subtitle}"
        if is_rich_enabled():
            return _render_rich(
                Panel(
                    Text(line, style="bold cyan" if use_color() else "bold"),
                    box=box.SQUARE,
                    border_style="cyan" if use_color() else None,
                    padding=(0, 1),
                    expand=False,
                )
            )
        return line

    if _supports_unicode_output():
        art_lines = [*_WORDMARK_LINES, APP_NAME]
        if subtitle:
            art_lines.append(subtitle)
        else:
            art_lines.append(TAGLINE)
    else:
        art_lines = [APP_NAME, subtitle or TAGLINE]

    if is_rich_enabled():
        text = Text()
        for index, line in enumerate(art_lines):
            if index:
                text.append("\n")
            style = "cyan" if index < len(_WORDMARK_LINES) else ("bold" if index == len(_WORDMARK_LINES) else "dim")
            text.append(line, style=style if use_color() else "")

        return _render_rich(
            Panel(
                Align.center(text),
                box=box.SQUARE,
                border_style="cyan" if use_color() else None,
                padding=(0, 2),
                expand=False,
            )
        )

    return "\n".join(art_lines)


def _render_banner_text(title: str, subtitle: str | None) -> str:
    lines = [title]
    if subtitle:
        lines.append(subtitle)

    if is_rich_enabled():
        text = Text()
        for index, line in enumerate(lines):
            if index:
                text.append("\n")
            text.append(line, style="bold cyan" if index == 0 else "dim")

        return _render_rich(
            Panel(
                Align.center(text),
                box=box.SQUARE,
                border_style="cyan" if use_color() else None,
                padding=(0, 2),
                expand=False,
            )
        )

    width = max(len(strip_ansi(line)) for line in lines)
    divider = _SEPARATOR * (width + 4)
    body = [f"  {line.ljust(width)}  " for line in lines]
    return "\n".join([divider, *body, divider])


def _build_section_renderable(title: str):
    separator = _SEPARATOR * max(len(strip_ansi(title)), 1)
    text = Text(title, style="bold cyan" if use_color() else "bold")
    text.append("\n")
    text.append(separator, style="dim" if use_color() else "")
    return text


def _build_kv_table_renderable(rows: Sequence[tuple[str, object]]):
    table = Table.grid(expand=False, padding=(0, 2))
    table.add_column(justify="right", style="bold" if use_color() else "", no_wrap=True)
    table.add_column()

    for label, value in rows:
        table.add_row(label, value)

    return table


def _build_result_panel_renderable(
    title: str,
    rows: Sequence[tuple[str, object]],
    status: str,
):
    table = Table.grid(expand=False, padding=(0, 2))
    table.add_column(justify="right", style="bold" if use_color() else "", no_wrap=True)
    table.add_column()

    for label, value in rows:
        table.add_row(label, value)

    return Panel(
        table,
        title=title,
        title_align="left",
        box=box.SQUARE,
        border_style=_status_style(status) if use_color() else None,
        padding=(0, 1),
        expand=False,
    )


def _build_lifecycle_renderable(title: str, steps: Sequence[str]):
    table = Table.grid(expand=False, padding=(0, 2))
    table.add_column(style="bold" if use_color() else "", no_wrap=True)
    table.add_column()

    for index, step in enumerate(steps, start=1):
        table.add_row(f"{index}.", step)

    return Panel(
        table,
        title=title,
        title_align="left",
        box=box.SQUARE,
        border_style="cyan" if use_color() else None,
        padding=(0, 1),
        expand=False,
    )


def _build_next_steps_renderable(steps: Sequence[str]):
    table = Table.grid(expand=False)
    table.add_column(no_wrap=True)

    for step in steps:
        table.add_row(step)

    return Panel(
        table,
        title="Next steps",
        title_align="left",
        box=box.SQUARE,
        border_style="cyan" if use_color() else None,
        padding=(0, 1),
        expand=False,
    )


def _build_metric_row_renderable(label: str, value: str, style: str | None):
    table = Table.grid(expand=False, padding=(0, 2))
    table.add_column(justify="right", style="bold" if use_color() else "", no_wrap=True)
    table.add_column(style=style or "")
    table.add_row(label, value)
    return table


def _build_footer_hint_renderable(text: str):
    return Panel(
        Text(text, style="dim" if use_color() else ""),
        box=box.SQUARE,
        border_style="bright_black" if use_color() else None,
        padding=(0, 1),
        expand=False,
    )


class _FallbackConsole:
    def __init__(self, stream=None):
        self._stream = sys.stdout if stream is None else stream

    def print(self, *objects, sep=" ", end="\n") -> None:
        print(*objects, sep=sep, end=end, file=self._stream)

    @contextmanager
    def status(self, message: str, spinner: str = "dots"):
        yield _NullSpinner()


class _NullSpinner:
    def update(self, message: str) -> None:
        return None


class _ConsoleSpinner:
    def __init__(self, status):
        self._status = status

    def update(self, message: str) -> None:
        self._status.update(message)
