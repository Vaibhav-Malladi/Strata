import tempfile
from pathlib import Path

from parsers.javascript_parser import parse_file


def write_file(folder: str, name: str, content: str) -> Path:
    path = Path(folder) / name
    path.write_text(content, encoding="utf-8")
    return path


def test_parses_javascript_imports():
    with tempfile.TemporaryDirectory() as temp_dir:
        path = write_file(
            temp_dir,
            "app.js",
            '''
import React from "react";
import { helper } from "./helper";
import "./styles.css";
const fs = require("fs");
            '''.strip(),
        )

        parsed = parse_file(str(path))

        assert parsed["language"] == "javascript"
        assert "react" in parsed["imports"]
        assert "./helper" in parsed["imports"]
        assert "./styles.css" in parsed["imports"]
        assert "fs" in parsed["imports"]


def test_parses_javascript_symbols():
    with tempfile.TemporaryDirectory() as temp_dir:
        path = write_file(
            temp_dir,
            "symbols.js",
            '''
export function run() {
}

function helper() {
}

const build = () => {
};

const makeThing = function() {
};

export default class App {
}

class UserService {
}
            '''.strip(),
        )

        parsed = parse_file(str(path))

        function_names = [item["name"] for item in parsed["functions"]]
        class_names = [item["name"] for item in parsed["classes"]]

        assert "run" in function_names
        assert "helper" in function_names
        assert "build" in function_names
        assert "makeThing" in function_names
        assert "App" in class_names
        assert "UserService" in class_names


def test_records_javascript_exports():
    with tempfile.TemporaryDirectory() as temp_dir:
        path = write_file(
            temp_dir,
            "exports.js",
            '''
export function run() {
}

export default class App {
}

export { run };
            '''.strip(),
        )

        parsed = parse_file(str(path))

        assert len(parsed["exports"]) == 3
        assert parsed["exports"][0]["line"] == 1


def test_javascript_read_error_is_reported():
    parsed = parse_file("missing-file.js")

    assert parsed["language"] == "javascript"
    assert parsed["error"]["type"] == "read_error"


TESTS = [
    test_parses_javascript_imports,
    test_parses_javascript_symbols,
    test_records_javascript_exports,
    test_javascript_read_error_is_reported,
]