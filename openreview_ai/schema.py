from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SeverityLevel(str, Enum):
    CRITICAL = "CRITICAL"
    MAJOR = "MAJOR"
    MINOR = "MINOR"
    SUGGESTION = "SUGGESTION"


class BugCategory(str, Enum):
    SYNTAX = "SYNTAX"
    LOGIC = "LOGIC"
    RUNTIME = "RUNTIME"
    EDGE_CASE = "EDGE_CASE"
    SECURITY = "SECURITY"
    PERFORMANCE = "PERFORMANCE"
    STYLE = "STYLE"


class ReviewStatus(str, Enum):
    APPROVED = "APPROVED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    REJECTED = "REJECTED"


class AcceptanceStatus(str, Enum):
    REVIEW_PASSED = "REVIEW_PASSED"
    SYNTAX_PASSED = "SYNTAX_PASSED"
    STATIC_ANALYSIS_PASSED = "STATIC_ANALYSIS_PASSED"
    TESTS_PASSED = "TESTS_PASSED"
    VALIDATION_PASSED = "VALIDATION_PASSED"
    COMPLETED = "COMPLETED"
    FINAL_ACCEPTED = "FINAL_ACCEPTED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    RETRY_LIMIT_REACHED = "RETRY_LIMIT_REACHED"
    NOT_RUN = "NOT_RUN"


class BugItem(BaseModel):
    id: str = Field(default_factory=lambda: f"BUG-{datetime.now().strftime('%M%S%f')[:8]}")
    line_number: Optional[int] = None
    category: BugCategory = BugCategory.LOGIC
    severity: SeverityLevel = SeverityLevel.MAJOR
    description: str
    suggested_fix: str
    resolved: bool = False


class ReviewFeedback(BaseModel):
    reviewer_name: str
    reviewer_model: str
    status: ReviewStatus
    has_bugs: bool
    summary: str
    bugs: List[BugItem] = Field(default_factory=list)
    overall_score: int = Field(default=7, ge=1, le=10)
    raw_response: Optional[str] = None


class ExecutionResult(BaseModel):
    success: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    execution_time_ms: float = 0.0
    syntax_valid: bool = True
    syntax_error: Optional[str] = None
    test_results: Dict[str, Any] = Field(default_factory=dict)


class AgentMessage(BaseModel):
    sender_role: str  # Generator, Reviewer, Validator, System
    sender_model: str
    round_idx: int
    timestamp: str = Field(default_factory=lambda: datetime.now().strftime("%H:%M:%S"))
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class IterationStep(BaseModel):
    round_idx: int
    code: str
    generator_explanation: Optional[str] = None
    execution: Optional[ExecutionResult] = None
    reviews: List[ReviewFeedback] = Field(default_factory=list)
    resolved_bug_count: int = 0
    open_bug_count: int = 0
    status: str = "IN_PROGRESS"


class WorkflowResult(BaseModel):
    task_prompt: str
    target_language: str = "python"
    final_code: str
    status: str  # APPROVED, MAX_RETRIES_REACHED, FAILED
    rounds_count: int
    iterations: List[IterationStep] = Field(default_factory=list)
    messages: List[AgentMessage] = Field(default_factory=list)
    total_bugs_detected: int = 0
    total_bugs_fixed: int = 0
    final_execution: Optional[ExecutionResult] = None
    generator_model: str
    reviewer_model: str
    validator_model: Optional[str] = None
    provider: str = "ollama"
    acceptance_status: AcceptanceStatus = AcceptanceStatus.NOT_RUN
    test_status: str = "NOT_RUN"


class ReviewState(BaseModel):
    """Current state passed through the Multi-LLM review graph."""
    task_prompt: str
    target_language: str = "python"
    unit_tests: Optional[str] = None
    
    current_round: int = 0
    max_retries: int = 3
    
    current_code: str = ""
    previous_code: Optional[str] = None
    
    execution_result: Optional[ExecutionResult] = None
    latest_reviews: List[ReviewFeedback] = Field(default_factory=list)
    all_iterations: List[IterationStep] = Field(default_factory=list)
    messages: List[AgentMessage] = Field(default_factory=list)
    
    all_bugs_detected: List[BugItem] = Field(default_factory=list)
    
    is_approved: bool = False
    is_finished: bool = False
    final_status: str = "PENDING"
    acceptance_status: AcceptanceStatus = AcceptanceStatus.NOT_RUN
    test_status: str = "NOT_RUN"
