import tempfile
from pathlib import Path

import js_parser as old_js_impl
import strata.parsers.javascript as new_js_impl
from js_parser import parse_js_file, parse_js_source


def _parse_temp_file(filename: str, source: str) -> dict:
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / filename
        path.write_text(source, encoding="utf-8")
        return parse_js_file(str(path))


def _names(items: list[dict]) -> list[str]:
    return [item["name"] for item in items]


def test_new_js_parser_import_matches_legacy_shim():
    assert old_js_impl.parse_js_file is new_js_impl.parse_js_file
    assert old_js_impl.parse_js_source is new_js_impl.parse_js_source


def test_js_default_import():
    parsed = _parse_temp_file("app.js", 'import React from "react";\n')
    assert "react" in parsed["imports"]
    assert parsed["import_details"][0]["kind"] == "es_import"
    assert parsed["import_details"][0]["imported_names"] == ["default"]
    assert parsed["import_details"][0]["local_names"] == ["React"]


def test_js_named_import():
    parsed = _parse_temp_file("app.js", 'import { useState, useEffect } from "react";\n')
    assert parsed["imports"] == ["react"]
    assert parsed["import_details"][0]["imported_names"] == ["useState", "useEffect"]
    assert parsed["import_details"][0]["local_names"] == ["useState", "useEffect"]


def test_js_relative_import_preserves_source_module():
    parsed = _parse_temp_file("app.ts", 'import { UserService } from "./user.service";\n')
    assert parsed["import_details"][0]["source"] == "./user.service"
    assert parsed["import_details"][0]["name"] == "./user.service"


def test_js_namespace_import():
    parsed = _parse_temp_file("app.js", 'import * as api from "./api";\n')
    assert parsed["imports"] == ["./api"]
    assert parsed["import_details"][0]["local_names"] == ["api"]


def test_js_side_effect_import():
    parsed = _parse_temp_file("app.js", 'import "./styles.css";\n')
    assert parsed["imports"] == ["./styles.css"]
    assert parsed["import_details"][0]["kind"] == "side_effect"


def test_js_multiline_import():
    parsed = _parse_temp_file(
        "app.tsx",
        'import {\n'
        '  Component,\n'
        '  Input,\n'
        '  Output\n'
        '} from "@angular/core";\n',
    )
    assert parsed["language"] == "typescript"
    assert parsed["imports"] == ["@angular/core"]
    assert parsed["import_details"][0]["imported_names"] == ["Component", "Input", "Output"]


def test_js_type_only_import():
    parsed = _parse_temp_file("types.ts", 'import type { User } from "./types";\n')
    assert parsed["import_details"][0]["kind"] == "type_import"
    assert parsed["import_details"][0]["imported_names"] == ["User"]


def test_js_commonjs_require():
    parsed = _parse_temp_file(
        "server.js",
        'const express = require("express");\n'
        'const { Router } = require("express");\n'
        'require("./polyfill");\n',
    )
    assert parsed["imports"] == ["express", "./polyfill"]
    assert any(item["kind"] == "require" for item in parsed["import_details"])
    assert any(item["local_names"] == ["express"] for item in parsed["import_details"])
    assert any(item["local_names"] == ["Router"] for item in parsed["import_details"])


def test_js_export_default_function():
    parsed = _parse_temp_file("app.js", "export default function App() {}\n")
    assert any(item["name"] == "App" and item["default"] for item in parsed["exports"])
    assert any(item["name"] == "App" for item in parsed["functions"])


def test_js_export_const():
    parsed = _parse_temp_file("app.js", "export const value = 1;\n")
    assert any(item["name"] == "value" and item["kind"] == "const" for item in parsed["exports"])


def test_js_export_class():
    parsed = _parse_temp_file("app.js", "export class UserService {}\n")
    assert any(item["name"] == "UserService" and item["kind"] == "class" for item in parsed["exports"])
    assert any(item["name"] == "UserService" for item in parsed["classes"])


