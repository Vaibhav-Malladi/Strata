import os
import sys
import tempfile
from pathlib import Path

TESTS_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.dirname(TESTS_DIR)

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

if TESTS_DIR not in sys.path:
    sys.path.insert(0, TESTS_DIR)

from languages import detect_language, parse_source_file
from python_parser import parse_file
import parsers.python_parser as old_python_parser
import strata.parsers.python_parser as new_python_parser
from tests.helpers import write_file


def test_python_version():
    assert sys.version_info >= (3, 10), "Strata requires Python 3.10 or newer"


def test_new_python_parser_import_matches_legacy_shim():
    assert old_python_parser.parse_file is new_python_parser.parse_file


def test_parse_current_parser_file():
    result = parse_file("python_parser.py")

    assert result["path"] == "python_parser.py"
    assert result["language"] == "python"
    assert "ast" in result["imports"]
    assert result["classes"] == []

    function_names = [function["name"] for function in result["functions"]]
    assert "parse_file" in function_names

    assert "error" not in result


def test_parse_source_file_routes_python_file():
    result = parse_source_file("python_parser.py")

    assert result is not None
    assert result["path"] == "python_parser.py"
    assert result["language"] == "python"

    function_names = [function["name"] for function in result["functions"]]
    assert "parse_file" in function_names


def test_parse_syntax_error_file():
    test_path = "tmp_syntax_error.py"

    try:
        write_file(test_path, "def broken(:\n    pass\n")

        result = parse_file(test_path)

        assert result["path"] == test_path
        assert result["imports"] == []
        assert result["classes"] == []
        assert result["functions"] == []

        assert result["error"]["type"] == "syntax_error"
        assert result["error"]["line"] == 1

    finally:
        if os.path.exists(test_path):
            os.remove(test_path)


def test_language_detection():
    assert detect_language("main.py") == "python"
    assert detect_language("app.js") == "javascript"
    assert detect_language("app.ts") == "typescript"
    assert detect_language("Main.java") == "java"
    assert detect_language("main.rs") == "rust"
    assert detect_language("README.md") is None

def test_parses_python_backend_routes():
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "api.py"
        path.write_text(
            '@app.get("/health")\n'
            'def health_check():\n'
            '    pass\n\n'
            '@router.post("/users")\n'
            'def create_user():\n'
            '    pass\n\n'
            '@router.put("/users/{user_id}")\n'
            'def update_user():\n'
            '    pass\n\n'
            '@app.route("/login", methods=["GET", "POST"])\n'
            'def login():\n'
            '    pass\n\n'
            '@app.route("/status")\n'
            'def status():\n'
            '    pass\n',
            encoding="utf-8",
        )

        parsed = parse_file(str(path))

        route_signatures = [
            (route["method"], route["path"], route["source"])
            for route in parsed["routes"]
        ]

        assert ("GET", "/health", "@app.get") in route_signatures
        assert ("POST", "/users", "@router.post") in route_signatures
        assert ("PUT", "/users/{user_id}", "@router.put") in route_signatures
        assert ("GET,POST", "/login", "@app.route") in route_signatures
        assert ("GET", "/status", "@app.route") in route_signatures

TESTS = [
    test_python_version,
    test_new_python_parser_import_matches_legacy_shim,
    test_parse_current_parser_file,
    test_parse_syntax_error_file,
    test_language_detection,
    test_parse_source_file_routes_python_file,
    test_parses_python_backend_routes,
]
