import re
import json
from typing import Dict, Any, List
from openreview_ai.providers.base import BaseLLMProvider


class MockSimulationProvider(BaseLLMProvider):
    """
    Intelligent simulation provider for offline demos, CI/CD, and evaluation.
    Demonstrates the full multi-LLM debate, review, and iterative correction cycle.
    """

    def __init__(self, model_name: str = "mock-model", **kwargs):
        super().__init__(model_name, **kwargs)
        self.call_history: List[Dict[str, Any]] = []

    def check_health(self) -> bool:
        return True

    def generate(self, system_prompt: str, user_prompt: str, temperature: float = 0.2) -> str:
        self.call_history.append({"system": system_prompt, "user": user_prompt})

        # 1. Detect if this is Generator LLM (Coder)
        if "LLM 1 - Coder" in system_prompt:
            # Check if this is an iterative fix request
            if "Bug Fixer" in system_prompt or "Reviewer Feedback & Bugs Found" in user_prompt:
                return self._generate_fixed_code_response(user_prompt)
            else:
                return self._generate_initial_code_response(user_prompt)

        # 2. Detect if this is Reviewer LLM (Inspector)
        elif "LLM 2 - Inspector" in system_prompt or "Principal Code Reviewer" in system_prompt:
            return self._generate_reviewer_response(user_prompt)

        # 3. Detect if this is Validator LLM (Arbiter)
        elif "LLM 3 - Arbiter" in system_prompt or "Security and Systems Auditor" in system_prompt:
            return self._generate_validator_response(user_prompt)

        # Fallback
        return "Acknowledged."

    def _generate_initial_code_response(self, user_prompt: str) -> str:
        """Generates initial code with a subtle edge-case bug for the reviewer to catch."""
        # Check task context
        if "palindrome" in user_prompt.lower():
            code = '''def is_palindrome(s: str) -> bool:
    """Checks if a string is a palindrome."""
    # Bug: Case-sensitive and does not filter non-alphanumeric characters
    return s == s[::-1]

if __name__ == '__main__':
    assert is_palindrome("racecar") == True
    print("Basic test passed!")
'''
        elif "factorial" in user_prompt.lower():
            code = '''def factorial(n: int) -> int:
    """Calculates factorial recursively."""
    # Bug: Missing base-case check for negative numbers causes infinite recursion
    if n == 0 or n == 1:
        return 1
    return n * factorial(n - 1)

if __name__ == '__main__':
    print(factorial(5))
'''
        elif "fibonacci" in user_prompt.lower():
            code = '''def fibonacci(n: int) -> int:
    """Returns the nth Fibonacci number."""
    # Bug: Off-by-one boundary check and missing negative handling
    if n <= 1:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)

if __name__ == '__main__':
    print(fibonacci(6))
'''
        else:
            # Generic clean implementation with an edge case bug
            code = '''def solve_task(data: list) -> list:
    """Processes input list by squaring even numbers."""
    # Bug: crashes if data is None, and does not handle negative values
    result = []
    for item in data:
        if item % 2 == 0:
            result.append(item ** 2)
    return result

if __name__ == '__main__':
    sample = [1, 2, 3, 4]
    print(f"Result: {solve_task(sample)}")
'''
        return f"""Here is my initial implementation for the task:

```python
{code}
```

This implementation directly addresses the core logic with optimal readability.
"""

    def _generate_fixed_code_response(self, user_prompt: str) -> str:
        """Generates corrected code resolving all reported bugs."""
        if "palindrome" in user_prompt.lower():
            fixed_code = '''import re

def is_palindrome(s: str) -> bool:
    """
    Checks if a string is a palindrome.
    Properly handles case-insensitivity, spaces, and punctuation.
    """
    if s is None:
        return False
    # Filter out non-alphanumeric characters and convert to lowercase
    cleaned = re.sub(r'[^a-zA-Z0-9]', '', s).lower()
    return cleaned == cleaned[::-1]

if __name__ == '__main__':
    assert is_palindrome("A man, a plan, a canal: Panama") == True
    assert is_palindrome("race a car") == False
    assert is_palindrome("") == True
    assert is_palindrome(None) == False
    print("All palindrome test cases passed successfully!")
'''
        elif "eval(" in user_prompt or "exec(" in user_prompt:
            fixed_code = '''import ast
from typing import Any

def safe_evaluate(expression: str) -> Any:
    """
    Safely evaluates literal expressions without using unsafe eval().
    Prevents remote code execution vulnerabilities (CWE-95).
    """
    if not isinstance(expression, str):
        raise TypeError("Input must be a string expression.")
    try:
        return ast.literal_eval(expression.strip())
    except (ValueError, SyntaxError) as e:
        raise ValueError(f"Unsafe or invalid expression: {e}")

if __name__ == '__main__':
    assert safe_evaluate("[1, 2, 3]") == [1, 2, 3]
    assert safe_evaluate("{'status': 'ok'}") == {'status': 'ok'}
    print("Safe evaluation passed security assertions!")
'''
        elif "factorial" in user_prompt.lower():
            fixed_code = '''def factorial(n: int) -> int:
    """
    Calculates factorial of a non-negative integer.
    Raises ValueError for negative inputs to prevent infinite recursion.
    """
    if not isinstance(n, int):
        raise TypeError("Input must be an integer.")
    if n < 0:
        raise ValueError("Factorial is not defined for negative integers.")
    if n == 0 or n == 1:
        return 1
        
    result = 1
    for i in range(2, n + 1):
        result *= i
    return result

if __name__ == '__main__':
    assert factorial(0) == 1
    assert factorial(5) == 120
    try:
        factorial(-1)
    except ValueError:
        pass
    print("Factorial tests passed successfully!")
'''
        else:
            fixed_code = '''from typing import List, Optional

def solve_task(data: Optional[List[int]]) -> List[int]:
    """
    Safely processes input list by squaring even numbers.
    Gracefully handles None, empty collections, and non-integer items.
    """
    if data is None:
        return []
    result = []
    for item in data:
        if isinstance(item, (int, float)) and int(item) % 2 == 0:
            result.append(int(item) ** 2)
    return result

if __name__ == '__main__':
    assert solve_task(None) == []
    assert solve_task([1, 2, 3, 4]) == [4, 16]
    print("All edge-case validations passed!")
'''
        return f"""### Fix Summary:
- Resolved edge-case validation when input is `None` or empty.
- Handled potential runtime errors and boundary conditions.
- Added comprehensive docstrings, type annotations, and automated assertion tests.

```python
{fixed_code}
```
"""

    def _generate_reviewer_response(self, user_prompt: str) -> str:
        """Reviews code: flags bugs in initial code, approves fixed code."""
        # Check for dangerous security anti-patterns
        if "eval(" in user_prompt or "exec(" in user_prompt:
            review_json = {
                "has_bugs": True,
                "status": "CHANGES_REQUESTED",
                "overall_score": 3,
                "summary": "CRITICAL SECURITY FLAW: Unsafe code execution via eval/exec detected.",
                "bugs": [
                    {
                        "line_number": 3,
                        "category": "SECURITY",
                        "severity": "CRITICAL",
                        "description": "Use of eval() introduces arbitrary remote code execution vulnerability (CWE-95).",
                        "suggested_fix": "Replace eval() with safe parsing (e.g., ast.literal_eval or type-cast)."
                    }
                ]
            }
            return f"Security review identified critical vulnerabilities:\n\n```json\n{json.dumps(review_json, indent=2)}\n```"

        # If code already contains proper edge-case handling or defensive checks:
        if "isinstance(" in user_prompt or "cleaned = " in user_prompt or "raise ValueError" in user_prompt or "ast.literal_eval" in user_prompt:
            review_json = {
                "has_bugs": False,
                "status": "APPROVED",
                "overall_score": 10,
                "summary": "Excellent revision. All edge cases, type safety, and runtime checks are properly implemented.",
                "bugs": []
            }
            return f"""The revised code has been thoroughly evaluated. All previous bugs have been resolved.

```json
{json.dumps(review_json, indent=2)}
```
"""
        else:
            review_json = {
                "has_bugs": True,
                "status": "CHANGES_REQUESTED",
                "overall_score": 6,
                "summary": "Initial implementation functions on happy paths but fails critical edge cases and lacks defensive input handling.",
                "bugs": [
                    {
                        "line_number": 4,
                        "category": "EDGE_CASE",
                        "severity": "MAJOR",
                        "description": "Fails on empty/None input or special formatting constraints.",
                        "suggested_fix": "Add explicit boundary validation and clean input before processing."
                    },
                    {
                        "line_number": 5,
                        "category": "RUNTIME",
                        "severity": "MINOR",
                        "description": "Missing defensive type-checking and docstring parameter specifications.",
                        "suggested_fix": "Use typing annotations and validate argument types."
                    }
                ]
            }
            return f"""Code review complete. Issues identified that require correction:

```json
{json.dumps(review_json, indent=2)}
```
"""

    def _generate_validator_response(self, user_prompt: str) -> str:
        """Validator response confirming security and sanity."""
        if "APPROVED" in user_prompt:
            val_json = {
                "has_bugs": False,
                "status": "APPROVED",
                "overall_score": 10,
                "summary": "Security audit passed. No injection or resource leaks detected. Production ready.",
                "bugs": []
            }
        else:
            val_json = {
                "has_bugs": True,
                "status": "CHANGES_REQUESTED",
                "overall_score": 6,
                "summary": "Agreed with LLM 2. Edge case handling must be hardened before deployment.",
                "bugs": [
                    {
                        "line_number": None,
                        "category": "SECURITY",
                        "severity": "MINOR",
                        "description": "Ensure no unhandled input exceptions propagate to calling services.",
                        "suggested_fix": "Catch and handle null pointers gracefully."
                    }
                ]
            }
        return f"""Audit assessment:

```json
{json.dumps(val_json, indent=2)}
```
"""
