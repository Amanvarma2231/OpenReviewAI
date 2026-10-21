"""
OpenReview AI - Code Generator Agent
===================================
Produces and iteratively corrects Python source code using a local LLM.
Preserves user requirements, handles edge cases, and normalizes output safely.
"""

import re
import ast
from typing import List, Optional, Dict, Any
from utils.ollama_client import OllamaClient
from utils.logging_config import setup_logger

logger = setup_logger("GeneratorAgent")


class GeneratorAgent:
    """
    Independent AI agent responsible for generating Python source code
    and revising it based on reviewer feedback and automated validation errors.
    """

    def __init__(self, client: OllamaClient, model_name: str = "qwen2.5-coder:3b"):
        self.client = client
        self.model_name = model_name

    def set_model(self, model_name: str) -> None:
        """Dynamically update model name."""
        self.model_name = model_name

    def generate_code(self, task: str, constraints: Optional[List[str]] = None) -> str:
        """
        Generates initial Python code for a given task.
        """
        if not task or not task.strip():
            raise ValueError("Task description cannot be empty.")

        constraints_text = ""
        if constraints:
            constraints_text = "\nTechnical Constraints:\n" + "\n".join(f"- {c}" for c in constraints)

        system_prompt = (
            "You are an expert Python software engineer. Your responsibility is to write clean, "
            "idiomatic, robust, and complete Python code that strictly satisfies the user's requirements.\n"
            "Rules:\n"
            "1. Output ONLY complete Python code inside a single ```python ... ``` block.\n"
            "2. Do not leave placeholders, TODOs, or incomplete functions.\n"
            "3. Handle boundary conditions and edge cases gracefully.\n"
            "4. Include concise docstrings and type annotations.\n"
            "5. Avoid unnecessary heavy external libraries; prefer standard library where possible.\n"
            "6. Never mix explanatory conversational text outside the code block."
        )

        user_prompt = f"Task Description:\n{task.strip()}\n{constraints_text}\n\nProvide the complete Python implementation:"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        logger.info(f"Generating initial code using model '{self.model_name}'...")
        raw_response = self.client.chat(
            model=self.model_name,
            messages=messages,
            temperature=0.2,
        )

        return self.normalize_generated_code(raw_response)

    def fix_code(
        self,
        task: str,
        current_code: str,
        review_feedback: Optional[str] = None,
        syntax_error: Optional[str] = None,
        test_failures: Optional[str] = None,
    ) -> str:
        """
        Generates a corrected version of the code based on reviewer feedback,
        syntax errors, or automated test failures.
        """
        system_prompt = (
            "You are an expert Python software engineer. You are revising code that failed review or automated validation.\n"
            "Rules:\n"
            "1. Return the ENTIRE revised Python code, complete and functional, inside a single ```python ... ``` block.\n"
            "2. Fix all reported defects, syntax errors, and failed test cases.\n"
            "3. Do not drop existing features or functionality to bypass tests.\n"
            "4. Output ONLY the code block without conversational filler."
        )

        issues_summary = []
        if syntax_error:
            issues_summary.append(f"### SYNTAX VALIDATION ERROR:\n{syntax_error.strip()}")
        if test_failures:
            issues_summary.append(f"### AUTOMATED TEST FAILURES:\n{test_failures.strip()}")
        if review_feedback:
            issues_summary.append(f"### CODE REVIEWER FEEDBACK:\n{review_feedback.strip()}")

        feedback_block = "\n\n".join(issues_summary)

        user_prompt = (
            f"Original Task:\n{task.strip()}\n\n"
            f"Current Code that Needs Correction:\n```python\n{current_code.strip()}\n```\n\n"
            f"Validation & Review Issues to Fix:\n{feedback_block}\n\n"
            f"Please provide the complete, corrected Python code:"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        logger.info(f"Fixing code using model '{self.model_name}'...")
        raw_response = self.client.chat(
            model=self.model_name,
            messages=messages,
            temperature=0.1,
        )

        return self.normalize_generated_code(raw_response)

    @staticmethod
    def normalize_generated_code(response: str) -> str:
        """
        Safely extracts pure Python code from model output.
        Handles markdown fences, extraneous explanations, and validates basic structure.
        """
        if not response or not response.strip():
            return ""

        text = response.strip()

        # Match ```python ... ``` or ```py ... ```
        pattern_py = r"```(?:python|py)\s*\n(.*?)```"
        matches = re.findall(pattern_py, text, flags=re.DOTALL | re.IGNORECASE)
        if matches:
            # Pick the largest code block if multiple exist
            best_code = max(matches, key=len).strip()
            return best_code

        # Fallback: Match any generic markdown fence ``` ... ```
        pattern_generic = r"```\s*\n(.*?)```"
        matches_generic = re.findall(pattern_generic, text, flags=re.DOTALL)
        if matches_generic:
            best_code = max(matches_generic, key=len).strip()
            return best_code

        # If no markdown fences found, check if whole text is parseable Python
        try:
            ast.parse(text)
            return text
        except SyntaxError:
            pass

        # Try stripping leading/trailing non-code lines (lines starting with Here is..., Note:, etc.)
        lines = text.splitlines()
        code_lines = []
        started = False
        for line in lines:
            stripped = line.strip()
            if not started:
                # Common Python starter keywords or imports
                if (
                    stripped.startswith("def ")
                    or stripped.startswith("class ")
                    or stripped.startswith("import ")
                    or stripped.startswith("from ")
                    or stripped.startswith("#")
                    or stripped.startswith('"""')
                    or stripped.startswith("'''")
                ):
                    started = True
                    code_lines.append(line)
            else:
                code_lines.append(line)

        if code_lines:
            candidate = "\n".join(code_lines).strip()
            try:
                ast.parse(candidate)
                return candidate
            except SyntaxError:
                pass

        return text
