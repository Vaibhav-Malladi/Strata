import strata.core.workflow_planner as new_workflow_planner
import workflow_planner as old_workflow_planner

from workflow_planner import (
    DEFAULT_TASK_TYPE,
    SUPPORTED_TASK_TYPES,
    build_step_plan,
    classify_task,
    get_base_plan,
    normalize_task_type,
    supported_task_types,
    summarize_plan,
    validate_task_type,
)


def test_workflow_planner_module_compatibility():
    assert (
        old_workflow_planner.supported_task_types
        is new_workflow_planner.supported_task_types
    )
    assert old_workflow_planner.classify_task is new_workflow_planner.classify_task
    assert old_workflow_planner.build_step_plan is new_workflow_planner.build_step_plan
    assert old_workflow_planner.summarize_plan is new_workflow_planner.summarize_plan


def _expect_value_error(function, *args, contains: str | None = None):
    try:
        function(*args)
    except ValueError as error:
        if contains is not None:
            assert contains in str(error)
    else:
        raise AssertionError("Expected ValueError")


def test_supported_task_types_returns_fresh_set():
    first = supported_task_types()
    second = supported_task_types()

    assert first == {
        "bugfix",
        "feature",
        "refactor",
        "docs",
        "test",
        "explain",
        "generic",
    }
    assert second == first
    assert first is not second

    first.add("banana")

    assert "banana" not in SUPPORTED_TASK_TYPES
    assert "banana" not in supported_task_types()


def test_normalize_task_type_handles_aliases():
    assert normalize_task_type(None) == DEFAULT_TASK_TYPE
    assert normalize_task_type("") == DEFAULT_TASK_TYPE
    assert normalize_task_type(" fix ") == "bugfix"
    assert normalize_task_type("feat") == "feature"
    assert normalize_task_type("documentation") == "docs"
    assert normalize_task_type("tests") == "test"
    assert normalize_task_type("cleanup") == "refactor"
    assert normalize_task_type("summary") == "explain"


def test_validate_task_type_rejects_unknown():
    _expect_value_error(validate_task_type, "banana", contains="Unknown task type")


def test_classify_task_rejects_empty_task():
    _expect_value_error(classify_task, "", contains="non-empty string")
    _expect_value_error(classify_task, "   ", contains="non-empty string")


def test_classify_task_uses_explicit_type():
    result = classify_task("do something", explicit_type="docs")

    assert result["task_type"] == "docs"
    assert result["confidence"] == "high"
    assert result["reason"] == "explicit task type: docs"


def test_classify_task_detects_bugfix():
    result = classify_task("fix broken helper import")

    assert result["task_type"] == "bugfix"
    assert result["confidence"] == "medium"


def test_classify_task_detects_feature():
    result = classify_task("add support for rust projects")

    assert result["task_type"] == "feature"
    assert result["confidence"] == "medium"


def test_classify_task_detects_refactor():
    result = classify_task("refactor scanner into smaller helpers")

    assert result["task_type"] == "refactor"
    assert result["confidence"] == "medium"


def test_classify_task_detects_docs():
    result = classify_task("update README documentation")

    assert result["task_type"] == "docs"
    assert result["confidence"] == "medium"


def test_classify_task_detects_test():
    result = classify_task("add regression test for parser")

    assert result["task_type"] == "test"
    assert result["confidence"] == "medium"


def test_classify_task_detects_explain():
    result = classify_task("explain how scanner works")

    assert result["task_type"] == "explain"
    assert result["confidence"] == "medium"


def test_classify_task_priority_bugfix_over_feature():
    result = classify_task("fix bug and add support for edge case")

    assert result["task_type"] == "bugfix"
    assert result["confidence"] == "medium"


def test_classify_task_unknown_returns_generic_low_confidence():
    result = classify_task("make it better somehow")

    assert result["task_type"] == "generic"
    assert result["confidence"] == "low"


def test_get_base_plan_returns_fresh_copy():
    first = get_base_plan("bugfix")
    first["before_adapter"].append("banana")

    second = get_base_plan("bugfix")

    assert "banana" not in second["before_adapter"]
    assert second["before_adapter"] == ["scan", "context", "preflight", "agent_prompt", "snapshot"]


