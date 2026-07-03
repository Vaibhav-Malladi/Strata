from pathlib import Path, PurePosixPath, PureWindowsPath

from strata.core.candidate_evaluation import (
    EXPECTED_FILE_TIERS,
    ExpectedFileTier,
    load_candidate_evaluation_manifest,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "candidate_quality"
EXPECTED_FIXTURES = {
    "strata_smoke",
    "messy_python",
    "messy_react",
    "messy_angular",
    "external_style_small",
}
GENERIC_IMPORTANT_FILENAMES = {
    "index.ts",
    "helpers.py",
    "utils.ts",
    "service.ts",
    "api.ts",
}


def _manifest_paths() -> tuple[Path, ...]:
    return tuple(sorted(FIXTURE_ROOT.glob("*/manifest.json")))


def _loaded_manifests():
    return tuple(
        (path, load_candidate_evaluation_manifest(path))
        for path in _manifest_paths()
    )


def test_all_candidate_quality_manifests_load_successfully():
    manifests = _loaded_manifests()

    assert {path.parent.name for path, _manifest in manifests} == EXPECTED_FIXTURES
    assert all(manifest.schema_version == 1 for _path, manifest in manifests)


def test_every_expected_file_exists_in_its_fixture_repo():
    missing: list[str] = []
    for manifest_path, manifest in _loaded_manifests():
        for task in manifest.tasks:
            fixture_repo = manifest_path.parent / Path(task.fixture_path)
            for tier in EXPECTED_FILE_TIERS:
                expected_files = task.expected_files.for_tier(ExpectedFileTier(tier))
                for expected_file in expected_files:
                    target = fixture_repo.joinpath(*PurePosixPath(expected_file.path).parts)
                    if not target.is_file():
                        missing.append(f"{task.task_id}:{tier}:{expected_file.path}")

    assert not missing, "Missing candidate-quality fixture files: " + ", ".join(missing)


def test_every_candidate_quality_fixture_has_at_least_one_task():
    for _path, manifest in _loaded_manifests():
        assert manifest.tasks
        for task in manifest.tasks:
            for tier in ExpectedFileTier:
                assert task.expected_files.for_tier(tier)


def test_fixture_set_covers_required_project_styles():
    coverage = {
        path.parent.name: {
            "stacks": {
                stack for task in manifest.tasks for stack in task.tags.stacks
            },
            "languages": {
                language for task in manifest.tasks for language in task.tags.languages
            },
            "frameworks": {
                framework for task in manifest.tasks for framework in task.tags.frameworks
            },
        }
        for path, manifest in _loaded_manifests()
    }

    assert "python" in coverage["messy_python"]["languages"]
    assert "react" in coverage["messy_react"]["frameworks"]
    assert "angular" in coverage["messy_angular"]["frameworks"]
    assert "repository-intelligence" in coverage["strata_smoke"]["stacks"]
    assert "library" in coverage["external_style_small"]["stacks"]


def test_generic_important_filenames_have_critical_or_useful_examples():
    represented: set[str] = set()
    for _manifest_path, manifest in _loaded_manifests():
        for task in manifest.tasks:
            for tier in ("critical", "useful"):
                expected_files = task.expected_files.for_tier(ExpectedFileTier(tier))
                represented.update(
                    PurePosixPath(expected_file.path).name
                    for expected_file in expected_files
                )

    assert GENERIC_IMPORTANT_FILENAMES <= represented


def test_manifest_paths_are_relative_and_stay_inside_fixture_directories():
    for manifest_path, manifest in _loaded_manifests():
        fixture_directory = manifest_path.parent.resolve()
        for task in manifest.tasks:
            fixture_path = PurePosixPath(task.fixture_path)
            assert not fixture_path.is_absolute()
            assert not PureWindowsPath(task.fixture_path).drive
            assert ".." not in fixture_path.parts

            fixture_repo = (fixture_directory / Path(task.fixture_path)).resolve()
            fixture_repo.relative_to(fixture_directory)
            for tier in EXPECTED_FILE_TIERS:
                expected_files = task.expected_files.for_tier(ExpectedFileTier(tier))
                for expected_file in expected_files:
                    expected_path = PurePosixPath(expected_file.path)
                    assert not expected_path.is_absolute()
                    assert not PureWindowsPath(expected_file.path).drive
                    assert ".." not in expected_path.parts
                    target = fixture_repo.joinpath(*expected_path.parts).resolve()
                    target.relative_to(fixture_repo)


TESTS = [
    test_all_candidate_quality_manifests_load_successfully,
    test_every_expected_file_exists_in_its_fixture_repo,
    test_every_candidate_quality_fixture_has_at_least_one_task,
    test_fixture_set_covers_required_project_styles,
    test_generic_important_filenames_have_critical_or_useful_examples,
    test_manifest_paths_are_relative_and_stay_inside_fixture_directories,
]
