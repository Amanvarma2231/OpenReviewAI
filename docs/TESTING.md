# OpenReview AI — Testing & Quality Assurance Guide

## 1. Quality Assurance Strategy

OpenReview AI employs a rigorous multi-tier testing and verification methodology:
1. **Automated Test Suite (`tests/`):** 51 comprehensive tests validating the internal components, JSON parsing, error traps, timeout handling, safe workspace sandboxing, Zip Slip defenses, and multi-iteration state machine using deterministic mock responses.
2. **LangGraph StateGraph Workflow Verification (`tests/test_langgraph.py`):** Tests verifying cyclic state transitions, event emission schema compliance, bounded retry termination, failed test overrides, and error node routing.
3. **Dynamic Validation Layer (`openreview_ai/sandbox/`):** Performs runtime checks on LLM-generated code during workflow execution, enforcing empirical separation between AST syntax verification, Ruff/AST static analysis, and isolated subprocess test execution.
4. **Live Model Integration Verification:** Validates communication with local Ollama runtime and handles server faults with actionable diagnostics.

---

## 2. Complete Test Suite Inventory (51 Tests)

All 51 automated tests pass with 100% success:

### A. LangGraph StateGraph & Workflow Orchestration (`tests/test_langgraph.py`)
| Test Case | Description |
|:---|:---|
| `test_langgraph_workflow_execution` | Verifies end-to-end execution of `build_langgraph_workflow` graph through all stages (`validate_request` ➔ `analyze_input` ➔ `generator` ➔ `syntax_static` ➔ `reviewer` ➔ `validator` ➔ `evaluate_acceptance` ➔ `save_final_result`). |
| `test_langgraph_workflow_orchestrator_integration` | Verifies that `WorkflowOrchestrator(orchestrator_engine="langgraph")` correctly initializes, executes, and converts graph state to a strongly typed `WorkflowResult`. |
| `test_langgraph_event_emission_compliance` | Verifies that all graph nodes emit valid progress events matching Section 9 schema (`run_id`, `event_type`, `stage`, `attempt_number`, `message`, `metadata`). |
| `test_langgraph_failed_tests_prevent_false_pass` | Verifies that failing test assertions prevent a `FINAL_ACCEPTED` status even when generator and reviewer claim success. |
| `test_langgraph_empty_task_routes_to_record_error` | Verifies that empty prompts cleanly route to the `record_error` node and terminate safely. |

### B. Safe Workspace & Project Archive Security (`tests/test_safe_workspace.py`)
| Test Case | Description |
|:---|:---|
| `test_safe_workspace_single_file_ingestion` | Verifies safe ingestion of single Python files, metadata parsing, and immutable backup creation. |
| `test_safe_workspace_zip_extraction_and_manifest` | Verifies extraction of project ZIP archives, manifest generation, and excluded files filtering (`.git`, `__pycache__`). |
| `test_zip_slip_traversal_blocked` | **Security Audit:** Verifies that malicious ZIP entries with `../` path traversal escape sequences are blocked and raise `SecurityValidationError`. |
| `test_oversized_archive_blocked` | Verifies that archives exceeding the 15 MB threshold are rejected before extraction. |
| `test_working_file_modification_and_diff` | Verifies that edits are applied solely to the isolated working copy and produce accurate unified diffs against the immutable original. |

### C. Agent Behaviors & Responsibilities (`tests/test_agents.py`)
| Test Case | Description |
|:---|:---|
| `test_generator_agent_initial` | Verifies that Agent A (Generator) produces clean Python code from a task prompt. |
| `test_reviewer_agent_flags_bugs` | Verifies that Agent B (Reviewer) adversarially detects bugs and returns structured findings. |
| `test_reviewer_agent_approves_fixed` | Verifies that Agent B returns `PASS` verdict when defects are resolved. |
| `test_validator_agent` | Verifies Agent C (Validator) validates AST syntax, static properties, and sandbox test execution. |

### D. Review Response Parsing & Contradiction Guards (`tests/test_review_parser.py`)
| Test Case | Description |
|:---|:---|
| `test_valid_json_review_parsing` | Validates parsing of standard Section 7 structured JSON review payloads. |
| `test_markdown_wrapped_json` | Validates extraction of JSON blocks embedded in markdown commentary. |
| `test_malformed_reviewer_response_fails_explicitly` | **Critical Security Check:** Verifies that malformed model outputs fail explicitly and are NEVER treated as a PASS. |
| `test_contradictory_pass_with_issues_is_overridden_to_fail` | **Contradiction Guard:** Asserts that if a model outputs `"verdict": "PASS"` while listing critical defects or runtime failures, the parser strictly overrides the verdict to `"FAIL"`. |
| `test_empty_reviewer_response` | Validates graceful recovery and explicit error handling on empty reviewer outputs. |

