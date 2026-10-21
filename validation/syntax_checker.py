"""
OpenReview AI - Python Syntax Checker
====================================
Validates generated Python source code using the standard library `ast.parse`.
Returns structured syntax diagnostics without executing the untrusted code.
"""

import ast
from typing import Optional
from models.schemas import SyntaxCheckResult


def check_syntax(code: str) -> SyntaxCheckResult:
    """
    Parses Python code into an Abstract Syntax Tree (AST).
    Does NOT execute the code.

    Returns:
        SyntaxCheckResult containing validity status, line number, offset, and error message.
    """
    if not code or not code.strip():
        return SyntaxCheckResult(
            is_valid=False,
            error_message="Code is empty.",
            line_number=0,
            offset=0,
            error_type="EmptyCodeError",
        )

    try:
        ast.parse(code, filename="<generated_code>")
        return SyntaxCheckResult(
            is_valid=True,
            error_message=None,
            line_number=None,
            offset=None,
            error_type=None,
        )
    except SyntaxError as e:
        return SyntaxCheckResult(
            is_valid=False,
            error_message=e.msg,
            line_number=e.lineno,
            offset=e.offset,
            error_type=e.__class__.__name__,
        )
    except Exception as e:
        return SyntaxCheckResult(
            is_valid=False,
            error_message=str(e),
            line_number=None,
            offset=None,
            error_type=e.__class__.__name__,
        )
