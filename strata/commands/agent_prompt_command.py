from pathlib import Path

from strata.adapters.export import write_agent_prompt
from cli_core import OUTPUT_DIR, build_graph
from strata.utils.output import build_banner, build_kv_table, build_section, format_path


AGENT_PROMPT_FILE = Path(OUTPUT_DIR) / "agent_prompt.md"


def write_agent_prompt_command(root: str, task: str, agent: str) -> None:
    graph = build_graph(root)
    write_agent_prompt(graph, task, agent, AGENT_PROMPT_FILE)

    print(build_banner())
    print()
    print(build_section("Agent prompt complete"))
    print(
        build_kv_table(
            [
                ("Task", task),
                ("Agent", agent),
                ("Output", format_path(Path(AGENT_PROMPT_FILE))),
            ]
        )
    )
