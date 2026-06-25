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


TESTS = [
    test_distribution_name_and_console_script_are_distinct_and_correct,
    test_all_runtime_top_level_modules_are_packaged,
    test_readme_python_and_generated_output_metadata_are_configured,
]
