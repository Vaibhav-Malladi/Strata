# Runtime compatibility investigation

Strata's current published runtime requirement remains Python 3.13 or newer.

A bounded source audit found no obvious syntax or standard-library API blocker for Python 3.11 or 3.12. This is not confirmation of support: runtime behavior, operating-system differences, optional Rich behavior, and the full test suite still need evidence from the compatibility matrix.

The test workflow runs source compilation and both repository test entrypoints on Python 3.11, 3.12, and 3.13 across Ubuntu, Windows, and macOS. It deliberately does not install the package on Python 3.11 or 3.12 because current package metadata correctly requires Python 3.13+.

Do not lower `requires-python` until the matrix is consistently green and any failures have been investigated.
