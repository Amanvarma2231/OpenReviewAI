import pytest
from openreview_ai.config import WorkflowConfig
from openreview_ai.engine import WorkflowOrchestrator
from openreview_ai.schema import WorkflowResult


def test_workflow_orchestrator_full_loop_approval():
    config = WorkflowConfig(
        provider_type="mock",
        generator_model="qwen2.5:0.5b",
        reviewer_model="mistral:latest",
        validator_model="deepseek-coder:1.3b",
        max_retries=3,
        enable_sandbox_execution=True,
        enable_third_llm_validator=True
    )
    events_logged = []
    def log_event(name, data):
        events_logged.append(name)

    orchestrator = WorkflowOrchestrator(config=config)
    result: WorkflowResult = orchestrator.run(
        task_prompt="Write a python function to check if a string is a palindrome.",
        target_language="python",
        on_event=log_event
    )

    assert result.status == "APPROVED"
    assert result.rounds_count >= 2
    assert result.total_bugs_detected > 0
    assert result.total_bugs_fixed > 0
    assert "workflow_started" in events_logged
    assert "workflow_completed" in events_logged
    assert "generation_started" in events_logged
    assert "review_completed" in events_logged
    assert "fix_started" in events_logged
    assert result.final_execution is not None
    assert result.final_execution.success is True


def test_workflow_orchestrator_max_retries_termination():
    # If max_retries = 0, initial round cannot loop
    config = WorkflowConfig(
        provider_type="mock",
        generator_model="qwen2.5:0.5b",
        reviewer_model="mistral:latest",
        validator_model="deepseek-coder:1.3b",
        max_retries=0,
        enable_sandbox_execution=True,
        enable_third_llm_validator=True
    )
    orchestrator = WorkflowOrchestrator(config=config)
    result = orchestrator.run(
        task_prompt="Write a python function to check if a string is a palindrome.",
        target_language="python"
    )

    # Initial round had bugs, and max_retries was 0, so it stops with MAX_RETRIES_REACHED
    assert result.status == "MAX_RETRIES_REACHED"
    assert result.rounds_count == 1
