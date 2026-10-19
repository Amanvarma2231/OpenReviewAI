import os
import io
import json
import time
import streamlit as st
from datetime import datetime

from openreview_ai.config import WorkflowConfig, OPENSOURCE_MODEL_FAMILIES
from openreview_ai.engine import WorkflowOrchestrator
from openreview_ai.schema import WorkflowResult, ReviewStatus, SeverityLevel, BugCategory
from openreview_ai.utils.diff_viewer import compute_unified_diff
from openreview_ai.utils.report_exporter import export_markdown_report
from openreview_ai.providers.ollama import OllamaProvider
from openreview_ai.sandbox.syntax_checker import check_syntax

# Page Configuration
st.set_page_config(
    page_title="OpenReviewAI — Multi-LLM Code Review & Correction",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Handcrafted Developer Styling
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    /* Sidebar Dark Modern Developer Theme */
    section[data-testid="stSidebar"] {
        background-color: #0F172A;
        border-right: 1px solid #1E293B;
    }
    section[data-testid="stSidebar"] * {
        color: #E2E8F0;
    }
    .sidebar-brand-box {
        background: #1E293B;
        border: 1px solid #334155;
        border-radius: 10px;
        padding: 0.9rem 1rem;
        margin-bottom: 1.2rem;
    }
    .sidebar-brand-title {
        font-size: 0.95rem;
        font-weight: 700;
        color: #38BDF8;
        display: flex;
        align-items: center;
        gap: 0.4rem;
    }
    .sidebar-brand-sub {
        font-size: 0.75rem;
        color: #94A3B8;
        margin-top: 0.2rem;
    }
    .sidebar-section-title {
        font-size: 0.75rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: #38BDF8;
        margin-top: 1rem;
        margin-bottom: 0.35rem;
        display: block;
    }

    /* Main Container Card */
    .dev-hero {
        background: linear-gradient(135deg, #0F172A 0%, #1E293B 100%);
        border: 1px solid #334155;
        border-radius: 14px;
        padding: 1.6rem 2rem;
        margin-bottom: 1.4rem;
        box-shadow: 0 4px 20px -2px rgba(0, 0, 0, 0.25);
    }
    .dev-hero-title {
        color: #F8FAFC;
        font-size: 1.85rem;
        font-weight: 700;
        letter-spacing: -0.02em;
        margin-bottom: 0.3rem;
        display: flex;
        align-items: center;
        gap: 0.6rem;
    }
    .dev-hero-sub {
        color: #94A3B8;
        font-size: 0.95rem;
        margin-bottom: 0.9rem;
    }
    .dev-badge-bar {
        display: flex;
        gap: 0.5rem;
        flex-wrap: wrap;
        align-items: center;
    }
    .dev-pill {
        background: rgba(56, 189, 248, 0.12);
        color: #38BDF8;
        border: 1px solid rgba(56, 189, 248, 0.25);
        padding: 0.2rem 0.55rem;
        border-radius: 6px;
        font-size: 0.74rem;
        font-weight: 600;
        font-family: 'JetBrains Mono', monospace;
    }
    .dev-pill-success {
        background: rgba(34, 197, 94, 0.12);
        color: #4ADE80;
        border: 1px solid rgba(34, 197, 94, 0.25);
        padding: 0.2rem 0.55rem;
        border-radius: 6px;
        font-size: 0.74rem;
        font-weight: 600;
    }

    /* Handcrafted Agent Role Cards */
    .role-card {
        border: 1px solid #E2E8F0;
        border-radius: 10px;
        padding: 1rem;
        background: #FFFFFF;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        height: 100%;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
    }
    .role-title {
        font-size: 0.92rem;
        font-weight: 700;
        color: #0F172A;
        display: flex;
        align-items: center;
        gap: 0.4rem;
    }
    .role-tag {
        font-size: 0.75rem;
        color: #2563EB;
        background: #EFF6FF;
        padding: 0.12rem 0.45rem;
        border-radius: 4px;
        display: inline-block;
        margin-top: 0.25rem;
        font-weight: 600;
    }
    .role-desc {
        font-size: 0.78rem;
        color: #64748B;
        margin-top: 0.4rem;
        line-height: 1.4;
    }

    /* Metric Cards */
    .stat-card {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 10px;
        padding: 1rem;
        text-align: center;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }
    .stat-val {
        font-size: 1.6rem;
        font-weight: 700;
        color: #0F172A;
    }
    .stat-lbl {
        font-size: 0.76rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        color: #64748B;
        margin-top: 0.25rem;
    }

    /* Defect Badges */
    .badge-critical {
        background-color: #FEE2E2;
        color: #991B1B;
        border: 1px solid #F87171;
        padding: 0.15rem 0.45rem;
        border-radius: 4px;
        font-size: 0.72rem;
        font-weight: 700;
    }
    .badge-major {
        background-color: #FEF3C7;
        color: #92400E;
        border: 1px solid #FBBF24;
        padding: 0.15rem 0.45rem;
        border-radius: 4px;
        font-size: 0.72rem;
        font-weight: 700;
    }
    .badge-minor {
        background-color: #DBEAFE;
        color: #1E40AF;
        border: 1px solid #93C5FD;
        padding: 0.15rem 0.45rem;
        border-radius: 4px;
        font-size: 0.72rem;
        font-weight: 700;
    }
</style>
""", unsafe_allow_html=True)


# Pre-flight Check for local Ollama
def check_ollama():
    ollama = OllamaProvider("check")
    if ollama.check_health():
        models = ollama.get_available_models()
        return True, models
    return False, []

ollama_online, installed_models = check_ollama()


# ==============================================================================
# SIDEBAR: DEVELOPER CONTROL PANEL
# ==============================================================================
with st.sidebar:
    st.markdown("""
    <div class="sidebar-brand-box">
        <div class="sidebar-brand-title">🛡️ OpenReviewAI</div>
        <div class="sidebar-brand-sub">Multi-LLM Code Review & Correction Engine</div>
        <div style="font-size: 0.72rem; color: #38BDF8; margin-top: 0.35rem; font-weight: 600;">
            👨‍💻 Developed by Aman Varma
        </div>
        <div style="font-size: 0.68rem; color: #94A3B8;">
            For Druidot Consulting Pvt. Ltd.
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Engine Status
    if ollama_online and installed_models:
        st.markdown(f"🟢 **Ollama Local Engine:** `{len(installed_models)} model(s) ready`")
    else:
        st.markdown("⚡ **Simulator Engine:** `Active (Instant Demo Mode)`")

    st.markdown('<span class="sidebar-section-title">1. LLM Engine Provider</span>', unsafe_allow_html=True)
    provider_choice = st.selectbox(
        "Select Provider",
        options=["mock", "ollama", "openai_compat", "huggingface"],
        format_func=lambda x: {
            "mock": "⚡ Smart Simulator (Instant Demo / No GPU Required)",
            "ollama": "🦙 Local Ollama (Self-Hosted Open Source)",
            "openai_compat": "🌐 Cloud API (Groq / vLLM / DeepSeek)",
            "huggingface": "🤗 Hugging Face Inference API"
        }.get(x, x),
        index=0 if not ollama_online or not installed_models else 1
    )

    st.markdown('<span class="sidebar-section-title">2. Choose Open-Source Models</span>', unsafe_allow_html=True)
    st.caption("Models specified by Druidot: Gemma, Mistral, Bonsai, Qwen, DeepSeek")

    all_models = WorkflowConfig.get_supported_model_list()

    generator_model = st.selectbox(
        "LLM 1: Code Generator & Fixer",
        options=["qwen2.5:0.5b", "qwen2.5-coder:1.5b", "deepseek-coder:1.3b", "gemma2:2b", "mistral:latest"] + all_models,
        index=0,
        help="Writes the initial code and applies fixes when bugs are reported."
    )

    reviewer_model = st.selectbox(
        "LLM 2: Code Reviewer",
        options=["mistral:latest", "gemma2:2b", "deepseek-coder:1.3b", "qwen2.5-coder:1.5b"] + all_models,
        index=0,
        help="Inspects code for bugs, edge cases, logic flaws, and syntax issues."
    )

    enable_validator = st.checkbox("Enable LLM 3: Security & QA Validator", value=True)
    validator_model = "deepseek-coder:1.3b"
    if enable_validator:
        validator_model = st.selectbox(
            "LLM 3: Security & QA Validator",
            options=["deepseek-coder:1.3b", "bonsai:latest", "gemma2:2b", "mistral:latest"] + all_models,
            index=0,
            help="Performs security checks and confirms final approval."
        )

    st.markdown('<span class="sidebar-section-title">3. Execution & Loop Guardrails</span>', unsafe_allow_html=True)
    max_retries = st.slider("Maximum Review Cycles (Retries)", min_value=1, max_value=5, value=3, help="Prevents infinite loops by stopping after N retry attempts.")
    enable_sandbox = st.checkbox("Run Code in Sandbox Subprocess", value=True, help="Executes code in safe subprocess with timeout to check for runtime errors.")
    temperature = st.slider("Temperature", min_value=0.0, max_value=0.8, value=0.2, step=0.05)

    if provider_choice == "openai_compat":
        st.markdown('<span class="sidebar-section-title">Cloud API Keys</span>', unsafe_allow_html=True)
        api_base = st.text_input("Base URL", value=os.getenv("OPENAI_COMPATIBLE_BASE_URL", "https://api.groq.com/openai/v1"))
        api_key = st.text_input("API Key", type="password", value=os.getenv("OPENAI_COMPATIBLE_API_KEY", ""))
        if api_base:
            os.environ["OPENAI_COMPATIBLE_BASE_URL"] = api_base
        if api_key:
            os.environ["OPENAI_COMPATIBLE_API_KEY"] = api_key
    elif provider_choice == "huggingface":
        st.markdown('<span class="sidebar-section-title">Hugging Face Token</span>', unsafe_allow_html=True)
        hf_token = st.text_input("HF Token", type="password", value=os.getenv("HUGGINGFACEHUB_API_TOKEN", ""))
        if hf_token:
            os.environ["HUGGINGFACEHUB_API_TOKEN"] = hf_token

    st.markdown("---")
    st.markdown("""
    <div style="font-size: 0.72rem; color: #64748B;">
        Python Development Internship Project<br/>
        Tested with Pytest • 100% Open Source
    </div>
    """, unsafe_allow_html=True)


# ==============================================================================
# MAIN PAGE: HERO BANNER & AGENT PIPELINE
# ==============================================================================
st.markdown("""
<div class="dev-hero">
    <div class="dev-hero-title">
        🛡️ OpenReviewAI — Multi-LLM Code Review & Auto-Correction
    </div>
    <div class="dev-hero-sub">
        An autonomous multi-agent system where one open-source LLM writes code, another reviews it, and bugs are sent back for iterative fixes until fully approved.
    </div>
    <div class="dev-badge-bar">
        <span class="dev-pill">Coder: Qwen</span>
        <span class="dev-pill">Reviewer: Mistral</span>
        <span class="dev-pill">Security: DeepSeek</span>
        <span class="dev-pill">Gemma & Bonsai</span>
        <span class="dev-pill-success">● Subprocess Sandbox Active</span>
        <span class="dev-pill-success">● Finite Retry Bound (K &le; 5)</span>
    </div>
</div>
""", unsafe_allow_html=True)


# Handcrafted Role Cards
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown(f"""
    <div class="role-card">
        <div>
            <div class="role-title">👨‍💻 LLM 1: Coder Agent</div>
            <div class="role-tag">Code Generator & Fixer</div>
            <div class="role-desc">Writes the initial code and updates it when the reviewer finds bugs.</div>
        </div>
        <div style="margin-top: 0.6rem; font-family: monospace; font-size: 0.72rem; color: #475569;">
            Model: <strong>{generator_model}</strong>
        </div>
    </div>
    """, unsafe_allow_html=True)

with c2:
    st.markdown(f"""
    <div class="role-card">
        <div>
            <div class="role-title">🧐 LLM 2: Reviewer Agent</div>
            <div class="role-tag">Code Inspector</div>
            <div class="role-desc">Scrutinizes code for logic errors, off-by-one bugs, and edge cases.</div>
        </div>
        <div style="margin-top: 0.6rem; font-family: monospace; font-size: 0.72rem; color: #475569;">
            Model: <strong>{reviewer_model}</strong>
        </div>
    </div>
    """, unsafe_allow_html=True)

with c3:
    st.markdown(f"""
    <div class="role-card">
        <div>
            <div class="role-title">🛡️ LLM 3: QA & Security</div>
            <div class="role-tag">Security Arbiter</div>
            <div class="role-desc">Checks for security vulnerabilities (e.g. unsafe eval) and confirms consensus.</div>
        </div>
        <div style="margin-top: 0.6rem; font-family: monospace; font-size: 0.72rem; color: #475569;">
            Model: <strong>{validator_model if enable_validator else 'Disabled'}</strong>
        </div>
    </div>
    """, unsafe_allow_html=True)

with c4:
    st.markdown(f"""
    <div class="role-card">
        <div>
            <div class="role-title">⚡ Test Sandbox</div>
            <div class="role-tag">Subprocess Runner</div>
            <div class="role-desc">Executes code safely in a timeout-guarded environment to catch crashes.</div>
        </div>
        <div style="margin-top: 0.6rem; font-family: monospace; font-size: 0.72rem; color: #475569;">
            Type: <strong>Python Subprocess</strong>
        </div>
    </div>
    """, unsafe_allow_html=True)

st.write("")

# Dual Mode Selector
workflow_mode = st.radio(
    "Choose How to Run",
    [
        "Option 1: 💡 Generate Code from Prompt (Specification -> Multi-LLM Review Loop)",
        "Option 2: 📂 Review & Fix Existing Code File (Upload / Paste Script -> Auto-Repair)"
    ],
    horizontal=True
)

existing_code_input = None
task_prompt_input = ""

if "Option 1" in workflow_mode:
    col_preset, col_lang = st.columns([3, 1])
    with col_preset:
        preset_tasks = {
            "1. Palindrome Checker (Catches edge cases & punctuation)": "Write a python function is_palindrome(s) that checks if a string is a palindrome. It must ignore punctuation, casing, and whitespace, and safely handle None and empty string.",
            "2. Factorial Function (Handles negative inputs & recursion limits)": "Write a python function factorial(n) that computes n! using recursion or iteration, handling base cases (0, 1) and raising ValueError on negative inputs.",
            "3. Fibonacci Sequence (Optimal O(n) time and O(1) space)": "Write a python function fibonacci(n) that returns the nth Fibonacci number with O(n) time complexity and O(1) auxiliary space complexity.",
            "4. Even Numbers Squared Filter (Type safety & None check)": "Write a python function solve_task(data) that filters even numbers and returns their squares, gracefully handling None and mixed non-integer types.",
            "5. Custom Task Prompt": ""
        }
        chosen_preset = st.selectbox("Quick Task Templates", list(preset_tasks.keys()), index=0)
    with col_lang:
        target_language = st.selectbox("Language", ["python", "javascript", "go", "cpp"], index=0)

    task_prompt_input = st.text_area(
        "Enter Coding Task Prompt",
        value=preset_tasks[chosen_preset] if chosen_preset != "5. Custom Task Prompt" else "",
        height=95,
        placeholder="Describe what function or script you want the multi-LLM team to build..."
    )

    with st.expander("🧪 Add Custom Unit Tests / Assertions (Optional)"):
        custom_tests = st.text_area(
            "Test assertions executed inside the sandbox",
            value="",
            height=80,
            placeholder="assert is_palindrome('A man, a plan, a canal: Panama') == True\nassert is_palindrome(None) == False"
        )
else:
    # Option 2: Review Existing Code File
    st.info("Upload or paste any Python script. LLM 2 & LLM 3 will review it for bugs/security flaws, and LLM 1 will fix it automatically!")
    col_u1, col_u2 = st.columns([1, 2])
    with col_u1:
        uploaded_file = st.file_uploader("Upload Python File (.py)", type=["py"])
    with col_u2:
        default_buggy_code = """# Sample Script with Security & Edge-Case Bugs
def process_user_query(raw_expr):
    # Unsafe evaluation vulnerability
    return eval(raw_expr)

if __name__ == '__main__':
    print(process_user_query("[1, 2, 3]"))
"""
        pasted_code = st.text_area("Or Paste Code Here", value=uploaded_file.getvalue().decode("utf-8") if uploaded_file else default_buggy_code, height=135)

    existing_code_input = pasted_code
    task_prompt_input = "Perform comprehensive code review, fix security vulnerabilities (e.g. unsafe eval), handle edge cases, and add type annotations and docstrings."
    custom_tests = None
    target_language = "python"


# Action Buttons
b_col1, b_col2 = st.columns([3, 1])
with b_col1:
    execute_button = st.button("🚀 Start Multi-LLM Review Workflow", type="primary", use_container_width=True)
with b_col2:
    if st.button("🔄 Reset", use_container_width=True):
        st.session_state.workflow_result = None
        st.rerun()

if "workflow_result" not in st.session_state:
    st.session_state.workflow_result = None


# Execution Handler
if execute_button:
    if not task_prompt_input.strip() and not existing_code_input:
        st.error("Please enter a task prompt or provide code to review!")
    else:
        config = WorkflowConfig(
            provider_type=provider_choice,
            generator_model=generator_model,
            reviewer_model=reviewer_model,
            validator_model=validator_model if enable_validator else "",
            max_retries=max_retries,
            enable_sandbox_execution=enable_sandbox,
            enable_third_llm_validator=enable_validator,
            temperature=temperature
        )

        p_container = st.container()
        with p_container:
            progress_bar = st.progress(0, text="Starting Multi-LLM Review Workflow...")

        def on_event(event_name: str, data: dict):
            if event_name == "generation_started":
                progress_bar.progress(15, text=f"Round {data.get('round')}: LLM 1 ({generator_model}) is writing code...")
            elif event_name == "generation_completed":
                progress_bar.progress(35, text="Code written. Passing to sandbox & reviewers...")
            elif event_name == "execution_started":
                progress_bar.progress(45, text="Running code in safe sandbox subprocess...")
            elif event_name == "review_started":
                progress_bar.progress(65, text=f"LLM 2 ({reviewer_model}) is reviewing code...")
            elif event_name == "validation_started":
                progress_bar.progress(78, text=f"LLM 3 ({validator_model}) is checking security & QA...")
            elif event_name == "fix_started":
                progress_bar.progress(88, text=f"Bugs found! Passing feedback to LLM 1 for Round {data.get('round')} fixes...")
            elif event_name == "workflow_completed":
                progress_bar.progress(100, text="Workflow completed! Code is approved.")

        try:
            with st.spinner("Multi-LLMs are communicating, reviewing, and fixing code..."):
                orchestrator = WorkflowOrchestrator(config=config)
                result = orchestrator.run(
                    task_prompt=task_prompt_input,
                    target_language=target_language,
                    unit_tests=custom_tests if custom_tests and custom_tests.strip() else None,
                    existing_code=existing_code_input,
                    on_event=on_event
                )
                st.session_state.workflow_result = result
                st.toast("Workflow finished successfully!", icon="✅")
        except Exception as e:
            st.error(f"Error: {str(e)}")
            if provider_choice == "ollama":
                st.warning("Tip: If local Ollama has missing server files, switch to '⚡ Smart Simulator' in the sidebar to test immediately!")


# ==============================================================================
# AUDIT RESULTS & TABS
# ==============================================================================
if st.session_state.workflow_result:
    res: WorkflowResult = st.session_state.workflow_result

    st.write("---")

    # Metrics Row
    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-val" style="color: {'#10B981' if res.status == 'APPROVED' else '#F59E0B'};">{res.status}</div>
            <div class="stat-lbl">Final Status</div>
        </div>
        """, unsafe_allow_html=True)
    with m2:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-val">{res.rounds_count}</div>
            <div class="stat-lbl">Review Rounds</div>
        </div>
        """, unsafe_allow_html=True)
    with m3:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-val" style="color: #EF4444;">{res.total_bugs_detected}</div>
            <div class="stat-lbl">Bugs Found</div>
        </div>
        """, unsafe_allow_html=True)
    with m4:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-val" style="color: #10B981;">{res.total_bugs_fixed}</div>
            <div class="stat-lbl">Bugs Fixed</div>
        </div>
        """, unsafe_allow_html=True)
    with m5:
        runtime_ms = res.final_execution.execution_time_ms if res.final_execution else 0.0
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-val">{runtime_ms:.1f}ms</div>
            <div class="stat-lbl">Sandbox Runtime</div>
        </div>
        """, unsafe_allow_html=True)

    st.write("")

    # Result Tabs
    t_chat, t_diff, t_code, t_metrics, t_sandbox, t_audit = st.tabs([
        "💬 Live Multi-LLM Chat & Bugs",
        "🔍 Code Changes (Diff)",
        "🏆 Final Approved Code",
        "📊 Code Quality & Security Scan",
        "🧪 Sandbox Test Output",
        "📄 Full Audit Report"
    ])

    # Tab 1: Live Chat
    with t_chat:
        st.markdown("### 💬 Multi-LLM Communication History")
        for step in res.iterations:
            is_last = (step.round_idx == len(res.iterations) - 1)
            with st.expander(f"📍 Round {step.round_idx} — Status: {step.status}", expanded=is_last):
                c_step1, c_step2 = st.columns(2)
                with c_step1:
                    st.markdown("**👨‍💻 LLM 1 (Coder & Fixer) Response:**")
                    st.info(step.generator_explanation or "Initial code generated.")
                with c_step2:
                    st.markdown("**🧐 Reviewer & Security Evaluations:**")
                    for rev in step.reviews:
                        score_color = "#10B981" if rev.overall_score >= 8 else "#F59E0B"
                        st.markdown(f"**{rev.reviewer_name}** (`{rev.reviewer_model}`): <span style='font-weight:700; color:{score_color}'>Score {rev.overall_score}/10</span>", unsafe_allow_html=True)
                        st.caption(rev.summary)

                step_bugs = []
                for rev in step.reviews:
                    step_bugs.extend(rev.bugs)

                if step_bugs:
                    st.markdown("##### 🐛 Bugs Flagged in this Round:")
                    for b in step_bugs:
                        badge_style = f"badge-{b.severity.lower()}"
                        line_info = f"Line {b.line_number}: " if b.line_number else ""
                        st.markdown(f"""
                        <div style="padding: 0.6rem 0.8rem; background: #F8FAFC; border-left: 4px solid #EF4444; margin-bottom: 0.4rem; border-radius: 6px;">
                            <span class="{badge_style}">{b.severity}</span> 
                            <strong style="color: #0F172A; margin-left: 0.4rem;">[{b.category}]</strong> {line_info}{b.description}<br/>
                            <span style="font-size: 0.82rem; color: #16A34A; font-family: monospace;">Suggested Fix: {b.suggested_fix}</span>
                        </div>
                        """, unsafe_allow_html=True)

    # Tab 2: Code Diff
    with t_diff:
        st.markdown("### 🔍 What Changed Between Rounds (Diff)")
        if len(res.iterations) > 1:
            initial_code = res.iterations[0].code
            diff_text = compute_unified_diff(initial_code, res.final_code, "Initial Code (Round 0)", f"Fixed Code (Round {res.rounds_count-1})")
            st.code(diff_text, language="diff")
        else:
            st.success("✅ The code was clean and approved in Round 0 without needing fixes!")

    # Tab 3: Final Code
    with t_code:
        st.markdown("### 🏆 Final Approved Source Code")
        st.code(res.final_code, language=res.target_language)
        
        col_down1, col_down2 = st.columns(2)
        with col_down1:
            st.download_button(
                "⬇️ Download Python Script (.py)",
                data=res.final_code,
                file_name="solution.py",
                mime="text/x-python",
                use_container_width=True
            )
        with col_down2:
            st.download_button(
                "⬇️ Download Audit Report (.md)",
                data=export_markdown_report(res),
                file_name=f"review_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                mime="text/markdown",
                use_container_width=True
            )

    # Tab 4: AST Metrics
    with t_metrics:
        st.markdown("### 📊 Code Quality & Security Scan")
        is_valid, err, meta = check_syntax(res.final_code, res.target_language)
        
        q1, q2, q3, q4 = st.columns(4)
        with q1:
            st.metric("Security Score", f"{meta.get('security_score', 100)}/100", delta="Clean" if meta.get('security_score', 100) == 100 else "Flagged")
        with q2:
            st.metric("Cyclomatic Complexity", meta.get("cyclomatic_complexity", 1))
        with q3:
            st.metric("Function Count", meta.get("num_functions", 0))
        with q4:
            st.metric("Lines of Code", meta.get("lines_of_code", 0))

        if meta.get("security_flags"):
            st.warning("Security Findings:")
            for flag in meta["security_flags"]:
                st.write(f"- ⚠️ {flag}")
        else:
            st.success("✅ Clean Code: No dangerous functions (eval, exec, shell injection) detected.")

        with st.expander("View Code Metadata Details"):
            st.json(meta)

    # Tab 5: Sandbox
    with t_sandbox:
        st.markdown("### 🧪 Sandbox Execution Output")
        if res.final_execution:
            fe = res.final_execution
            if fe.success:
                st.success(f"Execution Passed cleanly in {fe.execution_time_ms:.1f}ms (Exit Code: {fe.exit_code})")
            else:
                st.error(f"Execution Failed with Exit Code: {fe.exit_code}")
                
            st.markdown("**Standard Output (stdout):**")
            st.code(fe.stdout if fe.stdout.strip() else "(No standard output)")
            
            if fe.stderr.strip():
                st.markdown("**Standard Error (stderr):**")
                st.code(fe.stderr)
        else:
            st.info("Sandbox execution was disabled in settings.")

    # Tab 6: Audit Dossier
    with t_audit:
        st.markdown("### 📄 Complete Audit Report")
        report_text = export_markdown_report(res)
        st.markdown(report_text)
