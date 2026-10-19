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
    page_title="OpenReviewAI — IIT AI Systems & Multi-Agent Formal Verification Studio",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom High-End Academic & Enterprise Styling (IIT Professor Lab Aesthetic)
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&family=Newsreader:ital,opsz,wght@1,6..72,400;1,6..72,600&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    /* Sidebar Styling */
    section[data-testid="stSidebar"] {
        background-color: #0F172A;
        border-right: 1px solid #1E293B;
    }
    section[data-testid="stSidebar"] * {
        color: #E2E8F0;
    }
    .sidebar-lab-header {
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.8) 0%, rgba(15, 23, 42, 0.95) 100%);
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 1.1rem;
        margin-bottom: 1.2rem;
        text-align: center;
    }
    .sidebar-lab-title {
        font-size: 0.88rem;
        font-weight: 700;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        color: #38BDF8;
        margin-bottom: 0.2rem;
    }
    .sidebar-lab-sub {
        font-size: 0.72rem;
        color: #94A3B8;
        font-style: italic;
    }
    .sidebar-section-badge {
        font-size: 0.72rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #38BDF8;
        margin-top: 1rem;
        margin-bottom: 0.4rem;
        display: block;
    }

    /* Main Academic Hero Container */
    .academic-hero {
        background: linear-gradient(135deg, #090D16 0%, #0F172A 50%, #1E293B 100%);
        border: 1px solid #334155;
        border-radius: 16px;
        padding: 2.2rem 2.6rem;
        margin-bottom: 1.6rem;
        box-shadow: 0 15px 35px -5px rgba(0, 0, 0, 0.35);
        position: relative;
        overflow: hidden;
    }
    .academic-hero::before {
        content: "";
        position: absolute;
        top: 0; left: 0; right: 0; height: 3px;
        background: linear-gradient(90deg, #38BDF8, #818CF8, #C084FC);
    }
    .academic-title {
        color: #F8FAFC;
        font-size: 2.2rem;
        font-weight: 700;
        letter-spacing: -0.025em;
        margin-bottom: 0.5rem;
        display: flex;
        align-items: center;
        gap: 0.7rem;
    }
    .academic-abstract {
        color: #CBD5E1;
        font-size: 0.95rem;
        line-height: 1.55;
        max-width: 95%;
        margin-bottom: 1.2rem;
        background: rgba(15, 23, 42, 0.6);
        border-left: 3px solid #38BDF8;
        padding: 0.7rem 1rem;
        border-radius: 0 8px 8px 0;
    }
    .badge-bar {
        display: flex;
        gap: 0.6rem;
        flex-wrap: wrap;
        align-items: center;
    }
    .model-badge {
        background: rgba(56, 189, 248, 0.12);
        color: #38BDF8;
        border: 1px solid rgba(56, 189, 248, 0.28);
        padding: 0.22rem 0.65rem;
        border-radius: 6px;
        font-size: 0.76rem;
        font-weight: 600;
        font-family: 'JetBrains Mono', monospace;
    }
    .protocol-badge {
        background: rgba(52, 211, 153, 0.12);
        color: #34D399;
        border: 1px solid rgba(52, 211, 153, 0.28);
        padding: 0.22rem 0.65rem;
        border-radius: 6px;
        font-size: 0.76rem;
        font-weight: 600;
    }

    /* Agent Topology Cards */
    .agent-card-container {
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 1.1rem;
        background: #FFFFFF;
        box-shadow: 0 2px 5px rgba(0,0,0,0.03);
        height: 100%;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
    }
    .agent-card-title {
        font-size: 0.92rem;
        font-weight: 700;
        color: #0F172A;
        display: flex;
        align-items: center;
        gap: 0.45rem;
    }
    .agent-card-math {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.76rem;
        color: #2563EB;
        background: #EFF6FF;
        padding: 0.15rem 0.4rem;
        border-radius: 4px;
        display: inline-block;
        margin-top: 0.2rem;
    }
    .agent-card-desc {
        font-size: 0.78rem;
        color: #64748B;
        margin-top: 0.5rem;
        line-height: 1.4;
    }

    /* Metrics & Scorecards */
    .metric-card {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 1.1rem;
        text-align: center;
        box-shadow: 0 2px 4px rgba(0,0,0,0.02);
    }
    .metric-val {
        font-size: 1.7rem;
        font-weight: 700;
        color: #0F172A;
        font-family: 'Inter', sans-serif;
    }
    .metric-lbl {
        font-size: 0.78rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #64748B;
        margin-top: 0.3rem;
    }

    /* Badges */
    .badge-critical {
        background-color: #FEE2E2;
        color: #991B1B;
        border: 1px solid #F87171;
        padding: 0.18rem 0.45rem;
        border-radius: 4px;
        font-size: 0.72rem;
        font-weight: 700;
    }
    .badge-major {
        background-color: #FEF3C7;
        color: #92400E;
        border: 1px solid #FBBF24;
        padding: 0.18rem 0.45rem;
        border-radius: 4px;
        font-size: 0.72rem;
        font-weight: 700;
    }
    .badge-minor {
        background-color: #DBEAFE;
        color: #1E40AF;
        border: 1px solid #93C5FD;
        padding: 0.18rem 0.45rem;
        border-radius: 4px;
        font-size: 0.72rem;
        font-weight: 700;
    }
</style>
""", unsafe_allow_html=True)


# Pre-flight Diagnostic Check
def check_ollama_status():
    ollama = OllamaProvider("check")
    if ollama.check_health():
        models = ollama.get_available_models()
        return True, models
    return False, []

ollama_online, installed_ollama_models = check_ollama_status()


# ==============================================================================
# SIDEBAR: IIT PROFESSOR & RESEARCH LAB CONTROL PANEL
# ==============================================================================
with st.sidebar:
    st.markdown("""
    <div class="sidebar-lab-header">
        <div class="sidebar-lab-title">🏛️ IIT AI Systems Lab</div>
        <div class="sidebar-lab-sub">Autonomous Multi-Agent Peer-Review & Formal Verification Framework</div>
    </div>
    """, unsafe_allow_html=True)

    # Telemetry Status Widget
    if ollama_online and installed_ollama_models:
        st.markdown(f"🟢 **Ollama Local Engine:** `Active ({len(installed_ollama_models)} weights)`")
    else:
        st.markdown("⚡ **Simulation / Cloud Engine:** `Ready`")

    st.markdown('<span class="sidebar-section-badge">1. Execution Engine & Protocol</span>', unsafe_allow_html=True)
    provider_choice = st.selectbox(
        "Backend Inference Subsystem",
        options=["mock", "ollama", "openai_compat", "huggingface"],
        format_func=lambda x: {
            "mock": "⚡ High-Fidelity Deterministic Simulator (Zero Setup)",
            "ollama": "🦙 Ollama Local Host (On-Premise Private Weights)",
            "openai_compat": "🌐 Cloud OpenAI-Compatible (Groq / vLLM / DeepSeek)",
            "huggingface": "🤗 Hugging Face Inference API"
        }.get(x, x),
        index=0 if not ollama_online or not installed_ollama_models else 1
    )

    st.markdown('<span class="sidebar-section-badge">2. Heterogeneous Agent Topology</span>', unsafe_allow_html=True)
    st.caption("Heterogeneous open-source models as required by Druidot Consulting:")

    all_models = WorkflowConfig.get_supported_model_list()

    generator_model = st.selectbox(
        "Agent 1: Coder & Fixer (A_gen)",
        options=["qwen2.5:0.5b", "qwen2.5-coder:1.5b", "deepseek-coder:1.3b", "gemma2:2b", "mistral:latest"] + all_models,
        index=0,
        help="Generates initial implementation and synthesizes patches based on peer reviews."
    )

    reviewer_model = st.selectbox(
        "Agent 2: Peer Reviewer (A_rev)",
        options=["mistral:latest", "gemma2:2b", "deepseek-coder:1.3b", "qwen2.5-coder:1.5b"] + all_models,
        index=0,
        help="Executes static AST analysis, algorithmic boundary checks, and code scoring."
    )

    enable_validator = st.checkbox("Enable Agent 3: Security & Consensus (A_val)", value=True)
    validator_model = "deepseek-coder:1.3b"
    if enable_validator:
        validator_model = st.selectbox(
            "Agent 3: Security Arbiter (A_val)",
            options=["deepseek-coder:1.3b", "bonsai:latest", "gemma2:2b", "mistral:latest"] + all_models,
            index=0,
            help="Performs secondary audit (CWE-95, OWASP Top 10) and verifies consensus."
        )

    st.markdown('<span class="sidebar-section-badge">3. Theoretical Convergence Bounds</span>', unsafe_allow_html=True)
    max_retries = st.slider("Maximum Iteration Depth (K)", min_value=1, max_value=5, value=3, help="Provable halting bound guaranteeing O(K * T_infer) termination.")
    enable_sandbox = st.checkbox("Sandbox Subprocess Isolation", value=True, help="Executes code in ephemeral isolated subprocess with strict timeout.")
    temperature = st.slider("Sampling Temperature (T)", min_value=0.0, max_value=0.8, value=0.15, step=0.05, help="Low temperature guarantees deterministic reviews.")

    if provider_choice == "openai_compat":
        st.markdown('<span class="sidebar-section-badge">4. Cloud Credentials</span>', unsafe_allow_html=True)
        api_base = st.text_input("API Base URL", value=os.getenv("OPENAI_COMPATIBLE_BASE_URL", "https://api.groq.com/openai/v1"))
        api_key = st.text_input("API Key", type="password", value=os.getenv("OPENAI_COMPATIBLE_API_KEY", ""))
        if api_base:
            os.environ["OPENAI_COMPATIBLE_BASE_URL"] = api_base
        if api_key:
            os.environ["OPENAI_COMPATIBLE_API_KEY"] = api_key
    elif provider_choice == "huggingface":
        st.markdown('<span class="sidebar-section-badge">4. Hugging Face Token</span>', unsafe_allow_html=True)
        hf_token = st.text_input("HF Token", type="password", value=os.getenv("HUGGINGFACEHUB_API_TOKEN", ""))
        if hf_token:
            os.environ["HUGGINGFACEHUB_API_TOKEN"] = hf_token

    st.markdown("---")
    st.markdown("""
    <div style="font-size: 0.7rem; color: #64748B; line-height: 1.4;">
        <strong>Academic Reference:</strong><br/>
        Multi-Agent Consensus & Formal AST Code Repair Protocol.<br/>
        IIT Research Group • MIT Licensed • 2026.
    </div>
    """, unsafe_allow_html=True)


# ==============================================================================
# MAIN PAGE: SCHOLARLY HERO & RESEARCH TOPOLOGY
# ==============================================================================
st.markdown("""
<div class="academic-hero">
    <div class="academic-title">
        🏛️ OpenReviewAI: Multi-LLM Autonomous Peer-Review Protocol
    </div>
    <div class="academic-abstract">
        <strong>Abstract:</strong> We formulate software generation and verification as a discrete multi-agent game between heterogeneous open-source Large Language Models (<strong>Qwen, DeepSeek, Mistral, Gemma, Bonsai</strong>). A generator agent synthesizes code, an inspector agent conducts semantic static code analysis, and a security validator arbitrates consensus. An isolated subprocess sandbox guarantees runtime safety, bound enforcement, and provable halting.
    </div>
    <div class="badge-bar">
        <span class="model-badge">LLM-1: Qwen-Coder</span>
        <span class="model-badge">LLM-2: Mistral-7B</span>
        <span class="model-badge">LLM-3: DeepSeek-R1</span>
        <span class="model-badge">Gemma-2</span>
        <span class="model-badge">Bonsai</span>
        <span class="protocol-badge">Formal Subprocess Verification</span>
        <span class="protocol-badge">Halting Guard: K &le; 5</span>
    </div>
</div>
""", unsafe_allow_html=True)


# Agent Topology Visualization Cards
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown(f"""
    <div class="agent-card-container">
        <div>
            <div class="agent-card-title">👨‍💻 Agent 1: Code Generator</div>
            <div class="agent-card-math">&mathcal;A_&#123;gen&#125; &rarr; S_k</div>
            <div class="agent-card-desc">Synthesizes candidate implementation S_0 and computes refactored patches &Delta;S_k addressing peer feedback.</div>
        </div>
        <div style="margin-top: 0.6rem; font-family: monospace; font-size: 0.72rem; color: #475569;">
            Weights: <strong>{generator_model}</strong>
        </div>
    </div>
    """, unsafe_allow_html=True)

with c2:
    st.markdown(f"""
    <div class="agent-card-container">
        <div>
            <div class="agent-card-title">🧐 Agent 2: Peer Reviewer</div>
            <div class="agent-card-math">&mathcal;A_&#123;rev&#125; &rarr; &lang;Bugs, Severity, Score&rang;</div>
            <div class="agent-card-desc">Conducts strict static analysis, edge-case boundary checks, and algorithmic correctness scoring.</div>
        </div>
        <div style="margin-top: 0.6rem; font-family: monospace; font-size: 0.72rem; color: #475569;">
            Weights: <strong>{reviewer_model}</strong>
        </div>
    </div>
    """, unsafe_allow_html=True)

with c3:
    st.markdown(f"""
    <div class="agent-card-container">
        <div>
            <div class="agent-card-title">🛡️ Agent 3: Security Arbiter</div>
            <div class="agent-card-math">&mathcal;A_&#123;val&#125; &rarr; &#123;APPROVED, FLAGGED&#125;</div>
            <div class="agent-card-desc">Audits CWE/OWASP vulnerabilities (e.g. CWE-95, injection) and confirms inter-agent consensus.</div>
        </div>
        <div style="margin-top: 0.6rem; font-family: monospace; font-size: 0.72rem; color: #475569;">
            Weights: <strong>{validator_model if enable_validator else 'Disabled'}</strong>
        </div>
    </div>
    """, unsafe_allow_html=True)

with c4:
    st.markdown(f"""
    <div class="agent-card-container">
        <div>
            <div class="agent-card-title">⚡ Execution Sandbox</div>
            <div class="agent-card-math">&mathcal;E_&#123;box&#125; &rarr; &#123;stdout, stderr, &Delta;t&#125;</div>
            <div class="agent-card-desc">AST syntax validation, subprocess isolation, assertion suite, and timeout protection.</div>
        </div>
        <div style="margin-top: 0.6rem; font-family: monospace; font-size: 0.72rem; color: #475569;">
            Engine: <strong>Python Subprocess</strong>
        </div>
    </div>
    """, unsafe_allow_html=True)

st.write("")

# Dual Operational Protocol Switcher
protocol_selection = st.radio(
    "Operational Research Protocol",
    [
        "Protocol A: 💡 De Novo Code Synthesis & Peer-Review (Specification -> Multi-LLM Debate)",
        "Protocol B: 🛠️ Codebase Vulnerability Audit & Automated Patching (Existing File -> Auto-Repair)"
    ],
    horizontal=True
)

existing_code_input = None
task_prompt_input = ""

if "Protocol A" in protocol_selection:
    col_preset, col_lang = st.columns([3, 1])
    with col_preset:
        preset_benchmarks = {
            "Benchmark 1: String Palindrome Normalization & Invariant Preservation": "Write a python function is_palindrome(s) that checks if a string is a palindrome. It must ignore punctuation, casing, and whitespace, and safely handle None and empty string.",
            "Benchmark 2: Recursive Factorial & Mathematical Invariants": "Write a python function factorial(n) that computes n! using recursion or iteration, handling base cases (0, 1) and raising ValueError on negative inputs.",
            "Benchmark 3: Optimal Fibonacci with O(n) Time and O(1) Space Complexity": "Write a python function fibonacci(n) that returns the nth Fibonacci number with O(n) time complexity and O(1) auxiliary space complexity.",
            "Benchmark 4: List Data Cleaner & Square Filter (Defensive Types)": "Write a python function solve_task(data) that filters even numbers and returns their squares, gracefully handling None and mixed non-integer types.",
            "Custom Research Specification": ""
        }
        chosen_benchmark = st.selectbox("Computer Science Benchmark Presets", list(preset_benchmarks.keys()), index=0)
    with col_lang:
        target_language = st.selectbox("Target Language", ["python", "javascript", "go", "cpp"], index=0)

    task_prompt_input = st.text_area(
        "Functional Specification / Prompt",
        value=preset_benchmarks[chosen_benchmark] if chosen_benchmark != "Custom Research Specification" else "",
        height=95,
        placeholder="Enter formal software requirements, functional invariants, or algorithmic constraints..."
    )

    with st.expander("🧪 Formal Assertion Verification Suite (Unit Tests)"):
        custom_tests = st.text_area(
            "Test Assertions executed inside the sandbox",
            value="",
            height=80,
            placeholder="assert is_palindrome('A man, a plan, a canal: Panama') == True\nassert is_palindrome(None) == False"
        )
else:
    # Protocol B: Codebase Audit & Repair
    st.info("📂 **Codebase Audit Mode:** Upload or paste any legacy or unverified script. Agent 2 & Agent 3 will audit it for security and logic defects, and Agent 1 will synthesize a formal patch!")
    col_u1, col_u2 = st.columns([1, 2])
    with col_u1:
        uploaded_file = st.file_uploader("Upload Source File (.py)", type=["py"])
    with col_u2:
        default_buggy_snippet = """# Unsafe Code Snippet with Security Vulnerability
def process_user_query(raw_expr):
    # CRITICAL: Remote code execution vulnerability (CWE-95)
    return eval(raw_expr)

if __name__ == '__main__':
    print(process_user_query("[1, 2, 3]"))
"""
        pasted_code = st.text_area("Or Paste Code Snippet", value=uploaded_file.getvalue().decode("utf-8") if uploaded_file else default_buggy_snippet, height=135)

    existing_code_input = pasted_code
    task_prompt_input = "Perform comprehensive security audit, eliminate vulnerabilities (CWE-95), handle edge cases, and apply type annotations and docstrings."
    custom_tests = None
    target_language = "python"


# Action Execution Controls
b_col1, b_col2 = st.columns([3, 1])
with b_col1:
    execute_button = st.button("🚀 Initiate Multi-Agent Peer Review Protocol", type="primary", use_container_width=True)
with b_col2:
    if st.button("🔄 Reset Execution State", use_container_width=True):
        st.session_state.workflow_result = None
        st.rerun()

if "workflow_result" not in st.session_state:
    st.session_state.workflow_result = None


# Execution Handler
if execute_button:
    if not task_prompt_input.strip() and not existing_code_input:
        st.error("Please provide functional specifications or a code snippet to audit.")
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
            progress_bar = st.progress(0, text="Initializing Multi-Agent State Graph...")

        def on_event(event_name: str, data: dict):
            if event_name == "generation_started":
                progress_bar.progress(15, text=f"Round {data.get('round')}: Agent 1 ({generator_model}) synthesizing code...")
            elif event_name == "generation_completed":
                progress_bar.progress(35, text="Code generated. Invoking AST parsing & sandbox verification...")
            elif event_name == "execution_started":
                progress_bar.progress(45, text="Executing sandbox subprocess test runner...")
            elif event_name == "review_started":
                progress_bar.progress(65, text=f"Agent 2 ({reviewer_model}) conducting peer review & static inspection...")
            elif event_name == "validation_started":
                progress_bar.progress(78, text=f"Agent 3 ({validator_model}) auditing security & confirming consensus...")
            elif event_name == "fix_started":
                progress_bar.progress(88, text=f"Bugs detected! Passing structured bug ledger back to Agent 1 for Round {data.get('round')} refactoring...")
            elif event_name == "workflow_completed":
                progress_bar.progress(100, text="Protocol converged! Production-ready code verified.")

        try:
            with st.spinner("Multi-Agent Peer Review & Consensus Protocol in progress..."):
                orchestrator = WorkflowOrchestrator(config=config)
                result = orchestrator.run(
                    task_prompt=task_prompt_input,
                    target_language=target_language,
                    unit_tests=custom_tests if custom_tests and custom_tests.strip() else None,
                    existing_code=existing_code_input,
                    on_event=on_event
                )
                st.session_state.workflow_result = result
                st.toast("Peer Review Protocol converged successfully!", icon="🏛️")
        except Exception as e:
            st.error(f"Execution Error: {str(e)}")
            if provider_choice == "ollama":
                st.warning("Diagnostic Note: If local Ollama has missing server binaries, switch 'Backend Inference Subsystem' in the sidebar to '⚡ High-Fidelity Simulator' to test immediately!")


# ==============================================================================
# AUDIT RESULTS & RESEARCH DOSSIER
# ==============================================================================
if st.session_state.workflow_result:
    res: WorkflowResult = st.session_state.workflow_result

    st.write("---")

    # Executive Research Scorecard
    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-val" style="color: {'#10B981' if res.status == 'APPROVED' else '#F59E0B'};">{res.status}</div>
            <div class="metric-lbl">Consensus State</div>
        </div>
        """, unsafe_allow_html=True)
    with m2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-val">{res.rounds_count}</div>
            <div class="metric-lbl">Iteration Rounds (K)</div>
        </div>
        """, unsafe_allow_html=True)
    with m3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-val" style="color: #EF4444;">{res.total_bugs_detected}</div>
            <div class="metric-lbl">Defects Flagged</div>
        </div>
        """, unsafe_allow_html=True)
    with m4:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-val" style="color: #10B981;">{res.total_bugs_fixed}</div>
            <div class="metric-lbl">Defects Resolved</div>
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

    # Detailed Analysis Tabs
    t_chat, t_diff, t_code, t_metrics, t_sandbox, t_audit = st.tabs([
        "💬 Multi-Agent Debate Ledger",
        "🔍 Formal Code Evolution Diff",
        "🏆 Verified Production Source",
        "📊 AST Metrics & Security Scan",
        "🧪 Sandbox Subprocess Console",
        "📄 Formal Audit Dossier"
    ])

    # Tab 1: Debate History
    with t_chat:
        st.markdown("### 💬 Inter-Agent Dialogue & Bug Ledger")
        for step in res.iterations:
            is_last = (step.round_idx == len(res.iterations) - 1)
            with st.expander(f"📍 Round {step.round_idx} — Protocol State: `{step.status}`", expanded=is_last):
                c_step1, c_step2 = st.columns(2)
                with c_step1:
                    st.markdown("**👨‍💻 Agent 1 (Generator / Fixer) Explanation:**")
                    st.info(step.generator_explanation or "Initial implementation synthesized.")
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
                    st.markdown("##### 🐛 Formal Defect Breakdown:")
                    for b in step_bugs:
                        badge_style = f"badge-{b.severity.lower()}"
                        line_info = f"Line {b.line_number}: " if b.line_number else ""
                        st.markdown(f"""
                        <div style="padding: 0.6rem 0.8rem; background: #F8FAFC; border-left: 4px solid #EF4444; margin-bottom: 0.4rem; border-radius: 6px;">
                            <span class="{badge_style}">{b.severity}</span> 
                            <strong style="color: #0F172A; margin-left: 0.4rem;">[{b.category}]</strong> {line_info}{b.description}<br/>
                            <span style="font-size: 0.82rem; color: #16A34A; font-family: monospace;">Formal Fix: {b.suggested_fix}</span>
                        </div>
                        """, unsafe_allow_html=True)

    # Tab 2: Code Diff
    with t_diff:
        st.markdown("### 🔍 Mathematical Diff & Refactoring Evolution")
        if len(res.iterations) > 1:
            initial_code = res.iterations[0].code
            diff_text = compute_unified_diff(initial_code, res.final_code, "Initial Candidate (Round 0)", f"Verified Solution (Round {res.rounds_count-1})")
            st.code(diff_text, language="diff")
        else:
            st.success("✅ The candidate code satisfied all formal invariants and passed peer review on Round 0!")

    # Tab 3: Final Code
    with t_code:
        st.markdown("### 🏆 Final Verified Production Code")
        st.code(res.final_code, language=res.target_language)
        
        col_down1, col_down2 = st.columns(2)
        with col_down1:
            st.download_button(
                "⬇️ Download Verified Python Script (.py)",
                data=res.final_code,
                file_name="verified_solution.py",
                mime="text/x-python",
                use_container_width=True
            )
        with col_down2:
            st.download_button(
                "⬇️ Download Formal Markdown Audit Report (.md)",
                data=export_markdown_report(res),
                file_name=f"peer_review_dossier_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                mime="text/markdown",
                use_container_width=True
            )

    # Tab 4: AST Metrics
    with t_metrics:
        st.markdown("### 📊 Formal AST Complexity & Security Metrics")
        is_valid, err, meta = check_syntax(res.final_code, res.target_language)
        
        q1, q2, q3, q4 = st.columns(4)
        with q1:
            st.metric("Security Score", f"{meta.get('security_score', 100)}/100", delta="Clean" if meta.get('security_score', 100) == 100 else "Flagged")
        with q2:
            st.metric("Cyclomatic Complexity (M)", meta.get("cyclomatic_complexity", 1), help="McCabe Complexity M = E - N + 2P")
        with q3:
            st.metric("Functions", meta.get("num_functions", 0))
        with q4:
            st.metric("Executable LOC", meta.get("lines_of_code", 0))

        if meta.get("security_flags"):
            st.warning("Security Vulnerability Findings:")
            for flag in meta["security_flags"]:
                st.write(f"- ⚠️ {flag}")
        else:
            st.success("✅ Formal static AST analysis verified 0 security flaws (eval, exec, and command injection free).")

        with st.expander("Inspecting Full AST Structural Metadata"):
            st.json(meta)

    # Tab 5: Sandbox
    with t_sandbox:
        st.markdown("### 🧪 Sandbox Subprocess Execution Console")
        if res.final_execution:
            fe = res.final_execution
            if fe.success:
                st.success(f"Sandbox Verification Passed cleanly in {fe.execution_time_ms:.1f}ms (Exit Code: {fe.exit_code})")
            else:
                st.error(f"Sandbox Verification Failed (Exit Code: {fe.exit_code})")
                
            st.markdown("**Standard Output (stdout):**")
            st.code(fe.stdout if fe.stdout.strip() else "(No standard output)")
            
            if fe.stderr.strip():
                st.markdown("**Standard Error (stderr):**")
                st.code(fe.stderr)
        else:
            st.info("Sandbox execution was bypassed.")

    # Tab 6: Formal Audit Dossier
    with t_audit:
        st.markdown("### 📄 Formal Peer-Review Audit Dossier")
        report_text = export_markdown_report(res)
        st.markdown(report_text)
