import pytest
from openreview_ai.schema import (
    SeverityLevel,
    BugCategory,
    ReviewStatus,
    BugItem,
    ReviewFeedback,
    ExecutionResult,
    WorkflowResult,
    ReviewState
)


def test_bug_item_creation():
    bug = BugItem(
        line_number=12,
        category=BugCategory.LOGIC,
        severity=SeverityLevel.CRITICAL,
        description="Infinite loop condition",
        suggested_fix="Increment counter inside while loop"
    )
    assert bug.category == BugCategory.LOGIC
    assert bug.severity == SeverityLevel.CRITICAL
    assert bug.resolved is False
    assert bug.id.startswith("BUG-")


def test_review_feedback_creation():
    feedback = ReviewFeedback(
        reviewer_name="LLM 2 (Reviewer)",
        reviewer_model="mistral:latest",
        status=ReviewStatus.CHANGES_REQUESTED,
        has_bugs=True,
        summary="Edge cases detected",
        bugs=[
            BugItem(
                line_number=3,
                category=BugCategory.EDGE_CASE,
                severity=SeverityLevel.MAJOR,
                description="Empty list handling missing",
                suggested_fix="Check if not data: return []"
            )
        ],
        overall_score=6
    )
    assert feedback.has_bugs is True
    assert feedback.status == ReviewStatus.CHANGES_REQUESTED
    assert len(feedback.bugs) == 1
    assert feedback.overall_score == 6


def test_execution_result_defaults():
    res = ExecutionResult(success=True, stdout="Hello World\n")
    assert res.success is True
    assert res.exit_code == 0
    assert res.syntax_valid is True
    assert res.syntax_error is None
