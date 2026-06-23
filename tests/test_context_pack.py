from context_pack import (
    build_context_pack,
    extract_task_terms,
    find_dependency_neighbors,
    rank_relevant_files,
)


def context_pack_test_graph():
    return {
        "schema_version": 1,
        "root": "sample",
        "files": [
            {
                "path": "src/api/user_login.py",
                "language": "python",
                "classes": [
                    {"name": "UserLoginAPI"},
                ],
                "functions": [
                    {"name": "handle_login"},
                    {"name": "set_user_session"},
                ],
                "interfaces": [],
                "types": [],
                "enums": [],
                "exports": ["login_user"],
                "imports": ["src.auth.users", "utils.http"],
                "external_imports": ["json"],
                "unresolved_imports": [],
                "unresolved_import_details": [],
                "routes": [
                    {
                        "method": "POST",
                        "path": "/users/login",
                        "line": 10,
                        "source": "@app.post",
                    }
                ],
            },
            {
                "path": "src/auth/users.py",
                "language": "python",
                "classes": [
                    {"name": "UserDirectory"},
                ],
                "functions": [
                    {"name": "find_user"},
                ],
                "interfaces": [],
                "types": [],
                "enums": [],
                "exports": [],
                "imports": [],
                "external_imports": [],
                "unresolved_imports": [],
                "unresolved_import_details": [],
                "routes": [],
            },
            {
                "path": "src/other.py",
                "language": "python",
                "classes": [
                    {"name": "UnrelatedThing"},
                ],
                "functions": [
                    {"name": "do_other"},
                ],
                "interfaces": [],
                "types": [],
                "enums": [],
                "exports": [],
                "imports": [],
                "external_imports": [],
                "unresolved_imports": [],
                "unresolved_import_details": [],
                "routes": [],
            },
            {
                "path": "tests/test_user_login.py",
                "language": "python",
                "classes": [],
                "functions": [
                    {"name": "test_login_flow"},
                ],
                "interfaces": [],
                "types": [],
                "enums": [],
                "exports": [],
                "imports": ["src.api.user_login"],
                "external_imports": [],
                "unresolved_imports": [],
                "unresolved_import_details": [],
                "routes": [],
            },
        ],
        "edges": [
            {
                "from": "tests/test_user_login.py",
                "to": "src/api/user_login.py",
                "type": "imports",
                "import": "src.api.user_login",
            },
            {
                "from": "src/app.py",
                "to": "src/api/user_login.py",
                "type": "imports",
                "import": "src.api.user_login",
            },
            {
                "from": "src/api/user_login.py",
                "to": "src/auth/users.py",
                "type": "imports",
                "import": "src.auth.users",
            },
        ],
    }


def no_match_graph():
    return {
        "schema_version": 1,
        "root": "sample",
        "files": [
            {
                "path": "src/alpha.py",
                "language": "python",
                "classes": [],
                "functions": [
                    {"name": "alpha"},
                ],
                "interfaces": [],
                "types": [],
                "enums": [],
                "exports": [],
                "imports": [],
                "external_imports": [],
                "unresolved_imports": [],
                "unresolved_import_details": [],
                "routes": [],
            }
        ],
        "edges": [],
    }


def test_extract_task_terms_removes_common_tiny_words_and_keeps_useful_terms():
    terms = extract_task_terms("Change the user login API and the UI")

    assert "the" not in terms
    assert "and" not in terms
    assert "user" in terms
    assert "login" in terms
    assert "api" in terms


def test_rank_relevant_files_prefers_login_user_file_over_unrelated_files():
    graph = context_pack_test_graph()

    ranked = rank_relevant_files(graph, "change user login API")

    assert ranked[0]["file"]["path"] == "src/api/user_login.py"
    assert ranked[0]["score"] > ranked[-1]["score"]
    assert ranked[0]["file"]["path"] != "src/other.py"


def test_build_context_pack_includes_expected_sections_and_relevant_file():
    graph = context_pack_test_graph()

    content = build_context_pack(graph, "change user login API")

    assert "# Strata Context Pack" in content
    assert "change user login API" in content
    assert "How This Pack Was Built" in content
    assert "src/api/user_login.py" in content
    assert "AI Editing Instructions" in content


def test_dependency_neighbor_detection_uses_small_fake_graph():
    graph = context_pack_test_graph()

    neighbors = find_dependency_neighbors(graph, ["src/api/user_login.py"])

    dependency_targets = {
        edge["to"]
        for edge in neighbors["dependencies"]
    }
    dependent_sources = {
        edge["from"]
        for edge in neighbors["dependents"]
    }

    assert "src/auth/users.py" in dependency_targets
    assert "src/app.py" in dependent_sources
    assert "tests/test_user_login.py" in dependent_sources


def test_build_context_pack_handles_no_match_case_without_crashing():
    graph = no_match_graph()

    content = build_context_pack(graph, "quantum banana alignment")

    assert "# Strata Context Pack" in content
    assert "No strong file matches found." in content
    assert "Repository Summary" in content
    assert "Suggested Verification" in content
    assert "py tests.py" in content
    assert "py tests\\run.py" in content


TESTS = [
    test_extract_task_terms_removes_common_tiny_words_and_keeps_useful_terms,
    test_rank_relevant_files_prefers_login_user_file_over_unrelated_files,
    test_build_context_pack_includes_expected_sections_and_relevant_file,
    test_dependency_neighbor_detection_uses_small_fake_graph,
    test_build_context_pack_handles_no_match_case_without_crashing,
]
