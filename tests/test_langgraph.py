import pytest
from openreview_ai.config import WorkflowConfig
from openreview_ai.agents.generator import CodeGeneratorAgent
from openreview_ai.agents.reviewer import CodeReviewerAgent
from openreview_ai.agents.validator import ValidatorAgent
from openreview_ai.providers.mock_provider import MockSimulationProvider
from openreview_ai.langgraph_workflow import build_langgraph_workflow, LANGGRAPH_AVAILABLE


@pytest.mark.skipif(not LANGGRAPH_AVAILABLE, reason="LangGraph not available")
def test_langgraph_workflow_execution():
    config = WorkflowConfig(provider_type="mock", max_retries=2)
    provider = MockSimulationProvider("test-model")

    gen = CodeGeneratorAgent(provider)
    rev = CodeReviewerAgent(provider)
    val = ValidatorAgent(provider)

    app = build_langgraph_workflow(config, gen, rev, val)
    assert app is not None

    initial_state = {
        "task_prompt": "Write a python function to check if a string is a palindrome.",
        "target_language": "python",
        "unit_tests": None,
        "current_round": 0,
        "max_retries": 2,
        "current_code": "",
        "previous_code": None,
        "execution_result": None,
        "reviews": [],
        "is_approved": False,
        "status": "PENDING",
        "explanation": ""
    }

    final_state = app.invoke(initial_state)
    assert final_state is not None
    assert final_state["is_approved"] is True
    assert final_state["status"] == "APPROVED"
    assert "is_palindrome" in final_state["current_code"]


@pytest.mark.skipif(not LANGGRAPH_AVAILABLE, reason="LangGraph not available")
def test_langgraph_workflow_orchestrator_integration():
    from openreview_ai.engine import WorkflowOrchestrator

    config = WorkflowConfig(
        provider_type="mock",
        orchestrator_engine="langgraph",
        max_retries=2,
    )
    events_captured = []

    def handle_event(name, data):
        events_captured.append(name)

    orchestrator = WorkflowOrchestrator(config=config)
    result = orchestrator.run(
        task_prompt="Write a python function to check if a string is a palindrome.",
        target_language="python",
        on_event=handle_event,
    )

    assert result is not None
    assert result.status == "APPROVED"
    assert "run_started" in events_captured
    assert "generator_completed" in events_captured
    assert "reviewer_completed" in events_captured
    assert "run_completed" in events_captured


@pytest.mark.skipif(not LANGGRAPH_AVAILABLE, reason="LangGraph not available")
def test_langgraph_event_emission_compliance():
    config = WorkflowConfig(provider_type="mock", max_retries=2)
    provider = MockSimulationProvider("test-model")
    gen = CodeGeneratorAgent(provider)
    rev = CodeReviewerAgent(provider)
    val = ValidatorAgent(provider)

    received_events = []

    def on_evt(name, data):
        received_events.append((name, data))

    app = build_langgraph_workflow(config, gen, rev, val, on_event=on_evt)

    initial_state = {
        "run_id": "test_compliance_run",
        "task_prompt": "Write a function to add two numbers.",
        "target_language": "python",
        "unit_tests": "assert add(1, 2) == 3",
        "current_round": 0,
        "max_retries": 1,
        "current_code": "",
    }

    app.invoke(initial_state)

    event_names = [e[0] for e in received_events]
    assert "run_started" in event_names
    assert "input_validated" in event_names
    assert "files_analyzed" in event_names
    assert "generator_completed" in event_names
    assert "syntax_check_completed" in event_names
    assert "reviewer_completed" in event_names
    assert "validator_started" in event_names
    assert "tests_completed" in event_names

    # Verify event structure
    for name, payload in received_events:
        assert "run_id" in payload
        assert "event_type" in payload
        assert "timestamp" in payload
        assert "attempt_number" in payload
        assert "stage" in payload
        assert "message" in payload


@pytest.mark.skipif(not LANGGRAPH_AVAILABLE, reason="LangGraph not available")
def test_langgraph_failed_tests_prevent_false_pass():
    config = WorkflowConfig(provider_type="mock", max_retries=1)
    provider = MockSimulationProvider("test-model")
    gen = CodeGeneratorAgent(provider)
    rev = CodeReviewerAgent(provider)
    val = ValidatorAgent(provider)

    app = build_langgraph_workflow(config, gen, rev, val)

    # Supply an impossible test assertion to guarantee failure
    initial_state = {
        "task_prompt": "Write a function returning 42.",
        "target_language": "python",
        "unit_tests": "assert False, 'Deliberate test failure for validation check'",
        "current_round": 0,
        "max_retries": 0,  # No retries allowed
        "current_code": "",
    }

    final_state = app.invoke(initial_state)
    assert final_state["is_approved"] is False
    assert final_state["status"] in ["MAX_RETRIES_REACHED", "FAILED"]
    assert final_state["test_status"] == "FAIL"


@pytest.mark.skipif(not LANGGRAPH_AVAILABLE, reason="LangGraph not available")
def test_langgraph_empty_task_routes_to_record_error():
    config = WorkflowConfig(provider_type="mock", max_retries=1)
    provider = MockSimulationProvider("test-model")
    gen = CodeGeneratorAgent(provider)
    rev = CodeReviewerAgent(provider)
    val = ValidatorAgent(provider)

    app = build_langgraph_workflow(config, gen, rev, val)

    # Empty task and no code
    initial_state = {
        "task_prompt": "",
        "existing_code": "",
        "current_round": 0,
        "max_retries": 1,
    }

    final_state = app.invoke(initial_state)
    assert len(final_state.get("workflow_errors", [])) > 0
    assert final_state["status"] == "FAILED"
    assert "Halted with errors" in final_state["stop_reason"]
