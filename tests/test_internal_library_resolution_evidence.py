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


def test_explicit_internal_import_resolves_node_package_evidence():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        package = root / "node_modules" / "@company" / "master-library"
        _write(
            package / "package.json",
            json.dumps(
                {
                    "name": "@company/master-library",
                    "version": "2.3.1",
                    "types": "types/public-api.d.ts",
                }
            ),
        )
        _write(package / "types" / "public-api.d.ts", "export declare class Modal {}")

        result = _discover(root, "@company/master-library")[0]

        assert result.library_name == "@company/master-library"
        assert result.classification == "resolved_node_modules_declaration"
        assert result.source_availability == "declaration_only"
        assert result.version.to_dict() == {
            "version": "2.3.1",
            "version_source": "package_json",
            "version_confidence": "high",
        }
        assert result.evidence.resolved_path == "node_modules/@company/master-library"
        assert result.evidence.package_json_path == (
            "node_modules/@company/master-library/package.json"
        )
        assert result.context_paths == (
            "node_modules/@company/master-library/types/public-api.d.ts",
        )


def test_scoped_subpath_import_resolves_to_scoped_package_root():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        package = root / "node_modules" / "@company" / "master-library"
        _write(package / "index.d.ts", "export declare const dropdown: unknown;")

        result = _discover(root, "@company/master-library/dropdown")[0]

        assert result.library_name == "@company/master-library"
        assert result.classification == "resolved_node_modules_declaration"
        assert result.evidence.import_paths == ("@company/master-library/dropdown",)
        assert result.evidence.resolved_path == "node_modules/@company/master-library"


def test_extracted_vendor_directory_with_package_metadata_and_declaration_resolves():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        vendor = root / "vendor" / "master-library"
        _write(
            vendor / "package.json",
            json.dumps(
                {
                    "name": "@company/master-library",
                    "version": "4.0.0",
                    "typings": "public-api.d.ts",
                }
            ),
        )
        _write(vendor / "public-api.d.ts", "export declare const theme: string;")

        result = _discover(root, "master-library")[0]

        assert result.classification == "resolved_vendor_directory_declaration"
        assert result.source_availability == "declaration_only"
        assert result.evidence.vendor_path == "vendor/master-library"
        assert result.evidence.package_json_path == "vendor/master-library/package.json"
        assert result.evidence.declaration_paths == ("vendor/master-library/public-api.d.ts",)
        assert result.version.version == "4.0.0"


def test_extracted_vendor_directory_without_declaration_is_opaque():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        vendor = root / "vendor" / "master-library"
        _write(
            vendor / "package.json",
            json.dumps({"name": "@company/master-library", "version": "4.0.0"}),
        )

        result = _discover(root, "master-library")[0]

        assert result.classification == "opaque_private_package"
        assert result.source_availability == "metadata_only"
        assert result.evidence.vendor_path == "vendor/master-library"
        assert result.usage_inference_required is True
        assert "package exists without readable declarations" in result.diagnostic_notes


def test_archive_reference_is_detected_without_extraction_or_content_read():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        _write(root / "vendor" / "master-library.zip", "pretend zip bytes")

        result = _discover(root, "master-library")[0]

        assert result.classification == "resolved_vendor_zip_reference"
        assert result.source_availability == "zip_reference_only"
        assert result.evidence.archive_path == "vendor/master-library.zip"
        assert result.evidence.declaration_paths == ()
        assert result.context_paths == ()
        assert result.safety.bytes_read == 0
        assert "archive recorded without extraction" in result.evidence.notes
        assert not (root / "vendor" / "master-library").exists()


def test_versioned_archive_filename_sets_low_confidence_version_metadata():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        _write(root / "libs" / "master-library-2.3.1.tgz", "opaque")

        result = _discover(root, "master-library")[0]

        assert result.classification == "resolved_vendor_zip_reference"
        assert result.version.to_dict() == {
            "version": "2.3.1",
            "version_source": "filename",
            "version_confidence": "low",
        }


def test_missing_explicit_package_becomes_missing_package():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)

        result = _discover(root, "@company/missing-library")[0]

        assert result.library_name == "@company/missing-library"
        assert result.classification == "missing_package"
        assert result.source_availability == "unavailable"
        assert result.usage_inference_required is True
        assert "no targeted package, vendor, or archive candidate exists" in result.diagnostic_notes


