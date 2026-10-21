"""
OpenReview AI - Report Generator
================================
Produces human-readable Markdown reports from WorkflowReport data.
Explicitly highlights differences between LLM review verdicts and test execution evidence.
"""

from models.schemas import WorkflowReport, ReviewVerdict, TestStatus


def generate_markdown_report(report: WorkflowReport) -> str:
    """Generates a complete GitHub-flavored Markdown audit report."""
    md = []

    # Title & Metadata
    md.append(f"# OpenReview AI — Workflow Execution Report")
    md.append(f"**Run ID:** `{report.run_id}`  ")
    md.append(f"**Execution Timestamp:** {report.start_time} to {report.end_time}  ")
    md.append(f"**Total Duration:** {report.total_duration_seconds:.2f} seconds  ")
    md.append(f"**Final Status:** `{report.final_status.value}`  ")
    md.append(f"**Attempts Executed:** {report.total_attempts} of max {report.max_attempts}  ")
    md.append(f"**Stop Reason:** {report.stop_reason}\n")

    # Models & Environment
    md.append("## 1. Environment & Configuration")
    md.append(f"- **Code Generator Model:** `{report.generator_model}`")
    md.append(f"- **Code Reviewer Model:** `{report.reviewer_model}`")
    md.append(f"- **Execution Mode:** Local Ollama Inference (Sequential)")
    md.append(f"- **Test Suite Provided:** `{'Yes' if report.test_suite_provided else 'No'}`\n")

    # User Task & Constraints
    md.append("## 2. Task Requirements")
    md.append("```text")
    md.append(report.task_description.strip())
    md.append("```")
    if report.constraints:
        md.append("\n**Specified Constraints:**")
        for c in report.constraints:
            md.append(f"- {c}")
    md.append("")

    # Validation Limitations & Caveats
    md.append("## 3. Validation Limitations & Audit Notes")
    if report.validation_limitations:
        for lim in report.validation_limitations:
            md.append(f"> [!WARNING]\n> {lim}\n")
    else:
        md.append("> [!NOTE]\n> Both automated syntax analysis and functional pytest execution were completed.\n")

    # Iteration History
    md.append("## 4. Iteration Breakdown & Progression")
    for it in report.iterations:
        md.append(f"### Iteration {it.iteration_number}")
        md.append(f"- **Duration:** {it.duration_seconds:.2f}s | **Timestamp:** {it.timestamp}")

        # Syntax Result
        syn = it.syntax_result
        if syn.is_valid:
            md.append("- **Syntax Validation:** `PASSED` (ast.parse)")
        else:
            md.append(
                f"- **Syntax Validation:** `FAILED` ({syn.error_type} at line {syn.line_number}, col {syn.offset}: {syn.error_message})"
            )

        # Test Execution Result
        tst = it.test_result
        if tst.status == TestStatus.NOT_RUN:
            md.append(f"- **Test Execution:** `NOT_RUN` — {tst.error_details or 'No tests provided'}")
        elif tst.status == TestStatus.PASSED:
            md.append(
                f"- **Test Execution:** `PASSED` ({tst.passed_tests}/{tst.total_tests} tests in {tst.duration_seconds:.3f}s)"
            )
        else:
            md.append(
                f"- **Test Execution:** `{tst.status.value}` ({tst.failed_tests} failed, {tst.passed_tests} passed in {tst.duration_seconds:.3f}s)"
            )
            if tst.stderr or tst.error_details:
                md.append("  ```text")
                md.append(f"  {tst.error_details or ''}\n  {tst.stderr[:400]}")
                md.append("  ```")

        # Reviewer Verdict
        rev = it.review_result
        if rev:
            verdict_badge = "PASS" if rev.verdict == ReviewVerdict.PASS else "FAIL"
            md.append(f"- **Independent Reviewer Verdict:** `{verdict_badge}`")
            md.append(f"  - **Summary:** {rev.summary}")
            md.append(f"  - **Requirements Satisfied:** `{'Yes' if rev.requirements_met else 'No'}`")

            if rev.issues:
                md.append("\n  **Identified Issues:**")
                md.append("  | Type | Severity | Line | Description | Suggested Fix |")
                md.append("  | :--- | :--- | :--- | :--- | :--- |")
                for iss in rev.issues:
                    line_str = str(iss.line_number) if iss.line_number else "-"
                    fix_str = (iss.suggested_fix or "-").replace("\n", " ")
                    desc_str = iss.description.replace("\n", " ")
                    md.append(
                        f"  | {iss.issue_type} | {iss.severity.value} | {line_str} | {desc_str} | {fix_str} |"
                    )
                md.append("")
        else:
            md.append("- **Independent Reviewer Verdict:** `SKIPPED` (Syntax or fatal validation failure occurred first)")

        # Static Analysis
        sta = it.static_analysis
        if sta and not sta.is_clean and sta.findings:
            md.append(f"- **Static Analysis (Ruff):** {len(sta.findings)} linter notice(s)")
            for f in sta.findings[:5]:
                md.append(f"  - `[{f.get('code')}]` Line {f.get('line')}: {f.get('message')}")

        md.append("\n<details><summary>Click to view Python Code for Iteration " f"{it.iteration_number}</summary>\n")
        md.append("```python")
        md.append(it.code)
        md.append("```\n</details>\n")

    # Unresolved Concerns
    if report.unresolved_issues:
        md.append("## 5. Unresolved Concerns & Edge Cases")
        for u in report.unresolved_issues:
            md.append(f"- {u}")
        md.append("")

    # Final Python Code
    md.append("## 6. Final Python Implementation")
    md.append("```python")
    md.append(report.final_code or "# No final code produced")
    md.append("```\n")

    md.append("---\n*Generated by OpenReview AI — Multi-LLM Code Generation, Review & Self-Correction System*")

    return "\n".join(md)
