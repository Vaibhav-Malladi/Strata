from scanner import scan_repo


def test_scan_repo_finds_python_files():
    result = scan_repo("tmp_repo")

    paths = [file["path"] for file in result["files"]]

    assert result["root"] == "tmp_repo"
    assert len(result["files"]) == 2
    assert any(path.endswith("main.py") for path in paths)
    assert any(path.endswith("helper.py") for path in paths)


def test_scan_repo_detects_imports():
    result = scan_repo("tmp_repo")

    main_file = None

    for file in result["files"]:
        if file["path"].endswith("main.py"):
            main_file = file

    assert main_file is not None
    assert "helper" in main_file["imports"]


def test_scan_repo_creates_import_edges():
    result = scan_repo("tmp_repo")

    assert "edges" in result
    assert len(result["edges"]) == 1

    edge = result["edges"][0]

    assert edge["type"] == "imports"
    assert edge["import"] == "helper"
    assert edge["from"].endswith("main.py")
    assert edge["to"].endswith("helper.py")


def test_scan_repo_resolves_same_folder_imports_from_project_root():
    result = scan_repo(".")

    matching_edges = []

    for edge in result["edges"]:
        if (
            edge["from"].endswith("tmp_repo\\main.py")
            and edge["to"].endswith("tmp_repo\\helper.py")
            and edge["import"] == "helper"
        ):
            matching_edges.append(edge)

    assert len(matching_edges) == 1


def test_scan_repo_includes_schema_version():
    result = scan_repo("tmp_repo")

    assert result["schema_version"] == 1


def test_scan_repo_classifies_imports():
    result = scan_repo("tmp_repo")

    main_file = None

    for file_info in result["files"]:
        if file_info["path"].endswith("main.py"):
            main_file = file_info

    assert main_file is not None

    assert "os" in main_file["imports"]
    assert "helper" in main_file["imports"]
    assert "missing_module" in main_file["imports"]

    assert "os" in main_file["external_imports"]
    assert "missing_module" in main_file["unresolved_imports"]

    assert "helper" not in main_file["external_imports"]
    assert "helper" not in main_file["unresolved_imports"]


def test_scan_repo_records_unresolved_import_line_number():
    result = scan_repo("tmp_repo")

    main_file = None

    for file_info in result["files"]:
        if file_info["path"].endswith("main.py"):
            main_file = file_info

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