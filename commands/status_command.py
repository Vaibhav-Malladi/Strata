import json

from cli_core import OUTPUT_FILE
from repo_summary import build_repo_intelligence_rows, summarize_graph
from status import analyze_status, format_status_report
from ui import build_banner, build_kv_table, build_section, format_path


def show_status(root: str = ".") -> None:
    status = analyze_status(root)
    report = format_status_report(status)
    graph = _load_saved_graph()

    print(build_banner())
    print()
    print(build_section("Strata status"))
    print(
        build_kv_table(
            [
                ("Root", format_path(status.get("root", root))),
                ("State", status.get("state", "unknown")),
                ("Missing", len(status.get("missing_files", []))),
                ("Stale", len(status.get("stale_files", []))),
            ]
        )
    )
    if graph is not None:
        print()
        print(build_section("Repo intelligence"))
        print(build_kv_table(build_repo_intelligence_rows(summarize_graph(graph))))
    print()
    print(report)


def _load_saved_graph() -> dict | None:
    try:
        with open(OUTPUT_FILE, "r", encoding="utf-8") as file:
            graph = json.load(file)
    except (OSError, json.JSONDecodeError):
        return None

    return graph if isinstance(graph, dict) else None
