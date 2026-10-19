import os
import sys
import time
import tempfile
import subprocess
from typing import Optional
from openreview_ai.schema import ExecutionResult
from openreview_ai.sandbox.syntax_checker import check_syntax


def execute_code_safely(
    code: str,
    language: str = "python",
    timeout_seconds: int = 5,
    extra_stdin: Optional[str] = None
) -> ExecutionResult:
    """
    Safely executes code in an isolated subprocess with strict timeout guards.
    Returns structured ExecutionResult.
    """
    # Step 1: Pre-execution syntax validation
    syntax_valid, syntax_err, meta = check_syntax(code, language)
    if not syntax_valid:
        return ExecutionResult(
            success=False,
            stdout="",
            stderr=f"Syntax Check Failed:\n{syntax_err}",
            exit_code=1,
            execution_time_ms=0.0,
            syntax_valid=False,
            syntax_error=syntax_err,
            test_results={"metadata": meta}
        )

    # Step 2: Write to temporary file
    suffix = ".py" if language.lower() == "python" else f".{language}"
    with tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False, encoding="utf-8") as temp_file:
        temp_file.write(code)
        temp_path = temp_file.name

    start_time = time.perf_counter()
    try:
        # Step 3: Run in subprocess
        cmd = [sys.executable, temp_path] if language.lower() == "python" else [language, temp_path]
        
        # Safe execution environment
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        
        proc = subprocess.run(
            cmd,
            input=extra_stdin,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=env
        )
        duration_ms = (time.perf_counter() - start_time) * 1000
        
        return ExecutionResult(
            success=(proc.returncode == 0),
            stdout=proc.stdout,
            stderr=proc.stderr,
            exit_code=proc.returncode,
            execution_time_ms=duration_ms,
            syntax_valid=True,
            syntax_error=None,
            test_results={"metadata": meta}
        )

    except subprocess.TimeoutExpired:
        duration_ms = (time.perf_counter() - start_time) * 1000
        return ExecutionResult(
            success=False,
            stdout="",
            stderr=f"Execution timed out after {timeout_seconds} seconds! (Possible infinite loop or heavy computation)",
            exit_code=-1,
            execution_time_ms=duration_ms,
            syntax_valid=True,
            syntax_error="TimeoutExpired",
            test_results={"timeout": True}
        )
    except Exception as e:
        duration_ms = (time.perf_counter() - start_time) * 1000
        return ExecutionResult(
            success=False,
            stdout="",
            stderr=f"Execution runner error: {str(e)}",
            exit_code=-2,
            execution_time_ms=duration_ms,
            syntax_valid=True,
            syntax_error=str(e),
            test_results={"exception": str(e)}
        )
    finally:
        # Cleanup temp file
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
