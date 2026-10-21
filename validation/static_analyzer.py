"""
OpenReview AI - Static Analysis Layer
=====================================
Runs Ruff linter on code snippets to detect code quality, unused variables,
and style issues without conflating them with fatal execution errors.
"""

import sys
import tempfile
import subprocess
import json
import os
from typing import Dict, Any, List
from models.schemas import StaticAnalysisResult
from utils.logging_config import setup_logger

logger = setup_logger("StaticAnalyzer")


def analyze_code(code: str, enabled: bool = True) -> StaticAnalysisResult:
    """
    Runs `ruff check` on the provided Python code string in an isolated temp file.
    Does NOT treat style warnings as fatal test failures.
    """
    if not enabled or not code or not code.strip():
        return StaticAnalysisResult(
            is_clean=True,
            findings=[],
            tool_name="ruff",
            raw_output="Static analysis disabled or code empty.",
        )

    temp_fd, temp_path = tempfile.mkstemp(prefix="ruff_check_", suffix=".py")
    try:
        with open(temp_fd, "w", encoding="utf-8") as f:
            f.write(code)

        # Run ruff check --output-format=json
        cmd = [
            sys.executable,
            "-m",
            "ruff",
            "check",
            temp_path,
            "--output-format=json",
        ]

        process = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=5,
        )

        stdout = process.stdout or ""
        findings: List[Dict[str, Any]] = []

        if stdout.strip():
            try:
                raw_findings = json.loads(stdout)
                for item in raw_findings:
                    findings.append({
                        "code": item.get("code", "LINT"),
                        "message": item.get("message", ""),
                        "line": item.get("location", {}).get("row"),
                        "column": item.get("location", {}).get("column"),
                        "fix_available": item.get("fix") is not None,
                    })
            except json.JSONDecodeError:
                # Text output fallback
                findings.append({
                    "code": "RUFF_MSG",
                    "message": stdout[:300],
                    "line": None,
                    "column": None,
                    "fix_available": False,
                })

        return StaticAnalysisResult(
            is_clean=(len(findings) == 0),
            findings=findings,
            tool_name="ruff",
            raw_output=stdout,
        )
    except FileNotFoundError:
        logger.warning("Ruff executable not found in Python environment.")
        return StaticAnalysisResult(
            is_clean=True,
            findings=[],
            tool_name="ruff",
            raw_output="Ruff is not installed.",
        )
    except Exception as e:
        logger.warning(f"Static analysis failed: {e}")
        return StaticAnalysisResult(
            is_clean=True,
            findings=[],
            tool_name="ruff",
            raw_output=f"Error running ruff: {str(e)}",
        )
    finally:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except OSError:
            pass
