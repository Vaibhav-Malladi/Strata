import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from strata.core.inventory import (
    InventoryRecord,
    collect_inventory,
    create_inventory_record,
    guess_folder_role,
    guess_language,
    is_generated_path,
    is_test_path,
)


def test_create_inventory_record_uses_relative_path_and_stat_metadata_only():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        file_path = root / "src" / "Widget.TSX"
        file_path.parent.mkdir(parents=True)
        file_path.write_bytes(b"export const Widget = 1;\n")
        os.utime(file_path, (1_700_000_000, 1_700_000_000))

        with patch.object(Path, "open", side_effect=AssertionError("inventory read file contents")):
            record = create_inventory_record(root, file_path)

        assert isinstance(record, InventoryRecord)
        assert Path(record.path) == Path("src") / "Widget.TSX"
        assert record.extension == ".tsx"
        assert record.size == len(b"export const Widget = 1;\n")
        assert record.mtime == 1_700_000_000
        assert record.is_test is False
        assert record.is_generated_guess is False
        assert record.folder_role == "source"
        assert record.language_guess == "typescript"


def test_create_inventory_record_accepts_a_root_relative_file_path():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        file_path = root / "tests" / "test_api.py"
        file_path.parent.mkdir(parents=True)
        file_path.write_text("pass\n", encoding="utf-8")

        record = create_inventory_record(root, Path("tests") / "test_api.py")

        assert Path(record.path) == Path("tests") / "test_api.py"
        assert record.is_test is True
        assert record.folder_role == "test"
        assert record.language_guess == "python"


def test_path_classification_handles_windows_style_paths():
    path = r"packages\web\__tests__\checkout.spec.tsx"

    assert is_test_path(path) is True
    assert guess_folder_role(path) == "test"
    assert guess_language(path) == "typescript"


def test_generated_guess_covers_build_vendor_minified_and_lockfile_paths():
    assert is_generated_path("dist/app.js") is True
    assert is_generated_path(r"node_modules\pkg\index.js") is True
    assert is_generated_path("src/client.min.js") is True
    assert is_generated_path("package-lock.json") is True
    assert is_generated_path("src/client.js") is False


def test_folder_roles_are_path_derived_and_coarse():
    assert guess_folder_role("README.md") == "root"
    assert guess_folder_role("docs/architecture.md") == "docs"
    assert guess_folder_role(r"third_party\library\main.cc") == "vendor"
    assert guess_folder_role("unknown/place/data.bin") == "other"


def test_collect_inventory_returns_records_in_deterministic_order():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        (root / "src").mkdir(parents=True)
        (root / "src" / "zeta.ts").write_text("zeta\n", encoding="utf-8")
        (root / "src" / "alpha.ts").write_text("alpha\n", encoding="utf-8")
        (root / "README.md").write_text("readme\n", encoding="utf-8")

        first = collect_inventory(root)
        second = collect_inventory(root)

        assert all(isinstance(record, InventoryRecord) for record in first)
        assert [record.path for record in first] == [record.path for record in second]
        assert [Path(record.path) for record in first] == [
            Path("README.md"),
            Path("src") / "alpha.ts",
            Path("src") / "zeta.ts",
        ]


def test_collect_inventory_skips_noisy_and_hidden_paths_by_default():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        for folder in (".git", "node_modules", "build", "__pycache__", ".hidden"):
            path = root / folder
            path.mkdir(parents=True, exist_ok=True)
            (path / "ignored.py").write_text("ignored\n", encoding="utf-8")
        root.mkdir(exist_ok=True)
        (root / ".env").write_text("SECRET=value\n", encoding="utf-8")
        (root / "pyproject.toml").write_text("[project]\n", encoding="utf-8")

        default_records = collect_inventory(root)
        hidden_records = collect_inventory(root, include_hidden=True)

        assert [Path(record.path) for record in default_records] == [Path("pyproject.toml")]
        assert {Path(record.path) for record in hidden_records} == {
            Path(".env"),
            Path(".hidden") / "ignored.py",
            Path("pyproject.toml"),
        }


def test_collect_inventory_respects_max_files():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        root.mkdir()
        for name in ("c.py", "a.py", "b.py"):
            (root / name).write_text(name, encoding="utf-8")

        records = collect_inventory(root, max_files=2)

        assert [Path(record.path) for record in records] == [Path("a.py"), Path("b.py")]


def test_collect_inventory_rejects_invalid_max_files():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        invalid_values = (0, -1, True, 1.5)
        for invalid_value in invalid_values:
            try:
                collect_inventory(root, max_files=invalid_value)
            except (TypeError, ValueError):
                pass
            else:
                raise AssertionError(f"max_files {invalid_value!r} should be rejected")


def test_collect_inventory_rejects_missing_or_file_roots():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        file_path = root / "file.py"
        file_path.write_text("pass\n", encoding="utf-8")

        try:
            collect_inventory(root / "missing")
        except FileNotFoundError:
            pass
        else:
            raise AssertionError("missing inventory root should be rejected")

        try:
            collect_inventory(file_path)
        except NotADirectoryError:
            pass
        else:
            raise AssertionError("file inventory root should be rejected")


def test_collect_inventory_does_not_open_file_contents():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        root.mkdir()
        (root / "unreadable-by-contract.py").write_text("pass\n", encoding="utf-8")

        with patch.object(Path, "open", side_effect=AssertionError("inventory opened file")):
            records = collect_inventory(root)

        assert len(records) == 1


TESTS = [
    test_create_inventory_record_uses_relative_path_and_stat_metadata_only,
    test_create_inventory_record_accepts_a_root_relative_file_path,
    test_path_classification_handles_windows_style_paths,
    test_generated_guess_covers_build_vendor_minified_and_lockfile_paths,
    test_folder_roles_are_path_derived_and_coarse,
    test_collect_inventory_returns_records_in_deterministic_order,
    test_collect_inventory_skips_noisy_and_hidden_paths_by_default,
    test_collect_inventory_respects_max_files,
    test_collect_inventory_rejects_invalid_max_files,
    test_collect_inventory_rejects_missing_or_file_roots,
    test_collect_inventory_does_not_open_file_contents,
]
