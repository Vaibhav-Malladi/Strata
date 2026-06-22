import contextlib
import io


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