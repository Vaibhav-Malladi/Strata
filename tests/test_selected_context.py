import tempfile
from pathlib import Path

from selected_context import resolve_file_references, resolve_one_file_reference


def _create_resolver_repo(root: Path) -> None:
    files = {
        "commands/run_command.py": "def run_command():\n    return None\n",
        "commands/ask_command.py": "def ask_command():\n    return None\n",
        "commands/config_command.py": "def config_command():\n    return None\n",
        "workflow_config.py": "CONFIG = True\n",
        "tests/test_config_command.py": "def test_config_command():\n    assert True\n",
        "src/components/LoginForm.tsx": "export function LoginForm() { return null; }\n",
        "helper.py": "def helper():\n    return True\n",
        "main.py": "def main():\n    return helper()\n",
        "credentials.json": "{}\n",
        ".aidc/temp.py": "print('ignored')\n",
    }

    for relative_path, content in files.items():
        file_path = root / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

    (root / "src").mkdir(parents=True, exist_ok=True)


def test_resolve_file_reference_supports_exact_and_smart_matches():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_resolver_repo(root)

        cases = {
            "commands/run_command.py": "commands/run_command.py",
            "run_command.py": "commands/run_command.py",
            "run_command": "commands/run_command.py",
            "commands/run": "commands/run_command.py",
            "LoginForm": "src/components/LoginForm.tsx",
        }

        for reference, expected_path in cases.items():
            result = resolve_one_file_reference(root, reference, task="fix validation")

            assert result["status"] == "resolved"
            assert result["path"] == expected_path


def test_resolve_file_references_resolves_each_flag_independently():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_resolver_repo(root)

        result = resolve_file_references(root, ["run_command", "ask_command"], task="compare these flows")

        assert result["status"] == "resolved"
        assert result["resolved_paths"] == [
            "commands/run_command.py",
            "commands/ask_command.py",
        ]


def test_resolver_prefers_source_files_and_can_pick_explicit_test_files():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_resolver_repo(root)

        source_result = resolve_one_file_reference(root, "config_command", task="fix config flow")
        test_result = resolve_one_file_reference(root, "test_config_command", task="fix config flow")

        assert source_result["status"] == "resolved"
        assert source_result["path"] == "commands/config_command.py"
        assert test_result["status"] == "resolved"
        assert test_result["path"] == "tests/test_config_command.py"


def test_resolver_rejects_ambiguous_missing_and_unsafe_references():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_resolver_repo(root)

        ambiguous = resolve_one_file_reference(root, "config", task="fix loading")
        missing = resolve_one_file_reference(root, "does_not_exist", task="fix loading")
        directory = resolve_one_file_reference(root, "src", task="fix loading")
        outside = resolve_one_file_reference(root, str(root.parent / "outside.py"), task="fix loading")
        ignored = resolve_one_file_reference(root, ".aidc/temp.py", task="fix loading")
        secret = resolve_one_file_reference(root, "credentials.json", task="fix loading")

        assert ambiguous["status"] == "ambiguous"
        assert [candidate["path"] for candidate in ambiguous["candidates"][:3]] == [
            "workflow_config.py",
            "commands/config_command.py",
            "tests/test_config_command.py",
        ]
        assert missing["status"] == "missing"
        assert "No file matched" in missing["message"]
        assert missing["candidates"]
        assert directory["status"] == "directory"
        assert "directory" in directory["message"].lower()
        assert outside["status"] == "outside_root"
        assert "outside the repo root" in outside["message"].lower()
        assert ignored["status"] == "ignored"
        assert "ignored or generated" in ignored["message"].lower()
        assert secret["status"] == "secret"
        assert "secret/credential file" in secret["message"].lower()


TESTS = [
    test_resolve_file_reference_supports_exact_and_smart_matches,
    test_resolve_file_references_resolves_each_flag_independently,
    test_resolver_prefers_source_files_and_can_pick_explicit_test_files,
    test_resolver_rejects_ambiguous_missing_and_unsafe_references,
]