def test_build_step_plan_bugfix_default_steps():
    result = build_step_plan("fix broken helper import")

    assert result["classification"]["task_type"] == "bugfix"
    assert result["steps"] == [
        "scan",
        "context",
        "preflight",
        "agent_prompt",
        "snapshot",
        "adapter",
        "diff",
        "verify",
        "gate",
    ]


def test_build_step_plan_respects_auto_snapshot_false():
    result = build_step_plan("fix broken helper import", auto_snapshot=False)

    assert "snapshot" not in result["plan"]["before_adapter"]
    assert result["steps"] == [
        "scan",
        "context",
        "preflight",
        "agent_prompt",
        "adapter",
        "diff",
        "verify",
        "gate",
    ]


def test_build_step_plan_respects_auto_verify_false():
    result = build_step_plan("fix broken helper import", auto_verify=False)

    assert "verify" not in result["plan"]["after_adapter"]
    assert result["steps"] == [
        "scan",
        "context",
        "preflight",
        "agent_prompt",
        "snapshot",
        "adapter",
        "diff",
        "gate",
    ]


def test_build_step_plan_respects_include_adapter_false():
    result = build_step_plan("fix broken helper import", include_adapter=False)

    assert result["plan"]["adapter"] == []
    assert result["steps"] == [
        "scan",
        "context",
        "preflight",
        "agent_prompt",
        "snapshot",
        "diff",
        "verify",
        "gate",
    ]


def test_build_step_plan_docs_omits_preflight_and_verify():
    result = build_step_plan("update README documentation")

    assert result["classification"]["task_type"] == "docs"
    assert result["steps"] == [
        "scan",
        "context",
        "agent_prompt",
        "snapshot",
        "adapter",
        "diff",
        "gate",
    ]
    assert "preflight" not in result["steps"]
    assert "verify" not in result["steps"]


def test_build_step_plan_explain_minimal_plan():
    result = build_step_plan("explain how scanner works")

    assert result["classification"]["task_type"] == "explain"
    assert result["steps"] == [
        "scan",
        "context",
        "agent_prompt",
        "adapter",
        "gate",
    ]
    assert "snapshot" not in result["steps"]
    assert "diff" not in result["steps"]
    assert "verify" not in result["steps"]


def test_summarize_plan_returns_step_string_and_count():
    result = build_step_plan("fix broken helper import")
    summary = summarize_plan(result)

    assert summary["task_type"] == "bugfix"
    assert summary["confidence"] == "medium"
    assert summary["steps"] == "scan -> context -> preflight -> agent_prompt -> snapshot -> adapter -> diff -> verify -> gate"
    assert summary["step_count"] == len(result["steps"])


def test_build_step_plan_does_not_mutate_constants():
    build_step_plan("fix broken helper import", auto_snapshot=False, auto_verify=False)

    result = build_step_plan("fix broken helper import")

    assert result["plan"]["before_adapter"] == [
        "scan",
        "context",
        "preflight",
        "agent_prompt",
        "snapshot",
    ]
    assert result["plan"]["after_adapter"] == ["diff", "verify", "gate"]


TESTS = [
    test_workflow_planner_module_compatibility,
    test_supported_task_types_returns_fresh_set,
    test_normalize_task_type_handles_aliases,
    test_validate_task_type_rejects_unknown,
    test_classify_task_rejects_empty_task,
    test_classify_task_uses_explicit_type,
    test_classify_task_detects_bugfix,
    test_classify_task_detects_feature,
    test_classify_task_detects_refactor,
    test_classify_task_detects_docs,
    test_classify_task_detects_test,
    test_classify_task_detects_explain,
    test_classify_task_priority_bugfix_over_feature,
    test_classify_task_unknown_returns_generic_low_confidence,
    test_get_base_plan_returns_fresh_copy,
    test_build_step_plan_bugfix_default_steps,
    test_build_step_plan_respects_auto_snapshot_false,
    test_build_step_plan_respects_auto_verify_false,
    test_build_step_plan_respects_include_adapter_false,
    test_build_step_plan_docs_omits_preflight_and_verify,
    test_build_step_plan_explain_minimal_plan,
    test_summarize_plan_returns_step_string_and_count,
    test_build_step_plan_does_not_mutate_constants,
]
