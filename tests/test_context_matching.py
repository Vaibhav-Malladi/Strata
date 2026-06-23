from context_matching import (
    collect_file_terms,
    detect_file_roles,
    detect_task_hints,
    expand_task_terms,
    extract_identifier_terms,
    extract_task_phrases,
    extract_task_terms,
    score_confidence,
    score_file_for_task,
)


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


def test_extract_task_terms_removes_common_tiny_words_and_keeps_useful_terms():
    terms = extract_task_terms("Change the user login API and the UI")

    assert "the" not in terms
    assert "and" not in terms
    assert "user" in terms
    assert "login" in terms
    assert "api" in terms


def test_extract_identifier_terms_splits_paths_and_identifiers():
    landing_terms = extract_identifier_terms("src/pages/LandingPage.tsx")
    user_role_terms = extract_identifier_terms("src/components/user-role-card.tsx")

    assert "landing" in landing_terms
    assert "page" in landing_terms
    assert "user" in user_role_terms
    assert "role" in user_role_terms
    assert "card" in user_role_terms


def test_expand_task_terms_includes_small_generic_synonyms():
    expanded = expand_task_terms(["home", "page", "api"])

    assert "index" in expanded
    assert "landing" in expanded
    assert "screen" in expanded
    assert "view" in expanded
    assert "endpoint" in expanded
    assert "route" in expanded


def test_extract_task_phrases_collects_adjacent_terms():
    phrases = extract_task_phrases(["home", "landing", "page"])

    assert "home landing" in phrases
    assert "landing page" in phrases
    assert "home landing page" in phrases


def test_collect_file_terms_uses_path_symbols_language_and_route_data():
    file_info = make_file(
        "src/pages/LandingPage.tsx",
        language="typescript",
        classes=[{"name": "LandingPage"}],
        functions=[{"name": "renderLandingPage"}],
        exports=["LandingPage"],
        imports=["src.components.Navbar"],
        routes=[{"method": "GET", "path": "/landing-page", "source": "router.get"}],
    )

    terms = collect_file_terms(file_info)

    assert "landing" in terms
    assert "page" in terms
    assert "typescript" in terms
    assert "navbar" in terms
    assert "router" in terms
    assert "get" in terms


def test_detect_file_roles_uses_path_and_filename_clues():
    assert "page" in detect_file_roles(make_file("src/pages/Home.tsx"))
    assert "component" in detect_file_roles(make_file("src/components/Navbar.tsx"))
    assert "route" in detect_file_roles(make_file("src/routes/users.ts"))
    assert "middleware" in detect_file_roles(make_file("src/auth/authMiddleware.ts"))
    assert "test" in detect_file_roles(make_file("tests/test_home_page.py", language="python"))


def test_detect_task_hints_finds_frontend_and_backend_intent():
    frontend_hints = detect_task_hints("stuck on home/landing page")
    backend_hints = detect_task_hints("API response is wrong for orders")

    assert frontend_hints["frontend_ui"] is True
    assert backend_hints["backend_api"] is True


def test_score_confidence_labels_direct_and_hint_only_matches():
    high = score_confidence(20, ["home", "page"], ["page"])
    medium = score_confidence(14, ["home"], ["page"])
    low = score_confidence(4, [], ["component"])

    assert high == "high"
    assert medium == "medium"
    assert low == "low"


def test_score_file_for_task_prefers_direct_page_match():
    file_info = make_file("src/pages/LandingPage.tsx")
    task_terms = extract_task_terms("landing page broken")

    score = score_file_for_task(file_info, task_terms, "landing page broken")

    assert score > 0


TESTS = [
    test_extract_task_terms_removes_common_tiny_words_and_keeps_useful_terms,
    test_extract_identifier_terms_splits_paths_and_identifiers,
    test_expand_task_terms_includes_small_generic_synonyms,
    test_extract_task_phrases_collects_adjacent_terms,
    test_collect_file_terms_uses_path_symbols_language_and_route_data,
    test_detect_file_roles_uses_path_and_filename_clues,
    test_detect_task_hints_finds_frontend_and_backend_intent,
    test_score_confidence_labels_direct_and_hint_only_matches,
    test_score_file_for_task_prefers_direct_page_match,
]
