from typing import Optional, List
from openreview_ai.agents.base import BaseAgent
from openreview_ai.providers.base import BaseLLMProvider
from openreview_ai.schema import (
    ReviewFeedback,
    ReviewStatus,
    BugItem,
    BugCategory,
    SeverityLevel,
    ExecutionResult
)
from openreview_ai.utils.prompt_templates import REVIEWER_SYSTEM, REVIEWER_USER


class CodeReviewerAgent(BaseAgent):
    """
    LLM 2: Principal Code Reviewer & Inspector Agent.
    Performs static and semantic inspection, flagging edge cases, syntax, and logic errors.
    """

    def __init__(self, provider: BaseLLMProvider, role_name: str = "Reviewer (LLM 2)"):
        super().__init__(role_name, provider)

    def review_code(
        self,
        task_prompt: str,
        current_code: str,
        target_language: str = "python",
        execution_result: Optional[ExecutionResult] = None,
        temperature: float = 0.1
    ) -> ReviewFeedback:
        """
        Reviews code and outputs structured ReviewFeedback.
        """
        if execution_result:
            if execution_result.success:
                exec_summary = "Automated execution passed without errors."
            else:
                exec_summary = f"Execution error detected:\nExit code: {execution_result.exit_code}\nStderr:\n{execution_result.stderr}"
                if execution_result.syntax_error:
                    exec_summary += f"\nSyntax Error: {execution_result.syntax_error}"
        else:
            exec_summary = "No execution output available."

        user_prompt = REVIEWER_USER.format(
            task_prompt=task_prompt,
            current_code=current_code,
            target_language=target_language,
            execution_summary=exec_summary
        )

        raw_response = self.provider.generate(
            system_prompt=REVIEWER_SYSTEM,
            user_prompt=user_prompt,
            temperature=temperature
        )

        return self._parse_review_response(raw_response, execution_result)

    def _parse_review_response(
        self,
        raw_response: str,
        execution_result: Optional[ExecutionResult]
    ) -> ReviewFeedback:
        """Parses structured JSON review with robust fallback handling and strict overrides."""
        data = self.extract_json_block(raw_response)
        
        # If automated execution failed, code CANNOT be approved!
        execution_has_crashed = execution_result is not None and not execution_result.success

        if data and isinstance(data, dict):
            # Support both section 7 format ("verdict", "issues") and legacy format ("status", "bugs")
            raw_issues = data.get("issues") if "issues" in data else data.get("bugs", [])
            if not isinstance(raw_issues, list):
                raw_issues = []

            verdict_val = str(data.get("verdict", "")).strip().upper()
            explicit_fail = (verdict_val == "FAIL") or (data.get("has_bugs") is True)

            bugs: List[BugItem] = []
            for item in raw_issues:
                if not isinstance(item, dict):
                    continue
                cat_raw = str(item.get("category") or item.get("issue_type", "LOGIC")).upper()
                try:
                    category = BugCategory(cat_raw)
                except ValueError:
                    if "SEC" in cat_raw:
                        category = BugCategory.SECURITY
                    elif "SYN" in cat_raw:
                        category = BugCategory.SYNTAX
                    elif "RUN" in cat_raw:
                        category = BugCategory.RUNTIME
                    elif "EDGE" in cat_raw:
                        category = BugCategory.EDGE_CASE
                    elif "PERF" in cat_raw:
                        category = BugCategory.PERFORMANCE
                    elif "MAINT" in cat_raw:
                        category = BugCategory.MAINTAINABILITY
                    elif "CORR" in cat_raw:
                        category = BugCategory.CORRECTNESS
                    else:
                        category = BugCategory.LOGIC
                    
                sev_raw = str(item.get("severity", "MAJOR")).upper()
                try:
                    severity = SeverityLevel(sev_raw)
                except ValueError:
                    if "CRIT" in sev_raw:
                        severity = SeverityLevel.CRITICAL
                    elif "HIGH" in sev_raw:
                        severity = SeverityLevel.HIGH
                    elif "MED" in sev_raw:
                        severity = SeverityLevel.MEDIUM
                    elif "LOW" in sev_raw:
                        severity = SeverityLevel.LOW
                    elif "INFO" in sev_raw or "SUGG" in sev_raw:
                        severity = SeverityLevel.SUGGESTION
                    else:
                        severity = SeverityLevel.MAJOR
                    
                conf_val = item.get("confidence", 1.0)
                try:
                    conf = float(conf_val)
                except (ValueError, TypeError):
                    conf = 1.0

                line_num = item.get("line_number") or item.get("line")
                try:
                    line_num = int(line_num) if line_num is not None else None
                except (ValueError, TypeError):
                    line_num = None

                bugs.append(BugItem(
                    file=item.get("file"),
                    line_number=line_num,
                    category=category,
                    severity=severity,
                    description=item.get("description") or item.get("message", "Unspecified issue"),
                    suggested_fix=item.get("suggested_fix") or item.get("fix", "Refactor code"),
                    confidence=conf
                ))

            # If execution crashed, guarantee it is represented as a critical bug
            if execution_has_crashed:
                crash_msg = (execution_result.stderr.strip() or execution_result.stdout.strip())[:250] if execution_result else "Execution failed"
                bugs.append(BugItem(
                    line_number=None,
                    category=BugCategory.RUNTIME,
                    severity=SeverityLevel.CRITICAL,
                    description=f"Runtime execution failure: {crash_msg}",
                    suggested_fix="Fix runtime crash and ensure code executes cleanly with exit code 0."
                ))

            # Contradiction guard: If verdict said PASS but there are bugs or crashes, override to FAIL
            has_bugs = explicit_fail or len(bugs) > 0 or execution_has_crashed
            status = ReviewStatus.CHANGES_REQUESTED if has_bugs else ReviewStatus.APPROVED
            verdict = "FAIL" if has_bugs else "PASS"
            summary = data.get("summary", "Review complete.")
            score = int(data.get("overall_score", 5 if has_bugs else 9))

            reqs_met_raw = data.get("requirements_met")
            if isinstance(reqs_met_raw, list):
                reqs_met = [str(x) for x in reqs_met_raw]
            elif reqs_met_raw is True:
                reqs_met = ["All requirements met"]
            else:
                reqs_met = []

            unresolved_raw = data.get("unresolved_concerns")
            unresolved = [str(x) for x in unresolved_raw] if isinstance(unresolved_raw, list) else []

            return ReviewFeedback(
                reviewer_name=self.role_name,
                reviewer_model=self.model_name,
                status=status,
                has_bugs=has_bugs,
                summary=summary,
                verdict=verdict,
                bugs=bugs,
                overall_score=score,
                requirements_met=reqs_met,
                unresolved_concerns=unresolved,
                raw_response=raw_response
            )

        # Fallback when model output lacks standard JSON
        has_bugs = "bug" in raw_response.lower() or "error" in raw_response.lower() or execution_has_crashed
        fallback_bugs = []
        if has_bugs:
            fallback_bugs.append(BugItem(
                line_number=None,
                category=BugCategory.RUNTIME if execution_has_crashed else BugCategory.LOGIC,
                severity=SeverityLevel.CRITICAL if execution_has_crashed else SeverityLevel.MAJOR,
                description=raw_response[:300].strip() or "Defect detected in review response",
                suggested_fix="Address reported issues."
            ))

        return ReviewFeedback(
            reviewer_name=self.role_name,
            reviewer_model=self.model_name,
            status=ReviewStatus.CHANGES_REQUESTED if has_bugs else ReviewStatus.APPROVED,
            has_bugs=has_bugs,
            summary=raw_response[:200] if raw_response else "Review completed.",
            verdict="FAIL" if has_bugs else "PASS",
            bugs=fallback_bugs,
            overall_score=5 if has_bugs else 8,
            requirements_met=[],
            unresolved_concerns=["Raw response lacked structured JSON schema"],
            raw_response=raw_response
        )
