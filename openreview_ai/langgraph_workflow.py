"""
LangGraph Multi-Agent Architecture for OpenReviewAI.
====================================================
Implements StateGraph nodes, typed state, and conditional edges
for the 3-agent autonomous code generation, review, and self-correction loop.
"""

import uuid
import time
from typing import Dict, Any, TypedDict, List, Optional
from datetime import datetime, timezone

try:
    from langgraph.graph import StateGraph, END
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False

from openreview_ai.config import WorkflowConfig
from openreview_ai.schema import (
    ExecutionResult,
    ReviewFeedback,
    BugItem,
    AcceptanceStatus,
    ReviewStatus
)
from openreview_ai.agents.generator import CodeGeneratorAgent
from openreview_ai.agents.reviewer import CodeReviewerAgent
from openreview_ai.agents.validator import ValidatorAgent
from openreview_ai.sandbox.test_runner import run_code_with_tests
from openreview_ai.sandbox.syntax_checker import check_syntax


class AgentGraphState(TypedDict):
    """
    Typed shared state for the LangGraph StateGraph workflow.
    Preserves all evidence, iteration snapshots, and status transitions.
    """
    run_id: str
    task_description: str
    input_mode: str  # "generate", "existing_code", "upload_project"
    target_language: str
    unit_tests: Optional[str]
    existing_code: Optional[str]

    # Models & Config
    generator_model: str
    reviewer_model: str
    validator_model: Optional[str]
    current_round: int
    max_retries: int

    # Code versions
    current_code: str
    previous_code: Optional[str]
    explanation: str

    # Verification Evidence
    syntax_result: Optional[Dict[str, Any]]
    execution_result: Optional[Dict[str, Any]]
    test_status: str  # "PASS", "FAIL", "ERROR", "NOT_RUN"
    reviews: List[Dict[str, Any]]
    
    # Decisions & History
    is_approved: bool
    acceptance_status: str
    final_status: str
    stop_reason: str
    iteration_history: List[Dict[str, Any]]
    workflow_errors: List[str]
    started_at: str
    completed_at: Optional[str]
    duration_seconds: float


