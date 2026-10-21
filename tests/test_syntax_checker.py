"""
Unit Tests for Syntax Checker
=============================
Tests syntax validation via ast.parse for valid, invalid, and empty Python snippets.
"""

import pytest
from validation.syntax_checker import check_syntax


def test_valid_syntax():
    code = (
        "def add(a: int, b: int) -> int:\n"
        "    \"\"\"Add two numbers.\"\"\"\n"
        "    return a + b\n"
    )
    result = check_syntax(code)
    assert result.is_valid is True
    assert result.error_message is None
    assert result.line_number is None


def test_invalid_syntax_missing_colon():
    code = (
        "def multiply(a, b)\n"
        "    return a * b\n"
    )
    result = check_syntax(code)
    assert result.is_valid is False
    assert result.line_number == 1
    assert result.error_type == "SyntaxError"
    assert result.error_message is not None


def test_indentation_error():
    code = (
        "def foo():\n"
        "return 42\n"
    )
    result = check_syntax(code)
    assert result.is_valid is False
    assert result.error_type == "IndentationError"


def test_empty_code():
    result = check_syntax("")
    assert result.is_valid is False
    assert result.error_type == "EmptyCodeError"

    result_spaces = check_syntax("   \n\t  ")
    assert result_spaces.is_valid is False
