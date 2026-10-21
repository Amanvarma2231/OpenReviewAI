"""
OpenReview AI - Workflow Controller
===================================
Coordinates multi-agent interaction, review iterations, syntax checks, test execution,
and stopping conditions. Prevents infinite loops and preserves complete iteration evidence.
"""

import time
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Callable, Dict, Any

from models.schemas import (
    WorkflowReport,
    WorkflowStatus,
    IterationRecord,
    ReviewVerdict,
    TestStatus,
    SyntaxCheckResult,
    TestExecutionResult,
)
from agents.generator import GeneratorAgent
from agents.reviewer import ReviewerAgent
from validation.syntax_checker import check_syntax
from validation.test_runner import run_tests
from validation.static_analyzer import analyze_code
from storage.history_store import HistoryStore
from config.settings import Settings, get_settings
from utils.ollama_client import OllamaClient
from utils.logging_config import setup_logger

logger = setup_logger("WorkflowController")


class WorkflowController:
    """
    Orchestrates the iterative code generation, review, validation, and self-correction loop.
    """

    def __init__(
        self,
        client: Optional[OllamaClient] = None,
        generator: Optional[GeneratorAgent] = None,
        reviewer: Optional[ReviewerAgent] = None,
        history_store: Optional[HistoryStore] = None,
        settings: Optional[Settings] = None,
    ):
        self.settings = settings or get_settings()
        self.client = client or OllamaClient(
            base_url=self.settings.ollama_base_url,
            timeout=self.settings.ollama_timeout_seconds,
        )
        self.generator = generator or GeneratorAgent(
            self.client, model_name=self.settings.generator_model
        )
        self.reviewer = reviewer or ReviewerAgent(
            self.client, model_name=self.settings.reviewer_model
        )
        self.history_store = history_store or HistoryStore()

    def run(
        self,
        task: str,
        constraints: Optional[List[str]] = None,
        test_code: Optional[str] = None,
        max_attempts: Optional[int] = None,
        progress_callback: Optional[Callable[[str, int, str], None]] = None,
    ) -> WorkflowReport:
        """
        Executes the iterative review and self-correction workflow.

        Args:
            task: The coding problem or task specification.
            constraints: Optional technical or functional constraints.
            test_code: Optional pytest assertions for verification.
            max_attempts: Maximum iteration attempts (1 to 5, default 3).
            progress_callback: Optional UI callback (stage, attempt_number, message).

        Returns:
            WorkflowReport with complete iteration audit trail and final code.
        """
        start_time_dt = datetime.now(timezone.utc)
        start_iso = start_time_dt.isoformat()
        start_perf = time.time()

        run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        logger.info(f"Starting workflow run {run_id}")

        def notify(stage: str, attempt: int, msg: str):
            logger.info(f"[{stage}] Attempt {attempt}: {msg}")
            if progress_callback:
                try:
                    progress_callback(stage, attempt, msg)
                except Exception as cb_err:
                    logger.warning(f"Progress callback error: {cb_err}")

        # Task input validation
        if not task or not task.strip():
            error_msg = "Task description cannot be empty."
            logger.error(error_msg)
            report = WorkflowReport(
                run_id=run_id,
                task_description=task or "",
                constraints=constraints or [],
                generator_model=self.generator.model_name,
                reviewer_model=self.reviewer.model_name,
                iterations=[],
                final_status=WorkflowStatus.ERROR,
                stop_reason=error_msg,
                final_code="",
                total_attempts=0,
                max_attempts=max_attempts or self.settings.default_max_retries,
                start_time=start_iso,
                end_time=datetime.now(timezone.utc).isoformat(),
                total_duration_seconds=0.0,
                unresolved_issues=[error_msg],
                test_suite_provided=bool(test_code and test_code.strip()),
                validation_limitations=["Empty task provided."],
            )
            self.history_store.save_report(report)
            return report

        # Resolve attempt limit (constrained between 1 and 5)
        if max_attempts is None:
            max_attempts = self.settings.default_max_retries
        max_attempts = max(1, min(max_attempts, self.settings.max_allowed_retries))

        iterations: List[IterationRecord] = []
        validation_limitations: List[str] = []

        has_tests = bool(test_code and test_code.strip())
        if not has_tests:
            validation_limitations.append(
                "No automated pytest suite was provided. Functional correctness is evaluated "
                "via LLM code review only; runtime execution was NOT RUN."
            )

        if not self.settings.safe_testing_mode and has_tests:
            validation_limitations.append(
                "Execution of untrusted code is restricted by security policy."
            )

        current_code = ""
        last_review_feedback = ""
        last_syntax_error = ""
        last_test_failures = ""
        final_status = WorkflowStatus.RUNNING
        stop_reason = ""
        unresolved_issues: List[str] = []

        notify("INITIALIZING", 0, "Checking model availability and environment...")

        for attempt in range(1, max_attempts + 1):
            iter_start = time.time()
            notify("GENERATING", attempt, f"Generating code (Attempt {attempt}/{max_attempts})...")

            try:
                if attempt == 1:
                    current_code = self.generator.generate_code(task, constraints)
                else:
                    notify("REVISING", attempt, "Applying reviewer and validation corrections...")
                    current_code = self.generator.fix_code(
                        task=task,
                        current_code=current_code,
                        review_feedback=last_review_feedback,
                        syntax_error=last_syntax_error,
                        test_failures=last_test_failures,
                    )
            except Exception as gen_err:
                logger.error(f"Generator agent error on attempt {attempt}: {gen_err}")
                final_status = WorkflowStatus.ERROR
                stop_reason = f"Generator LLM error on attempt {attempt}: {str(gen_err)}"
                notify("ERROR", attempt, stop_reason)
                break

            # Save snapshot of code for this iteration
            self.history_store.save_code_iteration(run_id, attempt, current_code)

            # 1. Syntax Validation
            notify("SYNTAX_CHECK", attempt, "Validating Python syntax via AST...")
            syntax_result = check_syntax(current_code)

            # 2. Static Analysis (Ruff)
            static_result = None
            if self.settings.enable_ruff and syntax_result.is_valid:
                notify("STATIC_ANALYSIS", attempt, "Running Ruff static analysis...")
                static_result = analyze_code(current_code, enabled=True)

            # 3. Test Execution
            test_result = TestExecutionResult(
                status=TestStatus.NOT_RUN,
                total_tests=0,
                passed_tests=0,
                failed_tests=0,
                error_details="Syntax invalid; tests skipped." if not syntax_result.is_valid else (
                    "No test suite provided." if not has_tests else "Test execution skipped."
                ),
                stdout="",
                stderr="",
                duration_seconds=0.0,
                sandbox_mode="none",
            )

            if syntax_result.is_valid and has_tests:
                notify("TESTING", attempt, "Running pytest suite in isolated sandbox...")
                test_result = run_tests(
                    code=current_code,
                    test_code=test_code,
                    timeout_seconds=self.settings.test_timeout_seconds,
                    allow_execution=self.settings.safe_testing_mode,
                )

            # 4. Reviewer Agent
            review_result = None
            if syntax_result.is_valid:
                notify("REVIEWING", attempt, f"Independent reviewer ({self.reviewer.model_name}) inspecting code...")
                try:
                    review_result = self.reviewer.review_code(task, current_code)
                except Exception as rev_err:
                    logger.error(f"Reviewer error on attempt {attempt}: {rev_err}")
                    # Capture reviewer failure explicitly
                    last_review_feedback = f"Reviewer call failed: {rev_err}"
            else:
                last_syntax_error = f"{syntax_result.error_type} at line {syntax_result.line_number}: {syntax_result.error_message}"

            iter_duration = time.time() - iter_start
            iter_record = IterationRecord(
                iteration_number=attempt,
                code=current_code,
                generator_model=self.generator.model_name,
                reviewer_model=self.reviewer.model_name,
                syntax_result=syntax_result,
                test_result=test_result,
                review_result=review_result,
                static_analysis=static_result,
                duration_seconds=round(iter_duration, 3),
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            iterations.append(iter_record)

            # Evaluate Acceptance Criteria
            syntax_passed = syntax_result.is_valid
            tests_passed = (test_result.status == TestStatus.PASSED) if has_tests else True
            reviewer_passed = (
                review_result is not None
                and review_result.verdict == ReviewVerdict.PASS
                and review_result.requirements_met
            )

            # Collect unresolved concerns for audit
            if review_result and review_result.unresolved_concerns:
                unresolved_issues = review_result.unresolved_concerns
            elif review_result and review_result.issues:
                unresolved_issues = [iss.description for iss in review_result.issues]

            # Case: Everything passes!
            if syntax_passed and tests_passed and reviewer_passed:
                if has_tests:
                    final_status = WorkflowStatus.PASSED
                    stop_reason = (
                        f"All acceptance criteria met in attempt {attempt}: Syntax valid, "
                        f"all {test_result.total_tests} pytest tests passed, and reviewer gave PASS verdict."
                    )
                else:
                    final_status = WorkflowStatus.REVIEW_PASSED
                    stop_reason = (
                        f"Reviewer passed code with valid syntax on attempt {attempt}. "
                        "Note: No automated test suite was supplied."
                    )
                notify("SUCCESS", attempt, stop_reason)
                break

            # If not accepted, prepare feedback for next attempt
            if not syntax_passed:
                last_syntax_error = (
                    f"Syntax error ({syntax_result.error_type}): {syntax_result.error_message} "
                    f"at line {syntax_result.line_number}, column {syntax_result.offset}."
                )
            else:
                last_syntax_error = ""

            if has_tests and not tests_passed:
                last_test_failures = (
                    f"Pytest status: {test_result.status.value}.\n"
                    f"Details: {test_result.error_details or ''}\n"
                    f"Stderr: {test_result.stderr[:400]}\n"
                    f"Stdout: {test_result.stdout[:400]}"
                )
            else:
                last_test_failures = ""

            if review_result:
                issues_text = "\n".join(
                    f"- [{iss.severity.value}] {iss.issue_type} (line {iss.line_number or '?'}): {iss.description}. Fix: {iss.suggested_fix or 'N/A'}"
                    for iss in review_result.issues
                )
                last_review_feedback = f"Summary: {review_result.summary}\nIssues:\n{issues_text}"
            else:
                last_review_feedback = ""

            # Check if retry limit reached
            if attempt >= max_attempts:
                if not syntax_passed:
                    final_status = WorkflowStatus.VALIDATION_FAILED
                    stop_reason = f"Retry limit ({max_attempts}) reached. Code has syntax errors."
                elif has_tests and not tests_passed:
                    final_status = WorkflowStatus.VALIDATION_FAILED
                    stop_reason = (
                        f"Retry limit ({max_attempts}) reached. Automated pytest suite failed."
                    )
                elif review_result and review_result.verdict == ReviewVerdict.FAIL:
                    final_status = WorkflowStatus.REVIEW_FAILED
                    stop_reason = (
                        f"Retry limit ({max_attempts}) reached. Reviewer did not pass code."
                    )
                else:
                    final_status = WorkflowStatus.RETRY_LIMIT_REACHED
                    stop_reason = f"Retry limit ({max_attempts}) reached without satisfying acceptance criteria."

                notify("TERMINATED", attempt, stop_reason)
                break

        # Save final code
        if current_code:
            self.history_store.save_final_code(run_id, current_code)

        total_elapsed = time.time() - start_perf
        report = WorkflowReport(
            run_id=run_id,
            task_description=task.strip(),
            constraints=constraints or [],
            generator_model=self.generator.model_name,
            reviewer_model=self.reviewer.model_name,
            iterations=iterations,
            final_status=final_status,
            stop_reason=stop_reason,
            final_code=current_code,
            total_attempts=len(iterations),
            max_attempts=max_attempts,
            start_time=start_iso,
            end_time=datetime.now(timezone.utc).isoformat(),
            total_duration_seconds=round(total_elapsed, 3),
            unresolved_issues=unresolved_issues,
            test_suite_provided=has_tests,
            validation_limitations=validation_limitations,
        )

        self.history_store.save_report(report)
        return report
