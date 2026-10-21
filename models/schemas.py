"""
OpenReview AI - Data Models and Schemas
======================================
Strict Pydantic schemas for multi-agent code generation, reviews, syntax checks,
test execution, and full workflow reporting.
"""

from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class ReviewVerdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


class IssueSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class ReviewIssue(BaseModel):
    issue_type: str = Field(
        ...,
        description="Type of issue: e.g. syntax, logic, security, edge_case, maintainability, requirements",
    )
    severity: IssueSeverity = Field(
        default=IssueSeverity.MEDIUM,
        description="Severity level of the issue",
    )
    line_number: Optional[int] = Field(
        default=None,
        description="Approximate line number in generated code where the issue resides, if identifiable",
    )
    description: str = Field(..., description="Clear explanation of the defect or concern")
    suggested_fix: Optional[str] = Field(
        default=None,
        description="Actionable instruction or snippet on how to resolve this issue",
    )


class ReviewResult(BaseModel):
    verdict: ReviewVerdict = Field(..., description="Overall verdict: PASS or FAIL")
    summary: str = Field(..., description="High-level evaluation summary of the code")
    issues: List[ReviewIssue] = Field(
        default_factory=list,
        description="List of identified issues, bugs, or concerns",
    )
    suggested_fixes: List[str] = Field(
        default_factory=list,
        description="General suggestions to improve the implementation",
    )
    requirements_met: bool = Field(
        default=False,
        description="Whether the code completely satisfies the original user requirements",
    )
    unresolved_concerns: List[str] = Field(
        default_factory=list,
        description="Any remaining questions, edge cases, or potential risks",
    )
    raw_response: Optional[str] = Field(
        default=None,
        description="Raw reviewer LLM response for debugging and audit trail",
    )


class SyntaxCheckResult(BaseModel):
    is_valid: bool = Field(..., description="True if code parsed cleanly via ast.parse")
    error_message: Optional[str] = Field(
        default=None,
        description="SyntaxError exception message if invalid",
    )
    line_number: Optional[int] = Field(
        default=None,
        description="Line number where syntax error occurred",
    )
    offset: Optional[int] = Field(
        default=None,
        description="Column offset of the syntax error",
    )
    error_type: Optional[str] = Field(
        default=None,
        description="Specific error type, e.g. SyntaxError, IndentationError",
    )


class TestStatus(str, Enum):
    __test__ = False
    NOT_RUN = "NOT_RUN"
    PASSED = "PASSED"
    FAILED = "FAILED"
    ERROR = "ERROR"
    TIMEOUT = "TIMEOUT"


class TestExecutionResult(BaseModel):
    __test__ = False
    status: TestStatus = Field(
        default=TestStatus.NOT_RUN,
        description="Overall test execution status",
    )
    total_tests: int = Field(default=0, description="Total number of tests run")
    passed_tests: int = Field(default=0, description="Number of passed tests")
    failed_tests: int = Field(default=0, description="Number of failed tests")
    error_details: Optional[str] = Field(
        default=None,
        description="Detailed failure traceback or execution error",
    )
    stdout: str = Field(default="", description="Standard output from test runner")
    stderr: str = Field(default="", description="Standard error from test runner")
    duration_seconds: float = Field(
        default=0.0,
        description="Elapsed time for test execution in seconds",
    )
    sandbox_mode: str = Field(
        default="isolated_subprocess",
        description="Execution mode, e.g. isolated_subprocess, docker, disabled",
    )


class StaticAnalysisResult(BaseModel):
    is_clean: bool = Field(default=True, description="True if no linter errors found")
    findings: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of linting or static analysis findings",
    )
    tool_name: str = Field(default="ruff", description="Static analysis tool used")
    raw_output: str = Field(default="", description="Raw output from static analysis tool")


class IterationRecord(BaseModel):
    iteration_number: int = Field(..., description="Iteration sequence number (1, 2, ...)")
    code: str = Field(..., description="Python code produced in this iteration")
    generator_model: str = Field(..., description="Model used for generation")
    reviewer_model: str = Field(..., description="Model used for review")
    syntax_result: SyntaxCheckResult = Field(
        ...,
        description="Syntax check outcome for this iteration",
    )
    test_result: TestExecutionResult = Field(
        ...,
        description="Test execution outcome for this iteration",
    )
    review_result: Optional[ReviewResult] = Field(
        default=None,
        description="Structured review outcome from reviewer agent",
    )
    static_analysis: Optional[StaticAnalysisResult] = Field(
        default=None,
        description="Static analysis findings if enabled",
    )
    duration_seconds: float = Field(
        default=0.0,
        description="Total duration taken by this iteration",
    )
    timestamp: str = Field(..., description="ISO 8601 timestamp of iteration completion")


class WorkflowStatus(str, Enum):
    INITIALIZING = "INITIALIZING"
    RUNNING = "RUNNING"
    REVIEW_PASSED = "REVIEW_PASSED"
    REVIEW_FAILED = "REVIEW_FAILED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    PASSED = "PASSED"
    RETRY_LIMIT_REACHED = "RETRY_LIMIT_REACHED"
    ERROR = "ERROR"


class WorkflowReport(BaseModel):
    run_id: str = Field(..., description="Unique run identifier (UUID or timestamp-based)")
    task_description: str = Field(..., description="Original user task prompt")
    constraints: List[str] = Field(
        default_factory=list,
        description="Optional technical or business constraints specified by user",
    )
    generator_model: str = Field(..., description="Configured code generator model")
    reviewer_model: str = Field(..., description="Configured code reviewer model")
    iterations: List[IterationRecord] = Field(
        default_factory=list,
        description="Complete chronological history of each iteration",
    )
    final_status: WorkflowStatus = Field(
        ...,
        description="Final overall workflow status",
    )
    stop_reason: str = Field(..., description="Human-readable explanation of why workflow stopped")
    final_code: str = Field(default="", description="Final Python code produced")
    total_attempts: int = Field(default=0, description="Total number of attempts executed")
    max_attempts: int = Field(default=3, description="Configured maximum attempts allowed")
    start_time: str = Field(..., description="Workflow start ISO 8601 timestamp")
    end_time: str = Field(..., description="Workflow completion ISO 8601 timestamp")
    total_duration_seconds: float = Field(
        default=0.0,
        description="Total workflow run duration in seconds",
    )
    unresolved_issues: List[str] = Field(
        default_factory=list,
        description="Any remaining issues or concerns that were not resolved",
    )
    test_suite_provided: bool = Field(
        default=False,
        description="Whether an explicit test suite was provided and executed",
    )
    validation_limitations: List[str] = Field(
        default_factory=list,
        description="Explicit caveats, e.g. tests were not provided or sandbox restrictions",
    )
