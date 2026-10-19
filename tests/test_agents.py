import pytest
from openreview_ai.providers.mock_provider import MockSimulationProvider
from openreview_ai.agents.generator import CodeGeneratorAgent
from openreview_ai.agents.reviewer import CodeReviewerAgent
from openreview_ai.agents.validator import ValidatorAgent
from openreview_ai.schema import ReviewStatus, BugCategory


def test_generator_agent_initial():
    provider = MockSimulationProvider("qwen2.5:0.5b")
    agent = CodeGeneratorAgent(provider)
    code, explanation, raw = agent.generate_initial("Write a palindrome checker")
    assert "is_palindrome" in code
    assert len(explanation) > 0


def test_reviewer_agent_flags_bugs():
    provider = MockSimulationProvider("mistral:latest")
    reviewer = CodeReviewerAgent(provider)
    code_with_bugs = "def is_palindrome(s): return s == s[::-1]"
    feedback = reviewer.review_code("Write a palindrome checker", code_with_bugs)
    assert feedback.has_bugs is True
    assert feedback.status == ReviewStatus.CHANGES_REQUESTED
    assert len(feedback.bugs) > 0


def test_reviewer_agent_approves_fixed():
    provider = MockSimulationProvider("mistral:latest")
    reviewer = CodeReviewerAgent(provider)
    fixed_code = """
import re
def is_palindrome(s: str) -> bool:
    if s is None:
        return False
    cleaned = re.sub(r'[^a-zA-Z0-9]', '', s).lower()
    return cleaned == cleaned[::-1]
"""
    feedback = reviewer.review_code("Write a palindrome checker", fixed_code)
    assert feedback.has_bugs is False
    assert feedback.status == ReviewStatus.APPROVED


def test_validator_agent():
    provider = MockSimulationProvider("deepseek-coder:1.3b")
    validator = ValidatorAgent(provider)
    val_feedback = validator.validate_code("Task", "def test(): pass")
    assert val_feedback.reviewer_name == "Validator (LLM 3)"
