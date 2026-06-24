from context_pack import (
    build_context_pack,
    find_dependency_neighbors,
    rank_relevant_files,
)


def _assert_terms(text: str, *terms: object) -> None:
    normalized = text.lower()
    missing: list[str] = []

    for term in terms:
        if isinstance(term, (list, tuple, set, frozenset)):
            options = [str(option) for option in term]
            if not any(option.lower() in normalized for option in options):
                missing.append("one of: " + " | ".join(options))
            continue

        value = str(term)
        if value.lower() not in normalized:
            missing.append(value)

    assert not missing, f"Missing expected concept(s): {', '.join(missing)}"


def make_file(path, **overrides):
    base = {
        "path": path,
        "language": overrides.pop("language", "typescript"),
        "classes": overrides.pop("classes", []),
        "functions": overrides.pop("functions", []),
        "interfaces": overrides.pop("interfaces", []),
        "types": overrides.pop("types", []),
        "enums": overrides.pop("enums", []),
        "exports": overrides.pop("exports", []),
        "imports": overrides.pop("imports", []),
        "external_imports": overrides.pop("external_imports", []),
        "unresolved_imports": overrides.pop("unresolved_imports", []),
        "unresolved_import_details": overrides.pop("unresolved_import_details", []),
        "routes": overrides.pop("routes", []),
    }
    base.update(overrides)
    return base


def fake_graph(files, edges=None):
    return {
        "schema_version": 1,
        "root": "sample",
        "files": files,
        "edges": edges or [],
    }


def test_rank_relevant_files_does_not_fill_with_hint_only_noise():
    graph = fake_graph(
        [
            make_file("cli_ui.py", language="python"),
            make_file("test_mapper.py", language="python"),
            make_file("tests/helpers.py", language="python"),
            make_file("tests/test_ui.py", language="python"),
            make_file("src/ui_helpers.py", language="python"),
        ]
    )

    ranked = rank_relevant_files(graph, "we are stuck on home/landing page")
    paths = [item["file"]["path"] for item in ranked]

    assert len(paths) <= 3
    assert set(paths).issubset(
        {
            "cli_ui.py",
            "test_mapper.py",
            "tests/helpers.py",
            "tests/test_ui.py",
            "src/ui_helpers.py",
        }
    )


def test_rank_relevant_files_prefers_source_over_test_with_direct_fixture_terms():
    graph = fake_graph(
        [
            make_file("src/pages/Home.tsx"),
            make_file(
                "tests/test_context_pack.py",
                language="python",
                classes=[{"name": "HomeLandingPageFixture"}],
                functions=[
                    {"name": "renderLandingPage"},
                    {"name": "assertHomePage"},
                ],
                exports=["LandingPageSpec"],
                imports=["src.pages.home"],
            ),
        ]
    )

    ranked = rank_relevant_files(graph, "home landing page broken")
    paths = [item["file"]["path"] for item in ranked]

    assert paths[0] == "src/pages/Home.tsx"
    assert "tests/test_context_pack.py" in paths
    assert paths.index("src/pages/Home.tsx") < paths.index("tests/test_context_pack.py")


def test_rank_relevant_files_keeps_backend_route_above_unrelated_component():
    graph = fake_graph(
        [
            make_file(
                "src/routes/orders.ts",
                routes=[{"method": "GET", "path": "/orders", "source": "router.get"}],
            ),
            make_file("src/pages/OrdersPage.tsx"),
            make_file("src/components/Button.tsx"),
        ]
    )

    ranked = rank_relevant_files(graph, "orders API response is wrong")
    paths = [item["file"]["path"] for item in ranked]

    assert paths[0] == "src/routes/orders.ts"
    assert "src/components/Button.tsx" not in paths or paths.index("src/routes/orders.ts") < paths.index("src/components/Button.tsx")


def test_rank_relevant_files_demotes_tests_for_normal_page_task():
    graph = fake_graph(
        [
            make_file("src/pages/Home.tsx"),
            make_file("tests/test_home_page.py", language="python"),
        ]
    )

    ranked = rank_relevant_files(graph, "home page is broken")
    paths = [item["file"]["path"] for item in ranked]

    assert paths[0] == "src/pages/Home.tsx"
    assert paths.index("src/pages/Home.tsx") < paths.index("tests/test_home_page.py")


def test_rank_relevant_files_allows_tests_for_test_focused_task():
    graph = fake_graph(
        [
            make_file("src/pages/Home.tsx"),
            make_file("tests/test_home_page.py", language="python"),
        ]
    )

    ranked = rank_relevant_files(graph, "fix failing home page test")
    paths = [item["file"]["path"] for item in ranked]

    assert paths[0] == "tests/test_home_page.py"
    assert paths.index("tests/test_home_page.py") < paths.index("src/pages/Home.tsx")


