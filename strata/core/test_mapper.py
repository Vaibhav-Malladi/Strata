import os


DEFAULT_TEST_COMMAND = "py tests.py"


COMMAND_RULES = {
    "cli.py": [
        "strata help",
    ],
    "scanner.py": [
        "strata scan tmp_repo",
    ],
    "map_writer.py": [
        "strata map tmp_repo",
    ],
    "brief.py": [
        'strata brief "add map command tests"',
    ],
    "brief_impact.py": [
        'strata brief "change helper behavior"',
    ],
    "cycles.py": [
        "strata cycles tmp_repo",
    ],
    "health.py": [
        "strata health tmp_repo",
    ],
    "impact.py": [
        "strata impact tmp_repo helper.py",
    ],
    "python_parser.py": [
        "strata scan tmp_repo",
    ],
    "languages.py": [
        "strata scan tmp_repo",
    ],
    "graph.py": [
        "strata scan tmp_repo",
        "strata health tmp_repo",
    ],
}


def suggest_tests_for_file(graph: dict, target_path: str) -> dict:
    """Suggest verification commands and related test files for a changed file."""

    matching_path = _find_matching_path(graph, target_path)

    if matching_path is None:
        return {
            "target": target_path,
            "found": False,
            "recommended_commands": [DEFAULT_TEST_COMMAND],
            "related_test_files": [],
            "summary": f"File not found in graph: {target_path}",
        }

    basename = os.path.basename(matching_path)
    related_test_files = _find_related_test_files(graph, matching_path)

    commands = [DEFAULT_TEST_COMMAND]
    commands.extend(COMMAND_RULES.get(basename, []))

    return {
        "target": matching_path,
        "found": True,
        "recommended_commands": _dedupe(commands),
        "related_test_files": related_test_files,
        "summary": _summary(matching_path, related_test_files),
    }


def format_test_suggestions(result: dict) -> str:
    """Format test suggestions as readable text."""

    lines = []

    lines.append("Test suggestions")
    lines.append("")
    lines.append(f"Target: {result.get('target', '')}")
    lines.append(f"Found: {result.get('found', False)}")
    lines.append(f"Summary: {result.get('summary', '')}")
    lines.append("")

    lines.append("Recommended commands")
    lines.append("--------------------")

    for command in result.get("recommended_commands", []):
        lines.append(f"- {command}")

    lines.append("")
    lines.append("Likely related test files")
    lines.append("-------------------------")

    if result.get("related_test_files"):
        for path in result["related_test_files"]:
            lines.append(f"- {path}")
    else:
        lines.append("none")

    return "\n".join(lines).rstrip()


def _find_matching_path(graph: dict, target_path: str) -> str | None:
    normalized_target = _normalize_path(target_path)
    target_basename = os.path.basename(normalized_target)

    exact_path_matches = []
    exact_basename_matches = []
    suffix_matches = []

    for file_info in graph.get("files", []):
        path = file_info.get("path", "")
        normalized_path = _normalize_path(path)
        basename = os.path.basename(normalized_path)

        if normalized_path == normalized_target:
            exact_path_matches.append(path)
            continue

        if basename == target_basename:
            exact_basename_matches.append(path)
            continue

        if normalized_path.endswith(normalized_target):
            suffix_matches.append(path)

    if exact_path_matches:
        return _prefer_shortest_path(exact_path_matches)

    if exact_basename_matches:
        return _prefer_shortest_path(exact_basename_matches)

    if suffix_matches:
        return _prefer_shortest_path(suffix_matches)

    return None


def _find_related_test_files(graph: dict, target_path: str) -> list[str]:
    target_basename = os.path.basename(target_path)
    target_stem = _file_stem(target_basename)

    candidates = []

    for file_info in graph.get("files", []):
        path = file_info.get("path", "")
        normalized_path = _normalize_path(path)
        basename = os.path.basename(path)
        stem = _file_stem(basename)

        if not _is_test_file(normalized_path, basename):
            continue

        if stem == f"test_{target_stem}":
            candidates.append(path)
            continue

        if target_stem in stem:
            candidates.append(path)
            continue

    return sorted(_dedupe(candidates))


def _summary(target_path: str, related_test_files: list[str]) -> str:
    if related_test_files:
        return f"Found {len(related_test_files)} likely related test file(s) for {target_path}."

    return f"No specific test file found for {target_path}; run the general test suite."


def _is_test_file(normalized_path: str, basename: str) -> bool:
    if normalized_path.startswith("tests/") and basename.startswith("test_"):
        return True

    if basename == "tests.py":
        return True

    return False


def _file_stem(filename: str) -> str:
    if filename.endswith(".py"):
        return filename[:-3]

    return filename


def _prefer_shortest_path(paths: list[str]) -> str:
    return sorted(paths, key=lambda path: (path.count("\\") + path.count("/"), len(path), path))[0]


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/").strip()


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []

    for value in values:
        if value in seen:
            continue

        seen.add(value)
        result.append(value)

    return result
