@echo off
chcp 65001 >nul
title OpenReviewAI — Multi-LLM Code Review Studio
color 0B

echo.
echo  ╔══════════════════════════════════════════════════════╗
echo  ║  🛡️  OpenReviewAI — Multi-LLM Code Review Studio     ║
echo  ║  Developed by Aman Varma  ·  Druidot Consulting      ║
echo  ╚══════════════════════════════════════════════════════╝
echo.

echo  [1/4] Freeing port 8501 if busy...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8501 2^>nul') do (
    taskkill /PID %%a /F >nul 2>&1
)
echo  [1/4] Port 8501 is free. OK

echo  [2/4] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python not found. Please install Python 3.10+
    pause & exit /b 1
)
echo  [2/4] Python found. OK

echo  [3/4] Checking Streamlit...
python -c "import streamlit" >nul 2>&1
if errorlevel 1 (
    echo  Installing Streamlit...
    pip install streamlit
)
echo  [3/4] Streamlit ready. OK

echo  [4/4] Launching OpenReviewAI...
echo.
echo  Open browser at: http://localhost:8501
echo.

streamlit run app.py --server.port 8501

pause
