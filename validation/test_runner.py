"""
OpenReview AI - Test Runner & Sandbox Execution Layer
=====================================================
Executes explicit test suites against generated code in an isolated subprocess
with strict timeouts, temporary directories, sanitized environments, and cleanup.
Distinguishes NOT_RUN, PASSED, FAILED, TIMEOUT, and ERROR states clearly.
"""

import os
import sys
import time
import tempfile
import subprocess
import re
from typing import Optional, Dict
from models.schemas import TestExecutionResult, TestStatus
from utils.logging_config import setup_logger

logger = setup_logger("TestRunner")


def run_tests(
    code: str,
    test_code: Optional[str] = None,
    timeout_seconds: int = 10,
    allow_execution: bool = True,
) -> TestExecutionResult:
    """
    Executes test_code against code in an isolated temporary directory.

    Args:
        code: Python source code under test.
        test_code: Pytest or unittest code asserting behavior.
        timeout_seconds: Subprocess execution timeout in seconds.
        allow_execution: If False, execution is skipped for security.

    Returns:
        TestExecutionResult with structured counts, status, stdout, stderr, and timings.
    """
    # Case 1: No tests provided
    if not test_code or not test_code.strip():
        return TestExecutionResult(
            status=TestStatus.NOT_RUN,
            total_tests=0,
            passed_tests=0,
            failed_tests=0,
            error_details="No test suite provided. Automated functional testing was NOT RUN.",
            stdout="",
            stderr="",
            duration_seconds=0.0,
            sandbox_mode="none",
        )

    # Case 2: Execution disabled for security
    if not allow_execution:
        return TestExecutionResult(
            status=TestStatus.NOT_RUN,
            total_tests=0,
            passed_tests=0,
            failed_tests=0,
            error_details="Test execution is disabled by user security settings (Safe Mode / Untrusted Sandbox restriction).",
            stdout="",
            stderr="",
            duration_seconds=0.0,
            sandbox_mode="disabled_by_policy",
        )

    # Case 3: Prepare isolated temporary workspace
    start_time = time.time()
    temp_dir = tempfile.mkdtemp(prefix="openreview_sandbox_")

    try:
        solution_path = os.path.join(temp_dir, "solution.py")
        test_path = os.path.join(temp_dir, "test_solution.py")

        with open(solution_path, "w", encoding="utf-8") as f:
            f.write(code)

        # Ensure test file imports solution properly if not already done
        test_content = test_code.strip()
        if "from solution import" not in test_content and "import solution" not in test_content:
            test_content = "from solution import *\n\n" + test_content

        with open(test_path, "w", encoding="utf-8") as f:
            f.write(test_content)

        # Build sanitized environment for Windows subprocess (strip all secret env vars)
        clean_env: Dict[str, str] = {
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", "C:\\Windows"),
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": temp_dir,
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        if "WINDIR" in os.environ:
            clean_env["WINDIR"] = os.environ["WINDIR"]
        if "TEMP" in os.environ:
            clean_env["TEMP"] = os.environ["TEMP"]
        if "TMP" in os.environ:
            clean_env["TMP"] = os.environ["TMP"]

        # Run pytest inside isolated subprocess
        # Flags: -I (isolated mode), -B (no bytecode), -m pytest
        cmd = [
            sys.executable,
            "-I",
            "-B",
            "-m",
            "pytest",
            "test_solution.py",
            "-v",
            "--tb=short",
        ]

        logger.info(f"Running pytest in sandbox directory: {temp_dir}")
        process = subprocess.run(
            cmd,
            cwd=temp_dir,
            env=clean_env,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )

        elapsed = time.time() - start_time
        stdout = process.stdout or ""
        stderr = process.stderr or ""

        # Parse pytest summary line (e.g. "2 passed, 1 failed in 0.05s")
        passed, failed, total = _parse_pytest_summary(stdout)

        if process.returncode == 0:
            return TestExecutionResult(
                status=TestStatus.PASSED,
                total_tests=total if total > 0 else (passed if passed > 0 else 1),
                passed_tests=passed if passed > 0 else 1,
                failed_tests=0,
                error_details=None,
                stdout=stdout,
                stderr=stderr,
                duration_seconds=round(elapsed, 3),
                sandbox_mode="isolated_tempdir_subprocess",
            )
        else:
            return TestExecutionResult(
                status=TestStatus.FAILED,
                total_tests=total if total > 0 else (passed + (failed if failed > 0 else 1)),
                passed_tests=passed,
                failed_tests=failed if failed > 0 else 1,
                error_details=f"Test suite failed with exit code {process.returncode}.",
                stdout=stdout,
                stderr=stderr,
                duration_seconds=round(elapsed, 3),
                sandbox_mode="isolated_tempdir_subprocess",
            )

    except subprocess.TimeoutExpired:
        elapsed = time.time() - start_time
        logger.warning(f"Test execution timed out after {timeout_seconds}s")
        return TestExecutionResult(
            status=TestStatus.TIMEOUT,
            total_tests=1,
            passed_tests=0,
            failed_tests=1,
            error_details=f"Execution timed out after {timeout_seconds} seconds. Code may contain an infinite loop.",
            stdout="",
            stderr=f"TimeoutExpired: Process terminated after {timeout_seconds}s limit.",
            duration_seconds=round(elapsed, 3),
            sandbox_mode="isolated_tempdir_subprocess",
        )
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"Error executing test runner: {e}")
        return TestExecutionResult(
            status=TestStatus.ERROR,
            total_tests=0,
            passed_tests=0,
            failed_tests=0,
            error_details=f"Test runner error: {str(e)}",
            stdout="",
            stderr=str(e),
            duration_seconds=round(elapsed, 3),
            sandbox_mode="isolated_tempdir_subprocess",
        )
    finally:
        # Strict cleanup of temporary sandbox directory
        try:
            for root, dirs, files in os.walk(temp_dir, topdown=False):
                for name in files:
                    os.remove(os.path.join(root, name))
                for name in dirs:
                    os.rmdir(os.path.join(root, name))
            os.rmdir(temp_dir)
        except Exception as cleanup_err:
            logger.warning(f"Failed to fully delete sandbox dir {temp_dir}: {cleanup_err}")


def _parse_pytest_summary(stdout: str):
    """Extracts passed and failed test counts from pytest stdout."""
    passed = 0
    failed = 0

    # Look for "== 1 passed, 1 failed in 0.12s =="
    match_passed = re.search(r"(\d+)\s+passed", stdout)
    if match_passed:
        passed = int(match_passed.group(1))

    match_failed = re.search(r"(\d+)\s+failed", stdout)
    if match_failed:
        failed = int(match_failed.group(1))

    match_errors = re.search(r"(\d+)\s+error", stdout)
    if match_errors:
        failed += int(match_errors.group(1))

    total = passed + failed
    return passed, failed, total
