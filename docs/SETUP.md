# Windows 11 Setup & Installation Guide

This guide details step-by-step instructions for installing and running **OpenReview AI** on Windows 11 with 16 GB RAM and zero paid cloud API dependencies.

---

## 1. Prerequisites Verification

Open **PowerShell** (as a standard user or administrator) and verify installed tools:

```powershell
# Check Python version (Python 3.12 or 3.13 recommended)
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

Verify installed packages:
```powershell
pip list
```

---

## 4. Install Ollama for Windows

Ollama executes open-weight models locally with optimized quantization and automatic CPU/GPU layer offloading.

1. Download the Windows installer from [https://ollama.com/download/windows](https://ollama.com/download/windows).
2. Run `OllamaSetup.exe` and follow prompts.
3. Verify that the Ollama service is running:
   ```powershell
   ollama --version
   ```
4. Verify HTTP connectivity:
   ```powershell
   curl http://localhost:11434/api/version
   ```

---

## 5. Download Open-Weight LLM Models

For a **16 GB RAM machine** without dedicated GPU guarantees, download the recommended efficient models:

```powershell
# 1. Download Code Generator Model (approx. 1.9 GB download)
ollama pull qwen2.5-coder:3b

# 2. Download Code Reviewer Model (approx. 800 MB download)
ollama pull deepseek-coder:1.3b
```

Verify downloaded models:
```powershell
ollama list
```

### Alternative Lightweight Models (Low-RAM Profiles):
If your machine is under heavy memory load, you can pull smaller variants:
```powershell
# Ultra-light generator (approx. 980 MB)
ollama pull qwen2.5-coder:1.5b

# Reviewer option
ollama pull deepseek-coder:1.3b
```

---

## 6. Run Automated Test Suite

Before running the application, verify that all components and unit tests pass:

```powershell
pytest -v
```

Expected output:
```text
============================= 23 passed in ~9s =============================
```

---

## 7. Launch the Streamlit Web Application

Start the local web dashboard:

```powershell
streamlit run app.py
```

The application will automatically open in your default browser at:
`http://localhost:8501`

---

## 8. CLI Usage Examples

You can also run OpenReview AI tasks directly from PowerShell:

```powershell
# Check local Ollama connectivity
python main.py --check-ollama

# View aggregate summary statistics of past runs
python main.py --stats

# Run a task using local Ollama models
python main.py --task "Write a binary search function" --output-report outputs/reports/binary_search.md

# Run a task with an automated test suite
python main.py --task "Write an integer factorial function" --test-file path/to/test.py

# Offline / Demo Mode (simulates LLM without Ollama running)
python main.py --task "Implement Fibonacci" --mock
```

---

## 9. Troubleshooting & FAQ

### Problem 1: `WinError 10061: No connection could be made because the target machine actively refused it`
- **Cause:** Ollama is not running in the background.
- **Solution:** Open PowerShell and start Ollama by typing `ollama serve`, or start the Ollama application from the Windows Start menu.

### Problem 2: `Model not found: 'qwen2.5-coder:3b'`
- **Cause:** Model has not been pulled yet.
- **Solution:** Run `ollama pull qwen2.5-coder:3b`.

### Problem 3: High RAM consumption or slowdown
- **Cause:** OpenReview AI runs models **sequentially** by default to preserve RAM on 16GB systems. If RAM is constrained, select `qwen2.5-coder:1.5b` in the settings dropdown.

### Problem 4: Running without Ollama
- **Feature:** OpenReview AI includes a built-in **Demo / Mock Mode**. Check the "Demo / Mock Mode" checkbox in the Streamlit sidebar or use `--mock` on CLI to test full workflow capabilities immediately.
