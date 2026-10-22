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


class AgentGraphState(TypedDict, total=False):
    """
    Typed shared state for the LangGraph StateGraph workflow.
    Preserves all evidence, iteration snapshots, and status transitions.
    """
    run_id: str
    task_description: str
    task_prompt: str
    input_mode: str  # "generate", "existing_code", "upload_project"
    target_language: str
    unit_tests: Optional[str]
    existing_code: Optional[str]
    uploaded_files_metadata: Optional[List[Dict[str, Any]]]
    original_source_files: Optional[Dict[str, str]]
    working_source_files: Optional[Dict[str, str]]

    # Models & Config
    generator_model: str
    reviewer_model: str
    validator_model: Optional[str]
    validator_configuration: Optional[Dict[str, Any]]
    current_round: int
    current_attempt: int
    max_retries: int
    max_attempts: int

    # Code versions
    current_code: str
    generated_code: str
    previous_code: Optional[str]
    explanation: str

    # Verification Evidence
    syntax_result: Optional[Dict[str, Any]]
    validation_results: Optional[Dict[str, Any]]
    execution_result: Optional[Dict[str, Any]]
    test_results: Optional[Dict[str, Any]]
    test_status: str  # "PASS", "FAIL", "ERROR", "NOT_RUN"
    reviews: List[Dict[str, Any]]
    reviewer_findings: List[Dict[str, Any]]
    
    # Decisions, Stage & History
    current_stage: str
    is_approved: bool
    status: str
    acceptance_status: str
    final_status: str
    stop_reason: str
    iteration_history: List[Dict[str, Any]]
    workflow_errors: List[str]
    started_at: str
    completed_at: Optional[str]
    duration: float
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
    Implements the full architecture:
    START -> Validate Request -> Analyze Input -> Generator Agent ->
    Syntax / Static Validation -> Reviewer Agent -> Validator Agent ->
    Evaluate Acceptance Criteria:
        -> If issues remain and retries remain: Generator Fix -> Loop to Syntax/Static
        -> If all pass: Save Final Result -> END
        -> If retries exhausted: Save Partial Result -> END
        -> If error: Record Error -> END
    """
    if not LANGGRAPH_AVAILABLE:
        raise ImportError("langgraph is not installed. Install via pip install langgraph")

    # Fallback validator if none supplied
    actual_validator = validator or ValidatorAgent(generator.provider)

    def _emit(event_name: str, state: AgentGraphState, stage: str, message: str, metadata: Optional[Dict[str, Any]] = None):
        if on_event and callable(on_event):
            try:
                evt_dict = {
                    "run_id": state.get("run_id") or "run_default",
                    "event_type": event_name,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "attempt_number": state.get("current_round", 0) + 1,
                    "stage": stage,
                    "message": message,
                    "metadata": metadata or {},
                }
                on_event(event_name, evt_dict)
            except Exception:
                pass

    workflow = StateGraph(AgentGraphState)

    # ─────────────────────────────────────────────────────────────────────────
    # Node 1: Validate Request
    # ─────────────────────────────────────────────────────────────────────────
    def node_validate_request(state: AgentGraphState) -> Dict[str, Any]:
        run_id = state.get("run_id") or f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        task_prompt = (state.get("task_description") or state.get("task_prompt") or "").strip()
        existing = (state.get("existing_code") or "").strip()

        _emit("run_started", state, "VALIDATE_REQUEST", f"Initiated workflow run {run_id}", {"run_id": run_id})

        errors: List[str] = list(state.get("workflow_errors") or [])
        if not task_prompt and not existing:
            err = "Task specification or source code must be provided."
            errors.append(err)
            _emit("run_failed", state, "VALIDATE_REQUEST", err, {"error": err})
            return {"run_id": run_id, "current_stage": "VALIDATE_REQUEST", "workflow_errors": errors}

        input_mode = state.get("input_mode") or ("existing_code" if existing else "generate")
        _emit("input_validated", state, "VALIDATE_REQUEST", f"Validated input in '{input_mode}' mode", {"mode": input_mode})

        return {
            "run_id": run_id,
            "current_stage": "VALIDATE_REQUEST",
            "input_mode": input_mode,
            "workflow_errors": errors,
            "started_at": state.get("started_at") or datetime.now(timezone.utc).isoformat(),
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Node 2: Analyze Input
    # ─────────────────────────────────────────────────────────────────────────
    def node_analyze_input(state: AgentGraphState) -> Dict[str, Any]:
        existing = state.get("existing_code") or ""
        meta_info: Dict[str, Any] = {}
        if existing.strip():
            lines = len(existing.splitlines())
            syn_info = actual_validator.validate_syntax(existing, state.get("target_language", "python"))
            meta_info = {
                "lines": lines,
                "functions": syn_info.get("metadata", {}).get("num_functions", 0),
                "classes": syn_info.get("metadata", {}).get("num_classes", 0),
                "has_tests": bool(state.get("unit_tests")),
            }
            _emit("files_analyzed", state, "ANALYZE_INPUT", f"Analyzed input source: {lines} lines, {meta_info['functions']} functions", meta_info)
        else:
            _emit("files_analyzed", state, "ANALYZE_INPUT", "Task requirements analyzed for initial generation", {"mode": "generate"})

        return {
            "current_stage": "ANALYZE_INPUT",
            "validator_configuration": state.get("validator_configuration") or {
                "enable_sandbox": config.enable_sandbox_execution,
                "timeout": config.sandbox_timeout_seconds,
            }
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Node 3: Generator Agent (LLM 1)
    # ─────────────────────────────────────────────────────────────────────────
    def node_generator_agent(state: AgentGraphState) -> Dict[str, Any]:
        existing = state.get("existing_code")
        round_idx = state.get("current_round", 0)

        if existing and existing.strip() and not state.get("current_code"):
            code = existing.strip()
            explanation = "Ingested original codebase for audit, security hardening, and optimization."
            _emit("generator_completed", state, "GENERATOR", f"Adopted original source code ({len(code.splitlines())} lines)", {"lines": len(code.splitlines())})
        else:
            _emit("generator_started", state, "GENERATOR", f"LLM 1 ({generator.model_name}) synthesizing code solution...", {"model": generator.model_name})
            t_prompt = state.get("task_description") or state.get("task_prompt", "")
            code, explanation, _ = generator.generate_initial(
                task_prompt=t_prompt,
                target_language=state.get("target_language", "python"),
                unit_tests=state.get("unit_tests")
            )
            _emit("generator_completed", state, "GENERATOR", f"LLM 1 generated initial code candidate ({len(code.splitlines())} lines)", {"model": generator.model_name})

        snapshot = {
            "round": round_idx,
            "code": code,
            "explanation": explanation,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        history = list(state.get("iteration_history") or [])
        if not history:
            history.append(snapshot)

        return {
            "current_code": code,
            "generated_code": code,
            "explanation": explanation,
            "current_round": round_idx,
            "current_attempt": round_idx + 1,
            "current_stage": "GENERATOR",
            "reviews": [],
            "reviewer_findings": [],
            "iteration_history": history,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Node 4: Syntax & Static Validation
    # ─────────────────────────────────────────────────────────────────────────
    def node_syntax_static_validation(state: AgentGraphState) -> Dict[str, Any]:
        cur_round = state.get("current_round", 0)
        _emit("syntax_check_started", state, "SYNTAX_STATIC", f"Verifying Python AST syntax (Round {cur_round + 1})...", {"round": cur_round})

        code = state.get("current_code", "")
        syn_result = actual_validator.validate_syntax(code, state.get("target_language", "python"))
        static_result = actual_validator.run_static_analysis(code, enabled=True)

        _emit("syntax_check_completed", state, "SYNTAX_STATIC", 
              f"AST Syntax {'Valid' if syn_result['valid'] else 'Invalid'}. Static clean: {static_result.get('is_clean')}", 
              {"valid": syn_result["valid"], "static_clean": static_result.get("is_clean")})

        return {
            "syntax_result": syn_result,
            "validation_results": static_result,
            "current_stage": "SYNTAX_STATIC",
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Node 5: Reviewer Agent (LLM 2)
    # ─────────────────────────────────────────────────────────────────────────
    def node_reviewer_agent(state: AgentGraphState) -> Dict[str, Any]:
        cur_round = state.get("current_round", 0)
        _emit("reviewer_started", state, "REVIEWER", f"LLM 2 ({reviewer.model_name}) reviewing code...", {"model": reviewer.model_name, "round": cur_round})

        exec_model = ExecutionResult(**state["execution_result"]) if state.get("execution_result") else None
        t_prompt = state.get("task_description") or state.get("task_prompt", "")
        review = reviewer.review_code(
            task_prompt=t_prompt,
            current_code=state["current_code"],
            target_language=state.get("target_language", "python"),
            execution_result=exec_model
        )

        _emit("reviewer_completed", state, "REVIEWER", 
              f"LLM 2 Verdict: {review.verdict or review.status.value} ({len(review.bugs)} issues identified)", 
              {"verdict": review.verdict or review.status.value, "bugs_count": len(review.bugs)})

        rev_dict = review.model_dump()
        return {
            "reviews": [rev_dict],
            "reviewer_findings": rev_dict.get("bugs", []),
            "current_stage": "REVIEWER",
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Node 6: Validator Agent (Sandbox Execution & Arbiter)
    # ─────────────────────────────────────────────────────────────────────────
    def node_validator_agent(state: AgentGraphState) -> Dict[str, Any]:
        cur_round = state.get("current_round", 0)
        unit_tests = state.get("unit_tests")

        _emit("validator_started", state, "VALIDATOR", "Agent C validating execution and testing evidence...", {"round": cur_round})

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
            _emit("tests_started", state, "VALIDATOR", f"Executing tests in isolated sandbox (Round {cur_round + 1})...", {"round": cur_round})
            res = actual_validator.run_sandbox_tests(
                code=state["current_code"],
                unit_tests=unit_tests,
                language=state.get("target_language", "python"),
                timeout_seconds=config.sandbox_timeout_seconds
            )
            test_status = "PASS" if res.success else "FAIL"
            exec_dict = res.model_dump()
            _emit("tests_completed", state, "VALIDATOR", f"Sandbox tests finished: {test_status} (exit code {res.exit_code})", {"status": test_status, "exit_code": res.exit_code})

        reviews = list(state.get("reviews", []))
        if validator and config.enable_third_llm_validator:
            primary_rev = ReviewFeedback(**reviews[0]) if reviews else None
            val_task = state.get("task_description") or state.get("task_prompt", "")
            val_review = validator.validate_code(
                task_prompt=val_task,
                current_code=state["current_code"],
                target_language=state.get("target_language", "python"),
                primary_review=primary_rev
            )
            reviews.append(val_review.model_dump())

        return {
            "execution_result": exec_dict,
            "test_results": exec_dict.get("test_results", {}),
            "test_status": test_status,
            "reviews": reviews,
            "current_stage": "VALIDATOR",
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Node 7: Evaluate Acceptance Criteria
    # ─────────────────────────────────────────────────────────────────────────
    def node_evaluate_acceptance(state: AgentGraphState) -> Dict[str, Any]:
        cur_round = state.get("current_round", 0)
        max_r = state.get("max_retries", config.max_retries)
        unit_tests_provided = bool(state.get("unit_tests") and state.get("unit_tests", "").strip())
        
        exec_model = ExecutionResult(**state["execution_result"]) if state.get("execution_result") else None
        reviews = [ReviewFeedback(**r) for r in state.get("reviews", [])]
        primary_rev = reviews[0] if reviews else None
        val_rev = reviews[1] if len(reviews) > 1 else None

        syn_dict = state.get("syntax_result") or {"valid": True}

        eval_res = actual_validator.evaluate_acceptance_evidence(
            syntax_res=syn_dict,
            test_res=exec_model,
            unit_tests_provided=unit_tests_provided,
            primary_review=primary_rev,
            validator_review=val_rev,
            current_attempt=cur_round,
            max_attempts=max_r,
            strict_mode=True,
        )

        is_approved = eval_res["all_criteria_met"]
        acc_status = eval_res["acceptance_status"]
        status = "APPROVED" if is_approved else ("MAX_RETRIES_REACHED" if cur_round >= max_r else "CHANGES_REQUESTED")

        _emit("iteration_completed", state, "EVALUATE_ACCEPTANCE", 
              f"Round {cur_round + 1} completed. Approved: {is_approved}. Acceptance: {acc_status}",
              {"round": cur_round + 1, "is_approved": is_approved, "acceptance": acc_status})

        return {
            "is_approved": is_approved,
            "acceptance_status": acc_status,
            "status": status,
            "test_status": eval_res["test_status"],
            "current_stage": "EVALUATE_ACCEPTANCE",
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Node 8: Generator Fix / Self-Correction (LLM 1)
    # ─────────────────────────────────────────────────────────────────────────
    def node_generator_fix(state: AgentGraphState) -> Dict[str, Any]:
        next_round = state["current_round"] + 1
        _emit("correction_started", state, "GENERATOR_FIX", f"Applying corrections for Round {next_round + 1}...", {"round": next_round})

        exec_model = ExecutionResult(**state["execution_result"]) if state.get("execution_result") else None
        rev_models = [ReviewFeedback(**r) for r in state.get("reviews", [])]

        t_prompt = state.get("task_description") or state.get("task_prompt", "")
        fixed_code, summary, _ = generator.fix_code(
            task_prompt=t_prompt,
            current_code=state["current_code"],
            target_language=state.get("target_language", "python"),
            execution_result=exec_model,
            reviews=rev_models
        )
        _emit("correction_completed", state, "GENERATOR_FIX", f"Targeted corrections applied ({len(fixed_code.splitlines())} lines)", {"round": next_round})

        history = list(state.get("iteration_history") or [])
        history.append({
            "round": next_round,
            "code": fixed_code,
            "explanation": summary,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

        return {
            "previous_code": state["current_code"],
            "current_code": fixed_code,
            "generated_code": fixed_code,
            "explanation": summary,
            "current_round": next_round,
            "current_attempt": next_round + 1,
            "reviews": [],
            "reviewer_findings": [],
            "iteration_history": history,
            "current_stage": "GENERATOR_FIX",
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Node 9: Save Final Result
    # ─────────────────────────────────────────────────────────────────────────
    def node_save_final_result(state: AgentGraphState) -> Dict[str, Any]:
        cur_round = state.get("current_round", 0)
        stop_reason = "All acceptance criteria verified and approved by reviewers."
        _emit("run_completed", state, "FINAL_ACCEPTANCE", f"Workflow approved in {cur_round + 1} round(s)", {"status": "APPROVED"})

        return {
            "status": "APPROVED",
            "final_status": "APPROVED",
            "acceptance_status": AcceptanceStatus.FINAL_ACCEPTED.value,
            "stop_reason": stop_reason,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "current_stage": "TERMINAL_COMPLETE",
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Node 10: Save Partial Result (Retry Limit Reached)
    # ─────────────────────────────────────────────────────────────────────────
    def node_save_partial_result(state: AgentGraphState) -> Dict[str, Any]:
        max_r = state.get("max_retries", config.max_retries)
        stop_reason = f"Maximum review limit of {max_r} iterations reached with unresolved issues."
        _emit("retry_limit_reached", state, "RETRY_LIMIT", stop_reason, {"max_retries": max_r})
        _emit("run_completed", state, "RETRY_LIMIT", "Workflow terminated with partial results.", {"status": "MAX_RETRIES_REACHED"})

        return {
            "status": "MAX_RETRIES_REACHED",
            "final_status": "MAX_RETRIES_REACHED",
            "acceptance_status": AcceptanceStatus.RETRY_LIMIT_REACHED.value,
            "stop_reason": stop_reason,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "current_stage": "TERMINAL_PARTIAL",
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Node 11: Record Error
    # ─────────────────────────────────────────────────────────────────────────
    def node_record_error(state: AgentGraphState) -> Dict[str, Any]:
        errors = state.get("workflow_errors") or ["Fatal workflow failure occurred."]
        stop_reason = f"Halted with errors: {'; '.join(errors)}"
        _emit("run_failed", state, "RECORD_ERROR", stop_reason, {"errors": errors})

        return {
            "status": "FAILED",
            "final_status": "FAILED",
            "acceptance_status": AcceptanceStatus.FAILED.value,
            "stop_reason": stop_reason,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "current_stage": "TERMINAL_ERROR",
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Conditional Edge Routing
    # ─────────────────────────────────────────────────────────────────────────
    def route_request(state: AgentGraphState) -> str:
        if state.get("workflow_errors"):
            return "record_error"
        return "analyze_input"

    def route_acceptance(state: AgentGraphState) -> str:
        if state.get("workflow_errors"):
            return "record_error"
        if state.get("is_approved", False):
            return "save_final_result"
        if state.get("current_round", 0) >= state.get("max_retries", config.max_retries):
            return "save_partial_result"
        return "generator_fix"

    # Add all specialized nodes to graph
    workflow.add_node("validate_request", node_validate_request)
    workflow.add_node("analyze_input", node_analyze_input)
    workflow.add_node("generator_agent", node_generator_agent)
    workflow.add_node("syntax_static_validation", node_syntax_static_validation)
    workflow.add_node("reviewer_agent", node_reviewer_agent)
    workflow.add_node("validator_agent", node_validator_agent)
    workflow.add_node("evaluate_acceptance", node_evaluate_acceptance)
    workflow.add_node("generator_fix", node_generator_fix)
    workflow.add_node("save_final_result", node_save_final_result)
    workflow.add_node("save_partial_result", node_save_partial_result)
    workflow.add_node("record_error", node_record_error)

    # Topology
    workflow.set_entry_point("validate_request")
    workflow.add_conditional_edges(
        "validate_request",
        route_request,
        {
            "record_error": "record_error",
            "analyze_input": "analyze_input"
        }
    )
    workflow.add_edge("analyze_input", "generator_agent")
    workflow.add_edge("generator_agent", "syntax_static_validation")
    workflow.add_edge("syntax_static_validation", "reviewer_agent")
    workflow.add_edge("reviewer_agent", "validator_agent")
    workflow.add_edge("validator_agent", "evaluate_acceptance")

    # Conditional branching from acceptance evaluation
    workflow.add_conditional_edges(
        "evaluate_acceptance",
        route_acceptance,
        {
            "save_final_result": "save_final_result",
            "save_partial_result": "save_partial_result",
            "generator_fix": "generator_fix",
            "record_error": "record_error"
        }
    )

    # Loop back from fix to syntax/static
    workflow.add_edge("generator_fix", "syntax_static_validation")
    workflow.add_edge("save_final_result", END)
    workflow.add_edge("save_partial_result", END)
    workflow.add_edge("record_error", END)

    return workflow.compile()
