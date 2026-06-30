import repo_ignore as old_repo_ignore
import strata.core.repo_ignore as new_repo_ignore


def test_core_repo_ignore_import_matches_compatibility_shim():
    assert old_repo_ignore.should_ignore_directory is new_repo_ignore.should_ignore_directory
    assert old_repo_ignore.should_ignore_file is new_repo_ignore.should_ignore_file
    assert old_repo_ignore.should_ignore_path is new_repo_ignore.should_ignore_path


TESTS = [
    test_core_repo_ignore_import_matches_compatibility_shim,
]
