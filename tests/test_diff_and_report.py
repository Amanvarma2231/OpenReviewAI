import pytest
from openreview_ai.utils.diff_viewer import compute_unified_diff, compute_line_changes
from openreview_ai.utils.report_exporter import export_markdown_report
from openreview_ai.schema import WorkflowResult, IterationStep, ExecutionResult


def test_unified_diff():
    old = "def foo():\n    return 1\n"
    new = "def foo():\n    return 2\n"
    diff = compute_unified_diff(old, new)
    assert "-    return 1" in diff
    assert "+    return 2" in diff


def test_markdown_report_export():
    step = IterationStep(
        round_idx=0,
        code="def hello(): pass",
        generator_explanation="Initial code",
        execution=ExecutionResult(success=True, stdout="OK")
    )
    res = WorkflowResult(
        task_prompt="Say hello",
        target_language="python",
        final_code="def hello(): pass",
        status="APPROVED",
        rounds_count=1,
        iterations=[step],
        generator_model="qwen2.5:0.5b",
        reviewer_model="mistral:latest",
        validator_model="deepseek-coder:1.3b",
        provider="mock"
    )
    md = export_markdown_report(res)
    assert "OpenReviewAI: Multi-LLM Code Review" in md
    assert "APPROVED" in md
    assert "qwen2.5:0.5b" in md
