"""Guard against brittle prose assertions in tests.

Behavior tests should stay strict for commands, flags, file paths, JSON keys, and exit codes.
Help, README, installer, and onboarding copy should be checked by concepts so wording can evolve.
"""

from __future__ import annotations

import ast
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent

_SUSPICIOUS_TARGETS = (
    "output",
    "text",
    "content",
    "readme",
    "help",
    "install",
    "prompt",
    "usage",
    "banner",
)

_COMMANDISH_MARKERS = (
    "`",
    ".aidc/",
    "strata ",
    "py -m",
    "pip ",
    "git ",
    "shutil.which(",
    "read-host",
    "get-command",
    "--",
    "->",
    "<",
    ">",
)


def _assert_no_brittle_prose_assertions() -> None:
    findings: list[str] = []

    for path in sorted(TESTS_DIR.glob("test_*.py")):
        if path.name == Path(__file__).name:
            continue

        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as error:
            findings.append(f"{path.name}:{error.lineno or '?'}: syntax error: {error.msg}")
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.Assert) or node.test is None:
                continue

            snippet = ast.get_source_segment(source, node.test) or ""
            if not any(target in snippet for target in _SUSPICIOUS_TARGETS):
                continue

            for literal in _iter_string_literals(node.test):
                value = literal.strip()
                if len(value) < 80:
                    continue
                if _looks_commandish(value):
                    continue
                if not _looks_like_prose(value):
                    continue

                findings.append(f"{path.name}:{node.lineno}: {value}")

    assert not findings, (
        "Suspicious prose assertions found in tests. "
        "Use concept checks for help/README/installer/onboarding copy instead of exact prose.\n"
        + "\n".join(findings)
    )


def _iter_string_literals(node: ast.AST):
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            yield child.value


def _looks_like_prose(text: str) -> bool:
    words = text.split()
    return len(words) >= 8 or any(punctuation in text for punctuation in (".", "!", "?"))


def _looks_commandish(text: str) -> bool:
    normalized = text.lower()
    return any(marker in normalized for marker in _COMMANDISH_MARKERS)


TESTS = [
    _assert_no_brittle_prose_assertions,
]
