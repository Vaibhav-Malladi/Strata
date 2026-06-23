import tempfile
from pathlib import Path

from scanner import scan_repo


def write_file(folder: str, relative_path: str, content: str) -> Path:
    path = Path(folder) / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def get_file_by_name(graph: dict, file_name: str) -> dict:
    for file_info in graph["files"]:
        if file_info["path"].endswith(file_name):
            return file_info

    raise AssertionError(f"File not found in graph: {file_name}")


def has_edge(graph: dict, from_name: str, to_name: str, import_name: str) -> bool:
    for edge in graph["edges"]:
        if (
            edge["from"].endswith(from_name)
            and edge["to"].endswith(to_name)
            and edge["import"] == import_name
        ):
            return True

    return False


def test_scanner_includes_javascript_files():
    with tempfile.TemporaryDirectory() as temp_dir:
        write_file(
            temp_dir,
            "app.js",
            '''
import { helper } from "./helper";

export function run() {
    helper();
}
            '''.strip(),
        )
        write_file(
            temp_dir,
            "helper.js",
            '''
export function helper() {
}
            '''.strip(),
        )

        graph = scan_repo(temp_dir)

        app = get_file_by_name(graph, "app.js")
        helper = get_file_by_name(graph, "helper.js")

        assert app["language"] == "javascript"
        assert helper["language"] == "javascript"
        assert "./helper" in app["imports"]


def test_scanner_resolves_javascript_relative_edges():
    with tempfile.TemporaryDirectory() as temp_dir:
        write_file(
            temp_dir,
            "app.js",
            '''
import { helper } from "./helper";

export function run() {
    helper();
}
            '''.strip(),
        )
        write_file(
            temp_dir,
            "helper.js",
            '''
export function helper() {
}
            '''.strip(),
        )

        graph = scan_repo(temp_dir)

        assert has_edge(graph, "app.js", "helper.js", "./helper")


def test_scanner_resolves_javascript_index_edges():
    with tempfile.TemporaryDirectory() as temp_dir:
        write_file(
            temp_dir,
            "app.js",
            '''
import { Button } from "./components/Button";
            '''.strip(),
        )
        write_file(
            temp_dir,
            "components/Button/index.jsx",
            '''
export function Button() {
}
            '''.strip(),
        )

        graph = scan_repo(temp_dir)

        assert has_edge(
            graph,
            "app.js",
            "components\\Button\\index.jsx",
            "./components/Button",
        ) or has_edge(
            graph,
            "app.js",
            "components/Button/index.jsx",
            "./components/Button",
        )


def test_scanner_includes_typescript_files():
    with tempfile.TemporaryDirectory() as temp_dir:
        write_file(
            temp_dir,
            "app.ts",
            '''
import { UserService } from "./user.service";

export class AppComponent {
}
            '''.strip(),
        )
        write_file(
            temp_dir,
            "user.service.ts",
            '''
export class UserService {
}
            '''.strip(),
        )

        graph = scan_repo(temp_dir)

        app = get_file_by_name(graph, "app.ts")
        service = get_file_by_name(graph, "user.service.ts")

        assert app["language"] == "typescript"
        assert service["language"] == "typescript"
        assert "./user.service" in app["imports"]


def test_scanner_resolves_typescript_relative_edges():
    with tempfile.TemporaryDirectory() as temp_dir:
        write_file(
            temp_dir,
            "app.ts",
            '''
import { UserService } from "./user.service";

export class AppComponent {
}
            '''.strip(),
        )
        write_file(
            temp_dir,
            "user.service.ts",
            '''
export class UserService {
}
            '''.strip(),
        )

        graph = scan_repo(temp_dir)

        assert has_edge(graph, "app.ts", "user.service.ts", "./user.service")


def test_scanner_marks_javascript_package_imports_external():
    with tempfile.TemporaryDirectory() as temp_dir:
        write_file(
            temp_dir,
            "app.js",
            '''
import React from "react";
import { useState } from "react";
            '''.strip(),
        )

        graph = scan_repo(temp_dir)
        app = get_file_by_name(graph, "app.js")

        assert "react" in app["external_imports"]
        assert app["unresolved_imports"] == []


def test_scanner_still_ignores_unwired_java_and_rust_files():
    with tempfile.TemporaryDirectory() as temp_dir:
        write_file(
            temp_dir,
            "Main.java",
            '''
public class Main {
}
            '''.strip(),
        )
        write_file(
            temp_dir,
            "main.rs",
            '''
fn main() {
}
            '''.strip(),
        )

        graph = scan_repo(temp_dir)

        assert graph["files"] == []


TESTS = [
    test_scanner_includes_javascript_files,
    test_scanner_resolves_javascript_relative_edges,
    test_scanner_resolves_javascript_index_edges,
    test_scanner_includes_typescript_files,
    test_scanner_resolves_typescript_relative_edges,
    test_scanner_marks_javascript_package_imports_external,
    test_scanner_still_ignores_unwired_java_and_rust_files,
]