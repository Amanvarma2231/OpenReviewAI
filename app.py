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
    page_title="OpenReviewAI — Enterprise Multi-LLM Code Review Studio",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom High-End Enterprise Styling
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    .hero-container {
        background: linear-gradient(135deg, #0F172A 0%, #1E293B 100%);
        border: 1px solid #334155;
        border-radius: 14px;
        padding: 1.8rem 2.2rem;
        margin-bottom: 1.5rem;
        box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.2);
    }
    .hero-title {
        color: #F8FAFC;
        font-size: 2.1rem;
        font-weight: 700;
        letter-spacing: -0.02em;
        margin-bottom: 0.3rem;
        display: flex;
        align-items: center;
        gap: 0.6rem;
    }
    .hero-subtitle {
        color: #94A3B8;
        font-size: 0.98rem;
        margin-bottom: 1rem;
    }
    .badge-bar {
        display: flex;
        gap: 0.6rem;
        flex-wrap: wrap;
    }
    .model-pill {
        background-color: rgba(59, 130, 246, 0.15);
        color: #60A5FA;
        border: 1px solid rgba(59, 130, 246, 0.3);
        padding: 0.22rem 0.65rem;
        border-radius: 9999px;
        font-size: 0.78rem;
        font-weight: 600;
        font-family: 'JetBrains Mono', monospace;
    }
    .status-pill-ok {
        background-color: rgba(16, 185, 129, 0.15);
        color: #34D399;
        border: 1px solid rgba(16, 185, 129, 0.3);
        padding: 0.22rem 0.65rem;
        border-radius: 9999px;
        font-size: 0.78rem;
        font-weight: 600;
    }
    .agent-box {
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 1rem;
        background: #FFFFFF;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        height: 100%;
    }
    .agent-header {
        font-size: 0.92rem;
        font-weight: 700;
        color: #1E293B;
        display: flex;
        align-items: center;
        gap: 0.4rem;
        margin-bottom: 0.2rem;
    }
    .agent-model {
        font-size: 0.8rem;
        color: #64748B;
        font-family: 'JetBrains Mono', monospace;
    }
    .badge-critical {
        background-color: #FEE2E2;
        color: #991B1B;
        border: 1px solid #F87171;
        padding: 0.18rem 0.5rem;
        border-radius: 6px;
        font-size: 0.72rem;
        font-weight: 700;
    }
    .badge-major {
        background-color: #FEF3C7;
        color: #92400E;
        border: 1px solid #FBBF24;
        padding: 0.18rem 0.5rem;
        border-radius: 6px;
        font-size: 0.72rem;
        font-weight: 700;
    }
    .badge-minor {
        background-color: #DBEAFE;
        color: #1E40AF;
        border: 1px solid #93C5FD;
        padding: 0.18rem 0.5rem;
        border-radius: 6px;
        font-size: 0.72rem;
        font-weight: 700;
    }
    .metric-card {
        background: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 10px;
        padding: 1rem;
        text-align: center;
    }
    .metric-val {
        font-size: 1.6rem;
        font-weight: 700;
        color: #0F172A;
    }
    .metric-lbl {
        font-size: 0.82rem;
        color: #64748B;
        margin-top: 0.2rem;
    }
