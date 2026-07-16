# Runtime compatibility investigation

Strata's current published runtime requirement is Python 3.11 or newer.

A bounded source audit found no obvious syntax or standard-library API blocker for Python 3.11 or 3.12. The release metadata supports Python 3.11, 3.12, and 3.13.

The test workflow currently runs source compilation on Python 3.11, 3.12, and 3.13 across Ubuntu, Windows, and macOS.

For Python 3.11 and 3.12, the workflow runs source compatibility checks. This guards the supported source grammar while keeping the heavier repository validation on the primary release runtime.

For Python 3.13, the workflow installs Strata in editable mode and runs both repository test entrypoints:

```bash
python tests.py
python tests/run.py