def build_langgraph_workflow(
    config: WorkflowConfig,
    generator: CodeGeneratorAgent,
    reviewer: CodeReviewerAgent,
    validator: Optional[ValidatorAgent] = None,
    on_event: Optional[Any] = None
):
    """
    Compiles and returns a production-grade LangGraph StateGraph instance.
    Implements: Ingest -> Generator -> Syntax/Static -> Reviewer -> Validator -> Acceptance -> Fix -> Loop
    """
    if not LANGGRAPH_AVAILABLE:
        raise ImportError("langgraph is not installed. Install via pip install langgraph")

    def _emit(event_name: str, data: Dict[str, Any]):
        if on_event and callable(on_event):
            try:
                on_event(event_name, data)
            except Exception:
                pass

    workflow = StateGraph(AgentGraphState)

    # ─────────────────────────────────────────────────────────────────────────
    # Node 1: Ingest & Initial Code Generation
    # ─────────────────────────────────────────────────────────────────────────
    def node_ingest_and_generate(state: AgentGraphState) -> Dict[str, Any]:
        _emit("run_started", {"run_id": state.get("run_id")})
        
        existing = state.get("existing_code")
        if existing and existing.strip():
            code = existing.strip()
            explanation = "Loaded existing source code for audit and improvisation."
            _emit("files_analyzed", {"lines": len(code.splitlines())})
        else:
            _emit("generator_started", {"model": generator.model_name, "round": 0})
            code, explanation, _ = generator.generate_initial(
                task_prompt=state["task_description"],
                target_language=state.get("target_language", "python"),
                unit_tests=state.get("unit_tests")
            )
            _emit("generator_completed", {"round": 0})

        snapshot = {
            "round": 0,
            "code": code,
            "explanation": explanation,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        return {
            "current_code": code,
            "explanation": explanation,
            "current_round": 0,
            "reviews": [],
            "iteration_history": [snapshot],
            "workflow_errors": []
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Node 2: Syntax & Static Verification Layer
    # ─────────────────────────────────────────────────────────────────────────
    def node_syntax_and_static_check(state: AgentGraphState) -> Dict[str, Any]:
        _emit("syntax_check_started", {"round": state["current_round"]})
        
        syn_res = check_syntax(state["current_code"])
        _emit("syntax_check_completed", {
            "valid": syn_res.is_valid,
            "error": syn_res.error_message
        })

        return {
            "syntax_result": {
                "valid": syn_res.is_valid,
                "error": syn_res.error_message,
                "line": syn_res.line_number
            }
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Node 3: Isolated Sandbox Test Execution
    # ─────────────────────────────────────────────────────────────────────────
    def node_execute_sandbox(state: AgentGraphState) -> Dict[str, Any]:
        unit_tests = state.get("unit_tests")
        if not unit_tests or not unit_tests.strip():
            test_status = "NOT_RUN"
            exec_dict = {
                "success": True,
                "stdout": "No automated test assertions provided.",
                "stderr": "",
                "exit_code": 0,
                "execution_time_ms": 0.0,
                "syntax_valid": True,
                "syntax_error": None
            }
        else:
            _emit("tests_started", {"round": state["current_round"]})
            res = run_code_with_tests(
                code=state["current_code"],
                unit_tests=unit_tests,
                language=state.get("target_language", "python"),
                timeout_seconds=config.sandbox_timeout_seconds
            )
            test_status = "PASS" if res.success else "FAIL"
            exec_dict = res.model_dump()
            _emit("tests_completed", {"status": test_status, "exit_code": res.exit_code})

        return {
            "execution_result": exec_dict,
            "test_status": test_status
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Node 4: Independent Reviewer Inspection (LLM 2)
    # ─────────────────────────────────────────────────────────────────────────
    def node_reviewer_inspect(state: AgentGraphState) -> Dict[str, Any]:
        _emit("reviewer_started", {"model": reviewer.model_name, "round": state["current_round"]})
        
        exec_model = ExecutionResult(**state["execution_result"]) if state.get("execution_result") else None
        review = reviewer.review_code(
            task_prompt=state["task_description"],
            current_code=state["current_code"],
            target_language=state.get("target_language", "python"),
            execution_result=exec_model
        )
        _emit("reviewer_completed", {
            "status": review.status.value,
            "has_bugs": review.has_bugs,
            "bugs_count": len(review.bugs)
        })

        return {"reviews": [review.model_dump()]}

    # ─────────────────────────────────────────────────────────────────────────
    # Node 5: Security Arbiter & Consensus Validation (LLM 3)
    # ─────────────────────────────────────────────────────────────────────────
    def node_validator_evaluate(state: AgentGraphState) -> Dict[str, Any]:
        reviews = list(state.get("reviews", []))
        
        if validator and config.enable_third_llm_validator:
            _emit("validator_started", {"model": validator.model_name, "round": state["current_round"]})
            primary_rev = ReviewFeedback(**reviews[0]) if reviews else None
            val_review = validator.validate_code(
                task_prompt=state["task_description"],
                current_code=state["current_code"],
                target_language=state.get("target_language", "python"),
                primary_review=primary_rev
            )
            reviews.append(val_review.model_dump())

        # Synthesize real acceptance criteria
        syntax_ok = state.get("syntax_result", {}).get("valid", True)
        tests_ok = (state.get("test_status") in ["PASS", "NOT_RUN"]) and state.get("execution_result", {}).get("success", True)
        no_bugs = not any(r.get("has_bugs", False) for r in reviews)

        is_approved = syntax_ok and tests_ok and no_bugs

        if is_approved:
            acc_status = AcceptanceStatus.FINAL_ACCEPTED.value
        elif not syntax_ok:
            acc_status = AcceptanceStatus.FAILED.value
        elif state.get("test_status") == "FAIL":
            acc_status = AcceptanceStatus.FAILED.value
        else:
            acc_status = AcceptanceStatus.PARTIAL.value

        return {
            "reviews": reviews,
            "is_approved": is_approved,
            "acceptance_status": acc_status
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Node 6: Iterative Code Correction (LLM 1)
    # ─────────────────────────────────────────────────────────────────────────
    def node_generator_fix(state: AgentGraphState) -> Dict[str, Any]:
        next_round = state["current_round"] + 1
        _emit("correction_started", {"round": next_round})

        exec_model = ExecutionResult(**state["execution_result"]) if state.get("execution_result") else None
        rev_models = [ReviewFeedback(**r) for r in state.get("reviews", [])]

        fixed_code, summary, _ = generator.fix_code(
            task_prompt=state["task_description"],
            current_code=state["current_code"],
            target_language=state.get("target_language", "python"),
            execution_result=exec_model,
            reviews=rev_models
        )
        _emit("correction_completed", {"round": next_round})

        history = list(state.get("iteration_history", []))
        history.append({
            "round": next_round,
            "code": fixed_code,
            "explanation": summary,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

        return {
            "previous_code": state["current_code"],
            "current_code": fixed_code,
            "explanation": summary,
            "current_round": next_round,
            "reviews": [],
            "iteration_history": history
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Node 7: Terminal Result Aggregation
    # ─────────────────────────────────────────────────────────────────────────
    def node_finalize_result(state: AgentGraphState) -> Dict[str, Any]:
        is_appr = state.get("is_approved", False)
        round_num = state.get("current_round", 0)
        max_r = state.get("max_retries", 3)

        if is_appr:
            fin_status = "APPROVED"
            stop_reason = "All acceptance criteria verified and approved by reviewers."
            acc_status = AcceptanceStatus.FINAL_ACCEPTED.value
        elif round_num >= max_r:
            fin_status = "MAX_RETRIES_REACHED"
            stop_reason = f"Maximum review limit of {max_r} iterations reached."
            acc_status = AcceptanceStatus.RETRY_LIMIT_REACHED.value
        else:
            fin_status = "FAILED"
            stop_reason = "Workflow halted unexpectedly."
            acc_status = AcceptanceStatus.FAILED.value

        _emit("run_completed", {
            "status": fin_status,
            "acceptance": acc_status,
            "rounds": round_num
        })

        return {
            "final_status": fin_status,
            "stop_reason": stop_reason,
            "acceptance_status": acc_status,
            "completed_at": datetime.now(timezone.utc).isoformat()
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Conditional Edge Routing
    # ─────────────────────────────────────────────────────────────────────────
    def route_acceptance(state: AgentGraphState) -> str:
        if state.get("is_approved", False):
            return "finalize"
        if state["current_round"] >= state["max_retries"]:
            return "finalize"
        return "fix"

    # Add all specialized nodes
    workflow.add_node("ingest_and_generate", node_ingest_and_generate)
    workflow.add_node("syntax_check", node_syntax_and_static_check)
    workflow.add_node("sandbox_execute", node_execute_sandbox)
    workflow.add_node("reviewer_inspect", node_reviewer_inspect)
    workflow.add_node("validator_evaluate", node_validator_evaluate)
    workflow.add_node("generator_fix", node_generator_fix)
    workflow.add_node("finalize", node_finalize_result)

    # Set linear flow edges
    workflow.set_entry_point("ingest_and_generate")
    workflow.add_edge("ingest_and_generate", "syntax_check")
    workflow.add_edge("syntax_check", "sandbox_execute")
    workflow.add_edge("sandbox_execute", "reviewer_inspect")
    workflow.add_edge("reviewer_inspect", "validator_evaluate")

    # Conditional branching
    workflow.add_conditional_edges(
        "validator_evaluate",
        route_acceptance,
        {
            "finalize": "finalize",
            "fix": "generator_fix"
        }
    )

    # Loop back from fix to syntax & sandbox
    workflow.add_edge("generator_fix", "syntax_check")
    workflow.add_edge("finalize", END)

    return workflow.compile()
