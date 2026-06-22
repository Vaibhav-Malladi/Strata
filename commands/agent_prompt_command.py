from pathlib import Path

from agent_export import write_agent_prompt
from cli_core import OUTPUT_DIR, build_graph
from cli_ui import green, print_kv, print_title


AGENT_PROMPT_FILE = Path(OUTPUT_DIR) / "agent_prompt.md"


def write_agent_prompt_command(root: str, task: str, agent: str) -> None:
    graph = build_graph(root)
    write_agent_prompt(graph, task, agent, AGENT_PROMPT_FILE)

    print_title("Agent prompt generated")
    print_kv("Agent", agent)
    print_kv("Task", task)
    print_kv("Output", str(Path(AGENT_PROMPT_FILE)))
    print(green("Done"))