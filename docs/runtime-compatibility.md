# Runtime compatibility investigation

Strata's current published runtime requirement remains Python 3.13 or newer.

A bounded source audit found no obvious syntax or standard-library API blocker for Python 3.11 or 3.12. This is not confirmation of support: runtime behavior, operating-system differences, optional Rich behavior, packaging behavior, and the full test suite still need evidence before metadata can be lowered.

The test workflow currently runs source compilation on Python 3.11, 3.12, and 3.13 across Ubuntu, Windows, and macOS.

For Python 3.11 and 3.12, the workflow runs source compatibility checks only. It deliberately does not install the package or run the full test suite because current package metadata correctly requires Python 3.13+.

For Python 3.13, the workflow installs Strata in editable mode and runs both repository test entrypoints:

```bash
python tests.py
python tests/run.py