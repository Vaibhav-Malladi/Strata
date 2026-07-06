import json
import tempfile
from pathlib import Path

from strata.core.dependency_tracing import dependency_edge_to_dict
from strata.core.python_dependency_edges import extract_python_import_edges


def _write(root: Path, relative_path: str, content: str = "") -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _extract(files: dict[str, str], source: str = "main.py"):
    temporary = tempfile.TemporaryDirectory()
    root = Path(temporary.name)
    for path, content in files.items():
        _write(root, path, content)
    return temporary, root, extract_python_import_edges(root, source)


def _expect_error(error_type, function, *args, contains: str, **kwargs):
    try:
        function(*args, **kwargs)
    except error_type as error:
        assert contains in str(error)
    else:
        raise AssertionError(f"Expected {error_type.__name__}")


def test_import_module_resolves_module_file():
    temporary, _root, report = _extract(
        {"main.py": "import helper\n", "helper.py": "VALUE = 1\n"}
    )
    with temporary:
        assert [(edge.target_file, edge.priority, edge.confidence) for edge in report.edges] == [
            ("helper.py", "medium", "high")
        ]


def test_import_dotted_module_resolves_exact_module_file():
    temporary, _root, report = _extract(
        {
            "main.py": "import package.module\n",
            "package/__init__.py": "",
            "package/module.py": "",
        }
    )
    with temporary:
        assert report.edges[0].target_file == "package/module.py"


def test_import_package_resolves_package_initializer():
    temporary, _root, report = _extract(
        {"main.py": "import package\n", "package/__init__.py": ""}
    )
    with temporary:
        assert report.edges[0].target_file == "package/__init__.py"


def test_from_package_import_module_prefers_child_module():
    temporary, _root, report = _extract(
        {
            "main.py": "from package import module\n",
            "package/__init__.py": "",
            "package/module.py": "",
        }
    )
    with temporary:
        assert report.edges[0].target_file == "package/module.py"
        assert report.edges[0].confidence == "high"


def test_from_package_module_import_symbol_resolves_containing_module():
    temporary, _root, report = _extract(
        {
            "main.py": "from package.module import symbol\n",
            "package/__init__.py": "",
            "package/module.py": "symbol = 1\n",
        }
    )
    with temporary:
        assert report.edges[0].target_file == "package/module.py"
        assert report.edges[0].priority == "low"
        assert report.edges[0].confidence == "medium"


def test_alias_import_reason_preserves_alias():
    temporary, _root, report = _extract(
        {"main.py": "import helper as renamed\n", "helper.py": ""}
    )
    with temporary:
        assert report.edges[0].reason == "Python import: import helper as renamed"


def test_relative_import_from_sibling_resolves():
    temporary, _root, report = _extract(
        {
            "pkg/main.py": "from . import helper\n",
            "pkg/__init__.py": "",
            "pkg/helper.py": "",
        },
        source="pkg/main.py",
    )
    with temporary:
        assert report.edges[0].target_file == "pkg/helper.py"


def test_relative_import_from_parent_package_resolves():
    temporary, _root, report = _extract(
        {
            "pkg/sub/main.py": "from ..utils import thing\n",
            "pkg/__init__.py": "",
            "pkg/sub/__init__.py": "",
            "pkg/utils.py": "thing = 1\n",
        },
        source="pkg/sub/main.py",
    )
    with temporary:
        assert report.edges[0].target_file == "pkg/utils.py"


def test_common_src_root_is_supported_without_inventory_scan():
    temporary, _root, report = _extract(
        {
            "src/app/main.py": "import app.helper\n",
            "src/app/__init__.py": "",
            "src/app/helper.py": "",
        },
        source="src/app/main.py",
    )
    with temporary:
        assert report.edges[0].target_file == "src/app/helper.py"


def test_unresolved_external_import_is_skipped_deterministically():
    temporary, _root, report = _extract({"main.py": "import external_package\n"})
    with temporary:
        assert report.edges == ()
        assert report.skipped_items == ("unresolved import: import external_package",)
        assert report.warnings == ()


def test_syntax_error_returns_warning_and_empty_edges():
    temporary, _root, report = _extract({"main.py": "def broken(:\n"})
    with temporary:
        assert report.edges == ()
        assert report.skipped_items == ("main.py: syntax_error",)
        assert report.warnings[0].startswith("syntax error at line 1:")
        assert report.stage_report.bytes_read > 0


def test_absolute_and_escaping_source_paths_are_rejected():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write(root, "main.py", "")
        for source in (str((root / "main.py").resolve()), "../main.py"):
            _expect_error(
                ValueError,
                extract_python_import_edges,
                root,
                source,
                contains="path must",
            )


def test_target_module_is_never_executed_or_imported():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        marker = root / "executed.txt"
        _write(root, "main.py", "import dangerous\n")
        _write(
            root,
            "dangerous.py",
            f"from pathlib import Path\nPath({str(marker)!r}).write_text('bad')\n",
        )

        report = extract_python_import_edges(root, "main.py")

        assert report.edges[0].target_file == "dangerous.py"
        assert not marker.exists()


def test_output_is_deterministic_and_h1_json_ready():
    files = {
        "main.py": "import zed\nimport alpha\n",
        "alpha.py": "",
        "zed.py": "",
    }
    temporary, root, first = _extract(files)
    with temporary:
        second = extract_python_import_edges(root, "main.py")
        assert first.to_dict() == second.to_dict()
        payload = [dependency_edge_to_dict(edge) for edge in first.edges]
        assert [item["target_file"] for item in payload] == ["alpha.py", "zed.py"]
        assert json.loads(json.dumps(payload, allow_nan=False)) == payload


TESTS = [
    test_import_module_resolves_module_file,
    test_import_dotted_module_resolves_exact_module_file,
    test_import_package_resolves_package_initializer,
    test_from_package_import_module_prefers_child_module,
    test_from_package_module_import_symbol_resolves_containing_module,
    test_alias_import_reason_preserves_alias,
    test_relative_import_from_sibling_resolves,
    test_relative_import_from_parent_package_resolves,
    test_common_src_root_is_supported_without_inventory_scan,
    test_unresolved_external_import_is_skipped_deterministically,
    test_syntax_error_returns_warning_and_empty_edges,
    test_absolute_and_escaping_source_paths_are_rejected,
    test_target_module_is_never_executed_or_imported,
    test_output_is_deterministic_and_h1_json_ready,
]
