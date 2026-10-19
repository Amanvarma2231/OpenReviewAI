"""
LangGraph Multi-Agent Architecture for OpenReviewAI.
Implements StateGraph nodes and conditional edges for multi-LLM debate and code review.
"""

from typing import Dict, Any, TypedDict, List, Optional
try:
    from langgraph.graph import StateGraph, END
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False

from openreview_ai.config import WorkflowConfig
from openreview_ai.schema import ExecutionResult, ReviewFeedback, BugItem
from openreview_ai.agents.generator import CodeGeneratorAgent
from openreview_ai.agents.reviewer import CodeReviewerAgent
from openreview_ai.agents.validator import ValidatorAgent
from openreview_ai.sandbox.test_runner import run_code_with_tests


class AgentGraphState(TypedDict):
    task_prompt: str
    target_language: str
    unit_tests: Optional[str]
    current_round: int
    max_retries: int
    current_code: str
    previous_code: Optional[str]
    execution_result: Optional[Dict[str, Any]]
    reviews: List[Dict[str, Any]]
    is_approved: bool
    status: str
    explanation: str


def build_langgraph_workflow(
    config: WorkflowConfig,
    generator: CodeGeneratorAgent,
    reviewer: CodeReviewerAgent,
    validator: Optional[ValidatorAgent] = None
):
    """Compiles and returns a LangGraph StateGraph instance."""
    if not LANGGRAPH_AVAILABLE:
        raise ImportError("langgraph is not installed. Install via pip install langgraph")

    workflow = StateGraph(AgentGraphState)

    # Node 1: Initial Generator
    def node_generate_initial(state: AgentGraphState) -> Dict[str, Any]:
        code, explanation, _ = generator.generate_initial(
            task_prompt=state["task_prompt"],
            target_language=state.get("target_language", "python"),
            unit_tests=state.get("unit_tests")
        )
        return {
            "current_code": code,
            "explanation": explanation,
            "current_round": 0,
            "reviews": []
        }

    # Node 2: Sandbox Verification
    def node_execute(state: AgentGraphState) -> Dict[str, Any]:
        res = run_code_with_tests(
            code=state["current_code"],
            unit_tests=state.get("unit_tests"),
            language=state.get("target_language", "python"),
            timeout_seconds=config.sandbox_timeout_seconds
        )
        return {"execution_result": res.model_dump()}

    # Node 3: Reviewer Inspection
    def node_review(state: AgentGraphState) -> Dict[str, Any]:
        exec_model = ExecutionResult(**state["execution_result"]) if state.get("execution_result") else None
        review = reviewer.review_code(
            task_prompt=state["task_prompt"],
            current_code=state["current_code"],
            target_language=state.get("target_language", "python"),
            execution_result=exec_model
        )
        return {"reviews": [review.model_dump()]}

    # Node 4: Validator (LLM 3)
    def node_validate(state: AgentGraphState) -> Dict[str, Any]:
        reviews = list(state.get("reviews", []))
        if validator and config.enable_third_llm_validator:
            primary_rev = ReviewFeedback(**reviews[0]) if reviews else None
            val_review = validator.validate_code(
                task_prompt=state["task_prompt"],
                current_code=state["current_code"],
                target_language=state.get("target_language", "python"),
                primary_review=primary_rev
            )
            reviews.append(val_review.model_dump())
        
        # Check approval
        has_bugs = any(r.get("has_bugs", False) for r in reviews)
        exec_ok = state.get("execution_result", {}).get("success", True)
        approved = not has_bugs and exec_ok

        return {
            "reviews": reviews,
            "is_approved": approved,
            "status": "APPROVED" if approved else "CHANGES_REQUESTED"
        }

    # Node 5: Iterative Fixer
    def node_fix(state: AgentGraphState) -> Dict[str, Any]:
        next_round = state["current_round"] + 1
        exec_model = ExecutionResult(**state["execution_result"]) if state.get("execution_result") else None
        rev_models = [ReviewFeedback(**r) for r in state.get("reviews", [])]

        fixed_code, summary, _ = generator.fix_code(
            task_prompt=state["task_prompt"],
            current_code=state["current_code"],
            target_language=state.get("target_language", "python"),
            execution_result=exec_model,
            reviews=rev_models
        )

        return {
            "previous_code": state["current_code"],
            "current_code": fixed_code,
            "explanation": summary,
            "current_round": next_round,
            "reviews": []
        }

    # Conditional Routing
    def route_decision(state: AgentGraphState) -> str:
        if state.get("is_approved", False):
            return "end"
        if state["current_round"] >= state["max_retries"]:
            return "end"
        return "fix"

    # Add nodes to graph
    workflow.add_node("generate_initial", node_generate_initial)
    workflow.add_node("execute", node_execute)
    workflow.add_node("review", node_review)
    workflow.add_node("validate", node_validate)
    workflow.add_node("fix", node_fix)

    # Set flow edges
    workflow.set_entry_point("generate_initial")
    workflow.add_edge("generate_initial", "execute")
    workflow.add_edge("execute", "review")
    workflow.add_edge("review", "validate")

    workflow.add_conditional_edges(
        "validate",
        route_decision,
        {
            "end": END,
            "fix": "fix"
        }
    )
    workflow.add_edge("fix", "execute")

    return workflow.compile()
