import tempfile
from pathlib import Path

from scanner import scan_repo


def _write_file(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _create_scanner_repo(root: Path, *, include_unresolved: bool = True) -> None:
    root.mkdir(parents=True, exist_ok=True)

    _write_file(
        root / "helper.py",
        "def helper():\n"
        "    return True\n",
    )

    if include_unresolved:
        main_source = (
            "import os\n"
            "import helper\n"
            "import missing_module\n\n"
            "def run():\n"
            "    return helper()\n"
        )
    else:
        main_source = (
            "import os\n"
            "import helper\n\n"
            "def run():\n"
            "    return helper()\n"
        )

    _write_file(root / "main.py", main_source)


def _scan_temp_repo_result(*, include_unresolved: bool = True) -> dict:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        _create_scanner_repo(root, include_unresolved=include_unresolved)
        return scan_repo(str(root))


def _main_file(result: dict) -> dict | None:
    for file_info in result.get("files", []):
        if file_info["path"].endswith("main.py"):
            return file_info

    return None


def test_scan_repo_finds_python_files():
    result = _scan_temp_repo_result()

    paths = [file["path"] for file in result["files"]]

    assert result["root"].endswith("repo")
    assert len(result["files"]) == 2
    assert any(path.endswith("main.py") for path in paths)
    assert any(path.endswith("helper.py") for path in paths)


def test_scan_repo_detects_imports():
    result = _scan_temp_repo_result()

    main_file = _main_file(result)

    assert main_file is not None
    assert "helper" in main_file["imports"]


def test_scan_repo_creates_import_edges():
    result = _scan_temp_repo_result()

    assert "edges" in result
    assert len(result["edges"]) == 1

    edge = result["edges"][0]

    assert edge["type"] == "imports"
    assert edge["import"] == "helper"
    assert edge["from"].endswith("main.py")
    assert edge["to"].endswith("helper.py")


def test_scan_repo_resolves_same_folder_imports_from_project_root():
    result = _scan_temp_repo_result()

    matching_edges = []

    for edge in result["edges"]:
        if (
            edge["from"].endswith("main.py")
            and edge["to"].endswith("helper.py")
            and edge["import"] == "helper"
        ):
            matching_edges.append(edge)

    assert len(matching_edges) == 1


def test_scan_repo_includes_schema_version():
    result = _scan_temp_repo_result()

    assert result["schema_version"] == 1


def test_scan_repo_classifies_imports():
    result = _scan_temp_repo_result()
    main_file = _main_file(result)

    assert main_file is not None

    assert "os" in main_file["imports"]
    assert "helper" in main_file["imports"]
    assert "missing_module" in main_file["imports"]

    assert "os" in main_file["external_imports"]
    assert "missing_module" in main_file["unresolved_imports"]

    assert "helper" not in main_file["external_imports"]
    assert "helper" not in main_file["unresolved_imports"]


def test_scan_repo_records_unresolved_import_line_number():
    result = _scan_temp_repo_result()
    main_file = _main_file(result)

    assert main_file is not None

    matching_details = []

    for import_detail in main_file["unresolved_import_details"]:
        if import_detail["name"] == "missing_module":
            matching_details.append(import_detail)

    assert len(matching_details) == 1
    assert matching_details[0]["line"] == 3


TESTS = [
    test_scan_repo_finds_python_files,
    test_scan_repo_detects_imports,
    test_scan_repo_creates_import_edges,
    test_scan_repo_resolves_same_folder_imports_from_project_root,
    test_scan_repo_includes_schema_version,
    test_scan_repo_classifies_imports,
    test_scan_repo_records_unresolved_import_line_number,
]