def test_js_reexport():
    parsed = _parse_temp_file("index.js", 'export { A as B } from "./module";\n')
    assert any(item["name"] == "B" and item["source"] == "./module" for item in parsed["exports"])


def test_js_function_declaration():
    parsed = _parse_temp_file("app.js", "function helper() {}\n")
    assert _names(parsed["functions"]) == ["helper"]


def test_js_arrow_function():
    parsed = _parse_temp_file("app.js", "const helper = () => {};\n")
    assert "helper" in _names(parsed["functions"])


def test_js_async_arrow_function():
    parsed = _parse_temp_file("app.js", "const helper = async () => {};\n")
    assert any(item["name"] == "helper" and item["async"] for item in parsed["functions"])


def test_js_class_declaration():
    parsed = _parse_temp_file("app.js", "class Foo {}\n")
    assert _names(parsed["classes"]) == ["Foo"]


def test_js_react_framework_detection_from_import():
    parsed = _parse_temp_file("app.js", 'import React from "react";\n')
    assert "react" in parsed["frameworks"]


def test_js_react_framework_detection_from_jsx_tsx():
    parsed = _parse_temp_file("view.tsx", "const view = <div />;\n")
    assert parsed["language"] == "typescript"
    assert "react" in parsed["frameworks"]


def test_js_react_functional_component():
    parsed = _parse_temp_file(
        "App.tsx",
        'import React from "react";\n'
        "export function App() {\n"
        "  return <div />;\n"
        "}\n",
    )
    assert any(item["name"] == "App" for item in parsed["components"])
    assert any(item["confidence"] in {"high", "medium"} for item in parsed["components"])


def test_js_react_arrow_component():
    parsed = _parse_temp_file(
        "Button.jsx",
        'import React from "react";\n'
        "export const Button = () => <button />;\n",
    )
    assert any(item["name"] == "Button" for item in parsed["components"])


def test_js_react_class_component():
    parsed = _parse_temp_file(
        "Widget.tsx",
        'import React from "react";\n'
        "export class Widget extends React.Component {\n"
        "  render() { return <div />; }\n"
        "}\n",
    )
    assert any(item["name"] == "Widget" for item in parsed["components"])


def test_js_react_hooks_imported_and_called():
    parsed = _parse_temp_file(
        "App.tsx",
        'import React, { useState, useEffect } from "react";\n'
        "export function App() {\n"
        "  useState(0);\n"
        "  useEffect(() => {}, []);\n"
        "  return <div />;\n"
        "}\n",
    )
    hook_names = _names(parsed["hooks"])
    assert "useState" in hook_names
    assert "useEffect" in hook_names
    assert any(item["kind"] == "imported" for item in parsed["hooks"])
    assert any(item["kind"] == "call" for item in parsed["hooks"])


def test_js_custom_hook_detection():
    parsed = _parse_temp_file(
        "hooks.ts",
        "function useThing() {}\n"
        "const useOtherThing = () => {};\n",
    )
    assert "useThing" in _names(parsed["hooks"])
    assert "useOtherThing" in _names(parsed["hooks"])
    assert all(item["kind"] == "custom" for item in parsed["hooks"])


def test_js_angular_framework_detection_from_core_import():
    parsed = _parse_temp_file("app.component.ts", 'import { Component } from "@angular/core";\n')
    assert "angular" in parsed["frameworks"]


def test_js_angular_component_detection():
    parsed = _parse_temp_file(
        "app.component.ts",
        'import { Component } from "@angular/core";\n'
        "@Component({ selector: 'app-root' })\n"
        "export class AppComponent {}\n",
    )
    assert any(item["name"] == "AppComponent" for item in parsed["angular"]["components"])


def test_js_angular_selector_extraction():
    parsed = _parse_temp_file(
        "app.component.ts",
        'import { Component } from "@angular/core";\n'
        "@Component({ selector: 'app-root' })\n"
        "export class AppComponent {}\n",
    )
    assert parsed["angular"]["components"][0]["selector"] == "app-root"


