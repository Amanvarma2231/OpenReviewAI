# OpenReview AI — Testing & Quality Assurance Guide

## 1. Quality Assurance Strategy

OpenReview AI employs a dual-tier testing methodology:
1. **Unit & Integration Test Suite (`tests/`):** Validates the internal components, JSON parsing, error traps, timeout handling, and multi-iteration state machine using mocked LLM responses. This guarantees that test runs are fast, reproducible, and offline-compatible without requiring downloaded weights.
2. **Dynamic Validation Layer (`validation/`):** Performs runtime checks on LLM-generated code during workflow execution, separating AST syntax validation from dynamic test executions.

---

## 2. Test Suite Structure

The test suite consists of 23 automated tests across 5 test modules:

| Test File | Test Case | Description |
| :--- | :--- | :--- |
| `test_syntax_checker.py` | `test_valid_syntax` | Verifies clean AST parsing on valid Python functions. |
| `test_syntax_checker.py` | `test_invalid_syntax_missing_colon` | Checks that missing syntax tokens return line numbers and `SyntaxError`. |
| `test_syntax_checker.py` | `test_indentation_error` | Verifies identification of indentation defects. |
| `test_syntax_checker.py` | `test_empty_code` | Asserts that empty strings fail validation safely. |
| `test_review_parser.py` | `test_valid_json_review_parsing` | Validates parsing of structured JSON review schemas. |
| `test_review_parser.py` | `test_markdown_wrapped_json` | Ensures extraction of JSON blocks embedded in markdown commentary. |
| `test_review_parser.py` | `test_malformed_reviewer_response_fails_explicitly` | **Critical Security Check:** Verifies that malformed JSON is NEVER marked as `PASS`. |
| `test_review_parser.py` | `test_contradictory_pass_with_issues_is_overridden_to_fail` | Ensures a model claiming `PASS` while reporting critical bugs is overridden to `FAIL`. |
| `test_review_parser.py` | `test_empty_reviewer_response` | Validates handling of empty model outputs. |
| `test_api_client.py` | `test_health_check_online` | Mocked Ollama server status probe. |
| `test_api_client.py` | `test_health_check_offline` | Validates graceful recovery and user advice when Ollama is offline. |
| `test_api_client.py` | `test_health_check_timeout` | Tests network connection timeout handling. |
| `test_api_client.py` | `test_list_installed_models` | Validates parsing of model tags from `/api/tags`. |
| `test_api_client.py` | `test_missing_model_raises_error` | Checks that requests for missing models raise `OllamaModelNotFoundError` with `ollama pull` suggestions. |
| `test_api_client.py` | `test_chat_timeout_raises_ollama_timeout_error` | Asserts `OllamaTimeoutError` when inference exceeds timeout limits. |
| `test_api_client.py` | `test_mock_mode_execution` | Tests mock provider for offline evaluations. |
| `test_workflow.py` | `test_empty_task_returns_error` | Asserts `ERROR` status and clean rejection for empty user tasks. |
| `test_workflow.py` | `test_successful_workflow_single_attempt` | Verifies single-pass workflow completion when code satisfies all criteria. |
| `test_workflow.py` | `test_correction_called_after_failed_review` | Verifies that a failed review on attempt 1 correctly invokes `generator.fix_code()` on attempt 2. |
| `test_workflow.py` | `test_retry_limit_reached` | Tests graceful termination when issues persist through max retries. |
| `test_workflow.py` | `test_test_suite_failure_triggers_validation_failed` | **Separation of Concerns:** Proves that an LLM `PASS` verdict does NOT override failed test assertions. |
| `test_report_generator.py` | `test_history_store_save_load_delete` | Validates JSON persistence, metrics aggregation, and run deletion. |
| `test_report_generator.py` | `test_markdown_report_formatting` | Validates Markdown export formatting and audit tables. |

---

## 3. Running the Tests

Activate your virtual environment and run:

```powershell
# Run the complete test suite
pytest -v

# Run with short traceback on failure
pytest -v --tb=short

# Run a specific test module
pytest tests/test_workflow.py -v
```

### Static Analysis Verification (Ruff)

Verify that project codebase complies with Python standards:

```powershell
ruff check .
```

---

## 4. Acceptance Criteria Policy

A workflow execution is certified as **`PASSED`** if and only if all three conditions are met:
1. **Syntax Valid:** AST compiles without `SyntaxError` or `IndentationError`.
2. **Tests Verified:** An explicit test suite was provided and all test assertions passed (`exit code 0`).
3. **Reviewer Approved:** The adversarial reviewer returned a valid JSON verdict of `PASS` with `requirements_met: true` and zero unresolved defects.

If no test suite was provided by the user, the status is labeled **`REVIEW_PASSED`**, and the report explicitly records:
> *No automated test suite was provided. Functional correctness is based on static LLM review only; runtime execution was NOT RUN.*
