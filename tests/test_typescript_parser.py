import tempfile
from pathlib import Path

from parsers.typescript_parser import parse_file


def write_file(folder: str, name: str, content: str) -> Path:
    path = Path(folder) / name
    path.write_text(content, encoding="utf-8")
    return path


def test_parses_typescript_imports():
    with tempfile.TemporaryDirectory() as temp_dir:
        path = write_file(
            temp_dir,
            "app.ts",
            '''
import { Component } from "@angular/core";
import { UserService } from "./user.service";
import "./styles.css";
const fs = require("fs");
            '''.strip(),
        )

        parsed = parse_file(str(path))

        assert parsed["language"] == "typescript"
        assert "@angular/core" in parsed["imports"]
        assert "./user.service" in parsed["imports"]
        assert "./styles.css" in parsed["imports"]
        assert "fs" in parsed["imports"]


def test_parses_typescript_symbols():
    with tempfile.TemporaryDirectory() as temp_dir:
        path = write_file(
            temp_dir,
            "symbols.ts",
            '''
export interface User {
}

type UserId = string;

export enum Role {
    Admin,
}

export function run(): void {
}

const build = (): string => {
    return "ok";
};

export class UserService {
}
            '''.strip(),
        )

        parsed = parse_file(str(path))

        interface_names = [item["name"] for item in parsed["interfaces"]]
        type_names = [item["name"] for item in parsed["types"]]
        enum_names = [item["name"] for item in parsed["enums"]]
        function_names = [item["name"] for item in parsed["functions"]]
        class_names = [item["name"] for item in parsed["classes"]]

        assert "User" in interface_names
        assert "UserId" in type_names
        assert "Role" in enum_names
        assert "run" in function_names
        assert "build" in function_names
        assert "UserService" in class_names


def test_detects_angular_framework_hint():
    with tempfile.TemporaryDirectory() as temp_dir:
        path = write_file(
            temp_dir,
            "app.component.ts",
            '''
import { Component } from "@angular/core";

@Component({
    selector: "app-root"
})
export class AppComponent {
}
            '''.strip(),
        )

        parsed = parse_file(str(path))

        assert parsed["framework"] == "angular"


def test_detects_react_framework_hint():
    with tempfile.TemporaryDirectory() as temp_dir:
        path = write_file(
            temp_dir,
            "App.tsx",
            '''
import React from "react";

export function App() {
    return <h1>Hello</h1>;
}
            '''.strip(),
        )

        parsed = parse_file(str(path))

        assert parsed["framework"] == "react"


def test_typescript_read_error_is_reported():
    parsed = parse_file("missing-file.ts")

    assert parsed["language"] == "typescript"
    assert parsed["error"]["type"] == "read_error"

def test_parses_typescript_backend_routes():
    with tempfile.TemporaryDirectory() as temp_dir:
        path = write_file(
            temp_dir,
            "routes.ts",
            '''
app.get("/health", healthCheck);
app.post("/users", createUser);
router.put("/users/:id", updateUser);
router.delete("/users/:id", deleteUser);
api.patch("/users/:id", patchUser);
            '''.strip(),
        )

        parsed = parse_file(str(path))

        assert {
            "method": "GET",
            "path": "/health",
            "line": 1,
            "source": "app.get",
        } in parsed["routes"]

        assert {
            "method": "POST",
            "path": "/users",
            "line": 2,
            "source": "app.post",
        } in parsed["routes"]

        assert {
            "method": "PUT",
            "path": "/users/:id",
            "line": 3,
            "source": "router.put",
        } in parsed["routes"]

        assert {
            "method": "DELETE",
            "path": "/users/:id",
            "line": 4,
            "source": "router.delete",
        } in parsed["routes"]

        assert {
            "method": "PATCH",
            "path": "/users/:id",
            "line": 5,
            "source": "api.patch",
        } in parsed["routes"]

TESTS = [
    test_parses_typescript_imports,
    test_parses_typescript_symbols,
    test_detects_angular_framework_hint,
    test_detects_react_framework_hint,
    test_typescript_read_error_is_reported,
    test_parses_typescript_backend_routes,
]