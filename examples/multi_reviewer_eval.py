import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from openreview_ai.config import WorkflowConfig
from openreview_ai.engine import WorkflowOrchestrator
from openreview_ai.utils.diff_viewer import compute_unified_diff
from openreview_ai.utils.report_exporter import export_markdown_report


def event_logger(event_name: str, data: dict):
    if event_name == "generation_started":
        print(f"-> Round {data.get('round')}: Generator is generating code...")
    elif event_name == "review_completed":
        rev = data.get("review", {})
        print(f"   Reviewer Evaluation: Status={rev.get('status')}, Bugs Found={len(rev.get('bugs', []))}")
    elif event_name == "validation_completed":
        val = data.get("validation", {})
        print(f"   Validator Consensus: Status={val.get('status')}")
    elif event_name == "fix_started":
        print(f"-> Iterative Fix: Passing {data.get('bugs_to_fix')} bug(s) back to Generator...")
    elif event_name == "workflow_completed":
        print(f"-> Complete! Final Status={data.get('status')}")


def main():
    print("=== OpenReviewAI: 3-LLM Collaborative Debate Example ===\n")

    config = WorkflowConfig(
        provider_type="mock",
        generator_model="Qwen/Qwen2.5-Coder",
        reviewer_model="mistralai/Mistral-7B",
        validator_model="deepseek-ai/DeepSeek-Coder",
        max_retries=3,
        enable_third_llm_validator=True,
        enable_sandbox_execution=True
    )

    orchestrator = WorkflowOrchestrator(config=config)
    result = orchestrator.run(
        task_prompt="Write a python function to check if a string is a palindrome.",
        on_event=event_logger
    )

    print("\n=== Evolution Summary ===")
    print(f"Rounds: {result.rounds_count}")
    print(f"Status: {result.status}")

    # Export report
    report_file = "examples_audit_report.md"
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(export_markdown_report(result))
    print(f"Detailed Markdown audit report written to: {report_file}")


if __name__ == "__main__":
    main()
