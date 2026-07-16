from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tomllib


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_pyproject() -> dict:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as file:
        return tomllib.load(file)


def test_distribution_name_and_console_script_are_distinct_and_correct():
    pyproject = _load_pyproject()
    project = pyproject["project"]

    assert project["name"] == "strata-repo-intel"
    assert project["scripts"]["strata"] == "strata.cli:main"


def test_strata_package_import_and_module_entrypoint():
    import strata

    assert strata.__version__ == "0.4.1"

    result = subprocess.run(
        [sys.executable, "-m", "strata", "--help"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_all_runtime_top_level_modules_are_packaged():
    pyproject = _load_pyproject()
    configured = set(pyproject["tool"]["setuptools"]["py-modules"])
    runtime_modules = {
        path.stem
        for path in PROJECT_ROOT.glob("*.py")
        if path.name != "tests.py"
    }

    assert configured == runtime_modules


def test_readme_python_and_generated_output_metadata_are_configured():
    pyproject = _load_pyproject()
    project = pyproject["project"]
    gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")

    assert project["readme"] == "README.md"
    assert project["requires-python"] == ">=3.11"
    assert project["license"] == "MIT"
    assert "Programming Language :: Python :: 3.11" in project["classifiers"]
    assert "Programming Language :: Python :: 3.12" in project["classifiers"]
    assert "Programming Language :: Python :: 3.13" in project["classifiers"]
    assert ".aidc/" in gitignore
    assert ".codex-venv/" in gitignore
    assert ".env.*" in gitignore


def test_authoritative_versions_agree():
    pyproject = _load_pyproject()

    import strata

    assert pyproject["project"]["version"] == strata.__version__


def test_public_docs_use_honest_install_runtime_and_support_wording():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    runtime_doc = (PROJECT_ROOT / "docs" / "runtime-compatibility.md").read_text(encoding="utf-8")
    help_text = (
        (PROJECT_ROOT / "strata" / "commands" / "cli_help.py").read_text(encoding="utf-8")
        + (PROJECT_ROOT / "strata" / "commands" / "help_topics.py").read_text(encoding="utf-8")
    )
    public_text = readme + runtime_doc + help_text
    readme_normalized = readme.lower()
    normalized = public_text.lower()

    assert "the pypi package is `strata-repo-intel`; the cli command is `strata`" in normalized
    assert "pipx install strata-repo-intel" in public_text
    assert "python -m pip install --user strata-repo-intel" in public_text
    assert "python -m pip install -e ." in public_text
    assert "install.ps1" in public_text
    assert "strata start" in public_text
    assert "strata start --continue" in public_text
    assert 'strata context --budget small "your task"' in public_text
    assert "strata settings" in public_text
    assert "Strata does not store API keys in the repository." in public_text
    assert "python 3.11 or newer" in readme_normalized
    assert "python 3.11 or newer" in help_text.lower()
    assert "python 3.11, 3.12, and 3.13" in normalized
    assert "python 3.13 is the recommended development environment" in normalized
    assert "python 3.13+" not in normalized
    assert "older python versions" in normalized
    assert "controlled real-repository uat" in normalized
    assert "static explanations" in normalized
    assert "dynamic framework" in normalized
    assert "add `.aidc/` to `.gitignore`" in normalized
    assert "python -m strata" not in normalized
    assert "py -m strata" not in normalized


def test_project_urls_are_verified_absolute_repository_urls():
    project = _load_pyproject()["project"]
    urls = project["urls"]

    assert urls["Homepage"] == "https://github.com/Vaibhav-Malladi/Strata"
    assert urls["Repository"] == "https://github.com/Vaibhav-Malladi/Strata"
    assert urls["Issues"] == "https://github.com/Vaibhav-Malladi/Strata/issues"
    assert urls["Documentation"] == "https://github.com/Vaibhav-Malladi/Strata#documentation"
    assert urls["Changelog"] == "https://github.com/Vaibhav-Malladi/Strata/blob/main/CHANGELOG.md"


def test_release_metadata_and_manifest_exclude_generated_artifacts():
    pyproject = _load_pyproject()
    project = pyproject["project"]
    manifest = (PROJECT_ROOT / "MANIFEST.in").read_text(encoding="utf-8")

    assert project["license"] == "MIT"
    assert project["license-files"] == ["LICENSE"]
    assert "License :: OSI Approved :: MIT License" not in project["classifiers"]
    assert "include LICENSE" in manifest
    assert "include README.md" in manifest
    assert "include CHANGELOG.md" in manifest
    assert (PROJECT_ROOT / "CHANGELOG.md").is_file()
    assert (PROJECT_ROOT / "docs" / "releasing.md").is_file()

    for pattern in (
        "prune .aidc",
        "prune .codex-venv",
        "prune .pytest_cache",
        "prune *.egg-info",
        "prune build",
        "prune dist",
        "global-exclude .env.*",
    ):
        assert pattern in manifest


def test_publish_workflow_checks_tag_tests_build_and_trusted_publishing():
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "publish.yml").read_text(
        encoding="utf-8"
    )

    assert "Publish to PyPI" in workflow
    assert "id-token: write" in workflow
    assert "environment: pypi" in workflow
    assert 'prefix = "refs/tags/v"' in workflow
    assert 'tomllib.load(file)["project"]["version"]' in workflow
    assert "Tag/version mismatch" in workflow
    assert "python tests.py" in workflow
    assert "python -m pip install --upgrade build twine" in workflow
    assert "python -m build" in workflow
    assert "python -m twine check dist/*" in workflow
    assert "pypa/gh-action-pypi-publish@release/v1" in workflow


def test_compatibility_workflow_tests_source_without_publishing():
    workflow_path = PROJECT_ROOT / ".github" / "workflows" / "tests.yml"

    assert workflow_path.is_file()
    workflow = workflow_path.read_text(encoding="utf-8")

    for version in ('"3.11"', '"3.12"', '"3.13"'):
        assert version in workflow

    for os_name in ("ubuntu-latest", "windows-latest", "macos-latest"):
        assert os_name in workflow

    assert "pull_request:" in workflow
    assert "push:" in workflow
    assert "workflow_dispatch:" in workflow
    assert "python -m compileall -q ." in workflow

    assert "Python 3.11 source grammar audit" in workflow
    assert "feature_version=(3, 11)" in workflow
    assert "if: matrix.python-version != '3.13'" in workflow

    assert "python -m pip install -e ." in workflow
    assert "python tests.py" in workflow
    assert "python tests/run.py" in workflow
    assert "if: matrix.python-version == '3.13'" in workflow

    assert "gh-action-pypi-publish" not in workflow
    assert "id-token: write" not in workflow

TESTS = [
    test_distribution_name_and_console_script_are_distinct_and_correct,
    test_strata_package_import_and_module_entrypoint,
    test_all_runtime_top_level_modules_are_packaged,
    test_readme_python_and_generated_output_metadata_are_configured,
    test_authoritative_versions_agree,
    test_public_docs_use_honest_install_runtime_and_support_wording,
    test_project_urls_are_verified_absolute_repository_urls,
    test_release_metadata_and_manifest_exclude_generated_artifacts,
    test_publish_workflow_checks_tag_tests_build_and_trusted_publishing,
    test_compatibility_workflow_tests_source_without_publishing,
]
