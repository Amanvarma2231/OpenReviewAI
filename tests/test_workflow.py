"""
Unit Tests for Workflow Controller & Self-Correction Loop
=========================================================
Tests multi-attempt workflows, acceptance criteria, correction triggers,
retry limits, and error handling with mocked agents.
"""

import pytest
from unittest.mock import MagicMock
from models.schemas import (
    WorkflowStatus,
    ReviewResult,
    ReviewVerdict,
    ReviewIssue,
    IssueSeverity,
    SyntaxCheckResult,
    TestExecutionResult,
    TestStatus,
)
from workflow.controller import WorkflowController
from storage.history_store import HistoryStore
import tempfile
from pathlib import Path


@pytest.fixture
def mock_controller():
    temp_runs = tempfile.mkdtemp()
    temp_code = tempfile.mkdtemp()
    store = HistoryStore(runs_dir=Path(temp_runs), code_dir=Path(temp_code))

    generator = MagicMock()
    reviewer = MagicMock()
    generator.model_name = "qwen2.5-coder:3b"
    reviewer.model_name = "deepseek-coder:1.3b"

    client = MagicMock()
    controller = WorkflowController(
        client=client,
        generator=generator,
        reviewer=reviewer,
        history_store=store,
    )
    return controller, generator, reviewer


def test_empty_task_returns_error(mock_controller):
    controller, _, _ = mock_controller
    report = controller.run(task="")
    assert report.final_status == WorkflowStatus.ERROR
    assert "cannot be empty" in report.stop_reason.lower()
    assert report.total_attempts == 0


def test_successful_workflow_single_attempt(mock_controller):
    controller, generator, reviewer = mock_controller

    valid_code = "def add(a, b): return a + b\n"
    generator.generate_code.return_value = valid_code

    reviewer.review_code.return_value = ReviewResult(
        verdict=ReviewVerdict.PASS,
        summary="Code is clean and correct.",
        requirements_met=True,
        issues=[],
        suggested_fixes=[],
        unresolved_concerns=[],
    )

    test_code = "def test_add(): assert add(1, 2) == 3"
    report = controller.run(
        task="Write an add function",
        test_code=test_code,
        max_attempts=3,
    )

    assert report.total_attempts == 1
    assert report.final_status == WorkflowStatus.PASSED
    assert "All acceptance criteria met" in report.stop_reason
    generator.generate_code.assert_called_once()
    generator.fix_code.assert_not_called()


def test_correction_called_after_failed_review(mock_controller):
    controller, generator, reviewer = mock_controller

    buggy_code = "def add(a, b): return a - b\n"
    fixed_code = "def add(a, b): return a + b\n"

    generator.generate_code.return_value = buggy_code
    generator.fix_code.return_value = fixed_code

    # First attempt fails review; second attempt passes
    fail_review = ReviewResult(
        verdict=ReviewVerdict.FAIL,
        summary="Logic error: subtracts instead of adds.",
        requirements_met=False,
        issues=[
            ReviewIssue(
                issue_type="logic",
                severity=IssueSeverity.HIGH,
                line_number=1,
                description="Subtraction used instead of addition.",
                suggested_fix="Change '-' to '+'",
            )
        ],
        suggested_fixes=["Use + operator"],
        unresolved_concerns=[],
    )

    pass_review = ReviewResult(
        verdict=ReviewVerdict.PASS,
        summary="Logic error fixed.",
        requirements_met=True,
        issues=[],
        suggested_fixes=[],
        unresolved_concerns=[],
    )

    reviewer.review_code.side_effect = [fail_review, pass_review]

    test_code = "def test_add(): assert add(1, 2) == 3"
    report = controller.run(
        task="Write an add function",
        test_code=test_code,
        max_attempts=3,
    )

    assert report.total_attempts == 2
    assert report.final_status == WorkflowStatus.PASSED
    assert generator.generate_code.call_count == 1
    assert generator.fix_code.call_count == 1
    assert report.final_code == fixed_code


def test_retry_limit_reached(mock_controller):
    controller, generator, reviewer = mock_controller

    code = "def solve(): return False\n"
    generator.generate_code.return_value = code
    generator.fix_code.return_value = code

    failing_review = ReviewResult(
        verdict=ReviewVerdict.FAIL,
        summary="Requirement not met.",
        requirements_met=False,
        issues=[
            ReviewIssue(
                issue_type="requirements",
                severity=IssueSeverity.HIGH,
                description="Does not satisfy requirement.",
            )
        ],
        suggested_fixes=[],
        unresolved_concerns=["Function returns False"],
    )
    reviewer.review_code.return_value = failing_review

    report = controller.run(
        task="Return True",
        max_attempts=2,
    )

    assert report.total_attempts == 2
    assert report.final_status == WorkflowStatus.REVIEW_FAILED
    assert "Retry limit (2) reached" in report.stop_reason


def test_test_suite_failure_triggers_validation_failed(mock_controller):
    controller, generator, reviewer = mock_controller

    # Syntactically valid code, but fails test assertion
    failing_code = "def get_val(): return 100\n"
    generator.generate_code.return_value = failing_code
    generator.fix_code.return_value = failing_code

    # Reviewer mistakenly passes or says code looks okay
    reviewer.review_code.return_value = ReviewResult(
        verdict=ReviewVerdict.PASS,
        summary="Syntax is fine.",
        requirements_met=True,
        issues=[],
        suggested_fixes=[],
        unresolved_concerns=[],
    )

    # Test asserts get_val() == 42
    test_code = "def test_val(): assert get_val() == 42"

    report = controller.run(
        task="Return 42",
        test_code=test_code,
        max_attempts=2,
    )

    # Must NOT be labeled PASSED because pytest failed!
    assert report.final_status == WorkflowStatus.VALIDATION_FAILED
    assert report.total_attempts == 2
    assert "pytest suite failed" in report.stop_reason.lower()