def test_js_angular_template_url_extraction():
    parsed = _parse_temp_file(
        "app.component.ts",
        'import { Component } from "@angular/core";\n'
        "@Component({ templateUrl: './app.component.html' })\n"
        "export class AppComponent {}\n",
    )
    assert parsed["angular"]["components"][0]["templateUrl"] == "./app.component.html"


def test_js_angular_injectable_service_detection():
    parsed = _parse_temp_file(
        "user.service.ts",
        'import { Injectable } from "@angular/core";\n'
        '@Injectable({ providedIn: "root" })\n'
        "export class UserService {}\n",
    )
    assert any(item["name"] == "UserService" for item in parsed["angular"]["services"])
    assert parsed["angular"]["services"][0]["providedIn"] == "root"


def test_js_angular_ngmodule_detection():
    parsed = _parse_temp_file(
        "app.module.ts",
        'import { NgModule } from "@angular/core";\n'
        "@NgModule({})\n"
        "export class AppModule {}\n",
    )
    assert any(item["name"] == "AppModule" for item in parsed["angular"]["modules"])


def test_js_angular_routes_detection():
    parsed = _parse_temp_file(
        "app-routing.module.ts",
        'import { RouterModule } from "@angular/router";\n'
        "const routes = [\n"
        '  { path: "users", component: UsersComponent },\n'
        '  { path: "", redirectTo: "home", pathMatch: "full" },\n'
        "];\n",
    )
    paths = [route["path"] for route in parsed["angular"]["routes"]]
    assert "users" in paths
    assert "" in paths


def test_js_parser_handles_comments_and_strings_reasonably():
    parsed = _parse_temp_file(
        "app.js",
        "// import fake from 'fake';\n"
        "const text = 'export function nope() {}';\n"
        "/* class Hidden {} */\n"
        'import { real } from "./real";\n',
    )
    assert parsed["imports"] == ["./real"]
    assert parsed["functions"] == []
    assert parsed["classes"] == []


def test_js_parser_handles_malformed_js_without_crashing():
    parsed = parse_js_source("function broken( {\n  return <div />\n", path="broken.tsx")
    assert parsed["language"] == "typescript"
    assert isinstance(parsed["imports"], list)
    assert isinstance(parsed["functions"], list)


def test_js_parser_returns_fresh_deterministic_structures():
    source = (
        'import React from "react";\n'
        "export const App = () => <div />;\n"
    )
    first = parse_js_source(source, path="App.tsx")
    second = parse_js_source(source, path="App.tsx")

    assert first == second
    assert first is not second
    assert first["imports"] is not second["imports"]
    assert first["components"] is not second["components"]


TESTS = [
    test_new_js_parser_import_matches_legacy_shim,
    test_js_default_import,
    test_js_named_import,
    test_js_relative_import_preserves_source_module,
    test_js_namespace_import,
    test_js_side_effect_import,
    test_js_multiline_import,
    test_js_type_only_import,
    test_js_commonjs_require,
    test_js_export_default_function,
    test_js_export_const,
    test_js_export_class,
    test_js_reexport,
    test_js_function_declaration,
    test_js_arrow_function,
    test_js_async_arrow_function,
    test_js_class_declaration,
    test_js_react_framework_detection_from_import,
    test_js_react_framework_detection_from_jsx_tsx,
    test_js_react_functional_component,
    test_js_react_arrow_component,
    test_js_react_class_component,
    test_js_react_hooks_imported_and_called,
    test_js_custom_hook_detection,
    test_js_angular_framework_detection_from_core_import,
    test_js_angular_component_detection,
    test_js_angular_selector_extraction,
    test_js_angular_template_url_extraction,
    test_js_angular_injectable_service_detection,
    test_js_angular_ngmodule_detection,
    test_js_angular_routes_detection,
    test_js_parser_handles_comments_and_strings_reasonably,
    test_js_parser_handles_malformed_js_without_crashing,
    test_js_parser_returns_fresh_deterministic_structures,
]
