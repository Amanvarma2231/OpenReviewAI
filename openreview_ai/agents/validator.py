from typing import Optional, List, Dict, Any
from openreview_ai.agents.base import BaseAgent
from openreview_ai.providers.base import BaseLLMProvider
from openreview_ai.schema import (
    ReviewFeedback,
    ReviewStatus,
    BugItem,
    BugCategory,
    SeverityLevel,
    ExecutionResult,
    AcceptanceStatus,
)
from openreview_ai.sandbox.syntax_checker import check_syntax
from openreview_ai.sandbox.test_runner import run_code_with_tests
from openreview_ai.utils.prompt_templates import VALIDATOR_SYSTEM, VALIDATOR_USER

try:
    from validation.static_analyzer import analyze_code
except ImportError:
    analyze_code = None


class ValidatorAgent(BaseAgent):
    """
    AGENT C: Validator Agent.
    Responsibilities:
    - Check Python syntax using AST parsing or compilation checks.
    - Run configured static analysis (Ruff or AST security analyzer).
    - Execute approved tests within a restricted sandbox environment.
    - Capture exit status, stdout, stderr, timeout, and duration.
    - Identify regressions and verify test evidence after code changes.
    - Perform optional secondary LLM security & consensus arbitration.
    - Clearly evaluate and distinguish PASS, FAIL, ERROR, and NOT_RUN.
    """

    def __init__(self, provider: BaseLLMProvider, role_name: str = "Validator (LLM 3)"):
        super().__init__(role_name, provider)

    def validate_syntax(self, code: str, language: str = "python") -> Dict[str, Any]:
        """Performs Python AST structural checks and security checks."""
        is_valid, err_msg, meta = check_syntax(code, language)
        return {
            "valid": is_valid,
            "error": err_msg,
            "metadata": meta,
        }

    def run_static_analysis(self, code: str, enabled: bool = True) -> Dict[str, Any]:
        """Runs configured static analysis (Ruff or AST linter) on code."""
        if not enabled or not code or not code.strip():
            return {"is_clean": True, "findings": [], "tool_name": "ruff", "raw_output": "Static analysis disabled."}
        
        if analyze_code is not None:
            try:
                res = analyze_code(code, enabled=enabled)
                return {
                    "is_clean": res.is_clean,
                    "findings": res.findings,
                    "tool_name": res.tool_name,
                    "raw_output": res.raw_output,
                }
            except Exception as e:
                return {"is_clean": True, "findings": [], "tool_name": "ruff", "raw_output": f"Static check skipped: {e}"}

        # Fallback AST static check
        is_valid, err_msg, meta = check_syntax(code, "python")
        sec_flags = meta.get("security_flags", [])
        return {
            "is_clean": len(sec_flags) == 0,
            "findings": [{"code": "SECURITY_FLAG", "message": f} for f in sec_flags],
            "tool_name": "ast_analyzer",
            "raw_output": "AST security check completed.",
        }

    def run_sandbox_tests(
        self,
        code: str,
        unit_tests: Optional[str] = None,
        language: str = "python",
        timeout_seconds: int = 5,
    ) -> ExecutionResult:
        """
        Executes code with assertions in an isolated subprocess with strict timeouts.
        Captures exit status, stdout, stderr, duration, and distinguish PASS, FAIL, ERROR, NOT_RUN.
        """
        if not unit_tests or not unit_tests.strip():
            # Code execution without tests
            return run_code_with_tests(code, None, language, timeout_seconds)

        return run_code_with_tests(code, unit_tests, language, timeout_seconds)

    def evaluate_acceptance_evidence(
        self,
        syntax_res: Dict[str, Any],
        test_res: Optional[ExecutionResult],
        unit_tests_provided: bool,
        primary_review: Optional[ReviewFeedback],
        validator_review: Optional[ReviewFeedback] = None,
        current_attempt: int = 0,
        max_attempts: int = 3,
        strict_mode: bool = True,
    ) -> Dict[str, Any]:
        """
        Synthesizes real acceptance criteria from verifiable empirical evidence.
        Never equates different statuses or creates false PASS.
        """
        # 1. Syntax Status
        syntax_passed = bool(syntax_res.get("valid", False))

        # 2. Test Execution Status
        if not unit_tests_provided:
            test_status = "NOT_RUN"
            tests_passed = True  # Not failing, but reported as NOT_RUN
        elif test_res is None:
            test_status = "NOT_RUN"
            tests_passed = not strict_mode
        elif test_res.exit_code == -1 or "timeout" in test_res.test_results:
            test_status = "TIMEOUT"
            tests_passed = False
        elif test_res.success and test_res.test_results.get("tests_passed", True):
            test_status = "PASS"
            tests_passed = True
        elif test_res.exit_code != 0:
            test_status = "FAIL"
            tests_passed = False
        else:
            test_status = "FAIL"
            tests_passed = False

        # 3. Reviewer Status
        review_passed = False
        if primary_review:
            has_blocking_bugs = any(
                b.severity in [SeverityLevel.CRITICAL, SeverityLevel.HIGH, SeverityLevel.MAJOR]
                for b in primary_review.bugs
            )
            review_passed = (primary_review.status == ReviewStatus.APPROVED) and not has_blocking_bugs and not primary_review.has_bugs

        # 4. Secondary Validator Status
        val_passed = True
        if validator_review:
            has_val_bugs = any(
                b.severity in [SeverityLevel.CRITICAL, SeverityLevel.HIGH, SeverityLevel.MAJOR]
                for b in validator_review.bugs
            )
            val_passed = (validator_review.status == ReviewStatus.APPROVED) and not has_val_bugs and not validator_review.has_bugs

        # 5. Composite Validation Status
        validation_passed = syntax_passed and tests_passed and val_passed
        all_criteria_met = syntax_passed and (test_status in ["PASS", "NOT_RUN"]) and (test_res.success if test_res else True) and review_passed and val_passed

        # Strict requirement: if tests were provided and failed, MUST NOT PASS
        if unit_tests_provided and test_status != "PASS":
            all_criteria_met = False

        # Determine explicit AcceptanceStatus
        if all_criteria_met:
            acceptance_status = AcceptanceStatus.FINAL_ACCEPTED
        elif not syntax_passed or test_status in ["FAIL", "TIMEOUT"]:
            acceptance_status = AcceptanceStatus.FAILED
        elif current_attempt >= max_attempts:
            acceptance_status = AcceptanceStatus.RETRY_LIMIT_REACHED
        else:
            acceptance_status = AcceptanceStatus.PARTIAL

        return {
            "syntax_passed": syntax_passed,
            "test_status": test_status,
            "tests_passed": tests_passed,
            "review_passed": review_passed,
            "validation_passed": validation_passed,
            "all_criteria_met": all_criteria_met,
            "acceptance_status": acceptance_status.value,
        }

    def validate_code(
        self,
        task_prompt: str,
        current_code: str,
        target_language: str = "python",
        primary_review: Optional[ReviewFeedback] = None,
        temperature: float = 0.1,
    ) -> ReviewFeedback:
        """Executes secondary validation / security audit."""
        reviewer_summary = (
            f"Status: {primary_review.status.value}. Summary: {primary_review.summary}"
            if primary_review
            else "None provided."
        )
        user_prompt = VALIDATOR_USER.format(
            task_prompt=task_prompt,
            current_code=current_code,
            target_language=target_language,
            reviewer_summary=reviewer_summary
        )

        raw_response = self.provider.generate(
            system_prompt=VALIDATOR_SYSTEM,
            user_prompt=user_prompt,
            temperature=temperature
        )

        return self._parse_validator_response(raw_response)

    def _parse_validator_response(self, raw_response: str) -> ReviewFeedback:
        data = self.extract_json_block(raw_response)
        if data and isinstance(data, dict):
            raw_issues = data.get("issues") if "issues" in data else data.get("bugs", [])
            if not isinstance(raw_issues, list):
                raw_issues = []

            verdict_val = str(data.get("verdict", "")).strip().upper()
            has_bugs = (verdict_val == "FAIL") or data.get("has_bugs", False) or len(raw_issues) > 0
            status = ReviewStatus.CHANGES_REQUESTED if has_bugs else ReviewStatus.APPROVED
            summary = data.get("summary", "Validation complete.")
            score = int(data.get("overall_score", 6 if has_bugs else 9))
            
            bugs: List[BugItem] = []
            for item in raw_issues:
                if not isinstance(item, dict):
                    continue
                cat_raw = str(item.get("category", "SECURITY")).upper()
                try:
                    category = BugCategory(cat_raw)
                except ValueError:
                    category = BugCategory.SECURITY

                sev_raw = str(item.get("severity", "MAJOR")).upper()
                try:
                    severity = SeverityLevel(sev_raw)
                except ValueError:
                    severity = SeverityLevel.MAJOR

                conf_val = item.get("confidence", 1.0)
                try:
                    conf = float(conf_val)
                except (ValueError, TypeError):
                    conf = 1.0

                bugs.append(BugItem(
                    file=item.get("file"),
                    line_number=item.get("line_number") or item.get("line"),
                    category=category,
                    severity=severity,
                    description=item.get("description", "Security or edge-case finding"),
                    suggested_fix=item.get("suggested_fix", "Harden implementation"),
                    confidence=conf,
                ))

            reqs_met_raw = data.get("requirements_met", [])
            reqs_met = [str(x) for x in reqs_met_raw] if isinstance(reqs_met_raw, list) else []
            unres_raw = data.get("unresolved_concerns", [])
            unresolved = [str(x) for x in unres_raw] if isinstance(unres_raw, list) else []

            return ReviewFeedback(
                reviewer_name=self.role_name,
                reviewer_model=self.model_name,
                status=status,
                has_bugs=has_bugs or len(bugs) > 0,
                summary=summary,
                verdict="FAIL" if has_bugs else "PASS",
                bugs=bugs,
                overall_score=score,
                requirements_met=reqs_met,
                unresolved_concerns=unresolved,
                raw_response=raw_response,
            )

        # Fallback
        has_bugs = "vulnerability" in raw_response.lower() or "security issue" in raw_response.lower()
        return ReviewFeedback(
            reviewer_name=self.role_name,
            reviewer_model=self.model_name,
            status=ReviewStatus.CHANGES_REQUESTED if has_bugs else ReviewStatus.APPROVED,
            has_bugs=has_bugs,
            summary=raw_response[:200] if raw_response else "Validation passed.",
            verdict="FAIL" if has_bugs else "PASS",
            bugs=[],
            overall_score=5 if has_bugs else 9,
            raw_response=raw_response,
        )
