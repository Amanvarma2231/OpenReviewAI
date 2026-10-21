"""
OpenReview AI - Code Reviewer Agent
===================================
Independently reviews generated Python source code.
Assesses correctness, logic errors, edge cases, security, and maintainability.
Produces strictly structured JSON reviews parsed into Pydantic models.
"""

import json
import re
from typing import Dict, Any, Optional
from models.schemas import (
    ReviewResult,
    ReviewVerdict,
    ReviewIssue,
    IssueSeverity,
)
from utils.ollama_client import OllamaClient
from utils.logging_config import setup_logger

logger = setup_logger("ReviewerAgent")


class ReviewerAgent:
    """
    Independent AI agent that evaluates code without executing it.
    Validates against requirements, security principles, and quality standards.
    """

    def __init__(self, client: OllamaClient, model_name: str = "deepseek-coder:1.3b"):
        self.client = client
        self.model_name = model_name

    def set_model(self, model_name: str) -> None:
        """Dynamically update model name."""
        self.model_name = model_name

    def review_code(self, task: str, code: str) -> ReviewResult:
        """
        Sends code to the reviewer LLM and returns a structured ReviewResult.
        """
        system_prompt = (
            "You are an adversarial Senior Principal Software Engineer and Security Code Reviewer.\n"
            "Your job is to thoroughly inspect Python code for correctness, bugs, edge cases, "
            "security vulnerabilities, runtime exceptions, and conformance to the original task.\n"
            "Be critical and meticulous.\n\n"
            "CRITICAL INSTRUCTIONS:\n"
            "1. You MUST respond ONLY with a valid JSON object matching the schema below.\n"
            "2. Do NOT wrap JSON in conversational commentary. Do not prefix with 'Here is your review'.\n"
            "3. If any bug, logic flaw, missing requirement, or edge-case failure exists, verdict MUST be 'FAIL'.\n"
            "4. Only assign 'PASS' if the code is completely correct, safe, robust, and meets all criteria.\n\n"
            "JSON SCHEMA:\n"
            "{\n"
            '  "verdict": "PASS" | "FAIL",\n'
            '  "summary": "Brief overall evaluation",\n'
            '  "requirements_met": true | false,\n'
            '  "issues": [\n'
            "    {\n"
            '      "issue_type": "logic" | "syntax" | "security" | "edge_case" | "maintainability" | "requirements",\n'
            '      "severity": "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "INFO",\n'
            '      "line_number": 12,\n'
            '      "description": "Specific flaw description",\n'
            '      "suggested_fix": "Concrete fix instruction"\n'
            "    }\n"
            "  ],\n"
            '  "suggested_fixes": ["Summary fix 1", "Summary fix 2"],\n'
            '  "unresolved_concerns": ["Any potential residual concern"]\n'
            "}"
        )

        user_prompt = (
            f"Original Task Requirement:\n{task.strip()}\n\n"
            f"Python Code Under Review:\n```python\n{code.strip()}\n```\n\n"
            "Output your strict JSON review:"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        logger.info(f"Submitting code to Reviewer model '{self.model_name}'...")
        raw_response = self.client.chat(
            model=self.model_name,
            messages=messages,
            temperature=0.1,
            json_format=True,
        )

        return self.parse_review_response(raw_response)

    def parse_review_response(self, response: str) -> ReviewResult:
        """
        Parses and validates the raw JSON response from the reviewer model.
        Never silently assumes PASS on malformed output.
        """
        if not response or not response.strip():
            logger.error("Reviewer returned an empty response.")
            return ReviewResult(
                verdict=ReviewVerdict.FAIL,
                summary="Reviewer error: Empty response received from reviewer model.",
                issues=[
                    ReviewIssue(
                        issue_type="system",
                        severity=IssueSeverity.HIGH,
                        description="Reviewer LLM returned an empty output.",
                        suggested_fix="Retry review request with valid reviewer model.",
                    )
                ],
                requirements_met=False,
                unresolved_concerns=["Empty review output from LLM"],
                raw_response=response,
            )

        text = response.strip()

        # Extract JSON if enclosed in markdown code fences
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match:
            json_str = match.group(1)
        else:
            # Look for the outermost braces
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                json_str = text[start : end + 1]
            else:
                json_str = text

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as err:
            logger.warning(f"Failed to parse reviewer JSON response: {err}")
            # Try gentle repair for common trailing commas or single quotes
            repaired_str = re.sub(r",\s*([\]}])", r"\1", json_str)
            try:
                data = json.loads(repaired_str)
            except Exception:
                # If still invalid, fail explicitly. NEVER default to PASS!
                return ReviewResult(
                    verdict=ReviewVerdict.FAIL,
                    summary=f"Reviewer parse failure: Output was not valid JSON ({err}).",
                    issues=[
                        ReviewIssue(
                            issue_type="parsing_error",
                            severity=IssueSeverity.HIGH,
                            description=f"Reviewer response could not be parsed as JSON: {text[:200]}...",
                            suggested_fix="Ensure reviewer model supports structured JSON output.",
                        )
                    ],
                    requirements_met=False,
                    unresolved_concerns=["Malformed reviewer output received."],
                    raw_response=response,
                )

        # Normalize verdict
        raw_verdict = str(data.get("verdict", "FAIL")).strip().upper()
        verdict = ReviewVerdict.PASS if raw_verdict == "PASS" else ReviewVerdict.FAIL

        # Parse issues
        issues_list = []
        raw_issues = data.get("issues", [])
        if isinstance(raw_issues, list):
            for item in raw_issues:
                if isinstance(item, dict):
                    # Severity normalization
                    raw_sev = str(item.get("severity", "MEDIUM")).upper()
                    try:
                        severity = IssueSeverity(raw_sev)
                    except ValueError:
                        severity = IssueSeverity.MEDIUM

                    line_num = item.get("line_number")
                    if line_num is not None:
                        try:
                            line_num = int(line_num)
                        except (ValueError, TypeError):
                            line_num = None

                    issues_list.append(
                        ReviewIssue(
                            issue_type=str(item.get("issue_type", "logic")),
                            severity=severity,
                            line_number=line_num,
                            description=str(item.get("description", "Unspecified issue")),
                            suggested_fix=item.get("suggested_fix"),
                        )
                    )

        # If issues exist, verdict cannot be PASS
        if issues_list and verdict == ReviewVerdict.PASS:
            logger.info("Overriding contradictory PASS verdict: Issues were listed in review.")
            verdict = ReviewVerdict.FAIL

        suggested_fixes = [str(x) for x in data.get("suggested_fixes", []) if x]
        unresolved_concerns = [str(x) for x in data.get("unresolved_concerns", []) if x]
        requirements_met = bool(data.get("requirements_met", verdict == ReviewVerdict.PASS))

        return ReviewResult(
            verdict=verdict,
            summary=str(data.get("summary", "Review completed.")),
            issues=issues_list,
            suggested_fixes=suggested_fixes,
            requirements_met=requirements_met,
            unresolved_concerns=unresolved_concerns,
            raw_response=response,
        )
