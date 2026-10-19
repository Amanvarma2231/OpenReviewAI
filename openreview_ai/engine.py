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
    ReviewStatus
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

    def run(
        self,
        task_prompt: str,
        target_language: str = "python",
        unit_tests: Optional[str] = None,
        on_event: Optional[Callable[[str, dict], None]] = None
    ) -> WorkflowResult:
        """
        Executes the full multi-LLM review and correction loop.
        
        Args:
            task_prompt: The coding prompt or user requirement.
            target_language: Target programming language (default: python).
            unit_tests: Optional unit test assertions for automated verification.
            on_event: Optional callback function receiving (event_name, data_dict).
        """
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
        # STEP 1: Initial Code Generation by LLM 1
        # ==========================================
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
            provider=self.config.provider_type
        )

        emit("workflow_completed", {
            "status": final_result.status,
            "rounds": final_result.rounds_count,
            "bugs_detected": total_detected,
            "bugs_fixed": total_fixed
        })
        return final_result
