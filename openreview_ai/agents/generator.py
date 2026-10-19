from typing import Optional, List, Tuple
from openreview_ai.agents.base import BaseAgent
from openreview_ai.providers.base import BaseLLMProvider
from openreview_ai.schema import ExecutionResult, ReviewFeedback
from openreview_ai.utils.prompt_templates import (
    GENERATOR_INITIAL_SYSTEM,
    GENERATOR_INITIAL_USER,
    GENERATOR_FIX_SYSTEM,
    GENERATOR_FIX_USER
)


class CodeGeneratorAgent(BaseAgent):
    """
    LLM 1: Code Generator & Bug Fixer Agent.
    Generates initial implementation and refactors/fixes code iteratively based on reviewer feedback.
    """

    def __init__(self, provider: BaseLLMProvider, role_name: str = "Generator (LLM 1)"):
        super().__init__(role_name, provider)

    def generate_initial(
        self,
        task_prompt: str,
        target_language: str = "python",
        unit_tests: Optional[str] = None,
        temperature: float = 0.2
    ) -> Tuple[str, str, str]:
        """
        Generates the first version of code.
        Returns: (code, explanation, raw_response)
        """
        user_prompt = GENERATOR_INITIAL_USER.format(
            task_prompt=task_prompt,
            target_language=target_language,
            unit_tests=unit_tests or "None specified."
        )

        raw_response = self.provider.generate(
            system_prompt=GENERATOR_INITIAL_SYSTEM,
            user_prompt=user_prompt,
            temperature=temperature
        )

        code = self.extract_code_block(raw_response, target_language)
        
        # Explanation is text outside code blocks
        clean_explanation = raw_response.replace(code, "").replace("```", "").strip()
        if not clean_explanation:
            clean_explanation = "Initial code implementation generated."

        return code, clean_explanation, raw_response

    def fix_code(
        self,
        task_prompt: str,
        current_code: str,
        target_language: str = "python",
        execution_result: Optional[ExecutionResult] = None,
        reviews: Optional[List[ReviewFeedback]] = None,
        temperature: float = 0.2
    ) -> Tuple[str, str, str]:
        """
        Refactors and fixes code based on reviewer feedback and execution/test results.
        Returns: (fixed_code, fix_summary, raw_response)
        """
        # Format execution output
        if execution_result:
            if execution_result.success:
                exec_summary = "Code executed cleanly without runtime exceptions."
            else:
                exec_summary = f"Execution / Test Failures:\nExit Code: {execution_result.exit_code}\nStderr:\n{execution_result.stderr}"
                if execution_result.syntax_error:
                    exec_summary += f"\nSyntax Error: {execution_result.syntax_error}"
        else:
            exec_summary = "No execution output available."

        # Format reviewer feedback
        feedback_parts = []
        if reviews:
            for rev in reviews:
                feedback_parts.append(f"Reviewer [{rev.reviewer_name} - {rev.reviewer_model}]: {rev.summary}")
                for bug in rev.bugs:
                    line_str = f"Line {bug.line_number}: " if bug.line_number else ""
                    feedback_parts.append(f"  - [{bug.severity}] [{bug.category}] {line_str}{bug.description} -> Suggested fix: {bug.suggested_fix}")
        feedback_text = "\n".join(feedback_parts) if feedback_parts else "No specific reviewer feedback."

        user_prompt = GENERATOR_FIX_USER.format(
            task_prompt=task_prompt,
            current_code=current_code,
            target_language=target_language,
            execution_summary=exec_summary,
            reviewer_feedback=feedback_text
        )

        raw_response = self.provider.generate(
            system_prompt=GENERATOR_FIX_SYSTEM,
            user_prompt=user_prompt,
            temperature=temperature
        )

        fixed_code = self.extract_code_block(raw_response, target_language)
        
        # Extract fix summary
        clean_summary = raw_response.replace(fixed_code, "").replace("```", "").strip()
        if not clean_summary:
            clean_summary = "Applied fixes addressing reviewer feedback and test results."

        return fixed_code, clean_summary, raw_response
