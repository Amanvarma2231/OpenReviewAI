import re
from typing import Optional, Dict, Any
from openreview_ai.schema import ExecutionResult
from openreview_ai.sandbox.executor import execute_code_safely


def run_code_with_tests(
    code: str,
    unit_tests: Optional[str] = None,
    language: str = "python",
    timeout_seconds: int = 5
) -> ExecutionResult:
    """
    Executes code along with automated unit test verification.
    """
    if not unit_tests or not unit_tests.strip():
        # Just execute code standalone
        return execute_code_safely(code, language, timeout_seconds)
        
    combined_code = f"""# Code under test
{code}

# Test Suite Runner
if __name__ == '__main__':
{_indent_code(unit_tests.strip(), 4)}
"""
    result = execute_code_safely(combined_code, language, timeout_seconds)
    
    # Analyze if tests passed.
    # Ignore benign Python-path warnings (e.g. "Failed to find real location of …")
    # that appear on some Windows installs but are not actual errors.
    _BENIGN_STDERR_PATTERNS = (
        "failed to find real location",
        "deprecationwarning",
        "pendingdeprecation",
        "futurewarning",
        "resourcewarning",
    )
    real_stderr = "\n".join(
        line for line in result.stderr.splitlines()
        if not any(pat in line.lower() for pat in _BENIGN_STDERR_PATTERNS)
    ).strip()

    passed = result.success and not real_stderr
    test_info: Dict[str, Any] = {
        "tests_provided": True,
        "tests_passed": passed,
    }

    if not passed:
        # Extract assertion or exception details
        trace_match = re.search(r"(\w+Error: .+)", real_stderr)
        if trace_match:
            test_info["failure_reason"] = trace_match.group(1)
            
    result.test_results.update(test_info)
    return result


def _indent_code(code_str: str, spaces: int = 4) -> str:
    indent = " " * spaces
    return "\n".join(indent + line if line.strip() else "" for line in code_str.splitlines())
