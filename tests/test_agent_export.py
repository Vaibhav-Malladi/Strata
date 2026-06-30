import agent_export as old_agent_export
import strata.adapters.export as new_agent_export
from agent_export import generate_agent_prompt, normalize_agent, write_agent_prompt


def test_agent_export_shim_exports_new_implementation_objects():
    assert old_agent_export.generate_agent_prompt is new_agent_export.generate_agent_prompt


def fake_graph():
    return {
        "schema_version": 1,
        "root": ".",
        "files": [
            {
                "path": "cli.py",
                "language": "python",
                "classes": [],
                "functions": [{"name": "main", "line": 12}],
                "imports": ["commands.scan_command"],
                "external_imports": [],
                "unresolved_imports": [],
                "unresolved_import_details": [],
            },
            {
                "path": "agent_export.py",
                "language": "python",
                "classes": [],
                "functions": [
                    {"name": "generate_agent_prompt", "line": 12},
                    {"name": "write_agent_prompt", "line": 30},
                ],
                "imports": ["brief", "health", "test_mapper"],
                "external_imports": [],
                "unresolved_imports": [],
                "unresolved_import_details": [],
            },
            {
                "path": "tests/test_agent_export.py",
                "language": "python",
                "classes": [],
                "functions": [],
                "imports": ["agent_export"],
                "external_imports": [],
                "unresolved_imports": [],
                "unresolved_import_details": [],
            },
        ],
        "edges": [
            {
                "from": "tests/test_agent_export.py",
                "to": "agent_export.py",
                "type": "imports",
                "import": "agent_export",
            }
        ],
    }


def test_normalize_agent_accepts_supported_agent():
    assert normalize_agent("LOCAL") == "local"
    assert normalize_agent(" aider ") == "aider"


def test_normalize_agent_rejects_unsupported_agent():
    try:
        normalize_agent("unknown")
    except ValueError as error:
        assert "Unsupported agent" in str(error)
        assert "aider" in str(error)
        assert "local" in str(error)
    else:
        raise AssertionError("Expected ValueError for unsupported agent")


def test_generate_generic_agent_prompt_contains_task_and_rules():
    prompt = generate_agent_prompt(fake_graph(), "add agent prompt command", "generic")

    assert "# Agent Prompt" in prompt
    assert "add agent prompt command" in prompt
    assert "Do not add external dependencies" in prompt
    assert "## Relevant Files" in prompt
    assert "## Verification Plan" in prompt


def test_generate_generic_agent_prompt_mentions_selected_files_and_related_checks():
    prompt = generate_agent_prompt(
        fake_graph(),
        "adjust prompt generation",
        "generic",
        selected_paths=["cli.py"],
    )

    assert "User-selected files" in prompt
    assert "cli.py" in prompt
    assert "strata help" in prompt


def test_generate_local_prompt_is_compact():
    prompt = generate_agent_prompt(fake_graph(), "change agent export behavior", "local")

    assert "# Local Model Prompt" in prompt
    assert "Rules:" in prompt
    assert "Task:" in prompt
    assert "Relevant files:" in prompt
    assert "Verify with:" in prompt


def test_generate_aider_prompt_contains_file_guidance():
    prompt = generate_agent_prompt(fake_graph(), "edit cli routing", "aider")

    assert "# Aider Prompt" in prompt
    assert "Edit guidance:" in prompt
    assert "Files to inspect first:" in prompt
    assert "Do not change generated `.aidc/` files manually." in prompt


def test_generate_chatgpt_prompt_contains_project_context():
    prompt = generate_agent_prompt(fake_graph(), "add tests for agent export", "chatgpt")

    assert "# ChatGPT Coding Prompt" in prompt
    assert "Strata is a local-first repository intelligence layer" in prompt
    assert "## Development Rules" in prompt
    assert "## Repository Health" in prompt


def test_write_agent_prompt_creates_file():
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as temp_dir:
        output_path = Path(temp_dir) / ".aidc" / "agent_prompt.md"

        write_agent_prompt(
            fake_graph(),
            "add agent export tests",
            "generic",
            output_path,
        )

        assert output_path.exists()
        content = output_path.read_text(encoding="utf-8")

        assert "# Agent Prompt" in content
        assert "add agent export tests" in content


def test_write_agent_prompt_redacts_secret_like_task_text():
    import tempfile
    from pathlib import Path

    secret = "sk-testsecret-123456"

    with tempfile.TemporaryDirectory() as temp_dir:
        output_path = Path(temp_dir) / ".aidc" / "agent_prompt.md"

        write_agent_prompt(
            fake_graph(),
            f"fix {secret} credential leak",
            "generic",
            output_path,
        )

        content = output_path.read_text(encoding="utf-8")

        assert secret not in content
        assert "<redacted>" in content


TESTS = [
    test_agent_export_shim_exports_new_implementation_objects,
    test_normalize_agent_accepts_supported_agent,
    test_normalize_agent_rejects_unsupported_agent,
    test_generate_generic_agent_prompt_contains_task_and_rules,
    test_generate_local_prompt_is_compact,
    test_generate_aider_prompt_contains_file_guidance,
    test_generate_chatgpt_prompt_contains_project_context,
    test_write_agent_prompt_creates_file,
    test_write_agent_prompt_redacts_secret_like_task_text,
]
