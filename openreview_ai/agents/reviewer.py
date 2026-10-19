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
        """Parses structured JSON review with robust fallback handling."""
        data = self.extract_json_block(raw_response)
        
        # If automated execution failed, code CANNOT be approved!
        execution_has_crashed = execution_result is not None and not execution_result.success

        if data and isinstance(data, dict):
            has_bugs = data.get("has_bugs", False) or execution_has_crashed
            status_str = data.get("status", "CHANGES_REQUESTED" if has_bugs else "APPROVED")
            
            status = ReviewStatus.CHANGES_REQUESTED if has_bugs else ReviewStatus.APPROVED
            summary = data.get("summary", "Review complete.")
            score = int(data.get("overall_score", 5 if has_bugs else 9))
            
            bugs: List[BugItem] = []
            for item in data.get("bugs", []):
                try:
                    category = BugCategory(item.get("category", "LOGIC").upper())
                except ValueError:
                    category = BugCategory.LOGIC
                    
                try:
                    severity = SeverityLevel(item.get("severity", "MAJOR").upper())
                except ValueError:
                    severity = SeverityLevel.MAJOR
                    
                bugs.append(BugItem(
                    line_number=item.get("line_number"),
                    category=category,
                    severity=severity,
                    description=item.get("description", "Unspecified issue"),
                    suggested_fix=item.get("suggested_fix", "Refactor code")
                ))

            # If execution crashed but LLM didn't list it as bug, inject it
            if execution_has_crashed and not bugs:
                bugs.append(BugItem(
                    line_number=None,
                    category=BugCategory.RUNTIME,
                    severity=SeverityLevel.CRITICAL,
                    description=f"Runtime execution failure: {execution_result.stderr.strip()[:200]}",
                    suggested_fix="Fix runtime crash and ensure code runs without errors."
                ))

            return ReviewFeedback(
                reviewer_name=self.role_name,
                reviewer_model=self.model_name,
                status=status,
                has_bugs=has_bugs or len(bugs) > 0,
                summary=summary,
                bugs=bugs,
                overall_score=score,
                raw_response=raw_response
            )

        # Fallback when model output lacks standard JSON
        has_bugs = "bug" in raw_response.lower() or "error" in raw_response.lower() or execution_has_crashed
        fallback_bugs = []
        if has_bugs:
            fallback_bugs.append(BugItem(
                line_number=None,
                category=BugCategory.LOGIC,
                severity=SeverityLevel.MAJOR,
                description=raw_response[:300].strip(),
                suggested_fix="Address reported issues."
            ))

        return ReviewFeedback(
            reviewer_name=self.role_name,
            reviewer_model=self.model_name,
            status=ReviewStatus.CHANGES_REQUESTED if has_bugs else ReviewStatus.APPROVED,
            has_bugs=has_bugs,
            summary=raw_response[:200] if raw_response else "Review completed.",
            bugs=fallback_bugs,
            overall_score=5 if has_bugs else 8,
            raw_response=raw_response
        )
