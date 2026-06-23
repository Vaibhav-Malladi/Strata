from parsers.javascript_parser import parse_file as parse_javascript_file
from parsers.python_parser import parse_file as parse_python_file
from parsers.typescript_parser import parse_file as parse_typescript_file


LANGUAGE_BY_EXTENSION = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".rs": "rust",
}


PARSER_BY_LANGUAGE = {
    "python": parse_python_file,
    "javascript": parse_javascript_file,
    "typescript": parse_typescript_file,
}


def detect_language(path: str) -> str | None:
    """
    Detect the programming language from the file extension.
    """

    normalized_path = path.lower()

    for extension, language in LANGUAGE_BY_EXTENSION.items():
        if normalized_path.endswith(extension):
            return language

    return None


def parse_source_file(path: str) -> dict | None:
    """
    Parse a source file using the correct language parser.

    Returns None if the file language is detected but no parser is wired yet.
    """

    language = detect_language(path)

    if language is None:
        return None

    parser = PARSER_BY_LANGUAGE.get(language)

    if parser is None:
        return None

    return parser(path)