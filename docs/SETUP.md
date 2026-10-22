# Windows 11 Setup & Installation Guide

This guide details step-by-step instructions for installing, configuring, testing, and running **OpenReview AI** on Windows 11 (16 GB RAM) with 100% local execution and zero paid cloud API dependencies.

---

## 1. Prerequisites Verification

Open **PowerShell** (as a standard user or administrator) and verify the installed tools:

```powershell
# Check Python version (Python 3.11, 3.12, or 3.13 supported)
python --version

# Check Git version
git --version
```

If Python is not installed, install Python 3.12 or 3.13 from [python.org](https://www.python.org/) or via `winget`:
```powershell
winget install Python.Python.3.13
```
*Ensure you check "Add Python to PATH" during installation.*

---

## 2. Virtual Environment Setup

Navigate to your workspace directory and create an isolated virtual environment:

```powershell
# Navigate to project directory
cd "C:\Users\AMAN VARMA\OneDrive\Attachments\Desktop\OpenReviewAI"

# Create virtual environment
python -m venv .venv

# Activate virtual environment
.\.venv\Scripts\Activate.ps1
```

> **Note on PowerShell Execution Policy:**  
> If PowerShell blocks script execution (`Running Scripts is disabled on this system`), run:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```
> Then re-run `.\.venv\Scripts\Activate.ps1`.

---

## 3. Install Python Dependencies

With `.venv` active, install the project dependencies:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Verify the installed packages:
```powershell
pip list
```

Key packages installed:
- `langgraph` & `langchain-core`: Cyclic state machine multi-agent orchestration.
- `streamlit`: Enterprise 9-page reactive UI.
- `pydantic`: Schema validation for agent states and structured review payloads.
- `requests`: HTTP communication with local Ollama runtime.
- `pytest`: Comprehensive unit and integration test framework.

---

## 4. Install Ollama for Windows

Ollama executes open-weight models locally with 4-bit/8-bit quantization and CPU/GPU layer offloading.

1. Download the Windows installer from [https://ollama.com/download/windows](https://ollama.com/download/windows).
2. Run `OllamaSetup.exe` and follow prompts.
3. Start the Ollama background daemon in a PowerShell terminal:
   ```powershell
   ollama serve
   ```
4. In another terminal, verify HTTP connectivity:
   ```powershell
   curl http://localhost:11434/api/version
   ```

---

## 5. Download Open-Weight LLM Models

For a **16 GB RAM machine** without dedicated GPU guarantees, download the recommended efficient models:

```powershell
# 1. Ultra-light Generator (approx. 397 MB)
ollama pull qwen2.5:0.5b

# 2. Reviewer Model (approx. 776 MB)
ollama pull deepseek-coder:1.3b

# 3. Alternative 3B Generator (for higher capability if RAM permits, approx. 1.9 GB)
ollama pull qwen2.5-coder:3b
```

Verify downloaded models:
```powershell
ollama list
```

### Resource Management Strategy
- OpenReview AI executes agent inference **sequentially** by default to prevent memory exhaustion on 16 GB RAM machines.
- Temperature is capped at 0.2 by default to ensure deterministic, focused code output and reliable JSON formatting.

---

## 6. Run Automated Test Suite

Before launching the web application, verify that all 51 automated test cases pass:

```powershell
pytest -v
```

Expected output:
```text
======================= 51 passed in 20.75s =======================
```

The test suite covers:
- Unit tests: Safe workspace path resolution, Zip Slip rejection, AST syntax parsing, subprocess sandbox timeouts, review response parser contradiction overrides, report generation.
- Workflow tests: LangGraph StateGraph nodes, cyclic feedback transitions, retry count bounds, failed tests preventing false PASS, error recording.
- Integration tests: End-to-end multi-round review loops and history persistence.

---

## 7. Launch the Streamlit Web Application

Start the local web dashboard:

```powershell
streamlit run app.py
```

The application will automatically open in your default browser at:
`http://localhost:8501`

### Available Studio Pages:
1. **Dashboard**: System telemetry, Ollama connection status, installed models, and workflow summary.
2. **New Code Task**: Prompt specification, baseline code, unit test assertions, model selection, orchestrator engine choice (`LangGraph StateGraph` vs `Direct Controller`).
3. **Upload Project**: ZIP archive inspection, Zip Slip defense, project file manifest, target file selection, and module improvement.
4. **Live Workflow**: Real-time multi-agent conversation transcript, active stage stepper, and live event stream table.
5. **Code Comparison**: Side-by-side view and unified diff with line-level addition/deletion tracking.
6. **Review Results**: Structured findings audit trail, file locations, line numbers, confidence ratings, verified requirements checklist, and unresolved concerns.
7. **Testing Results**: AST syntax status, static analysis metrics (complexity, functions, docstrings), and sandbox execution status (`TESTS_PASSED`, `TESTS_FAILED`, or explicit `NOT_RUN` badge). Includes interactive test execution tool.
8. **History & Reports**: Searchable past execution history, JSON export, Markdown report download, and improved Python code download.
9. **Settings**: Ollama endpoint URL, agent model assignments, retry limit, subprocess sandbox toggle, and local privacy guarantee.

---

## 8. CLI Usage Examples

You can also run OpenReview AI tasks directly from PowerShell:

```powershell
# Check local Ollama connectivity
python main.py --check-ollama

# View aggregate summary statistics of past runs
python main.py --stats

# Run a task using local Ollama models with LangGraph engine
python main.py --task "Write a binary search function" --output-report outputs/reports/binary_search.md

# Run a task with an automated test suite
python main.py --task "Write an integer factorial function" --test-file path/to/test.py

# Offline / Demo Mode (simulates LLM without Ollama running)
python main.py --task "Implement Fibonacci" --mock
```

---

## 9. Troubleshooting & FAQ

### Problem 1: `RuntimeError: Ollama HTTP 500: error starting llama-server: llama-server binary not found`
- **Cause:** Ollama CLI was installed, but the background runner `llama-server.exe` was omitted or blocked by antivirus/Windows Defender during installation.
- **Solution A (Recommended for immediate testing):** Switch the provider selector to **`⚡ Smart Simulator`** in the application sidebar or pass `--mock` on CLI. The full LangGraph StateGraph, AST validation, subprocess sandboxing, and diff generation execute with 100% fidelity without requiring GPU or external binaries.
- **Solution B (To fix Ollama):** Close Ollama from the Windows system tray, download the latest installer from [https://ollama.com/download/windows](https://ollama.com/download/windows), right-click and select **Run as Administrator**, and reinstall.

### Problem 2: `WinError 10061: No connection could be made because the target machine actively refused it`
- **Cause:** Ollama service is not running in the background.
- **Solution:** Open PowerShell and start Ollama by typing `ollama serve`, or start the Ollama application from the Windows Start menu.

### Problem 3: `Model not found: 'qwen2.5-coder:3b'`
- **Cause:** Model has not been pulled yet.
- **Solution:** Run `ollama pull qwen2.5:0.5b` or pull the exact model named in settings.

### Problem 4: High RAM consumption or system slowdown
- **Cause:** Multiple heavy background applications open alongside LLM inference.
- **Solution:** OpenReview AI runs models **sequentially** by default to preserve RAM on 16GB systems. Ensure you select `qwen2.5:0.5b` or `deepseek-coder:1.3b` in the settings dropdown rather than 7B+ parameter models.
