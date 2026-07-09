import json
import tempfile
from pathlib import Path

from strata.core.internal_library_discovery import (
    InternalLibraryDiscoveryLimits,
    discover_internal_libraries,
)


def _write(path: Path, content: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _discover(root: Path, *imports: str, limits=None):
    kwargs = {} if limits is None else {"limits": limits}
    return discover_internal_libraries(root, imports, **kwargs)


def test_targeted_node_package_reads_version_and_types_entrypoint():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        package = root / "node_modules" / "@company" / "master-library"
        _write(
            package / "package.json",
            json.dumps(
                {
                    "name": "@company/master-library",
                    "version": "2.3.1",
                    "types": "types/public.d.ts",
                    "module": "fesm2022/master.mjs",
                }
            ),
        )
        _write(package / "types" / "public.d.ts", "export declare const button: string;")

        result = _discover(root, "@company/master-library")[0]

        assert result.classification == "resolved_node_modules_declaration"
        assert result.version.to_dict() == {
            "version": "2.3.1",
            "version_source": "package_json",
            "version_confidence": "high",
        }
        assert result.evidence.declaration_paths == (
            "node_modules/@company/master-library/types/public.d.ts",
        )


def test_node_package_index_declaration_is_detected_without_metadata():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        _write(root / "node_modules" / "master-library" / "index.d.ts", "export {};")

        result = _discover(root, "master-library")[0]

        assert result.classification == "resolved_node_modules_declaration"
        assert result.source_availability == "declaration_only"
        assert result.version.version is None


def test_node_package_without_declarations_is_opaque_and_missing_is_missing():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        _write(
            root / "node_modules" / "private-kit" / "package.json",
            json.dumps({"name": "private-kit", "version": "1.0.0"}),
        )

        opaque, missing = _discover(root, "missing-kit", "private-kit")

        assert opaque.library_name == "missing-kit"
        assert opaque.classification == "missing_package"
        assert missing.library_name == "private-kit"
        assert missing.classification == "opaque_private_package"
        assert missing.source_availability == "metadata_only"


def test_scoped_subpath_import_resolves_only_the_package_root():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        package = root / "node_modules" / "@company" / "master-library"
        _write(package / "index.d.ts", "export {};")

        result = _discover(root, "@company/master-library/button")[0]

        assert result.library_name == "@company/master-library"
        assert result.evidence.resolved_path == "node_modules/@company/master-library"
        assert result.evidence.import_paths == ("@company/master-library/button",)


def test_vendor_directory_declaration_and_package_version_are_detected():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        vendor = root / "vendor" / "master-library"
        _write(
            vendor / "package.json",
            json.dumps({"version": "4.5.0", "typings": "public-api.d.ts"}),
        )
        _write(vendor / "public-api.d.ts", "export {};")

        result = _discover(root, "master-library")[0]

        assert result.classification == "resolved_vendor_directory_declaration"
        assert result.evidence.vendor_path == "vendor/master-library"
        assert result.version.version == "4.5.0"
        assert result.version.version_source == "package_json"


def test_vendor_zip_is_referenced_without_being_opened_or_extracted():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        _write(root / "vendor" / "master-library.zip", "not actually a zip")

        result = _discover(root, "master-library")[0]

        assert result.classification == "resolved_vendor_zip_reference"
        assert result.source_availability == "zip_reference_only"
        assert result.evidence.archive_path == "vendor/master-library.zip"
        assert result.version.version is None
        assert "without extraction" in result.evidence.notes[0]


def test_versioned_vendor_zip_uses_low_confidence_filename_metadata():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        _write(root / "third_party" / "master-library-2.3.1.zip", "opaque")

        result = _discover(root, "master-library")[0]

        assert result.version.to_dict() == {
            "version": "2.3.1",
            "version_source": "filename",
            "version_confidence": "low",
        }


def test_discovery_never_enumerates_the_node_modules_root():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        package = root / "node_modules" / "target-package"
        _write(package / "index.d.ts", "export {};")
        _write(root / "node_modules" / "unrelated" / "secret.d.ts", "export {};")
        original_iterdir = Path.iterdir
        enumerated = []

        def recording_iterdir(path):
            enumerated.append(path)
            return original_iterdir(path)

        Path.iterdir = recording_iterdir
        try:
            result = _discover(root, "target-package")[0]
        finally:
            Path.iterdir = original_iterdir

        assert result.classification == "resolved_node_modules_declaration"
        assert root / "node_modules" not in enumerated
        assert root / "node_modules" / "unrelated" not in enumerated


def test_declaration_file_cap_is_enforced():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        package = root / "node_modules" / "many-types"
        for name in ("a.d.ts", "b.d.ts", "c.d.ts", "d.d.ts"):
            _write(package / name, "export {};")
        limits = InternalLibraryDiscoveryLimits(max_declaration_files=2)

        result = _discover(root, "many-types", limits=limits)[0]

        assert len(result.evidence.declaration_paths) == 2
        assert "declaration file cap reached" in result.safety.skipped_items


def test_package_json_byte_cap_is_enforced_without_reading_metadata():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        package = root / "node_modules" / "large-metadata"
        _write(package / "package.json", json.dumps({"version": "9.9.9", "pad": "x" * 200}))
        limits = InternalLibraryDiscoveryLimits(max_package_json_bytes=32)

        result = _discover(root, "large-metadata", limits=limits)[0]

        assert result.classification == "opaque_private_package"
        assert result.version.version is None
        assert result.safety.bytes_read == 0
        assert any("package.json byte cap exceeded" in item for item in result.safety.skipped_items)


def test_multiple_imports_are_deduped_ordered_and_json_serializable():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        _write(root / "node_modules" / "alpha" / "index.d.ts", "export {};")
        _write(root / "node_modules" / "zeta" / "index.d.ts", "export {};")

        results = _discover(root, "zeta/button", "alpha", "zeta/dialog")
        payload = [result.to_dict() for result in results]

        assert tuple(result.library_name for result in results) == ("alpha", "zeta")
        assert results[1].evidence.import_paths == ("zeta/button", "zeta/dialog")
        assert json.loads(json.dumps(payload, allow_nan=False)) == payload


TESTS = [
    test_targeted_node_package_reads_version_and_types_entrypoint,
    test_node_package_index_declaration_is_detected_without_metadata,
    test_node_package_without_declarations_is_opaque_and_missing_is_missing,
    test_scoped_subpath_import_resolves_only_the_package_root,
    test_vendor_directory_declaration_and_package_version_are_detected,
    test_vendor_zip_is_referenced_without_being_opened_or_extracted,
    test_versioned_vendor_zip_uses_low_confidence_filename_metadata,
    test_discovery_never_enumerates_the_node_modules_root,
    test_declaration_file_cap_is_enforced,
    test_package_json_byte_cap_is_enforced_without_reading_metadata,
    test_multiple_imports_are_deduped_ordered_and_json_serializable,
]