def test_dependency_neighbor_detection_uses_small_fake_graph():
    graph = fake_graph(
        [
            make_file("src/api/user_login.py", language="python"),
            make_file("src/auth/users.py", language="python"),
            make_file("src/other.py", language="python"),
            make_file("tests/test_user_login.py", language="python"),
        ],
        edges=[
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
    )

    neighbors = find_dependency_neighbors(graph, ["src/api/user_login.py"])

    dependency_targets = {edge["to"] for edge in neighbors["dependencies"]}
    dependent_sources = {edge["from"] for edge in neighbors["dependents"]}

    assert "src/auth/users.py" in dependency_targets
    assert "src/app.py" in dependent_sources
    assert "tests/test_user_login.py" in dependent_sources


def test_build_context_pack_includes_deterministic_ranking_notes_and_paths():
    graph = fake_graph(
        [
            make_file("src/pages/LandingPage.tsx"),
            make_file("src/components/HeroSection.tsx"),
            make_file("src/components/Navbar.tsx"),
        ]
    )

    content = build_context_pack(graph, "we are stuck on home/landing page")

    assert "# Strata Context Pack" in content
    assert "we are stuck on home/landing page" in content
    _assert_terms(
        content,
        "deterministic repo matching was used",
        "task is only a hint",
        "not an llm plan",
        "repository file paths",
        "symbols",
        "routes",
        "framework hints",
        "broad task hints",
        "frontend/backend/test/data",
        "ranking",
        "confidence:",
    )
    assert "src/pages/LandingPage.tsx" in content
    assert "AI Editing Instructions" in content


def test_build_context_pack_shows_best_effort_note_when_matches_are_weak():
    graph = fake_graph(
        [
            make_file("cli_ui.py", language="python"),
            make_file("test_mapper.py", language="python"),
            make_file("tests/helpers.py", language="python"),
        ]
    )

    content = build_context_pack(graph, "landing page blank")

    assert "# Strata Context Pack" in content
    assert "did not find strong direct file matches" in content or "best-effort hints" in content
    assert "Suggested Verification" in content
    assert "py tests.py" in content
    assert "py tests\\run.py" in content


def test_build_context_pack_reports_no_files_when_everything_is_filtered_out():
    graph = fake_graph(
        [
            make_file("src/alpha.py", language="python"),
            make_file("src/beta.py", language="python"),
        ]
    )

    content = build_context_pack(graph, "landing page blank")

    assert "No strong file matches found." in content or "did not find strong direct file matches" in content
    assert "Suggested Verification" in content


def test_build_context_pack_compacts_dependency_neighbors():
    files = [make_file("src/pages/Home.tsx")]
    edges = []

    for index in range(10):
        source = f"src/feature/dependent_{index}.ts"
        files.append(make_file(source))
        edges.append(
            {
                "from": source,
                "to": "src/pages/Home.tsx",
                "type": "imports",
                "import": f"feature.dependent_{index}",
            }
        )

    content = build_context_pack(fake_graph(files, edges), "home page is broken")

    assert "...and" in content
    assert "Dependency Neighbors" in content


def test_build_context_pack_includes_alias_resolved_dependency_neighbors():
    graph = fake_graph(
        [
            make_file("src/App.tsx", imports=["@/components/Button"]),
            make_file("src/components/Button.tsx"),
        ],
        edges=[
            {
                "from": "src/App.tsx",
                "to": "src/components/Button.tsx",
                "type": "imports",
                "import": "@/components/Button",
            }
        ],
    )

    content = build_context_pack(graph, "app layout issue")

    assert "src/App.tsx" in content
    assert "src/components/Button.tsx" in content
    assert "@/components/Button" in content


TESTS = [
    test_rank_relevant_files_does_not_fill_with_hint_only_noise,
    test_rank_relevant_files_prefers_source_over_test_with_direct_fixture_terms,
    test_rank_relevant_files_keeps_backend_route_above_unrelated_component,
    test_rank_relevant_files_demotes_tests_for_normal_page_task,
    test_rank_relevant_files_allows_tests_for_test_focused_task,
    test_dependency_neighbor_detection_uses_small_fake_graph,
    test_build_context_pack_includes_deterministic_ranking_notes_and_paths,
    test_build_context_pack_shows_best_effort_note_when_matches_are_weak,
    test_build_context_pack_reports_no_files_when_everything_is_filtered_out,
    test_build_context_pack_compacts_dependency_neighbors,
    test_build_context_pack_includes_alias_resolved_dependency_neighbors,
]
