import json
import tempfile
from pathlib import Path
from unittest import mock

import strata.utils.config as workflow_config
import strata.utils.workspace_discovery as discovery


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _write(path: Path, text: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _repo(root: Path, name: str, *, git: bool = True) -> Path:
    path = root / name
    path.mkdir(parents=True, exist_ok=True)
    if git:
        (path / ".git").mkdir()
    return path


def _package(path: Path, name: str, extra: str = "") -> None:
    suffix = f",\n{extra}" if extra else ""
    _write(path / "package.json", f'{{"name": "{name}"{suffix}}}\n')


def _candidate_paths(result) -> list[str]:
    return [candidate["path"] for candidate in result.to_dict()["candidates"]]


def _candidate(result, path: str) -> dict:
    for item in result.to_dict()["candidates"]:
        if item["path"] == path:
            return item
    raise AssertionError(f"candidate not found: {path}")


def _diagnostic_codes(result) -> list[str]:
    return [item["code"] for item in result.to_dict()["diagnostics"]]


def test_discovers_direct_sibling_git_repositories_and_omits_current():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        current = _repo(root, "app-current")
        _repo(root, "app-backend")

        result = discovery.discover_workspace_repositories(current)

        assert _candidate_paths(result) == ["../app-backend"]
        backend = _candidate(result, "../app-backend")
        assert backend["confidence"] == "low"
        assert [item["signal_type"] for item in backend["evidence"]] == [
            "sibling_proximity",
            "git_marker",
            "name_similarity",
        ]


def test_ignores_non_repository_directories():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        current = _repo(root, "current")
        (root / "notes").mkdir()

        result = discovery.discover_workspace_repositories(current)

        assert result.to_dict()["candidates"] == []


def test_detects_package_json_project_name_and_react_frontend_role():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        current = _repo(root, "current")
        frontend = _repo(root, "frontend")
        _package(
            frontend,
            "@example/frontend",
            '"dependencies": {"react": "^19.0.0"}',
        )

        candidate = _candidate(discovery.discover_workspace_repositories(current), "../frontend")

        assert candidate["display_name"] == "@example/frontend"
        assert candidate["suggested_id"] == "frontend"
        assert candidate["probable_role"] == "frontend"
        assert any(item["source_path"].endswith("package.json") for item in candidate["evidence"])


def test_detects_pyproject_project_name_and_backend_role():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        current = _repo(root, "current")
        backend = _repo(root, "backend")
        _write(
            backend / "pyproject.toml",
            '[project]\nname = "example-backend"\ndependencies = ["fastapi"]\n',
        )

        candidate = _candidate(discovery.discover_workspace_repositories(current), "../backend")

        assert candidate["display_name"] == "example-backend"
        assert candidate["probable_role"] == "backend"


def test_detects_go_mod_module_name_and_backend_role():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        current = _repo(root, "current")
        service = _repo(root, "service")
        _write(service / "go.mod", "module example.com/app/service\n\ngo 1.23\n")

        candidate = _candidate(discovery.discover_workspace_repositories(current), "../service")

        assert candidate["display_name"] == "example.com/app/service"
        assert candidate["probable_role"] == "backend"


def test_detects_angular_frontend_role():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        current = _repo(root, "current")
        frontend = _repo(root, "angular-ui")
        _write(frontend / "angular.json", "{}\n")

        candidate = _candidate(discovery.discover_workspace_repositories(current), "../angular-ui")

        assert candidate["probable_role"] == "frontend"


def test_detects_infrastructure_role_from_docker_compose_only_candidate():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        current = _repo(root, "current")
        infra = root / "infra"
        infra.mkdir()
        _write(infra / "docker-compose.yml", "services: {}\n")

        candidate = _candidate(discovery.discover_workspace_repositories(current), "../infra")

        assert candidate["probable_role"] == "infrastructure"


def test_detects_explicit_package_json_file_dependency():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        current = _repo(root, "frontend")
        backend = _repo(root, "backend")
        _package(backend, "@example/backend")
        _package(
            current,
            "@example/frontend",
            '"dependencies": {"@example/backend": "file:../backend"}',
        )

        candidate = _candidate(discovery.discover_workspace_repositories(current), "../backend")

        assert candidate["confidence"] == "high"
        assert any(item["signal_type"] == "local_path_reference" for item in candidate["evidence"])


def test_detects_go_work_use_relationship():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        current = _repo(root, "gateway")
        backend = _repo(root, "backend")
        _write(backend / "go.mod", "module example.com/backend\n")
        _write(current / "go.work", "go 1.23\n\nuse (\n  ../backend\n)\n")

        candidate = _candidate(discovery.discover_workspace_repositories(current), "../backend")

        assert candidate["confidence"] == "high"
        assert any(item["signal_type"] == "workspace_file_membership" for item in candidate["evidence"])


def test_detects_docker_compose_build_context_relationship():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        current = _repo(root, "ops")
        worker = _repo(root, "worker")
        _write(worker / "go.mod", "module example.com/worker\n")
        _write(current / "docker-compose.yml", "services:\n  worker:\n    build: ../worker\n")

        candidate = _candidate(discovery.discover_workspace_repositories(current), "../worker")

        assert candidate["confidence"] == "high"
        assert any(item["signal_type"] == "docker_compose_build_context" for item in candidate["evidence"])


def test_sibling_proximity_and_name_similarity_remain_weak_without_strong_relationship_signal():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        current = _repo(root, "billing-frontend")
        sibling = _repo(root, "billing-tools")
        _package(sibling, "billing-tools")

        candidate = _candidate(discovery.discover_workspace_repositories(current), "../billing-tools")

        assert candidate["confidence"] != "high"
        assert not any(
            item["signal_type"] in {"local_path_reference", "workspace_file_membership", "docker_compose_build_context"}
            for item in candidate["evidence"]
        )


def test_combines_independent_signals_deterministically():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        current = _repo(root, "shop-frontend")
        backend = _repo(root, "shop-backend")
        _package(backend, "@shop/backend")
        _package(current, "@shop/frontend", '"dependencies": {"@shop/backend": "file:../shop-backend"}')

        first = discovery.discover_workspace_repositories(current).to_dict()
        second = discovery.discover_workspace_repositories(current).to_dict()

        assert first == second
        candidate = first["candidates"][0]
        assert candidate["confidence"] == "high"
        assert [item["signal_type"] for item in candidate["evidence"]] == [
            "sibling_proximity",
            "git_marker",
            "project_manifest",
            "local_path_reference",
            "name_similarity",
        ]


def test_caps_candidate_count_and_reports_truncation():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        current = _repo(root, "current")
        for name in ("one", "two", "three"):
            sibling = _repo(root, name)
            _package(sibling, name)

        result = discovery.discover_workspace_repositories(current, max_candidates=2)

        assert len(result.to_dict()["candidates"]) == 2
        assert "workspace_discovery_candidate_cap_reached" in _diagnostic_codes(result)


def test_caps_evidence_count_and_reports_truncation():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        current = _repo(root, "shop-current")
        sibling = _repo(root, "shop-frontend")
        _package(
            sibling,
            "@shop/frontend",
            '"dependencies": {"react": "^19.0.0"}',
        )
        _write(sibling / "angular.json", "{}\n")
        _write(sibling / "package-lock.json", "{}\n")
        _package(current, "@shop/current", '"dependencies": {"@shop/frontend": "file:../shop-frontend"}')

        result = discovery.discover_workspace_repositories(
            current,
            max_evidence_per_candidate=2,
        )
        candidate = _candidate(result, "../shop-frontend")

        assert len(candidate["evidence"]) == 2
        assert candidate["warnings"] == ["evidence cap reached; omitted 5 item(s)."]
        assert "workspace_discovery_evidence_cap_reached" in _diagnostic_codes(result)


def test_skips_symlinks_when_supported_by_filesystem():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        current = _repo(root, "current")
        target = _repo(root, "target")
        link = root / "linked-target"
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError:
            return

        result = discovery.discover_workspace_repositories(current)

        assert "../linked-target" not in _candidate_paths(result)
        assert "workspace_discovery_symlink_skipped" in _diagnostic_codes(result)


def test_does_not_escape_explicit_search_root():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        current = _repo(root / "outside", "current")
        search = root / "search"
        search.mkdir()

        result = discovery.discover_workspace_repositories(current, search_root=search)

        assert result.to_dict()["candidates"] == []
        assert _diagnostic_codes(result) == ["workspace_discovery_repository_outside_search_root"]


def test_handles_malformed_package_json_and_pyproject_toml():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        current = _repo(root, "current")
        bad_package = _repo(root, "bad-package")
        _write(bad_package / "package.json", "{bad json")
        bad_pyproject = _repo(root, "bad-python")
        _write(bad_pyproject / "pyproject.toml", "[project\n")

        result = discovery.discover_workspace_repositories(current)
        codes = _diagnostic_codes(result)

        assert codes.count("workspace_discovery_malformed_manifest") == 2
        assert sorted(_candidate_paths(result)) == ["../bad-package", "../bad-python"]


def test_handles_missing_search_root_and_file_search_root_safely():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        current = _repo(root, "current")
        file_search_root = _write(root / "search.txt", "not a directory")

        missing = discovery.discover_workspace_repositories(current, search_root=root / "missing")
        file_result = discovery.discover_workspace_repositories(current, search_root=file_search_root)

        assert _diagnostic_codes(missing) == ["workspace_discovery_search_root_missing"]
        assert _diagnostic_codes(file_result) == ["workspace_discovery_search_root_not_directory"]


def test_handles_unreadable_candidate_safely():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        current = _repo(root, "current")
        broken = root / "broken"
        broken.mkdir()

        original_is_dir = Path.is_dir

        def fake_is_dir(path: Path):
            if path == broken:
                raise OSError("blocked")
            return original_is_dir(path)

        with mock.patch.object(Path, "is_dir", fake_is_dir):
            result = discovery.discover_workspace_repositories(current)

        assert result.to_dict()["candidates"] == []
        assert "workspace_discovery_candidate_unreadable" in _diagnostic_codes(result)


def test_deduplicates_normalized_candidate_paths():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        current = _repo(root, "current")
        backend = _repo(root, "backend")
        _package(backend, "backend")

        original_iterdir = Path.iterdir

        def fake_iterdir(path: Path):
            if path == root:
                return iter((current, backend, backend))
            return original_iterdir(path)

        with mock.patch.object(Path, "iterdir", fake_iterdir):
            result = discovery.discover_workspace_repositories(current)

        assert _candidate_paths(result) == ["../backend"]
        assert "workspace_discovery_duplicate_candidate_path" in _diagnostic_codes(result)


def test_reports_unsupported_or_ambiguous_manifest_patterns():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        current = _repo(root, "current")
        backend = _repo(root, "backend")
        _package(backend, "backend")
        _write(current / "pnpm-workspace.yaml", "packages:\n  - '../*'\n")

        result = discovery.discover_workspace_repositories(current)

        assert "workspace_discovery_unsupported_or_ambiguous_manifest" in _diagnostic_codes(result)


def test_omits_already_configured_repositories():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        current = _repo(root, "current")
        backend = _repo(root, "backend")
        _package(backend, "backend")
        workspace = {
            "schema_version": 1,
            "name": "configured",
            "repositories": [
                {"id": "backend", "path": "../backend", "role": "backend"},
            ],
        }

        result = discovery.discover_workspace_repositories(
            current,
            existing_workspace_config=workspace,
        )

        assert result.to_dict()["candidates"] == []


def test_result_serialization_is_json_ready_and_field_order_is_stable():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        current = _repo(root, "current")
        sibling = _repo(root, "backend")
        _package(sibling, "backend")

        payload = discovery.discover_workspace_repositories(current).to_dict()

        assert list(payload) == list(discovery.DISCOVERY_RESULT_FIELD_ORDER)
        assert list(payload["candidates"][0]) == list(discovery.CANDIDATE_FIELD_ORDER)
        assert list(payload["candidates"][0]["evidence"][0]) == list(discovery.EVIDENCE_FIELD_ORDER)
        assert json.loads(json.dumps(payload, allow_nan=False)) == payload


def test_preserves_q1_workspace_configuration_behaviour():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        workspace = {
            "schema_version": 1,
            "name": "example",
            "repositories": [
                {"id": "frontend", "path": "../frontend", "role": "frontend"},
            ],
        }

        normalized = workflow_config.validate_config({"workspace": workspace})

        assert normalized["workspace"]["repositories"][0]["id"] == "frontend"


def test_workspace_discovery_imports_are_scanner_compatible_and_layer_safe():
    source = (PROJECT_ROOT / "strata" / "utils" / "workspace_discovery.py").read_text(
        encoding="utf-8"
    )

    assert "import strata.utils.workspace_config as workspace_config" in source
    assert "from strata.utils import" not in source
    assert "strata.commands" not in source
    assert "strata.core" not in source


def test_workspace_q2_docs_define_suggestion_only_scope():
    content = (PROJECT_ROOT / "docs" / "roadmap" / "workspace-intelligence.md").read_text(
        encoding="utf-8"
    )

    assert "Q2" in content
    assert "suggestions only" in content
    assert "candidate cap" in content
    assert "does not alter `.aidc/config.json`" in content
    assert "does not perform deep cross-repository source scanning" in content


TESTS = [
    test_discovers_direct_sibling_git_repositories_and_omits_current,
    test_ignores_non_repository_directories,
    test_detects_package_json_project_name_and_react_frontend_role,
    test_detects_pyproject_project_name_and_backend_role,
    test_detects_go_mod_module_name_and_backend_role,
    test_detects_angular_frontend_role,
    test_detects_infrastructure_role_from_docker_compose_only_candidate,
    test_detects_explicit_package_json_file_dependency,
    test_detects_go_work_use_relationship,
    test_detects_docker_compose_build_context_relationship,
    test_sibling_proximity_and_name_similarity_remain_weak_without_strong_relationship_signal,
    test_combines_independent_signals_deterministically,
    test_caps_candidate_count_and_reports_truncation,
    test_caps_evidence_count_and_reports_truncation,
    test_skips_symlinks_when_supported_by_filesystem,
    test_does_not_escape_explicit_search_root,
    test_handles_malformed_package_json_and_pyproject_toml,
    test_handles_missing_search_root_and_file_search_root_safely,
    test_handles_unreadable_candidate_safely,
    test_deduplicates_normalized_candidate_paths,
    test_reports_unsupported_or_ambiguous_manifest_patterns,
    test_omits_already_configured_repositories,
    test_result_serialization_is_json_ready_and_field_order_is_stable,
    test_preserves_q1_workspace_configuration_behaviour,
    test_workspace_discovery_imports_are_scanner_compatible_and_layer_safe,
    test_workspace_q2_docs_define_suggestion_only_scope,
]
