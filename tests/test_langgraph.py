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
