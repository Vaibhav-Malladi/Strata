from python_parser import parse_file as parse_python_file


def detect_language(path: str) -> str | None:
    """
    Detect the programming language from the file extension.
    """

    if path.endswith(".py"):
        return "python"

    return None


def parse_source_file(path: str) -> dict | None:
    """
    Parse a source file using the correct language parser.

    Returns None if the file language is not supported yet.
    """

    language = detect_language(path)

    if language == "python":
        return parse_python_file(path)

    return None