from pathlib import Path
from unittest.mock import patch

import strata.core.backend_linking_summary as backend_linking_summary
from strata.core.backend_linking_summary import (
    backend_relationship_summary_to_dict,
    summarize_backend_relationships,
)
from strata.core.backend_relationships import BackendRelationship


def _relationship(framework: str, route_path: str, method: str, **overrides):
    values = {
        "framework": framework,
        "relationship_type": "backend_route",
        "source_path": f"src/{framework}.py",
        "target_path": f"src/{framework}.py",
        "target_symbol": f"{framework}_handler",
        "route_path": route_path,
        "http_method": method,
        "handler_symbol": f"{framework}_handler",
        "confidence": "high",
        "evidence": (f"{framework} evidence",),
        "reason": f"{framework}_test",
    }
    values.update(overrides)
    return BackendRelationship(**values)


def _relationships():
    return (
        _relationship("fastapi", "/fastapi", "GET"),
        _relationship("flask", "/flask", "POST"),
        _relationship("django", "items/", "ANY"),
        _relationship("django_rest_framework", None, "GET", relationship_type="route_handler"),
        _relationship("express", "/express", "PATCH"),
        _relationship("nestjs", "/nestjs", "DELETE"),
        _relationship("go", "/go", "GET", warnings=("go warning",)),
    )


def test_summary_is_deterministic_and_json_ready():
    forward = backend_relationship_summary_to_dict(
        summarize_backend_relationships(_relationships())
    )
    reverse = backend_relationship_summary_to_dict(
        summarize_backend_relationships(reversed(_relationships()))
    )

    assert forward == reverse
    assert forward["relationship_count"] == len(forward["relationships"])


def test_duplicates_are_counted_and_payloads_are_deduped():
    relationships = _relationships()
    payload = summarize_backend_relationships((*relationships, relationships[0])).to_dict()

    assert payload["duplicate_relationship_count"] == 1
    assert payload["relationship_count"] == len(relationships)


def test_warnings_and_counts_are_preserved_across_frameworks():
    payload = summarize_backend_relationships(_relationships()).to_dict()

    assert payload["frameworks"] == {
        "django": 1,
        "django_rest_framework": 1,
        "express": 1,
        "fastapi": 1,
        "flask": 1,
        "go": 1,
        "nestjs": 1,
    }
    assert payload["http_methods"]["GET"] == 3
    assert payload["relationship_types"] == {"backend_route": 6, "route_handler": 1}
    assert payload["warnings"] == ["go warning"]
    assert payload["warning_count"] == 1
    assert "/go" in payload["route_paths"]


def test_summary_does_not_call_extractors_or_scan_files():
    with (
        patch("builtins.open", side_effect=AssertionError("opened a path")),
        patch.object(Path, "read_text", side_effect=AssertionError("read a path")),
        patch.object(Path, "stat", side_effect=AssertionError("statted a path")),
    ):
        payload = summarize_backend_relationships(_relationships()).to_dict()

    assert payload["relationship_count"] == 7


def test_summary_module_does_not_expose_scanning_workspace_or_journey_apis():
    public_names = {
        name
        for name in dir(backend_linking_summary)
        if not name.startswith("_")
    }
    forbidden_fragments = ("scan", "read", "workspace", "journey", "extract", "infer")

    assert not {
        name
        for name in public_names
        if any(fragment in name.lower() for fragment in forbidden_fragments)
    }


def test_docs_mention_k1_k10_and_handoffs():
    with open("docs/roadmap/backend-intelligence-foundation.md", encoding="utf-8") as handle:
        text = " ".join(handle.read().split())

    for batch in ("K1", "K2", "K3", "K4", "K5", "K6", "K7", "K8", "K9", "K10"):
        assert batch in text
    assert "supplied source text only" in text
    assert "Q owns workspace intelligence" in text
    assert "P owns user flow/journey intelligence" in text
    assert "Go is included because it was explicitly reintroduced by product direction" in text


TESTS = [
    test_summary_is_deterministic_and_json_ready,
    test_duplicates_are_counted_and_payloads_are_deduped,
    test_warnings_and_counts_are_preserved_across_frameworks,
    test_summary_does_not_call_extractors_or_scan_files,
    test_summary_module_does_not_expose_scanning_workspace_or_journey_apis,
    test_docs_mention_k1_k10_and_handoffs,
]
