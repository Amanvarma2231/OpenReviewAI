"""
Unit Tests for Storage, History Store & Report Generator
========================================================
Validates that runs are saved, loaded, deleted, summarized, and rendered into Markdown.
"""

import tempfile
from pathlib import Path
from storage.history_store import HistoryStore
from storage.report_generator import generate_markdown_report
from models.schemas import (
    WorkflowReport,
    WorkflowStatus,
    IterationRecord,
    SyntaxCheckResult,
    TestExecutionResult,
    TestStatus,
    ReviewResult,
    ReviewVerdict,
    ReviewIssue,
    IssueSeverity,
)


def create_dummy_report(run_id: str = "run_test_001", status: WorkflowStatus = WorkflowStatus.PASSED) -> WorkflowReport:
    syntax_res = SyntaxCheckResult(is_valid=True)
    test_res = TestExecutionResult(
        status=TestStatus.PASSED,
        total_tests=2,
        passed_tests=2,
        failed_tests=0,
        stdout="2 passed in 0.02s",
        duration_seconds=0.02,
    )
    rev_res = ReviewResult(
        verdict=ReviewVerdict.PASS,
        summary="Code passes all criteria.",
        requirements_met=True,
        issues=[],
        suggested_fixes=[],
        unresolved_concerns=[],
    )

    iteration = IterationRecord(
        iteration_number=1,
        code="def solve(): return 42\n",
        generator_model="qwen2.5-coder:3b",
        reviewer_model="deepseek-coder:1.3b",
        syntax_result=syntax_res,
        test_result=test_res,
        review_result=rev_res,
        duration_seconds=1.2,
        timestamp="2026-10-22T00:00:00Z",
    )

    return WorkflowReport(
        run_id=run_id,
        task_description="Return the number 42",
        constraints=["No loops"],
        generator_model="qwen2.5-coder:3b",
        reviewer_model="deepseek-coder:1.3b",
        iterations=[iteration],
        final_status=status,
        stop_reason="Criteria satisfied on attempt 1",
        final_code="def solve(): return 42\n",
        total_attempts=1,
        max_attempts=3,
        start_time="2026-10-22T00:00:00Z",
        end_time="2026-10-22T00:00:02Z",
        total_duration_seconds=2.0,
        unresolved_issues=[],
        test_suite_provided=True,
        validation_limitations=[],
    )


def test_history_store_save_load_delete():
    with tempfile.TemporaryDirectory() as temp_runs, tempfile.TemporaryDirectory() as temp_code:
        store = HistoryStore(runs_dir=Path(temp_runs), code_dir=Path(temp_code))
        report = create_dummy_report("run_12345")

        # Save
        saved_path = store.save_report(report)
        assert saved_path.exists()

        # Load
        loaded = store.load_report("run_12345")
        assert loaded is not None
        assert loaded.run_id == "run_12345"
        assert loaded.final_status == WorkflowStatus.PASSED

        # List runs
        runs = store.list_runs()
        assert len(runs) == 1
        assert runs[0]["run_id"] == "run_12345"

        # Summary stats
        stats = store.get_summary_stats()
        assert stats["total_runs"] == 1
        assert stats["passed_runs"] == 1
        assert stats["pass_rate_pct"] == 100.0

        # Delete
        deleted = store.delete_run("run_12345")
        assert deleted is True
        assert store.load_report("run_12345") is None


def test_markdown_report_formatting():
    report = create_dummy_report("run_format_test")
    md = generate_markdown_report(report)

    assert "# OpenReview AI — Workflow Execution Report" in md
    assert "`run_format_test`" in md
    assert "qwen2.5-coder:3b" in md
    assert "deepseek-coder:1.3b" in md
    assert "def solve(): return 42" in md
    assert "Criteria satisfied on attempt 1" in md
