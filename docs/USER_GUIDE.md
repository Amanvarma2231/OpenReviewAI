# OpenReview AI — Comprehensive User Guide

## 1. Introduction

**OpenReview AI** is a professional, local-first multi-agent development studio. It pairs specialized AI agents to generate, review, patch, and empirically validate Python code without transmitting source code to paid cloud APIs.

---

## 2. Studio Pages Overview

The application is structured into 9 dedicated functional pages accessible via the left sidebar navigation:

```
┌────────────────────────────────────────────────────────┐
│                   STUDIO NAVIGATION                    │
├──────────────────────┬─────────────────────────────────┤
│ Page Name            │ Primary Purpose                 │
├──────────────────────┼─────────────────────────────────┤
│ 📊 Dashboard         │ Health telemetry & statistics   │
│ ➕ New Code Task     │ Prompt, constraints & tests     │
│ 📦 Upload Project    │ ZIP archive audit & patching    │
│ ⚡ Live Workflow     │ Real-time agent event stream    │
│ 🔍 Code Comparison   │ Side-by-side & unified diff     │
│ 🛡️ Review Results    │ Structured findings & findings  │
│ 🧪 Testing Results   │ AST parsing, static & sandboxing│
│ 📁 History & Reports │ Past runs, JSON/MD export       │
│ ⚙️ Settings          │ Ollama URL, models, guardrails  │
└──────────────────────┴─────────────────────────────────┘
```

---

## 3. Step-by-Step Workflows

### Workflow A: Generate & Review a New Python Function

1. **Navigate to "New Code Task":**
   - Click **➕ New Code Task** in the sidebar.
2. **Specify Task Goal:**
   - Enter your prompt in the **Task Description** field (e.g., *"Write a function `parse_log_line(line)` that extracts timestamp, log level, and message using regex. Return None if line is malformed."*).
   - Or select one of the built-in scenario presets from the dropdown.
3. **Add Test Assertions (Optional but Recommended):**
   - In the **Custom Unit Tests (Python Assertions)** box, paste test cases:
     ```python
     assert parse_log_line("2026-10-22 INFO User logged in") == {
         "timestamp": "2026-10-22", "level": "INFO", "message": "User logged in"
     }
     assert parse_log_line("garbage data") is None
     ```
4. **Choose Execution Engine & Models:**
   - **Orchestrator Architecture:** Select **`LangGraph StateGraph`** (cyclic state machine with typed state) or **`Direct Controller`**.
   - **Provider:** Select **`🦙 Ollama`** (local models) or **`⚡ Smart Simulator`** (instant, offline).
   - Select Generator and Reviewer models.
5. **Start Workflow:**
   - Click **🚀 Start Multi-LLM Review Workflow**.
   - Watch the progress bar as the system transitions through `Generator` ➔ `Syntax / Static Validation` ➔ `Reviewer` ➔ `Validator` ➔ `Self-Correction`.
6. **Inspect Outcomes:**
   - Use the post-run navigation buttons to view the **Review Verdict**, **Unified Diff**, or **Live Workflow Transcript**.

---

### Workflow B: Upload & Improve an Existing Project (ZIP Archive)

1. **Navigate to "Upload Project":**
   - Click **📦 Upload Project** in the sidebar.
2. **Upload ZIP Archive or Python File:**
   - Drag and drop your project `.zip` archive or individual `.py` file into the upload box.
   - The safe workspace will inspect the archive, enforce Zip Slip path traversal defenses, filter out `.git`, `__pycache__`, and `.env` files, and construct a **Project Manifest**.
3. **Select Target Module:**
   - Review the manifest table showing all recognized Python files and file sizes.
   - Choose the specific file you permit OpenReview AI to modify from the **Target Module to Improve** dropdown.
4. **Define Improvement Instructions:**
   - Choose a preset or type your custom instruction:
     > *"Find bugs, improve error handling, optimize the implementation, and add tests without breaking existing behavior."*
5. **Execute Multi-Agent Audit:**
   - Select **`LangGraph StateGraph`**, choose iterations (e.g. 3), and click **🚀 Improve Selected Module**.
   - The agents will audit the file, detect bugs, produce targeted fixes in an isolated working copy, and re-review the updated module.
6. **Review Unified Diff:**
   - The studio automatically computes line additions (`+`) and deletions (`-`).
   - Click **🔍 View Project Diff** to review exact code modifications.
7. **Download Improved ZIP:**
   - Click **📦 Download Improved Project ZIP** to export the entire updated project archive with original baseline files intact and your improved module in place.

---

## 4. Understanding Review & Testing Results

### Review Results Page
- **Verdict Banner:** Displays `APPROVED` (green) or `RETRY_LIMIT_REACHED` / `FAILED` (orange/red).
- **Requirements Checklist:** Shows specific requirements verified by the adversarial reviewer.
- **Unresolved Concerns:** Explicitly highlights open questions or potential regressions.
- **Detailed Defect Audit Trail:** Each card displays:
  - **Severity:** `Critical` (red), `Major` (yellow), or `Minor` (blue).
  - **Category:** `logic`, `security`, `edge_case`, `syntax`, or `performance`.
  - **Location:** File path and exact line number where the defect was found.
  - **Confidence:** Statistical confidence rating (e.g., `Confidence: 95%`).
  - **Suggested Fix:** Concrete code remediation suggested by the reviewer.

### Testing & Verification Page
- **AST Syntax Status:** Shows `✅ Syntax Valid` or `❌ Syntax Error` with cyclomatic complexity, function count, and docstring metrics.
- **Sandbox Execution Status:**
  - `✅ TESTS_PASSED`: Subprocess executed with exit code 0 and all assertions passed.
  - `❌ TESTS_FAILED`: Test assertions raised `AssertionError` or exception; trace is shown.
  - `⚠️ NOT_RUN: No Test Suite Provided`: Prominent warning informing the user that functional correctness was not verified because test assertions were omitted.
- **Live Test Suite Runner:** An interactive tool at the bottom of the page allowing you to paste unit tests and run them immediately against the final code in the sandbox.

---

## 5. History, Export, and Reports

- **Search & Filter:** Filter past runs by status (`ALL`, `PASSED`, `RETRY_LIMIT_REACHED`, `FAILED`) or search by prompt keyword.
- **Inspect Past Run:** Click **👁️ Load** to restore any historical run into active studio memory.
- **Download Artifacts:**
  - **📋 Report:** Formatted Markdown file containing executive summary, iteration audit trail, and diffs.
  - **📄 JSON:** Complete machine-readable execution record.
  - **📥 Code:** Python source code file ready to run.
