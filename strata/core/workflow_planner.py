"""Deterministic helpers for classifying tasks and building workflow plans."""

from collections.abc import Mapping
from copy import deepcopy
import re
from typing import Any

DEFAULT_TASK_TYPE = "generic"

SUPPORTED_TASK_TYPE_ORDER = (
    "bugfix",
    "feature",
    "refactor",
    "docs",
    "test",
    "explain",
    "generic",
)

SUPPORTED_TASK_TYPES = set(SUPPORTED_TASK_TYPE_ORDER)

_TASK_TYPE_ALIASES = {
    "bug": "bugfix",
    "fix": "bugfix",
    "repair": "bugfix",
    "feat": "feature",
    "add": "feature",
    "doc": "docs",
    "documentation": "docs",
    "tests": "test",
    "testing": "test",
    "spec": "test",
    "cleanup": "refactor",
    "clean": "refactor",
    "restructure": "refactor",
    "understand": "explain",
    "summary": "explain",
}

_BUGFIX_KEYWORDS = (
    "fix",
    "bug",
    "broken",
    "error",
    "failing",
    "failure",
    "crash",
    "exception",
    "traceback",
    "regression",
    "wrong",
)

_BUGFIX_STRONG_KEYWORDS = tuple(
    keyword for keyword in _BUGFIX_KEYWORDS if keyword != "regression"
)

_TEST_KEYWORDS = (
    "test",
    "tests",
    "testing",
    "coverage",
    "unit test",
    "regression test",
)

_DOCS_KEYWORDS = (
    "docs",
    "documentation",
    "readme",
    "comment",
    "comments",
    "explain in docs",
)

_REFACTOR_KEYWORDS = (
    "refactor",
    "cleanup",
    "clean up",
    "restructure",
    "simplify",
    "organize",
    "rename",
)

_FEATURE_KEYWORDS = (
    "add",
    "implement",
    "create",
    "build",
    "support",
    "enable",
    "new feature",
)

_EXPLAIN_KEYWORDS = (
    "explain",
    "summarize",
    "understand",
    "analyze",
    "review architecture",
    "what does",
)

_BASE_PLANS = {
    "bugfix": {
        "before_adapter": ["scan", "context", "preflight", "agent_prompt", "snapshot"],
        "adapter": ["adapter"],
        "after_adapter": ["diff", "verify", "gate"],
    },
    "feature": {
        "before_adapter": ["scan", "context", "preflight", "agent_prompt", "snapshot"],
        "adapter": ["adapter"],
        "after_adapter": ["diff", "verify", "gate"],
    },
    "refactor": {
        "before_adapter": ["scan", "context", "preflight", "agent_prompt", "snapshot"],
        "adapter": ["adapter"],
        "after_adapter": ["diff", "verify", "gate"],
    },
    "docs": {
        "before_adapter": ["scan", "context", "agent_prompt", "snapshot"],
        "adapter": ["adapter"],
        "after_adapter": ["diff", "gate"],
    },
    "test": {
        "before_adapter": ["scan", "context", "preflight", "agent_prompt", "snapshot"],
        "adapter": ["adapter"],
        "after_adapter": ["diff", "verify", "gate"],
    },
    "explain": {
        "before_adapter": ["scan", "context", "agent_prompt"],
        "adapter": ["adapter"],
        "after_adapter": ["gate"],
    },
    "generic": {
        "before_adapter": ["scan", "context", "preflight", "agent_prompt", "snapshot"],
        "adapter": ["adapter"],
        "after_adapter": ["diff", "verify", "gate"],
    },
}


def supported_task_types() -> set[str]:
    """Return a fresh set of the supported task types."""

    return set(SUPPORTED_TASK_TYPES)


def normalize_task_type(task_type: str | None) -> str:
    """Normalize a task type name and resolve common aliases."""

    if task_type is None:
        return DEFAULT_TASK_TYPE

    normalized = task_type.strip().lower()
    if not normalized:
        return DEFAULT_TASK_TYPE

    return _TASK_TYPE_ALIASES.get(normalized, normalized)


def validate_task_type(task_type: str | None) -> str:
    """Normalize and validate a task type."""

    normalized = normalize_task_type(task_type)
    if normalized not in SUPPORTED_TASK_TYPES:
        supported = ", ".join(SUPPORTED_TASK_TYPE_ORDER)
        raise ValueError(f"Unknown task type: {normalized}. Supported task types: {supported}")
    return normalized


