# Candidate Quality Fixtures

These repositories are tiny synthetic fixtures authored for Strata's tests.
They are not copied from, cloned from, or intended to represent benchmarks of
third-party repositories. The repository's project license applies.

Each named directory contains a G1 `manifest.json` and an isolated `repo/`
directory. Evaluation tools should inventory only the path named by the
manifest's `fixture_path`.