</style>
""", unsafe_allow_html=True)


# Pre-flight Ollama Environment Check
def check_ollama_status():
    ollama = OllamaProvider("check")
    if ollama.check_health():
        models = ollama.get_available_models()
        return True, models
    return False, []

ollama_online, installed_ollama_models = check_ollama_status()


# Sidebar Configuration Panel
st.sidebar.markdown("### ⚙️ Engine Settings")

provider_choice = st.sidebar.selectbox(
    "Inference Provider",
    options=["mock", "ollama", "openai_compat", "huggingface"],
    format_func=lambda x: {
        "mock": "⚡ Smart Simulator (Instant Demo / Zero Setup)",
        "ollama": "🦙 Local Ollama (Self-Hosted Private LLMs)",
        "openai_compat": "🌐 OpenAI-Compatible (Groq / DeepSeek / vLLM)",
        "huggingface": "🤗 Hugging Face Inference API"
    }.get(x, x),
    index=0 if not ollama_online or not installed_ollama_models else 1
)

st.sidebar.markdown("---")
st.sidebar.markdown("### 🤖 Multi-LLM Role Assignment")
st.sidebar.caption("Open-source models specified by Druidot Consulting:")

all_models = WorkflowConfig.get_supported_model_list()

# LLM 1: Generator
generator_model = st.sidebar.selectbox(
    "LLM 1: Generator (Coder & Fixer)",
    options=["qwen2.5:0.5b", "qwen2.5-coder:1.5b", "deepseek-coder:1.3b", "gemma2:2b", "mistral:latest"] + all_models,
    index=0,
    help="Generates code and applies refactoring fixes based on reviewer comments."
)

# LLM 2: Reviewer
reviewer_model = st.sidebar.selectbox(
    "LLM 2: Reviewer (Inspector)",
    options=["mistral:latest", "gemma2:2b", "deepseek-coder:1.3b", "qwen2.5-coder:1.5b"] + all_models,
    index=0,
    help="Performs static analysis, detects logic flaws, edge cases, and runtime bugs."
)

# LLM 3: Validator
enable_validator = st.sidebar.checkbox("Enable LLM 3: Security & Arbiter", value=True)
validator_model = "deepseek-coder:1.3b"
if enable_validator:
    validator_model = st.sidebar.selectbox(
        "LLM 3: Security Auditor & Consensus",
        options=["deepseek-coder:1.3b", "bonsai:latest", "gemma2:2b", "mistral:latest"] + all_models,
        index=0,
        help="Validates security (CWE/OWASP), checks edge cases, and confirms reviewer consensus."
    )

st.sidebar.markdown("---")
st.sidebar.markdown("### 🔄 Convergence & Guardrails")
max_retries = st.sidebar.slider("Retry Limit (Max Review Cycles)", min_value=1, max_value=5, value=3)
enable_sandbox = st.sidebar.checkbox("Automated Subprocess Sandbox Testing", value=True)
temperature = st.sidebar.slider("Model Temperature", min_value=0.0, max_value=0.8, value=0.2, step=0.05)

# Credentials if external provider
if provider_choice == "openai_compat":
    st.sidebar.markdown("#### Cloud Provider Keys")
    api_base = st.sidebar.text_input("Base URL", value=os.getenv("OPENAI_COMPATIBLE_BASE_URL", "https://api.groq.com/openai/v1"))
    api_key = st.sidebar.text_input("API Key", type="password", value=os.getenv("OPENAI_COMPATIBLE_API_KEY", ""))
    if api_base:
        os.environ["OPENAI_COMPATIBLE_BASE_URL"] = api_base
    if api_key:
        os.environ["OPENAI_COMPATIBLE_API_KEY"] = api_key
elif provider_choice == "huggingface":
    st.sidebar.markdown("#### Hugging Face Token")
    hf_token = st.sidebar.text_input("HF Token", type="password", value=os.getenv("HUGGINGFACEHUB_API_TOKEN", ""))
    if hf_token:
        os.environ["HUGGINGFACEHUB_API_TOKEN"] = hf_token


# Main Hero Banner
st.markdown("""
<div class="hero-container">
    <div class="hero-title">
        🛡️ OpenReviewAI Enterprise Studio
    </div>
    <div class="hero-subtitle">
        Autonomous Multi-LLM Collaborative Code Generation, Automated Static Analysis & Iterative Self-Healing Loop
    </div>
    <div class="badge-bar">
        <span class="model-pill">Qwen 2.5</span>
        <span class="model-pill">DeepSeek Coder</span>
        <span class="model-pill">Mistral 7B</span>
        <span class="model-pill">Gemma 2</span>
        <span class="model-pill">Bonsai</span>
        <span class="status-pill-ok">● Enterprise Sandbox Active</span>
    </div>