def test_multiple_imports_for_same_library_dedupe_and_retain_import_evidence():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        package = root / "node_modules" / "@company" / "master-library"
        _write(package / "index.d.ts", "export {};")

        results = _discover(
            root,
            "@company/master-library/dropdown",
            "@company/master-library/button",
        )

        assert len(results) == 1
        assert results[0].library_name == "@company/master-library"
        assert results[0].evidence.import_paths == (
            "@company/master-library/button",
            "@company/master-library/dropdown",
        )


def test_declaration_caps_record_skipped_items_and_cost_metadata():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        package = root / "node_modules" / "busy-library"
        for index in range(5):
            _write(package / f"entry-{index}.d.ts", f"export declare const v{index}: string;")
        limits = InternalLibraryDiscoveryLimits(max_declaration_files=2)

        result = _discover(root, "busy-library", limits=limits)[0]

        assert result.classification == "resolved_node_modules_declaration"
        assert len(result.evidence.declaration_paths) == 2
        assert "declaration file cap reached" in result.safety.skipped_items
        assert result.safety.files_inspected > 0
        assert result.safety.bytes_read > 0


def test_declaration_path_escape_is_skipped_safely():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        package = root / "node_modules" / "escape-library"
        _write(
            package / "package.json",
            json.dumps({"version": "1.0.0", "types": "../escaped.d.ts"}),
        )
        _write(root / "node_modules" / "escaped.d.ts", "export declare const leaked: string;")

        result = _discover(root, "escape-library")[0]

        assert result.classification == "opaque_private_package"
        assert result.evidence.declaration_paths == ()
        assert any(
            "unsafe types declaration target" in item
            for item in result.safety.skipped_items
        )


def test_discovery_only_checks_explicit_imports_and_never_scans_node_modules_root():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        _write(root / "node_modules" / "target-library" / "index.d.ts", "export {};")
        _write(root / "node_modules" / "unrelated-library" / "index.d.ts", "export {};")
        original_iterdir = Path.iterdir
        enumerated = []

        def recording_iterdir(path):
            enumerated.append(path)
            return original_iterdir(path)

        Path.iterdir = recording_iterdir
        try:
            results = _discover(root, "target-library")
        finally:
            Path.iterdir = original_iterdir

        assert tuple(result.library_name for result in results) == ("target-library",)
        assert root / "node_modules" not in enumerated
        assert root / "node_modules" / "unrelated-library" not in enumerated


def test_evidence_payloads_are_deterministic_json_ready_and_confidence_is_metadata_only():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        beta = root / "node_modules" / "beta-library"
        _write(
            beta / "package.json",
            json.dumps({"version": "9.0.0", "types": "index.d.ts"}),
        )
        _write(beta / "index.d.ts", "export {};")
        _write(root / "vendor" / "alpha-library-1.0.0.zip", "opaque")

        results = _discover(root, "beta-library", "alpha-library")
        payload = [result.to_dict() for result in results]

        assert tuple(result.library_name for result in results) == (
            "alpha-library",
            "beta-library",
        )
        assert results[0].version.version_confidence == "low"
        assert results[1].version.version_confidence == "high"
        assert json.loads(json.dumps(payload, allow_nan=False)) == payload
        assert payload == [result.to_dict() for result in _discover(root, "alpha-library", "beta-library")]


TESTS = [
    test_explicit_internal_import_resolves_node_package_evidence,
    test_scoped_subpath_import_resolves_to_scoped_package_root,
    test_extracted_vendor_directory_with_package_metadata_and_declaration_resolves,
    test_extracted_vendor_directory_without_declaration_is_opaque,
    test_archive_reference_is_detected_without_extraction_or_content_read,
    test_versioned_archive_filename_sets_low_confidence_version_metadata,
    test_missing_explicit_package_becomes_missing_package,
    test_multiple_imports_for_same_library_dedupe_and_retain_import_evidence,
    test_declaration_caps_record_skipped_items_and_cost_metadata,
    test_declaration_path_escape_is_skipped_safely,
    test_discovery_only_checks_explicit_imports_and_never_scans_node_modules_root,
    test_evidence_payloads_are_deterministic_json_ready_and_confidence_is_metadata_only,
]
