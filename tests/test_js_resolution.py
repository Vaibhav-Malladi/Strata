from __future__ import annotations

import json
import tempfile
from pathlib import Path

from js_resolution import (
    build_js_resolution_context,
    load_tsconfig_paths,
    resolve_js_import,
)


def write_file(root: Path, relative_path: str, content: str) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def write_json(root: Path, relative_path: str, data: dict) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _resolve(root: Path, importer: str, source: str, context: dict | None = None) -> dict:
    return resolve_js_import(str(root), str(root / importer), source, context)


def test_js_resolution_resolves_relative_imports():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        write_file(root, "src/app.ts", 'import { helper } from "./helper";\n')
        write_file(root, "src/helper.ts", "export const helper = 1;\n")

        context = build_js_resolution_context(root)
        result = _resolve(root, "src/app.ts", "./helper", context)

        assert result["status"] == "resolved"
        assert result["resolved_path"] == "src/helper.ts"
        assert result["candidates"][0] == "src/helper.ts"


def test_js_resolution_resolves_extensionless_relative_imports():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        write_file(root, "src/app.ts", 'import { helper } from "./helper";\n')
        write_file(root, "src/helper.tsx", "export const helper = () => null;\n")

        context = build_js_resolution_context(root)
        result = _resolve(root, "src/app.ts", "./helper", context)

        assert result["status"] == "resolved"
        assert result["resolved_path"] == "src/helper.tsx"


def test_js_resolution_resolves_index_imports():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        write_file(root, "src/app.ts", 'import { shared } from "./shared";\n')
        write_file(root, "src/shared/index.ts", "export const shared = 1;\n")

        context = build_js_resolution_context(root)
        result = _resolve(root, "src/app.ts", "./shared", context)

        assert result["status"] == "resolved"
        assert result["resolved_path"] == "src/shared/index.ts"


def test_js_resolution_resolves_exact_extension_imports():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        write_file(root, "src/app.ts", 'import { helper } from "./helper.ts";\n')
        write_file(root, "src/helper.ts", "export const helper = 1;\n")

        context = build_js_resolution_context(root)
        result = _resolve(root, "src/app.ts", "./helper.ts", context)

        assert result["status"] == "resolved"
        assert result["resolved_path"] == "src/helper.ts"
        assert result["candidates"] == ["src/helper.ts"]


def test_js_resolution_marks_external_npm_imports():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        write_file(root, "src/app.tsx", 'import React from "react";\n')

        context = build_js_resolution_context(root)
        result = _resolve(root, "src/app.tsx", "react", context)

        assert result["status"] == "external"
        assert result["resolved_path"] is None
        assert result["candidates"] == []


def test_js_resolution_handles_malformed_tsconfig():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        write_file(root, "tsconfig.json", "{ not valid json")
        write_file(root, "src/app.ts", 'import { Button } from "@/components/Button";\n')

        paths = load_tsconfig_paths(root)
        context = build_js_resolution_context(root)
        result = _resolve(root, "src/app.ts", "@/components/Button", context)

        assert paths["patterns"] == []
        assert result["status"] == "path_alias"
        assert result["resolved_path"] is None


