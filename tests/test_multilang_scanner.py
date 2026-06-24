import json
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


def has_edge_any_separator(graph: dict, from_name: str, to_name: str, import_name: str) -> bool:
    return has_edge(graph, from_name, to_name, import_name) or has_edge(
        graph,
        from_name,
        to_name.replace("/", "\\"),
        import_name,
    )


def write_json_file(folder: str, relative_path: str, data: dict) -> Path:
    path = Path(folder) / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


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
        app = get_file_by_name(graph, "app.ts")
        assert "user.service" in "".join(app["imports"])
        assert "user.service" not in app["unresolved_imports"]


def test_scanner_resolves_typescript_index_and_tsx_edges():
    with tempfile.TemporaryDirectory() as temp_dir:
        write_file(
            temp_dir,
            "app.ts",
            '''
import { Button } from "./components/Button";
import { shared } from "./shared";
            '''.strip(),
        )
        write_file(
            temp_dir,
            "components/Button.tsx",
            '''
export const Button = () => {
}
            '''.strip(),
        )
        write_file(
            temp_dir,
            "shared/index.ts",
            '''
export const shared = 1;
            '''.strip(),
        )

        graph = scan_repo(temp_dir)

        assert has_edge(graph, "app.ts", "components/Button.tsx", "./components/Button")
        assert has_edge(graph, "app.ts", "shared/index.ts", "./shared")


def test_scanner_records_external_react_import_without_local_edge():
    with tempfile.TemporaryDirectory() as temp_dir:
        write_file(
            temp_dir,
            "app.tsx",
            '''
import React from "react";
export const App = () => <div />;
            '''.strip(),
        )

        graph = scan_repo(temp_dir)
        app = get_file_by_name(graph, "app.tsx")

        assert "react" in app["external_imports"]
        assert not any(edge["import"] == "react" for edge in graph["edges"])


def test_scanner_resolves_tsconfig_alias_edges():
    with tempfile.TemporaryDirectory() as temp_dir:
        write_json_file(
            temp_dir,
            "tsconfig.json",
            {
                "compilerOptions": {
                    "baseUrl": ".",
                    "paths": {
                        "@/*": ["src/*"],
                    },
                }
            },
        )
        write_file(
            temp_dir,
            "src/App.tsx",
            '''
import { Button } from "@/components/Button";
export const App = () => <div />;
            '''.strip(),
        )
        write_file(
            temp_dir,
            "src/components/Button.tsx",
            '''
export const Button = () => <button />;
            '''.strip(),
        )

        graph = scan_repo(temp_dir)

        assert has_edge_any_separator(graph, "App.tsx", "src/components/Button.tsx", "@/components/Button")


def test_scanner_resolves_angular_alias_edges():
    with tempfile.TemporaryDirectory() as temp_dir:
        write_json_file(
            temp_dir,
            "tsconfig.json",
            {
                "compilerOptions": {
                    "baseUrl": ".",
                    "paths": {
                        "@app/*": ["src/app/*"],
                    },
                }
            },
        )
        write_file(
            temp_dir,
            "src/app/app.component.ts",
            '''
import { Component } from "@angular/core";
import { UserService } from "@app/services/user.service";
@Component({ selector: "app-root" })
export class AppComponent {}
            '''.strip(),
        )
        write_file(
            temp_dir,
            "src/app/services/user.service.ts",
            '''
export class UserService {}
            '''.strip(),
        )

        graph = scan_repo(temp_dir)

        assert has_edge_any_separator(
            graph,
            "app.component.ts",
            "src/app/services/user.service.ts",
            "@app/services/user.service",
        )


def test_scanner_resolves_shared_alias_index_edges():
    with tempfile.TemporaryDirectory() as temp_dir:
        write_json_file(
            temp_dir,
            "tsconfig.json",
            {
                "compilerOptions": {
                    "baseUrl": ".",
                    "paths": {
                        "@shared/*": ["src/shared/*"],
                    },
                }
            },
        )
        write_file(
            temp_dir,
            "src/app.ts",
            '''
import { api } from "@shared/api";
            '''.strip(),
        )
        write_file(
            temp_dir,
            "src/shared/api/index.ts",
            '''
export const api = 1;
            '''.strip(),
        )

        graph = scan_repo(temp_dir)

        assert has_edge_any_separator(graph, "app.ts", "src/shared/api/index.ts", "@shared/api")


def test_scanner_resolves_package_self_reference_edges():
    with tempfile.TemporaryDirectory() as temp_dir:
        write_json_file(
            temp_dir,
            "package.json",
            {"name": "@my/app"},
        )
        write_file(
            temp_dir,
            "src/app.ts",
            '''
import { foo } from "@my/app/src/foo";
            '''.strip(),
        )
        write_file(
            temp_dir,
            "src/foo.ts",
            '''
export const foo = 1;
            '''.strip(),
        )

        graph = scan_repo(temp_dir)

        assert has_edge_any_separator(graph, "app.ts", "src/foo.ts", "@my/app/src/foo")


def test_scanner_resolves_workspace_package_root_edges():
    with tempfile.TemporaryDirectory() as temp_dir:
        write_json_file(
            temp_dir,
            "package.json",
            {
                "name": "@my/app",
                "workspaces": ["packages/*"],
            },
        )
        write_json_file(
            temp_dir,
            "packages/shared/package.json",
            {"name": "@my/shared"},
        )
        write_file(
            temp_dir,
            "src/app.ts",
            '''
import { shared } from "@my/shared";
            '''.strip(),
        )
        write_file(
            temp_dir,
            "packages/shared/src/index.ts",
            '''
export const shared = 1;
            '''.strip(),
        )

        graph = scan_repo(temp_dir)

        assert has_edge_any_separator(
            graph,
            "app.ts",
            "packages/shared/src/index.ts",
            "@my/shared",
        )


def test_scanner_resolves_workspace_package_subpath_edges():
    with tempfile.TemporaryDirectory() as temp_dir:
        write_json_file(
            temp_dir,
            "package.json",
            {
                "name": "@my/app",
                "workspaces": ["packages/*"],
            },
        )
        write_json_file(
            temp_dir,
            "packages/shared/package.json",
            {"name": "@my/shared"},
        )
        write_file(
            temp_dir,
            "src/app.ts",
            '''
import { utils } from "@my/shared/utils";
            '''.strip(),
        )
        write_file(
            temp_dir,
            "packages/shared/src/utils.ts",
            '''
export const utils = 1;
            '''.strip(),
        )

        graph = scan_repo(temp_dir)

        assert has_edge_any_separator(
            graph,
            "app.ts",
            "packages/shared/src/utils.ts",
            "@my/shared/utils",
        )


def test_scanner_resolves_barrel_reexport_edges():
    with tempfile.TemporaryDirectory() as temp_dir:
        write_file(
            temp_dir,
            "src/index.ts",
            '''
export { Button } from "./Button";
            '''.strip(),
        )
        write_file(
            temp_dir,
            "src/Button.tsx",
            '''
export const Button = () => <button />;
            '''.strip(),
        )

        graph = scan_repo(temp_dir)

        assert has_edge_any_separator(graph, "index.ts", "src/Button.tsx", "./Button")


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
