import json
import os

from context_budget import (
    BudgetParseError,
    build_budget_report,
    build_budget_summary_rows,
    parse_budget_value,
)
from context_efficiency import compute_context_efficiency, estimate_graph_source_chars, estimate_tokens
from cli_core import (
    CONTEXT_PACK_FILE,
    OUTPUT_FILE,
    ROUTES_JSON_FILE,
    build_graph,
    save_graph,
)
from context_pack import build_context_pack
from repo_summary import build_repo_intelligence_rows, summarize_graph
from routes import collect_routes
from ui import build_banner, build_kv_table, build_section, format_error, format_path, print_status_card


def write_context(root_path: str = ".", *args: str) -> int:
    try:
        parsed = _parse_context_args(args)
    except BudgetParseError as error:
        _print_error("Context failed", str(error))
        return 1
    except ValueError:
        _print_usage()
        return 1

    root = parsed["root"] or root_path
    task = parsed["task"]
    budget_value = parsed["budget"]

    graph = build_graph(root)

    if graph is None:
        return 1

    save_graph(graph)
    routes_data = _load_routes_data(graph)
    budget_report = build_budget_report(graph, task, budget_value=budget_value)
    content = build_context_pack(graph, task, routes_data, budget_value=budget_value)
    budget_report["budgeted_context_tokens"] = estimate_tokens(content)

    output_dir = os.path.dirname(CONTEXT_PACK_FILE)

    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    with open(CONTEXT_PACK_FILE, "w", encoding="utf-8") as file:
        file.write(content)

    relevant_files = budget_report["included_entries"]
    routes_count = _count_routes(routes_data)
    symbols_count = _count_symbols(graph)
    repo_intelligence = summarize_graph(graph)

    print(build_banner())
    print()
    print(build_section("Context complete"))
    print(
        build_kv_table(
            [
                ("Task", task),
                ("Output", format_path(CONTEXT_PACK_FILE)),
                ("Graph", format_path(OUTPUT_FILE)),
                ("Files", len(graph.get("files", []))),
                ("Symbols", symbols_count),
                ("Routes", routes_count),
                ("Relevant files", len(relevant_files)),
            ]
        )
    )
    print()
    print(build_section("Repo intelligence"))
    print(build_kv_table(build_repo_intelligence_rows(repo_intelligence)))
    print()
    print_status_card(
        "Context Efficiency",
        _build_context_efficiency_rows(graph, relevant_files, len(content)),
    )
    print_status_card("Budget Summary", build_budget_summary_rows(budget_report))

    return 0


def _load_routes_data(graph: dict) -> dict:
    if os.path.exists(ROUTES_JSON_FILE):
        try:
            with open(ROUTES_JSON_FILE, "r", encoding="utf-8") as file:
                routes_data = json.load(file)

            if isinstance(routes_data, dict):
                return routes_data
        except (OSError, json.JSONDecodeError):
            pass

    return {"routes": collect_routes(graph)}


def _print_usage() -> None:
    print('Usage: strata context [--budget <preset|tokens>] "<task>" [root]')


def _count_routes(routes_data: dict) -> int:
    routes = routes_data.get("routes", [])

    if not isinstance(routes, list):
        return 0

    return len(routes)


def _count_symbols(graph: dict) -> int:
    symbol_keys = (
        "classes",
        "functions",
        "interfaces",
        "types",
        "enums",
        "exports",
    )
    total = 0

    for file_info in graph.get("files", []):
        if not isinstance(file_info, dict):
            continue

        for key in symbol_keys:
            values = file_info.get(key, [])

            if isinstance(values, list):
                total += len(values)

    return total


def _build_context_efficiency_rows(
    graph: dict,
    relevant_files: list[dict],
    focused_context_chars: int,
) -> list[tuple[str, object]]:
    source_files_scanned = len(graph.get("files", []))
    files_included = len(relevant_files)
    full_source_chars = estimate_graph_source_chars(graph)
    efficiency = compute_context_efficiency(full_source_chars, focused_context_chars)

    return [
        ("Source files scanned", f"{source_files_scanned:,}"),
        ("Files included", f"{files_included:,}"),
        ("Full source estimate", f"~{efficiency['full_source_tokens']:,} tokens"),
        ("Strata context estimate", f"~{efficiency['focused_context_tokens']:,} tokens"),
        ("Estimated context reduction", f"~{efficiency['reduction_percent']:,}%"),
        ("Note", "Actual AI token usage may vary by adapter."),
    ]


def _parse_context_args(args: list[str]) -> dict:
    positionals: list[str] = []
    budget_value: str | None = None
    index = 0

    while index < len(args):
        arg = args[index]

        if arg == "--budget":
            index += 1
            if index >= len(args):
                raise ValueError("--budget requires a preset or token count")
            budget_value = args[index]
        elif arg.startswith("--budget="):
            budget_value = arg.split("=", 1)[1]
            if not budget_value:
                raise ValueError("--budget requires a preset or token count")
        elif arg.startswith("-"):
            raise ValueError(f"Unknown option: {arg}")
        else:
            positionals.append(arg)

        index += 1

    if not positionals:
        raise ValueError("context requires a task")

    if len(positionals) > 2:
        raise ValueError("context accepts a task and an optional root path")

    task = positionals[0]
    root = positionals[1] if len(positionals) == 2 else None

    if budget_value is not None:
        budget_value = parse_budget_value(budget_value).get("raw")

    return {
        "task": task,
        "root": root,
        "budget": budget_value,
    }


def _print_error(title: str, message: str) -> None:
    print(build_banner())
    print()
    print(build_section(title))
    print(format_error(message))