def test_js_resolution_resolves_tsconfig_aliases():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        write_json(
            root,
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
        write_file(root, "src/app.tsx", 'import { Button } from "@/components/Button";\n')
        write_file(root, "src/components/Button.tsx", "export const Button = () => null;\n")

        context = build_js_resolution_context(root)
        result = _resolve(root, "src/app.tsx", "@/components/Button", context)

        assert result["status"] == "resolved"
        assert result["resolved_path"] == "src/components/Button.tsx"


def test_js_resolution_prefers_longest_alias_pattern():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        write_json(
            root,
            "tsconfig.json",
            {
                "compilerOptions": {
                    "baseUrl": ".",
                    "paths": {
                        "@/*": ["src/*"],
                        "@app/*": ["src/app/*"],
                    },
                }
            },
        )
        write_file(root, "src/app/services/user.service.ts", "export const service = 1;\n")
        write_file(root, "src/services/user.service.ts", "export const fallback = 1;\n")

        context = build_js_resolution_context(root)
        result = _resolve(root, "src/app.ts", "@app/services/user.service", context)

        assert result["status"] == "resolved"
        assert result["resolved_path"] == "src/app/services/user.service.ts"


def test_js_resolution_supports_exact_aliases():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        write_json(
            root,
            "tsconfig.json",
            {
                "compilerOptions": {
                    "baseUrl": ".",
                    "paths": {
                        "@shared": ["src/shared/index.ts"],
                    },
                }
            },
        )
        write_file(root, "src/shared/index.ts", "export const shared = 1;\n")

        context = build_js_resolution_context(root)
        result = _resolve(root, "src/app.ts", "@shared", context)

        assert result["status"] == "resolved"
        assert result["resolved_path"] == "src/shared/index.ts"


def test_js_resolution_tries_multiple_alias_targets_in_order():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        write_json(
            root,
            "tsconfig.json",
            {
                "compilerOptions": {
                    "baseUrl": ".",
                    "paths": {
                        "@shared/*": ["src/shared/*", "lib/shared/*"],
                    },
                }
            },
        )
        write_file(root, "src/shared/api.ts", "export const first = 1;\n")
        write_file(root, "lib/shared/api.ts", "export const second = 1;\n")

        context = build_js_resolution_context(root)
        result = _resolve(root, "src/app.ts", "@shared/api", context)

        assert result["status"] == "resolved"
        assert result["resolved_path"] == "src/shared/api.ts"


def test_js_resolution_supports_jsconfig_aliases():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        write_json(
            root,
            "jsconfig.json",
            {
                "compilerOptions": {
                    "baseUrl": ".",
                    "paths": {
                        "@components/*": ["src/components/*"],
                    },
                }
            },
        )
        write_file(root, "src/components/Button.jsx", "export const Button = () => null;\n")

        context = build_js_resolution_context(root)
        result = _resolve(root, "src/app.jsx", "@components/Button", context)

        assert result["status"] == "resolved"
        assert result["resolved_path"] == "src/components/Button.jsx"


def test_js_resolution_resolves_package_self_reference():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        write_json(root, "package.json", {"name": "@my/app"})
        write_file(root, "src/foo.ts", "export const foo = 1;\n")

        context = build_js_resolution_context(root)
        result = _resolve(root, "src/app.ts", "@my/app/src/foo", context)

        assert result["status"] == "resolved"
        assert result["resolved_path"] == "src/foo.ts"


def test_js_resolution_resolves_workspace_package_root():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        write_json(
            root,
            "package.json",
            {
                "name": "@my/app",
                "workspaces": ["packages/*"],
            },
        )
        write_json(root, "packages/shared/package.json", {"name": "@my/shared"})
        write_file(root, "packages/shared/src/index.ts", "export const shared = 1;\n")

        context = build_js_resolution_context(root)
        result = _resolve(root, "src/app.ts", "@my/shared", context)

        assert result["status"] == "resolved"
        assert result["resolved_path"] == "packages/shared/src/index.ts"


def test_js_resolution_resolves_workspace_package_subpath():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        write_json(
            root,
            "package.json",
            {
                "name": "@my/app",
                "workspaces": ["packages/*"],
            },
        )
        write_json(root, "packages/shared/package.json", {"name": "@my/shared"})
        write_file(root, "packages/shared/src/utils.ts", "export const utils = 1;\n")

        context = build_js_resolution_context(root)
        result = _resolve(root, "src/app.ts", "@my/shared/utils", context)

        assert result["status"] == "resolved"
        assert result["resolved_path"] == "packages/shared/src/utils.ts"


def test_js_resolution_marks_unresolved_aliases():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        write_json(
            root,
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
        write_file(root, "src/app.ts", 'import { Button } from "@/missing/Button";\n')

        context = build_js_resolution_context(root)
        result = _resolve(root, "src/app.ts", "@/missing/Button", context)

        assert result["status"] == "path_alias"
        assert result["resolved_path"] is None
        assert result["candidates"]


def test_js_resolution_returns_fresh_dicts_and_lists():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        write_json(
            root,
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
        write_file(root, "src/app.ts", 'import { Button } from "@/missing/Button";\n')

        context_one = build_js_resolution_context(root)
        context_two = build_js_resolution_context(root)

        context_one["source_files"].append("mutated")
        context_one["tsconfig"]["patterns"][0]["targets"].append("mutated")

        assert "mutated" not in context_two["source_files"]
        assert "mutated" not in context_two["tsconfig"]["patterns"][0]["targets"]

        result_one = _resolve(root, "src/app.ts", "@/missing/Button", context_one)
        result_two = _resolve(root, "src/app.ts", "@/missing/Button", context_two)

        result_one["candidates"].append("mutated")

        assert result_one["candidates"] is not result_two["candidates"]
        assert "mutated" not in result_two["candidates"]


TESTS = [
    test_js_resolution_resolves_relative_imports,
    test_js_resolution_resolves_extensionless_relative_imports,
    test_js_resolution_resolves_index_imports,
    test_js_resolution_resolves_exact_extension_imports,
    test_js_resolution_marks_external_npm_imports,
    test_js_resolution_handles_malformed_tsconfig,
    test_js_resolution_resolves_tsconfig_aliases,
    test_js_resolution_prefers_longest_alias_pattern,
    test_js_resolution_supports_exact_aliases,
    test_js_resolution_tries_multiple_alias_targets_in_order,
    test_js_resolution_supports_jsconfig_aliases,
    test_js_resolution_resolves_package_self_reference,
    test_js_resolution_resolves_workspace_package_root,
    test_js_resolution_resolves_workspace_package_subpath,
    test_js_resolution_marks_unresolved_aliases,
    test_js_resolution_returns_fresh_dicts_and_lists,
]
