"""
Unit Tests for Reviewer Agent & JSON Parser
===========================================
Validates that review outputs are strictly parsed and malformed output is never marked PASS.
"""

import json
from agents.reviewer import ReviewerAgent
from models.schemas import ReviewVerdict, IssueSeverity
from utils.ollama_client import OllamaClient


def test_valid_json_review_parsing():
    client = OllamaClient(mock_mode=True)
    reviewer = ReviewerAgent(client=client)

    raw_json = json.dumps({
        "verdict": "PASS",
        "summary": "Implementation is clean and efficient.",
        "requirements_met": True,
        "issues": [],
        "suggested_fixes": ["Add type hints"],
        "unresolved_concerns": []
    })

    result = reviewer.parse_review_response(raw_json)
    assert result.verdict == ReviewVerdict.PASS
    assert result.requirements_met is True
    assert len(result.issues) == 0
    assert "clean" in result.summary


def test_markdown_wrapped_json():
    client = OllamaClient(mock_mode=True)
    reviewer = ReviewerAgent(client=client)

    raw_response = (
        "Here is my code review analysis:\n"
        "```json\n"
        "{\n"
        '  "verdict": "FAIL",\n'
        '  "summary": "Division by zero is not handled.",\n'
        '  "requirements_met": false,\n'
        '  "issues": [\n'
        "    {\n"
        '      "issue_type": "logic",\n'
        '      "severity": "HIGH",\n'
        '      "line_number": 4,\n'
        '      "description": "Zero denominator raises ZeroDivisionError",\n'
        '      "suggested_fix": "Add check: if b == 0: raise ValueError()"\n'
        "    }\n"
        "  ],\n"
        '  "suggested_fixes": ["Check for zero denominator"],\n'
        '  "unresolved_concerns": ["Negative division rounding"]\n'
        "}\n"
        "```\n"
        "Hope this helps!"
    )

    result = reviewer.parse_review_response(raw_response)
    assert result.verdict == ReviewVerdict.FAIL
    assert len(result.issues) == 1
    assert result.issues[0].severity == IssueSeverity.HIGH
    assert result.issues[0].line_number == 4
    assert result.issues[0].issue_type == "logic"
    assert not result.requirements_met


def test_malformed_reviewer_response_fails_explicitly():
    client = OllamaClient(mock_mode=True)
    reviewer = ReviewerAgent(client=client)

    # Malformed text that cannot be parsed as JSON
    malformed = "I checked the code and it looks okay, but here is some random text without JSON."
    result = reviewer.parse_review_response(malformed)

    assert result.verdict == ReviewVerdict.FAIL
    assert result.requirements_met is False
    assert len(result.issues) > 0
    assert result.issues[0].issue_type == "parsing_error"
    assert "parse failure" in result.summary.lower()


def test_contradictory_pass_with_issues_is_overridden_to_fail():
    client = OllamaClient(mock_mode=True)
    reviewer = ReviewerAgent(client=client)

    contradictory_json = json.dumps({
        "verdict": "PASS",
        "summary": "Good code.",
        "requirements_met": True,
        "issues": [
            {
                "issue_type": "security",
                "severity": "CRITICAL",
                "line_number": 2,
                "description": "SQL injection vulnerability",
                "suggested_fix": "Use parameterized queries"
            }
        ],
        "suggested_fixes": [],
        "unresolved_concerns": []
    })

    result = reviewer.parse_review_response(contradictory_json)
    # Must be overridden to FAIL because critical issues were detected!
    assert result.verdict == ReviewVerdict.FAIL


def test_empty_reviewer_response():
    client = OllamaClient(mock_mode=True)
    reviewer = ReviewerAgent(client=client)

    result = reviewer.parse_review_response("")
    assert result.verdict == ReviewVerdict.FAIL
    assert result.requirements_met is False
