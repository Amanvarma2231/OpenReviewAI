from datetime import datetime
from typing import Optional
from openreview_ai.schema import WorkflowResult
from openreview_ai.utils.diff_viewer import compute_unified_diff


def export_markdown_report(result: WorkflowResult) -> str:
    """Generates a complete, beautiful markdown audit report of the review workflow."""
    lines = []
    lines.append(f"# 🛡️ OpenReviewAI: Multi-LLM Code Review & Correction Audit Report")
    lines.append(f"**Generated at:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ")
    lines.append(f"**Final Workflow Status:** `{result.status}`  ")
    lines.append(f"**Total Iterations:** `{result.rounds_count}`  ")
    lines.append(f"**Bugs Detected:** `{result.total_bugs_detected}` | **Bugs Resolved:** `{result.total_bugs_fixed}`  ")
    lines.append("")
    
    # Model configuration table
    lines.append("## 🤖 Multi-LLM Architecture")
    lines.append("| Agent Role | Model Name | Responsibility |")
    lines.append("| :--- | :--- | :--- |")
    lines.append(f"| **LLM 1 (Generator / Coder)** | `{result.generator_model}` | Generates code & fixes bugs iteratively |")
    lines.append(f"| **LLM 2 (Reviewer / Inspector)** | `{result.reviewer_model}` | Static analysis, logic, & edge-case review |")
    if result.validator_model:
        lines.append(f"| **LLM 3 (Validator / Arbiter)** | `{result.validator_model}` | Security audit & secondary consensus check |")
    lines.append("")
    
    # Task Specification
    lines.append("## 📋 Task Specification")
    lines.append("```text")
    lines.append(result.task_prompt.strip())
    lines.append("```")
    lines.append("")
    
    # Iteration History
    lines.append("## 🔄 Iteration & Debate History")
    for step in result.iterations:
        lines.append(f"### Round {step.round_idx}")
        if step.generator_explanation:
            lines.append(f"**LLM 1 Explanation / Fix Summary:**")
            lines.append(f"> {step.generator_explanation.strip()}")
            lines.append("")
            
        if step.execution:
            exec_icon = "✅" if step.execution.success else "❌"
            lines.append(f"**Automated Verification:** {exec_icon} `Success: {step.execution.success}` | `Exit Code: {step.execution.exit_code}` | `Runtime: {step.execution.execution_time_ms:.1f}ms`")
            if not step.execution.syntax_valid and step.execution.syntax_error:
                lines.append(f"> ⚠️ **Syntax Error:** `{step.execution.syntax_error}`")
            if step.execution.stderr:
                lines.append("```")
                lines.append(f"Standard Error:\n{step.execution.stderr.strip()}")
                lines.append("```")
            lines.append("")
            
        lines.append(f"**Reviewer Evaluations:**")
        for rev in step.reviews:
            status_icon = "🟢" if rev.status == "APPROVED" else "🔴"
            lines.append(f"- **{rev.reviewer_name}** ({rev.reviewer_model}): {status_icon} `{rev.status}` (Score: {rev.overall_score}/10)")
            lines.append(f"  *Summary:* {rev.summary}")
            if rev.bugs:
                lines.append(f"  *Bugs Identified ({len(rev.bugs)}):*")
                for bug in rev.bugs:
                    line_ref = f"Line {bug.line_number}: " if bug.line_number else ""
                    lines.append(f"    - `[{bug.severity}]` `[{bug.category}]` {line_ref}{bug.description} *(Fix: {bug.suggested_fix})*")
        lines.append("")
        
    # Code Evolution Diff
    if len(result.iterations) > 1:
        initial_code = result.iterations[0].code
        diff_text = compute_unified_diff(initial_code, result.final_code, "Round 0 (Initial)", f"Round {result.rounds_count} (Final)")
        lines.append("## 🔍 Code Evolution (Unified Diff)")
        lines.append("```diff")
        lines.append(diff_text)
        lines.append("```")
        lines.append("")
        
    # Final Approved Source Code
    lines.append("## 🏆 Final Approved Source Code")
    lines.append(f"```{result.target_language}")
    lines.append(result.final_code.strip())
    lines.append("```")
    lines.append("")
    
    return "\n".join(lines)
