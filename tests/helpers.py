import contextlib
import io
import os
import tempfile
from pathlib import Path


def run_silently(function, *args):
    output = io.StringIO()

    with contextlib.redirect_stdout(output):
        result = function(*args)

    return result


def capture_output(function, *args):
    output = io.StringIO()

    with contextlib.redirect_stdout(output):
        result = function(*args)

    return result, output.getvalue()


def write_file(path, content):
    with open(path, "w", encoding="utf-8") as file:
        file.write(content)


@contextlib.contextmanager
def change_directory(path: Path):
    original = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(original)


@contextlib.contextmanager
def temporary_repo(files: dict[str, str] | None = None):
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        root.mkdir(parents=True, exist_ok=True)

        for relative_path, content in (files or {}).items():
            file_path = root / relative_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")

        yield root
