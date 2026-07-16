# Releasing Strata

This checklist separates local artifact validation, optional TestPyPI verification, production publication through the repository's trusted-publishing workflow, and post-publication release steps. Do not commit credentials, and do not rebuild manually between TestPyPI and production unless the package version changes.

Replace `<VERSION>` with the finalized package version.

## 1. Synchronize and validate

```powershell
git switch main
git pull --ff-only
git status --short

$env:PYTHONIOENCODING="utf-8"
$env:PYTHONUTF8="1"

python tests.py
python tests\run.py
python -m strata scan
python -m strata gate
```

On Windows, symlink-focused tests may be skipped with `WinError 1314` when the current account cannot create symlinks. Treat those as skips rather than failures.

## 2. Clean old build output

```powershell
Remove-Item -Recurse -Force dist, build -ErrorAction SilentlyContinue
Get-ChildItem -Directory -Filter "*.egg-info" -Recurse |
    Remove-Item -Recurse -Force
```

## 3. Install release tooling

```powershell
python -m pip install --upgrade build twine
```

## 4. Build

```powershell
python -m build
```

## 5. Inspect artifacts

```powershell
Get-ChildItem dist
python -m twine check dist/*
```

Optional archive inspection:

```powershell
python -m zipfile -l dist\strata_repo_intel-<VERSION>-py3-none-any.whl
tar -tf dist\strata_repo_intel-<VERSION>.tar.gz
```

Confirm the wheel contains the `strata` package, package metadata, and console-script metadata. Confirm generated directories, local caches, virtual environments, build output, credentials, and private environment files are absent.

## 6. Optional TestPyPI verification

```powershell
python -m twine upload --repository testpypi dist/*
```

Create a clean test environment:

```powershell
py -3.13 -m venv .release-test-venv
.\.release-test-venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install `
  --index-url https://test.pypi.org/simple/ `
  --extra-index-url https://pypi.org/simple/ `
  strata-repo-intel==<VERSION>

strata --help
strata start --help
```

`--extra-index-url` may be needed because TestPyPI does not mirror all runtime dependencies. This step validates local artifacts before production, but it is not the production publication mechanism.

## 7. Production publication

```powershell
git tag v<VERSION>
git push origin v<VERSION>
```

Production publication uses the GitHub `Publish to PyPI` workflow triggered by the pushed `v<VERSION>` tag. The workflow verifies that the tag matches `pyproject.toml`, installs Strata, runs the release test entrypoint, builds the package, runs `twine check`, and publishes to PyPI through trusted publishing.

Do not run a separate production `twine upload` when the trusted-publishing workflow is used. PyPI versions cannot normally be overwritten.

## 8. Verify production installation

```powershell
deactivate
Remove-Item -Recurse -Force .release-test-venv -ErrorAction SilentlyContinue

py -3.13 -m venv .release-prod-venv
.\.release-prod-venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install strata-repo-intel==<VERSION>

strata --help
strata start --help
```

Confirm the installed distribution name is `strata-repo-intel`, the console command is `strata`, and the normal user workflow remains `strata start`.

## 9. GitHub release

Create the GitHub release only after PyPI verification succeeds:

```powershell
gh release create v<VERSION> --title "Strata v<VERSION>" --notes-file <release-notes-file>
```

Use the changelog entry as the basis for the release notes. Do not create the GitHub release before production package verification.

## Security guidance

- Use PyPI API tokens for manual TestPyPI or Twine operations that require them.
- Do not commit credentials.
- Use the configured trusted-publishing workflow for production PyPI publication.
- Scope tokens as narrowly as possible.
- Verify the package name before upload.