</div>
""", unsafe_allow_html=True)


# Live Agent Persona Visualizer
col_a1, col_a2, col_a3, col_a4 = st.columns(4)
with col_a1:
    st.markdown(f"""
    <div class="agent-box">
        <div class="agent-header">👨‍💻 LLM 1: Coder Agent</div>
        <div class="agent-model">{generator_model}</div>
        <p style="font-size: 0.78rem; color: #64748B; margin-top: 0.4rem;">Generates code & executes targeted bug refactoring.</p>
    </div>
    """, unsafe_allow_html=True)
with col_a2:
    st.markdown(f"""
    <div class="agent-box">
        <div class="agent-header">🧐 LLM 2: Code Reviewer</div>
        <div class="agent-model">{reviewer_model}</div>
        <p style="font-size: 0.78rem; color: #64748B; margin-top: 0.4rem;">Static logic analysis, boundary checks, and code scoring.</p>
    </div>
    """, unsafe_allow_html=True)
with col_a3:
    st.markdown(f"""
    <div class="agent-box">
        <div class="agent-header">🛡️ LLM 3: Security Arbiter</div>
        <div class="agent-model">{validator_model if enable_validator else 'Disabled'}</div>
        <p style="font-size: 0.78rem; color: #64748B; margin-top: 0.4rem;">Security vulnerability audit and consensus agreement.</p>
    </div>
    """, unsafe_allow_html=True)
with col_a4:
    st.markdown(f"""
    <div class="agent-box">
        <div class="agent-header">⚡ Isolated Sandbox</div>
        <div class="agent-model">Python AST + Subprocess</div>
        <p style="font-size: 0.78rem; color: #64748B; margin-top: 0.4rem;">Timeout guards, runtime exception & test runner.</p>
    </div>
    """, unsafe_allow_html=True)

st.write("")

# Dual Mode Tabs: (1) Prompt to Code, (2) Direct Code Audit & Repair
mode_selection = st.radio(
    "Workflow Execution Mode",
    ["Mode 1: 💡 Feature Specification to Production Code", "Mode 2: 🛠️ Direct File Audit & Automated Bug Repair"],
    horizontal=True
)

existing_code_input = None
task_prompt_input = ""

if "Mode 1" in mode_selection:
    col_preset, col_lang = st.columns([3, 1])
    with col_preset:
        preset_options = {
            "Palindrome Normalization (Edge cases & punctuation)": "Write a python function is_palindrome(s) to check if a string is a palindrome. It must ignore punctuation, casing, and whitespace, and safely handle None and empty string.",
            "Factorial Calculator (Boundary & negative inputs)": "Write a python function factorial(n) that computes n! using recursion or iteration, handling 0, 1, and raising ValueError on negative inputs.",
            "Fibonacci Generator (Time O(n), Space O(1))": "Write a python function fibonacci(n) that returns the nth Fibonacci number with O(n) time and O(1) space complexity.",
            "List Data Cleaner & Square Filter": "Write a python function solve_task(data) that filters even numbers and returns their squares, gracefully handling None and mixed types.",
            "Custom Task": ""
        }
        chosen_preset = st.selectbox("Quick Enterprise Templates", list(preset_options.keys()), index=0)
    with col_lang:
        target_language = st.selectbox("Language", ["python", "javascript", "go", "cpp"], index=0)

    task_prompt_input = st.text_area(
        "Feature Specification / Task Prompt",
        value=preset_options[chosen_preset] if chosen_preset != "Custom Task" else "",
        height=100,
        placeholder="Enter your algorithm, function, or software requirement here..."
    )

    with st.expander("🧪 Add Custom Unit Test Assertions (Optional)"):
        custom_tests = st.text_area(
            "Assertions executed inside isolated sandbox",
            value="",
            height=80,
            placeholder="assert is_palindrome('A man, a plan, a canal: Panama') == True\nassert is_palindrome(None) == False"
        )
else:
    # Mode 2: Direct File / Code Review
    st.info("Upload or paste any Python script. LLM 2 & LLM 3 will audit it for bugs/security flaws, and LLM 1 will repair it automatically!")
    
    col_up, col_paste = st.columns([1, 2])
    with col_up:
        uploaded_file = st.file_uploader("Upload Python File (.py)", type=["py"])
    with col_paste:
        sample_buggy_code = """# Legacy Code with Security & Runtime Flaws
def process_user_query(raw_expr):
    # Unsafe evaluation vulnerability
    return eval(raw_expr)

if __name__ == '__main__':
    print(process_user_query("[1, 2, 3]"))
