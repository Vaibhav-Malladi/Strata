import json
import tempfile
from pathlib import Path

from strata.core.dependency_tracing import dependency_edge_to_dict
from strata.core.js_ts_dependency_edges import extract_js_ts_import_edges
from tests.helpers import try_symlink_or_skip


def _write(root: Path, relative_path: str, content: str = "") -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _extract(files: dict[str, str], source: str = "src/main.ts"):
    temporary = tempfile.TemporaryDirectory()
    root = Path(temporary.name)
    for path, content in files.items():
        _write(root, path, content)
    return temporary, root, extract_js_ts_import_edges(root, source)


def _expect_error(error_type, function, *args, contains: str, **kwargs):
    try:
        function(*args, **kwargs)
    except error_type as error:
        assert contains in str(error)
    else:
        raise AssertionError(f"Expected {error_type.__name__}")


def test_default_import_resolves_supported_extensions():
    for extension in (".ts", ".tsx", ".js"):
        temporary, _root, report = _extract(
            {
                "src/main.ts": "import value from './module'\n",
                f"src/module{extension}": "",
            }
        )
        with temporary:
            assert report.edges[0].target_file == f"src/module{extension}"
            assert report.edges[0].priority == "medium"
            assert report.edges[0].confidence == "high"


def test_named_and_namespace_imports_resolve():
    temporary, _root, report = _extract(
        {
            "src/main.ts": (
                "import { value } from './named'\n"
                "import * as helpers from './helpers'\n"
            ),
            "src/named.ts": "",
            "src/helpers.ts": "",
        }
    )
    with temporary:
        assert {edge.target_file for edge in report.edges} == {
            "src/helpers.ts",
            "src/named.ts",
        }


def test_side_effect_import_resolves():
    temporary, _root, report = _extract(
        {"src/main.ts": "import './setup'\n", "src/setup.js": ""}
    )
    with temporary:
        assert report.edges[0].target_file == "src/setup.js"
        assert "side-effect import" in report.edges[0].reason


def test_named_re_export_resolves_with_re_export_type():
    temporary, _root, report = _extract(
        {"src/main.ts": "export { value } from './module'\n", "src/module.ts": ""}
    )
    with temporary:
        assert report.edges[0].edge_type == "re_export"
        assert report.edges[0].target_file == "src/module.ts"


def test_export_star_resolves_with_re_export_type():
    temporary, _root, report = _extract(
        {"src/main.ts": "export * from './module'\n", "src/module.ts": ""}
    )
    with temporary:
        assert report.edges[0].edge_type == "re_export"


def test_dynamic_import_and_require_resolve_as_lower_certainty_edges():
    temporary, _root, report = _extract(
        {
            "src/main.ts": (
                "const lazy = import('./lazy')\n"
                "const legacy = require('./legacy')\n"
            ),
            "src/lazy.ts": "",
            "src/legacy.cjs": "",
        }
    )
    with temporary:
        assert {edge.target_file for edge in report.edges} == {
            "src/lazy.ts",
            "src/legacy.cjs",
        }
        assert all(edge.priority == "low" for edge in report.edges)
        assert all(edge.confidence == "medium" for edge in report.edges)


def test_directory_index_resolution_uses_documented_extensions():
    temporary, _root, report = _extract(
        {"src/main.ts": "import './feature'\n", "src/feature/index.tsx": ""}
    )
    with temporary:
        assert report.edges[0].target_file == "src/feature/index.tsx"


def test_external_and_alias_imports_are_skipped_deterministically():
    temporary, _root, report = _extract(
        {
            "src/main.ts": (
                "import React from 'react'\n"
                "import { Component } from '@angular/core'\n"
                "import local from '@/local'\n"
            )
        }
    )
    with temporary:
        assert report.edges == ()
        assert report.skipped_items == (
            "unsupported non-relative import: @/local",
            "unsupported non-relative import: @angular/core",
            "unsupported non-relative import: react",
        )


def test_unresolved_relative_import_is_skipped_deterministically():
    temporary, _root, report = _extract(
        {"src/main.ts": "import missing from './missing'\n"}
    )
    with temporary:
        assert report.edges == ()
        assert report.skipped_items == (
            "unresolved relative import: ./missing",
        )