### E. Sandboxing & Isolated Execution (`tests/test_sandbox.py`)
| Test Case | Description |
|:---|:---|
| `test_syntax_checker_valid` | Verifies clean AST parsing on valid Python functions. |
| `test_syntax_checker_invalid` | Verifies that syntax errors return line numbers and error descriptions. |
| `test_executor_success` | Verifies successful execution in disposable subprocess with captured stdout. |
| `test_executor_runtime_error` | Verifies capture of runtime exceptions and stderr. |
| `test_executor_timeout_protection` | **Sandboxing:** Verifies that infinite loops (`while True`) are terminated by the 5-second kill timer. |
| `test_test_runner_pass` | Verifies unit test runner reports `tests_passed: True` when assertions pass. |
| `test_test_runner_assertion_fail` | Verifies unit test runner reports `tests_passed: False` and captures assertion failure trace. |

### F. Multi-Round Correction Workflow (`tests/test_workflow.py` & `tests/test_engine_workflow.py`)
| Test Case | Description |
|:---|:---|
| `test_empty_task_returns_error` | Asserts `ERROR` status and clean rejection for empty user tasks. |
| `test_successful_workflow_single_attempt` | Verifies single-pass workflow completion when code satisfies all criteria. |
| `test_correction_called_after_failed_review` | Verifies that a failed review on attempt 1 correctly invokes `generator.fix_code()` on attempt 2. |
| `test_retry_limit_reached` | Tests graceful termination when issues persist through max retries. |
| `test_test_suite_failure_triggers_validation_failed` | **Separation of Concerns:** Proves that an LLM `PASS` verdict does NOT override failed test assertions. |
| `test_workflow_orchestrator_full_loop_approval` | Verifies multi-agent orchestrator approval loop with AST and review feedback. |
| `test_workflow_orchestrator_max_retries_termination` | Verifies orchestrator stops at max_retries without runaway loops. |

### G. Local Provider & Connectivity (`tests/test_api_client.py`)
| Test Case | Description |
|:---|:---|
| `test_health_check_online` | Mocked Ollama server status probe. |
| `test_health_check_offline` | Validates graceful recovery and user advice when Ollama is offline. |
| `test_health_check_timeout` | Tests network connection timeout handling. |
| `test_list_installed_models` | Validates parsing of model tags from `/api/tags`. |
| `test_missing_model_raises_error` | Checks that requests for missing models raise `OllamaModelNotFoundError` with `ollama pull` suggestions. |
| `test_chat_timeout_raises_ollama_timeout_error` | Asserts `OllamaTimeoutError` when inference exceeds timeout limits. |
| `test_mock_mode_execution` | Tests mock provider for offline evaluations. |

### H. Persistence, Reports & Diffs (`tests/test_diff_and_report.py`, `tests/test_report_generator.py`)
| Test Case | Description |
|:---|:---|
| `test_unified_diff` | Verifies computation of unified diffs and line additions/deletions. |
| `test_markdown_report_export` | Verifies generation of formatted Markdown reports. |
| `test_history_store_save_load_delete` | Validates JSON persistence, metrics aggregation, and run deletion. |
| `test_markdown_report_formatting` | Validates Markdown export formatting and audit tables. |

### I. Data Schema Integrity (`tests/test_schema.py`)
| Test Case | Description |
|:---|:---|
| `test_bug_item_creation` | Validates BugItem instantiation with file, line, category, severity, confidence. |
| `test_review_feedback_creation` | Validates ReviewFeedback schema with requirements_met and unresolved_concerns. |
| `test_execution_result_defaults` | Validates ExecutionResult model defaults and test_results dictionary. |

### J. Syntax Parsing Rigor (`tests/test_syntax_checker.py`)
| Test Case | Description |
|:---|:---|
| `test_valid_syntax` | Verifies clean AST parsing on valid Python functions. |
| `test_invalid_syntax_missing_colon` | Checks that missing syntax tokens return line numbers and `SyntaxError`. |
| `test_indentation_error` | Verifies identification of indentation defects. |
| `test_empty_code` | Asserts that empty strings fail validation safely. |

---

## 3. Running the Test Suite

Execute all tests from PowerShell:

```powershell
# Run the complete test suite with verbose output
pytest -v

# Run with concise output
pytest -q

# Run only LangGraph tests
pytest tests/test_langgraph.py -v

# Run only Safe Workspace security tests
pytest tests/test_safe_workspace.py -v
```

### Static Analysis Verification (Ruff)

Verify that the codebase complies with PEP 8 and Python static analysis standards:

```powershell
ruff check .
```

---

## 4. Live Ollama Verification Results

When running against the local Ollama runtime on Windows 11:
- The Ollama CLI is installed and detects `qwen2.5:0.5b` and `deepseek-coder:1.3b` on port 11434.
- If Ollama throws HTTP 500 (`llama-server binary not found`), OpenReview AI catches the error explicitly and displays an actionable diagnostic advising the user to reinstall Ollama or switch to **⚡ Smart Simulator**.
- In **Smart Simulator Mode**, all 51 automated unit, workflow, and security tests pass with zero errors, executing full AST parsing, subprocess sandboxing, diff generation, and report persistence.