def classify_task(task: str, explicit_type: str | None = None) -> dict:
    """Classify a task deterministically without calling any external tools."""

    if explicit_type is not None:
        task_type = validate_task_type(explicit_type)
        return {
            "task_type": task_type,
            "confidence": "high",
            "reason": f"explicit task type: {task_type}",
        }

    if not isinstance(task, str) or not task.strip():
        raise ValueError("task must be a non-empty string")

    normalized_task = _normalize_text(task)

    matched_keyword = _first_matching_keyword(normalized_task, _BUGFIX_STRONG_KEYWORDS)
    if matched_keyword is not None:
        return {
            "task_type": "bugfix",
            "confidence": "medium",
            "reason": f"matched bugfix keyword: {matched_keyword}",
        }

    matched_keyword = _first_matching_keyword(normalized_task, _TEST_KEYWORDS)
    if matched_keyword is not None:
        return {
            "task_type": "test",
            "confidence": "medium",
            "reason": f"matched test keyword: {matched_keyword}",
        }

    matched_keyword = _first_matching_keyword(normalized_task, ("regression",))
    if matched_keyword is not None:
        return {
            "task_type": "bugfix",
            "confidence": "medium",
            "reason": f"matched bugfix keyword: {matched_keyword}",
        }

    for task_type, keywords in (
        ("docs", _DOCS_KEYWORDS),
        ("refactor", _REFACTOR_KEYWORDS),
        ("feature", _FEATURE_KEYWORDS),
        ("explain", _EXPLAIN_KEYWORDS),
    ):
        matched_keyword = _first_matching_keyword(normalized_task, keywords)
        if matched_keyword is not None:
            return {
                "task_type": task_type,
                "confidence": "medium",
                "reason": f"matched {task_type} keyword: {matched_keyword}",
            }

    return {
        "task_type": DEFAULT_TASK_TYPE,
        "confidence": "low",
        "reason": "no workflow keywords matched",
    }


def get_base_plan(task_type: str | None) -> dict:
    """Return a fresh base plan for a validated task type."""

    normalized = validate_task_type(task_type)
    return {
        "task_type": normalized,
        "before_adapter": deepcopy(_BASE_PLANS[normalized]["before_adapter"]),
        "adapter": deepcopy(_BASE_PLANS[normalized]["adapter"]),
        "after_adapter": deepcopy(_BASE_PLANS[normalized]["after_adapter"]),
    }


def build_step_plan(
    task: str,
    explicit_type: str | None = None,
    auto_snapshot: bool = True,
    auto_verify: bool = True,
    include_adapter: bool = True,
) -> dict:
    """Build a deterministic step plan for a task."""

    classification = classify_task(task, explicit_type=explicit_type)
    plan = get_base_plan(classification["task_type"])

    if not auto_snapshot:
        plan["before_adapter"] = [step for step in plan["before_adapter"] if step != "snapshot"]

    if not auto_verify:
        plan["after_adapter"] = [step for step in plan["after_adapter"] if step != "verify"]

    if not include_adapter:
        plan["adapter"] = [step for step in plan["adapter"] if step != "adapter"]

    steps = [
        *plan["before_adapter"],
        *plan["adapter"],
        *plan["after_adapter"],
    ]

    return {
        "task": task,
        "classification": classification,
        "plan": plan,
        "steps": steps,
    }


def summarize_plan(plan: dict) -> dict:
    """Summarize a step plan without mutating it."""

    if not isinstance(plan, Mapping):
        raise ValueError("plan must be a mapping")

    classification = plan.get("classification", {})
    steps = plan.get("steps", [])

    if not isinstance(classification, Mapping):
        classification = {}

    if not isinstance(steps, list):
        steps = list(steps) if steps is not None else []

    return {
        "task_type": classification.get("task_type", DEFAULT_TASK_TYPE),
        "confidence": classification.get("confidence", "low"),
        "steps": " -> ".join(steps),
        "step_count": len(steps),
    }


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _first_matching_keyword(text: str, keywords: tuple[str, ...]) -> str | None:
    for keyword in keywords:
        if _keyword_matches(text, keyword):
            return keyword
    return None


def _keyword_matches(text: str, keyword: str) -> bool:
    if " " in keyword:
        return keyword in text

    return re.search(rf"\b{re.escape(keyword)}\b", text) is not None
