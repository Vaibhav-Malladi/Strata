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


def test_only_python_is_parsed_in_first_multilanguage_batch():
    assert parse_source_file("example.js") is None
    assert parse_source_file("example.ts") is None
    assert parse_source_file("Example.java") is None
    assert parse_source_file("main.rs") is None

def test_python_parser_is_registered():
    assert parse_source_file("README.md") is None

TESTS = [
    test_detects_python_files,
    test_detects_javascript_files,
    test_detects_typescript_files,
    test_detects_java_files,
    test_detects_rust_files,
    test_unknown_files_return_none,
    test_only_python_is_parsed_in_first_multilanguage_batch,
    test_python_parser_is_registered,
]