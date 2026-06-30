import os
import sys


USE_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def color(text: str, code: str) -> str:
    if not USE_COLOR:
        return text

    return f"\033[{code}m{text}\033[0m"


def green(text: str) -> str:
    return color(text, "32")


def yellow(text: str) -> str:
    return color(text, "33")


def red(text: str) -> str:
    return color(text, "31")


def cyan(text: str) -> str:
    return color(text, "36")


def dim(text: str) -> str:
    return color(text, "90")


def bold(text: str) -> str:
    return color(text, "1")


def print_title(title: str) -> None:
    print()
    print(bold(cyan(title)))
    print(dim("─" * len(title)))


def print_kv(label: str, value) -> None:
    print(f"  {dim(label.ljust(18))} {value}")


def print_list(label: str, values: list[str]) -> None:
    if values:
        print_kv(label, ", ".join(values))
    else:
        print_kv(label, dim("none"))
