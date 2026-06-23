from languages import detect_language, parse_source_file


def test_detects_python_files():
    assert detect_language("main.py") == "python"
    assert detect_language("src\\app.py") == "python"


def test_detects_javascript_files():
    assert detect_language("index.js") == "javascript"
    assert detect_language("component.jsx") == "javascript"
    assert detect_language("server.mjs") == "javascript"
    assert detect_language("config.cjs") == "javascript"


def test_detects_typescript_files():
    assert detect_language("app.ts") == "typescript"
    assert detect_language("component.tsx") == "typescript"


def test_detects_java_files():
    assert detect_language("Main.java") == "java"
    assert detect_language("src\\main\\java\\App.java") == "java"


def test_detects_rust_files():
    assert detect_language("main.rs") == "rust"
    assert detect_language("src\\lib.rs") == "rust"


def test_unknown_files_return_none():
    assert detect_language("README.md") is None
    assert detect_language("styles.css") is None
    assert detect_language("data.json") is None


def test_unwired_languages_are_not_parsed_yet():
    assert parse_source_file("Example.java") is None
    assert parse_source_file("main.rs") is None

def test_python_parser_is_registered():
    assert parse_source_file("README.md") is None

def test_javascript_and_typescript_parsers_are_registered():
    js_result = parse_source_file("missing-file.js")
    ts_result = parse_source_file("missing-file.ts")

    assert js_result["language"] == "javascript"
    assert js_result["error"]["type"] == "read_error"

    assert ts_result["language"] == "typescript"
    assert ts_result["error"]["type"] == "read_error"

TESTS = [
    test_detects_python_files,
    test_detects_javascript_files,
    test_detects_typescript_files,
    test_detects_java_files,
    test_detects_rust_files,
    test_unknown_files_return_none,
    test_unwired_languages_are_not_parsed_yet,
    test_python_parser_is_registered,
    test_javascript_and_typescript_parsers_are_registered,
]