"""
        pasted_code = st.text_area("Or Paste Code Directly", value=uploaded_file.getvalue().decode("utf-8") if uploaded_file else sample_buggy_code, height=140)

    existing_code_input = pasted_code
    task_prompt_input = "Perform comprehensive code review, fix security vulnerabilities, handle edge cases, and add type hints and docstrings."
    custom_tests = None
    target_language = "python"


# Launch Action Button
launch_col1, launch_col2 = st.columns([3, 1])
with launch_col1:
    start_btn = st.button("🚀 Run Multi-LLM Review & Correction Workflow", type="primary", use_container_width=True)
with launch_col2:
    if st.button("🔄 Reset Studio", use_container_width=True):
        st.session_state.workflow_result = None
        st.rerun()

# Session State
if "workflow_result" not in st.session_state:
    st.session_state.workflow_result = None


# Workflow Execution Handler
if start_btn:
    if not task_prompt_input.strip() and not existing_code_input:
        st.error("Please provide a task prompt or code to review!")
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

        progress_container = st.container()
        with progress_container:
            p_bar = st.progress(0, text="Initializing Multi-LLM Agents...")
            log_placeholder = st.empty()

        def on_event(event_name: str, data: dict):
            if event_name == "generation_started":
                p_bar.progress(15, text=f"Round {data.get('round')}: LLM 1 ({generator_model}) is generating solution...")
            elif event_name == "generation_completed":
                p_bar.progress(35, text="Code generated. Running AST checks & sandbox verification...")
            elif event_name == "execution_started":
                p_bar.progress(45, text=f"Executing code in subprocess sandbox...")
            elif event_name == "review_started":
                p_bar.progress(65, text=f"LLM 2 ({reviewer_model}) is conducting static inspection...")
            elif event_name == "validation_started":
                p_bar.progress(78, text=f"LLM 3 ({validator_model}) is running security audit...")
            elif event_name == "fix_started":
                p_bar.progress(88, text=f"Bugs detected! Passing feedback to LLM 1 for Round {data.get('round')} refactoring...")
            elif event_name == "workflow_completed":
                p_bar.progress(100, text="Workflow converged successfully!")

        try:
            with st.spinner("Multi-LLM Debate and Iterative Repair in progress..."):
                orchestrator = WorkflowOrchestrator(config=config)
                result = orchestrator.run(
                    task_prompt=task_prompt_input,
                    target_language=target_language,
                    unit_tests=custom_tests if custom_tests and custom_tests.strip() else None,
                    existing_code=existing_code_input,
                    on_event=on_event
                )
                st.session_state.workflow_result = result
                st.toast("Workflow converged successfully!", icon="✅")
        except Exception as e:
            st.error(f"Execution Error: {str(e)}")
            if provider_choice == "ollama":
                st.warning("Notice: If local Ollama has missing binary components, switch to '⚡ Smart Simulator' in the sidebar to test immediately!")


# Render Results Dashboard
if st.session_state.workflow_result:
    res: WorkflowResult = st.session_state.workflow_result

    st.write("---")
    
    # Executive Metrics Row
    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-val" style="color: {'#10B981' if res.status == 'APPROVED' else '#F59E0B'};">{res.status}</div>
            <div class="metric-lbl">Final Consensus Status</div>
        </div>
        """, unsafe_allow_html=True)
    with m2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-val">{res.rounds_count}</div>
            <div class="metric-lbl">Debate / Fix Rounds</div>
        </div>
        """, unsafe_allow_html=True)
    with m3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-val" style="color: #EF4444;">{res.total_bugs_detected}</div>
            <div class="metric-lbl">Bugs Detected</div>
        </div>
        """, unsafe_allow_html=True)
    with m4:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-val" style="color: #10B981;">{res.total_bugs_fixed}</div>
            <div class="metric-lbl">Bugs Resolved</div>
        </div>
        """, unsafe_allow_html=True)
    with m5:
        runtime_ms = res.final_execution.execution_time_ms if res.final_execution else 0.0
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-val">{runtime_ms:.1f}ms</div>
            <div class="metric-lbl">Sandbox Execution Time</div>
        </div>
        """, unsafe_allow_html=True)

    st.write("")

    # Result Tabs
    t_chat, t_diff, t_code, t_metrics, t_sandbox, t_audit = st.tabs([
        "💬 Multi-LLM Debate History",
        "🔍 Code Evolution Diffs",
        "🏆 Final Approved Code",
        "📊 Enterprise Code Metrics",
        "🧪 Sandbox Terminal",
        "📄 Audit Report & Export"
    ])

    # Tab 1: Debate History & Bug Log
    with t_chat:
        st.markdown("### 💬 Agent Dialogue & Feedback Cycles")
        for step in res.iterations:
            is_last = (step.round_idx == len(res.iterations) - 1)
            with st.expander(f"📍 Round {step.round_idx} — Status: {step.status}", expanded=is_last):
                col_exp_1, col_exp_2 = st.columns([1, 1])
                with col_exp_1:
                    st.markdown("**👨‍💻 LLM 1 (Generator / Fixer) Response:**")
                    st.info(step.generator_explanation or "Initial implementation generated.")
                with col_exp_2:
                    st.markdown("**🧐 Reviewer & Security Evaluations:**")
                    for rev in step.reviews:
                        score_color = "#10B981" if rev.overall_score >= 8 else "#F59E0B"
                        st.markdown(f"**{rev.reviewer_name}** (`{rev.reviewer_model}`): <span style='font-weight:700; color:{score_color}'>Score {rev.overall_score}/10</span>", unsafe_allow_html=True)
                        st.caption(rev.summary)

                # Bug List Table
                all_step_bugs = []
                for rev in step.reviews:
                    all_step_bugs.extend(rev.bugs)

                if all_step_bugs:
                    st.markdown("##### 🐛 Issues Identified in this Round:")
                    for b in all_step_bugs:
                        badge_style = f"badge-{b.severity.lower()}"
                        line_info = f"Line {b.line_number}: " if b.line_number else ""
                        st.markdown(f"""
                        <div style="padding: 0.6rem 0.8rem; background: #F8FAFC; border-left: 4px solid #EF4444; margin-bottom: 0.4rem; border-radius: 4px;">
                            <span class="{badge_style}">{b.severity}</span> 
                            <strong style="color: #1E293B; margin-left: 0.4rem;">[{b.category}]</strong> {line_info}{b.description}<br/>
                            <span style="font-size: 0.82rem; color: #16A34A; font-family: monospace;">Suggested Fix: {b.suggested_fix}</span>
                        </div>
                        """, unsafe_allow_html=True)

    # Tab 2: Code Diffs
    with t_diff:
        st.markdown("### 🔍 Code Refactoring Across Rounds")
        if len(res.iterations) > 1:
            initial_code = res.iterations[0].code
            diff_text = compute_unified_diff(initial_code, res.final_code, "Original Code (Round 0)", f"Refactored Code (Round {res.rounds_count-1})")
            st.code(diff_text, language="diff")
        else:
            st.success("The code was verified and approved on the first round without requiring code modifications!")

    # Tab 3: Final Code
    with t_code:
        st.markdown("### 🏆 Final Verified Production Code")
        st.code(res.final_code, language=res.target_language)
        
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            st.download_button(
                "⬇️ Download Solution (.py)",
                data=res.final_code,
                file_name="solution.py",
                mime="text/x-python",
                use_container_width=True
            )
        with col_d2:
            st.download_button(
                "⬇️ Download Full Audit Report (.md)",
                data=export_markdown_report(res),
                file_name=f"audit_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                mime="text/markdown",
                use_container_width=True
            )

    # Tab 4: Enterprise AST Metrics
    with t_metrics:
        st.markdown("### 📊 Enterprise Code Quality & Security Scan")
        is_valid, err, meta = check_syntax(res.final_code, res.target_language)
        
        q1, q2, q3, q4 = st.columns(4)
        with q1:
            st.metric("Security Score", f"{meta.get('security_score', 100)}/100", delta="Clean" if meta.get('security_score', 100) == 100 else "Flagged")
        with q2:
            st.metric("Cyclomatic Complexity", meta.get("cyclomatic_complexity", 1))
        with q3:
            st.metric("Functions", meta.get("num_functions", 0))
        with q4:
            st.metric("Lines of Code", meta.get("lines_of_code", 0))

        if meta.get("security_flags"):
            st.warning("Security Findings:")
            for flag in meta["security_flags"]:
                st.write(f"- ⚠️ {flag}")
        else:
            st.success("✅ No dangerous built-ins (eval, exec, injection vectors) detected in final source.")

        st.json(meta)

    # Tab 5: Sandbox Terminal
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
            st.info("Sandbox execution was disabled in configuration.")

    # Tab 6: Audit Report
    with t_audit:
        st.markdown("### 📄 Full Audit Trail Report")
        report_text = export_markdown_report(res)
        st.markdown(report_text)
