from typing import Optional, List
from openreview_ai.agents.base import BaseAgent
from openreview_ai.providers.base import BaseLLMProvider
from openreview_ai.schema import (
    ReviewFeedback,
    ReviewStatus,
    BugItem,
    BugCategory,
    SeverityLevel
)
from openreview_ai.utils.prompt_templates import VALIDATOR_SYSTEM, VALIDATOR_USER


class ValidatorAgent(BaseAgent):
    """
    LLM 3: Security & Consensus Arbiter Agent.
    Validates code against security vulnerabilities and checks agreement with LLM 2.
    """

    def __init__(self, provider: BaseLLMProvider, role_name: str = "Validator (LLM 3)"):
        super().__init__(role_name, provider)

    def validate_code(
        self,
        task_prompt: str,
        current_code: str,
        target_language: str = "python",
        primary_review: Optional[ReviewFeedback] = None,
        temperature: float = 0.1
    ) -> ReviewFeedback:
        """
        Executes secondary validation / security audit.
        """
        reviewer_summary = (
            f"Status: {primary_review.status.value}. Summary: {primary_review.summary}"
            if primary_review
            else "None provided."
        )
        user_prompt = VALIDATOR_USER.format(
            task_prompt=task_prompt,
            current_code=current_code,
            target_language=target_language,
            reviewer_summary=reviewer_summary
        )

        raw_response = self.provider.generate(
            system_prompt=VALIDATOR_SYSTEM,
            user_prompt=user_prompt,
            temperature=temperature
        )

        return self._parse_validator_response(raw_response)

    def _parse_validator_response(self, raw_response: str) -> ReviewFeedback:
        data = self.extract_json_block(raw_response)
        if data and isinstance(data, dict):
            has_bugs = data.get("has_bugs", False)
            status = ReviewStatus.CHANGES_REQUESTED if has_bugs else ReviewStatus.APPROVED
            summary = data.get("summary", "Validation complete.")
            score = int(data.get("overall_score", 6 if has_bugs else 9))
            
            bugs: List[BugItem] = []
            for item in data.get("bugs", []):
                try:
                    category = BugCategory(item.get("category", "SECURITY").upper())
                except ValueError:
                    category = BugCategory.SECURITY
                try:
                    severity = SeverityLevel(item.get("severity", "MAJOR").upper())
                except ValueError:
                    severity = SeverityLevel.MAJOR
                bugs.append(BugItem(
                    line_number=item.get("line_number"),
                    category=category,
                    severity=severity,
                    description=item.get("description", "Security or edge-case finding"),
                    suggested_fix=item.get("suggested_fix", "Harden implementation")
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

        # Fallback
        has_bugs = "vulnerability" in raw_response.lower() or "security issue" in raw_response.lower()
        return ReviewFeedback(
            reviewer_name=self.role_name,
            reviewer_model=self.model_name,
            status=ReviewStatus.CHANGES_REQUESTED if has_bugs else ReviewStatus.APPROVED,
            has_bugs=has_bugs,
            summary=raw_response[:200] if raw_response else "Validation passed.",
            bugs=[],
            overall_score=5 if has_bugs else 9,
            raw_response=raw_response
        )
