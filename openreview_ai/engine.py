import time
from typing import Callable, Optional, List
from openreview_ai.config import WorkflowConfig
from openreview_ai.schema import (
    ReviewState,
    WorkflowResult,
    IterationStep,
    AgentMessage,
    ReviewFeedback,
    ExecutionResult,
    ReviewStatus,
    AcceptanceStatus
)
from openreview_ai.agents.generator import CodeGeneratorAgent
from openreview_ai.agents.reviewer import CodeReviewerAgent
from openreview_ai.agents.validator import ValidatorAgent
from openreview_ai.providers.factory import get_provider
from openreview_ai.sandbox.test_runner import run_code_with_tests


class WorkflowOrchestrator:
    """
    Core Multi-LLM Review and Iterative Correction Workflow Orchestrator.
    Manages communication, review cycles, sandbox testing, and termination conditions.
    """

    def __init__(
        self,
        config: Optional[WorkflowConfig] = None,
        generator_agent: Optional[CodeGeneratorAgent] = None,
        reviewer_agent: Optional[CodeReviewerAgent] = None,
        validator_agent: Optional[ValidatorAgent] = None,
    ):
        self.config = config or WorkflowConfig()
        
        # Instantiate agents if not provided
        if generator_agent:
            self.generator = generator_agent
        else:
            provider = get_provider(
                provider_type=self.config.provider_type,
                model_name=self.config.generator_model,
                base_url=self.config.ollama_base_url if self.config.provider_type == "ollama" else self.config.openai_compat_base_url,
                api_key=self.config.openai_compat_api_key or self.config.hf_token
            )
            self.generator = CodeGeneratorAgent(provider, role_name="LLM 1 (Generator)")

        if reviewer_agent:
            self.reviewer = reviewer_agent
        else:
            provider = get_provider(
                provider_type=self.config.provider_type,
                model_name=self.config.reviewer_model,
                base_url=self.config.ollama_base_url if self.config.provider_type == "ollama" else self.config.openai_compat_base_url,
                api_key=self.config.openai_compat_api_key or self.config.hf_token
            )
            self.reviewer = CodeReviewerAgent(provider, role_name="LLM 2 (Reviewer)")

        if validator_agent:
            self.validator = validator_agent
        elif self.config.enable_third_llm_validator and self.config.validator_model:
            provider = get_provider(
                provider_type=self.config.provider_type,
                model_name=self.config.validator_model,
                base_url=self.config.ollama_base_url if self.config.provider_type == "ollama" else self.config.openai_compat_base_url,
                api_key=self.config.openai_compat_api_key or self.config.hf_token
            )
            self.validator = ValidatorAgent(provider, role_name="LLM 3 (Validator)")
        else:
            self.validator = None

    def _run_langgraph(
        self,
        task_prompt: str,
        target_language: str = "python",
        unit_tests: Optional[str] = None,
        existing_code: Optional[str] = None,
        on_event: Optional[Callable[[str, dict], None]] = None,
    ) -> WorkflowResult:
        from openreview_ai.langgraph_workflow import build_langgraph_workflow
        import uuid
        from datetime import datetime, timezone

        run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        now_iso = datetime.now(timezone.utc).isoformat()

        initial_state = {
            "run_id": run_id,
            "task_description": task_prompt,
            "task_prompt": task_prompt,
            "input_mode": "existing_code" if existing_code else "generate",
            "target_language": target_language,
            "unit_tests": unit_tests,
            "existing_code": existing_code,
            "generator_model": self.generator.model_name,
            "reviewer_model": self.reviewer.model_name,
            "validator_model": self.validator.model_name if self.validator else None,
            "validator_configuration": {
                "enable_sandbox": self.config.enable_sandbox_execution,
                "timeout": self.config.sandbox_timeout_seconds,
            },
            "current_round": 0,
            "current_attempt": 1,
            "max_retries": self.config.max_retries,
            "max_attempts": self.config.max_retries,
            "current_code": "",
            "generated_code": "",
            "previous_code": None,
            "explanation": "",
            "syntax_result": None,
            "validation_results": None,
            "execution_result": None,
            "test_results": None,
            "test_status": "NOT_RUN",
            "reviews": [],
            "reviewer_findings": [],
            "current_stage": "START",
            "is_approved": False,
            "status": "PENDING",
            "acceptance_status": AcceptanceStatus.NOT_RUN.value,
            "final_status": "PENDING",
            "stop_reason": "",
            "iteration_history": [],
            "workflow_errors": [],
            "started_at": now_iso,
            "completed_at": None,
            "duration": 0.0,
            "duration_seconds": 0.0,
        }

        app = build_langgraph_workflow(
            config=self.config,
            generator=self.generator,
            reviewer=self.reviewer,
            validator=self.validator,
            on_event=on_event,
        )
        final_state = app.invoke(initial_state)

        # Translate final_state into WorkflowResult
        iterations: List[IterationStep] = []
        messages: List[AgentMessage] = []
        history = final_state.get("iteration_history") or []
        reviews_data = final_state.get("reviews") or []

        total_bugs = 0
        for idx, snap in enumerate(history):
            rnd = snap.get("round", idx)
            code = snap.get("code", final_state.get("current_code", ""))
            expl = snap.get("explanation", "")

            ex_model = None
            if final_state.get("execution_result"):
                ex_model = ExecutionResult(**final_state["execution_result"])

            rev_models = [ReviewFeedback(**r) for r in reviews_data]
            bugs_in_round = sum(len(r.bugs) for r in rev_models)
            total_bugs += bugs_in_round

            iterations.append(IterationStep(
                round_idx=rnd,
                code=code,
                generator_explanation=expl,
                execution=ex_model,
                reviews=rev_models,
                status="APPROVED" if final_state.get("is_approved") and idx == len(history) - 1 else "CHANGES_REQUESTED",
                open_bug_count=bugs_in_round,
            ))

            messages.append(AgentMessage(
                sender_role="Generator",
                sender_model=self.generator.model_name,
                round_idx=rnd,
                content=f"Code generation snapshot:\n{expl}",
                metadata={"code": code}
            ))
            if rev_models:
                messages.append(AgentMessage(
                    sender_role="Reviewer",
                    sender_model=self.reviewer.model_name,
                    round_idx=rnd,
                    content=f"Review assessment: Status={rev_models[0].status.value}\nSummary: {rev_models[0].summary}",
                    metadata={"verdict": rev_models[0].verdict or rev_models[0].status.value}
                ))

        acc_st = final_state.get("acceptance_status", AcceptanceStatus.NOT_RUN.value)
        try:
            acc_enum = AcceptanceStatus(acc_st)
        except Exception:
            acc_enum = AcceptanceStatus.NOT_RUN

        fin_status = final_state.get("status", "APPROVED" if final_state.get("is_approved") else "FAILED")

        return WorkflowResult(
            task_prompt=task_prompt,
            target_language=target_language,
            final_code=final_state.get("current_code", ""),
            status=fin_status,
            rounds_count=max(1, len(history)),
            iterations=iterations,
            messages=messages,
            total_bugs_detected=total_bugs,
            total_bugs_fixed=total_bugs if fin_status == "APPROVED" else max(0, total_bugs - 1),
            final_execution=ExecutionResult(**final_state["execution_result"]) if final_state.get("execution_result") else None,
            generator_model=self.generator.model_name,
            reviewer_model=self.reviewer.model_name,
            validator_model=self.validator.model_name if self.validator else None,
            provider=self.config.provider_type,
            acceptance_status=acc_enum,
            test_status=final_state.get("test_status", "NOT_RUN"),
        )

    def run(
        self,
        task_prompt: str,
        target_language: str = "python",
        unit_tests: Optional[str] = None,
        existing_code: Optional[str] = None,
        on_event: Optional[Callable[[str, dict], None]] = None
    ) -> WorkflowResult:
        """
        Executes the full multi-LLM review and correction loop.
        Dispatches to LangGraph StateGraph if configured, otherwise uses direct engine.
        """
        if getattr(self.config, "orchestrator_engine", "langgraph") == "langgraph":
            try:
                from openreview_ai.langgraph_workflow import LANGGRAPH_AVAILABLE
                if LANGGRAPH_AVAILABLE:
                    return self._run_langgraph(
                        task_prompt=task_prompt,
                        target_language=target_language,
                        unit_tests=unit_tests,
                        existing_code=existing_code,
                        on_event=on_event,
                    )
            except Exception:
                # Safe fallback to direct engine on any graph failure
                pass

        def emit(event_name: str, data: dict):
            if on_event:
                try:
                    on_event(event_name, data)
                except Exception:
                    pass

        # Initialize State
        state = ReviewState(
            task_prompt=task_prompt,
            target_language=target_language,
            unit_tests=unit_tests,
            max_retries=self.config.max_retries
        )

        emit("workflow_started", {
            "task": task_prompt,
            "generator": self.generator.model_name,
            "reviewer": self.reviewer.model_name,
            "validator": self.validator.model_name if self.validator else None,
            "max_retries": self.config.max_retries
        })

        # ==========================================
        # STEP 1: Code Ingestion / Initial Generation
        # ==========================================
        if existing_code and existing_code.strip():
            initial_code = existing_code.strip()
            explanation = "Loaded existing source file for audit and auto-repair."
            state.current_code = initial_code
            state.messages.append(AgentMessage(
                sender_role="User/System",
                sender_model="Original Code",
                round_idx=0,
                content=explanation,
                metadata={"code": initial_code}
            ))
            emit("generation_completed", {"round": 0, "code": initial_code, "explanation": explanation})
        else:
            emit("generation_started", {"round": 0, "agent": self.generator.role_name})
            initial_code, explanation, raw_gen = self.generator.generate_initial(
                task_prompt=task_prompt,
                target_language=target_language,
                unit_tests=unit_tests,
                temperature=self.config.temperature
            )
            state.current_code = initial_code

            state.messages.append(AgentMessage(
                sender_role="Generator",
                sender_model=self.generator.model_name,
                round_idx=0,
                content=f"Initial code generated:\n\n{explanation}",
                metadata={"code": initial_code}
            ))
            emit("generation_completed", {"round": 0, "code": initial_code, "explanation": explanation})

        # ==========================================
        # STEP 2: Iterative Review & Correction Loop
        # ==========================================
        total_detected = 0
        total_fixed = 0

        while state.current_round <= self.config.max_retries:
            round_idx = state.current_round
            step = IterationStep(
                round_idx=round_idx,
                code=state.current_code,
                generator_explanation=explanation
            )

            # 2.1 Automated Sandbox Verification
            exec_result = None
            if self.config.enable_sandbox_execution:
                emit("execution_started", {"round": round_idx})
                exec_result = run_code_with_tests(
                    code=state.current_code,
                    unit_tests=unit_tests,
                    language=target_language,
                    timeout_seconds=self.config.sandbox_timeout_seconds
                )
                step.execution = exec_result
                state.execution_result = exec_result
                emit("execution_completed", {"round": round_idx, "success": exec_result.success, "stderr": exec_result.stderr})

            # 2.2 LLM 2 Review
            emit("review_started", {"round": round_idx, "agent": self.reviewer.role_name})
            rev_feedback = self.reviewer.review_code(
                task_prompt=task_prompt,
                current_code=state.current_code,
                target_language=target_language,
                execution_result=exec_result,
                temperature=0.1
            )
            step.reviews.append(rev_feedback)
            state.messages.append(AgentMessage(
                sender_role="Reviewer",
                sender_model=self.reviewer.model_name,
                round_idx=round_idx,
                content=f"Review Assessment: Status={rev_feedback.status}, Score={rev_feedback.overall_score}/10\nSummary: {rev_feedback.summary}",
                metadata={"has_bugs": rev_feedback.has_bugs, "bugs_count": len(rev_feedback.bugs)}
            ))
            emit("review_completed", {"round": round_idx, "review": rev_feedback.model_dump()})

            # 2.3 Optional LLM 3 Secondary Validation & Security Audit
            val_feedback = None
            if self.validator and self.config.enable_third_llm_validator:
                emit("validation_started", {"round": round_idx, "agent": self.validator.role_name})
                val_feedback = self.validator.validate_code(
                    task_prompt=task_prompt,
                    current_code=state.current_code,
                    target_language=target_language,
                    primary_review=rev_feedback,
                    temperature=0.1
                )
                step.reviews.append(val_feedback)
                state.messages.append(AgentMessage(
                    sender_role="Validator",
                    sender_model=self.validator.model_name,
                    round_idx=round_idx,
                    content=f"Security & Arbiter Assessment: Status={val_feedback.status}\nSummary: {val_feedback.summary}",
                    metadata={"has_bugs": val_feedback.has_bugs, "bugs_count": len(val_feedback.bugs)}
                ))
                emit("validation_completed", {"round": round_idx, "validation": val_feedback.model_dump()})

            # 2.4 Bug Aggregation and Status Assessment
            current_bugs = list(rev_feedback.bugs)
            if val_feedback:
                current_bugs.extend(val_feedback.bugs)

            # Deduplicate bugs for metrics
            step.open_bug_count = len(current_bugs)
            total_detected += len(current_bugs)
            state.all_bugs_detected.extend(current_bugs)

            # Determine whether code is clean & approved
            has_runtime_failure = exec_result is not None and not exec_result.success
            has_reviewer_bugs = rev_feedback.has_bugs or (val_feedback.has_bugs if val_feedback else False)
            is_approved = not has_runtime_failure and not has_reviewer_bugs

            if is_approved:
                step.status = "APPROVED"
                state.all_iterations.append(step)
                state.is_approved = True
                state.is_finished = True
                state.final_status = "APPROVED"
                emit("round_approved", {"round": round_idx})
                break

            # 2.5 Termination Check (Max retries reached)
            if state.current_round >= self.config.max_retries:
                step.status = "MAX_RETRIES_REACHED"
                state.all_iterations.append(step)
                state.is_finished = True
                state.final_status = "MAX_RETRIES_REACHED"
                emit("max_retries_reached", {"round": round_idx, "max_retries": self.config.max_retries})
                break

            # 2.6 Iterative Fix: Pass Feedback back to LLM 1 (Generator / Fixer)
            state.all_iterations.append(step)
            state.previous_code = state.current_code
            state.current_round += 1
            next_round = state.current_round

            emit("fix_started", {"round": next_round, "agent": self.generator.role_name, "bugs_to_fix": len(current_bugs)})
            fixed_code, explanation, raw_fix = self.generator.fix_code(
                task_prompt=task_prompt,
                current_code=state.current_code,
                target_language=target_language,
                execution_result=exec_result,
                reviews=[rev_feedback] + ([val_feedback] if val_feedback else []),
                temperature=self.config.temperature
            )
            state.current_code = fixed_code

            # Bugs fixed in this cycle
            fixed_in_this_round = len(current_bugs)
            total_fixed += fixed_in_this_round
            step.resolved_bug_count = fixed_in_this_round

            state.messages.append(AgentMessage(
                sender_role="Generator",
                sender_model=self.generator.model_name,
                round_idx=next_round,
                content=f"Fixed code addressing reviewer feedback:\n\n{explanation}",
                metadata={"code": fixed_code, "fixed_bugs_count": fixed_in_this_round}
            ))
            emit("fix_completed", {"round": next_round, "code": fixed_code, "summary": explanation})

        # Determine explicit acceptance and testing status (never claim false PASS)
        if not unit_tests:
            computed_test_status = "NOT_RUN"
        elif state.execution_result and state.execution_result.success:
            computed_test_status = "TESTS_PASSED"
        else:
            computed_test_status = "TESTS_FAILED"

        if state.is_approved:
            computed_acc_status = AcceptanceStatus.FINAL_ACCEPTED
        elif state.final_status == "MAX_RETRIES_REACHED":
            computed_acc_status = AcceptanceStatus.RETRY_LIMIT_REACHED
        else:
            computed_acc_status = AcceptanceStatus.PARTIAL

        # Final Result Compilation
        final_result = WorkflowResult(
            task_prompt=task_prompt,
            target_language=target_language,
            final_code=state.current_code,
            status=state.final_status,
            rounds_count=len(state.all_iterations),
            iterations=state.all_iterations,
            messages=state.messages,
            total_bugs_detected=total_detected,
            total_bugs_fixed=total_fixed,
            final_execution=state.execution_result,
            generator_model=self.generator.model_name,
            reviewer_model=self.reviewer.model_name,
            validator_model=self.validator.model_name if self.validator else None,
            provider=self.config.provider_type,
            acceptance_status=computed_acc_status,
            test_status=computed_test_status
        )

        emit("workflow_completed", {
            "status": final_result.status,
            "rounds": final_result.rounds_count,
            "bugs_detected": total_detected,
            "bugs_fixed": total_fixed
        })
        return final_result
