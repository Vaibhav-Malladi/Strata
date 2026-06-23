import os
import sys

TESTS_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.dirname(TESTS_DIR)

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

if TESTS_DIR not in sys.path:
    sys.path.insert(0, TESTS_DIR)

import test_parser
import test_scanner
import test_graph
import test_cli_core
import test_map_writer
import test_brief
import test_cycles
import test_health
import test_impact
import test_brief_impact
import test_test_mapper
import test_preflight
import test_agent_export
import test_status
from tests import test_languages
from tests import test_javascript_parser
from tests import test_typescript_parser
from tests import test_multilang_scanner


TEST_MODULES = [
    test_parser,
    test_scanner,
    test_graph,
    test_cli_core,
    test_map_writer,
    test_brief,
    test_cycles,
    test_health,
    test_impact,
    test_brief_impact,
    test_test_mapper,
    test_preflight,
    test_agent_export,
    test_status,
    test_languages,
    test_javascript_parser,
    test_typescript_parser,
    test_multilang_scanner,
]


def main():
    total = 0

    for module in TEST_MODULES:
        for test in module.TESTS:
            test()
            total += 1

    print(f"All tests passed. ({total} tests)")


if __name__ == "__main__":
    main()