def test_absolute_and_escaping_source_paths_are_rejected():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "src/main.ts", "")
        for source in (str((root / "src/main.ts").resolve()), "../main.ts"):
            _expect_error(
                ValueError,
                extract_js_ts_import_edges,
                root,
                source,
                contains="path must",
            )


def test_symlink_target_escaping_root_is_skipped_safely():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        outside = Path(temp_dir) / "outside.ts"
        root.mkdir()
        outside.write_text("export const outside = true\n", encoding="utf-8")
        _write(root, "src/main.ts", "import './linked'\n")
        if not try_symlink_or_skip(root / "src/linked.ts", outside):
            return

        report = extract_js_ts_import_edges(root, "src/main.ts")

        assert report.edges == ()
        assert report.skipped_items == (
            "unresolved relative import: ./linked",
        )


def test_target_module_is_not_read_or_executed():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        marker = root / "executed.txt"
        source = _write(root, "src/main.ts", "import './dangerous'\n")
        target = _write(
            root,
            "src/dangerous.js",
            f"require('fs').writeFileSync({str(marker)!r}, 'bad')\n",
        )
        original_open = Path.open

        def guarded_open(path, *args, **kwargs):
            if path.resolve() == target.resolve():
                raise AssertionError("target content was read")
            return original_open(path, *args, **kwargs)

        Path.open = guarded_open
        try:
            report = extract_js_ts_import_edges(root, source.relative_to(root))
        finally:
            Path.open = original_open

        assert report.edges[0].target_file == "src/dangerous.js"
        assert not marker.exists()


def test_oversized_and_non_utf8_sources_are_skipped():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "src/large.ts", "import './module'\n")
        _write(root, "src/module.ts", "")
        oversized = extract_js_ts_import_edges(
            root, "src/large.ts", max_source_bytes=4
        )
        bad = root / "src/bad.ts"
        bad.write_bytes(b"\xff\xfe\x00")
        undecodable = extract_js_ts_import_edges(root, "src/bad.ts")

        assert oversized.skipped_items == ("src/large.ts: oversized_source",)
        assert undecodable.skipped_items == ("src/bad.ts: decode_error",)
        assert oversized.edges == undecodable.edges == ()


def test_comments_and_strings_do_not_create_edges():
    temporary, _root, report = _extract(
        {
            "src/main.ts": (
                "// import './fake'\n"
                "const text = \"require('./also-fake')\"\n"
                "import './real'\n"
            ),
            "src/fake.ts": "",
            "src/also-fake.ts": "",
            "src/real.ts": "",
        }
    )
    with temporary:
        assert [edge.target_file for edge in report.edges] == ["src/real.ts"]


def test_output_is_deterministic_and_h1_json_ready():
    files = {
        "src/main.ts": "import './zed'\nexport * from './alpha'\n",
        "src/alpha.ts": "",
        "src/zed.ts": "",
    }
    temporary, root, first = _extract(files)
    with temporary:
        second = extract_js_ts_import_edges(root, "src/main.ts")
        assert first.to_dict() == second.to_dict()
        payload = [dependency_edge_to_dict(edge) for edge in first.edges]
        assert json.loads(json.dumps(payload, allow_nan=False)) == payload
        assert {item["edge_type"] for item in payload} == {"import", "re_export"}


TESTS = [
    test_default_import_resolves_supported_extensions,
    test_named_and_namespace_imports_resolve,
    test_side_effect_import_resolves,
    test_named_re_export_resolves_with_re_export_type,
    test_export_star_resolves_with_re_export_type,
    test_dynamic_import_and_require_resolve_as_lower_certainty_edges,
    test_directory_index_resolution_uses_documented_extensions,
    test_external_and_alias_imports_are_skipped_deterministically,
    test_unresolved_relative_import_is_skipped_deterministically,
    test_absolute_and_escaping_source_paths_are_rejected,
    test_symlink_target_escaping_root_is_skipped_safely,
    test_target_module_is_not_read_or_executed,
    test_oversized_and_non_utf8_sources_are_skipped,
    test_comments_and_strings_do_not_create_edges,
    test_output_is_deterministic_and_h1_json_ready,
]
