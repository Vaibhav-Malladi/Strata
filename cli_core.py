import json
import os

from fs_utils import atomic_write_json
from graph import validate_graph
from scanner import scan_repo
from cli_ui import print_title, print_kv, red


OUTPUT_DIR = ".aidc"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "graph.json")
PROJECT_MAP_FILE = os.path.join(OUTPUT_DIR, "project_map.md")
TASK_BRIEF_FILE = os.path.join(OUTPUT_DIR, "task_brief.md")
PREFLIGHT_FILE = os.path.join(OUTPUT_DIR, "preflight.md")
ROUTES_MD_FILE = os.path.join(OUTPUT_DIR, "routes.md")
ROUTES_JSON_FILE = os.path.join(OUTPUT_DIR, "routes.json")
GATE_REPORT_MD_FILE = os.path.join(OUTPUT_DIR, "gate_report.md")
GATE_REPORT_JSON_FILE = os.path.join(OUTPUT_DIR, "gate_report.json")
DIFF_REPORT_MD_FILE = os.path.join(OUTPUT_DIR, "diff_report.md")
DIFF_REPORT_JSON_FILE = os.path.join(OUTPUT_DIR, "diff_report.json")
VERIFICATION_REPORT_MD_FILE = os.path.join(OUTPUT_DIR, "verification_report.md")
VERIFICATION_REPORT_JSON_FILE = os.path.join(OUTPUT_DIR, "verification_report.json")
CONTEXT_PACK_FILE = os.path.join(OUTPUT_DIR, "context_pack.md")
CONTEXT_PACK_JSON_FILE = os.path.join(OUTPUT_DIR, "context_pack.json")
SNAPSHOT_LATEST_FILE = os.path.join(OUTPUT_DIR, "snapshots", "latest.txt")


def normalize_path(path: str) -> str:
    return os.path.normpath(path)


def build_graph(
    root_path: str,
    progress=None,
    expected_file_count: int | None = None,
) -> dict | None:
    root_path = normalize_path(root_path)

    if not os.path.exists(root_path):
        print_title(red("Scan failed"))
        print_kv("Reason", f"path does not exist: {root_path}")
        return None

    if not os.path.isdir(root_path):
        print_title(red("Scan failed"))
        print_kv("Reason", f"path is not a directory: {root_path}")
        return None

    graph = scan_repo(root_path, progress=progress, expected_file_count=expected_file_count)
    problems = validate_graph(graph)

    if problems:
        print_title(red("Graph validation failed"))

        for problem in problems:
            print(f"  {red('✗')} {problem}")

        return None

    return graph


def save_graph(graph: dict) -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    atomic_write_json(OUTPUT_FILE, graph)


def load_saved_graph() -> dict | None:
    if not os.path.exists(OUTPUT_FILE):
        print_title(red("No saved graph found"))
        print("  Run this first:")
        print()
        print("    py cli.py scan")
        return None

    with open(OUTPUT_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def count_unresolved_imports(graph: dict) -> int:
    unresolved_count = 0

    for file_info in graph["files"]:
        unresolved_count += len(file_info["unresolved_imports"])

    return unresolved_count
