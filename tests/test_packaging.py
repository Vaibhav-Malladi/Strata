from __future__ import annotations

from pathlib import Path
import tomllib


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_pyproject() -> dict:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as file:
        return tomllib.load(file)


def test_distribution_name_and_console_script_are_distinct_and_correct():
    pyproject = _load_pyproject()
    project = pyproject["project"]

    assert project["name"] == "strata-repo-intel"
    assert project["scripts"]["strata"] == "cli:main"


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
    assert project["requires-python"] == ">=3.13"
    assert project["license"] == "MIT"
    assert ".aidc/" in gitignore


def test_public_docs_use_honest_install_runtime_and_support_wording():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    help_text = (
        (PROJECT_ROOT / "cli_help.py").read_text(encoding="utf-8")
        + (PROJECT_ROOT / "help_topics.py").read_text(encoding="utf-8")
    )
    public_text = readme + help_text
    normalized = public_text.lower()

    assert "the pypi package is `strata-repo-intel`; the cli command is `strata`" in normalized
    assert "pipx install strata-repo-intel" in public_text
    assert "python -m pip install --user strata-repo-intel" in public_text
    assert "python 3.13" in normalized
    assert "older python versions" in normalized
    assert "experimental/preview" in normalized
    assert "regex/convention" in normalized
    assert "add `.aidc/` to `.gitignore`" in normalized
    assert "python -m strata" not in normalized
    assert "py -m strata" not in normalized


def test_publish_workflow_checks_tag_tests_and_built_distribution():
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "publish.yml").read_text(
        encoding="utf-8"
    )

    assert 'prefix = "refs/tags/v"' in workflow
    assert 'tomllib.load(file)["project"]["version"]' in workflow
    assert "Tag/version mismatch" in workflow
    assert "python tests.py" in workflow
    assert "python -m pip install --upgrade build twine" in workflow
    assert "python -m build" in workflow
    assert "python -m twine check dist/*" in workflow


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
    test_all_runtime_top_level_modules_are_packaged,
    test_readme_python_and_generated_output_metadata_are_configured,
    test_public_docs_use_honest_install_runtime_and_support_wording,
    test_publish_workflow_checks_tag_tests_and_built_distribution,
    test_compatibility_workflow_tests_source_without_publishing,
]
