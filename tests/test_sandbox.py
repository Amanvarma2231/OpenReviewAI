import pytest
from openreview_ai.sandbox.syntax_checker import check_syntax
from openreview_ai.sandbox.executor import execute_code_safely
from openreview_ai.sandbox.test_runner import run_code_with_tests


def test_syntax_checker_valid():
    code = """
def add(a: int, b: int) -> int:
    \"\"\"Adds two numbers.\"\"\"
    return a + b
"""
    valid, err, meta = check_syntax(code)
    assert valid is True
    assert err is None
    assert meta["num_functions"] == 1
    assert meta["has_docstrings"] is True


def test_syntax_checker_invalid():
    code = "def broken_syntax(x\n    return x"
    valid, err, meta = check_syntax(code)
    assert valid is False
    assert "SyntaxError" in err


def test_executor_success():
    code = "print('Sandbox safe execution successful')"
    res = execute_code_safely(code, timeout_seconds=3)
    assert res.success is True
    assert "Sandbox safe execution successful" in res.stdout
    assert res.exit_code == 0


def test_executor_runtime_error():
    code = "x = 1 / 0"
    res = execute_code_safely(code, timeout_seconds=3)
    assert res.success is False
    assert res.exit_code != 0
    assert "ZeroDivisionError" in res.stderr


def test_executor_timeout_protection():
    # Infinite loop must terminate safely without freezing
    code = "while True:\n    pass"
    res = execute_code_safely(code, timeout_seconds=1)
    assert res.success is False
    assert res.exit_code == -1
    assert "timed out" in res.stderr.lower()


def test_test_runner_pass():
    code = "def multiply(a, b): return a * b"
    tests = "assert multiply(3, 4) == 12"
    res = run_code_with_tests(code, tests, timeout_seconds=3)
    assert res.success is True
    assert res.test_results.get("tests_passed") is True


def test_test_runner_assertion_fail():
    code = "def multiply(a, b): return a + b"
    tests = "assert multiply(3, 4) == 12"
    res = run_code_with_tests(code, tests, timeout_seconds=3)
    assert res.success is False
    assert res.test_results.get("tests_passed") is False
