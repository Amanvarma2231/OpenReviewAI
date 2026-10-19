import os
import json
import streamlit as st
from datetime import datetime

from openreview_ai.config import WorkflowConfig, OPENSOURCE_MODEL_FAMILIES
from openreview_ai.engine import WorkflowOrchestrator
from openreview_ai.schema import WorkflowResult, ReviewStatus, SeverityLevel
from openreview_ai.utils.diff_viewer import compute_unified_diff
from openreview_ai.utils.report_exporter import export_markdown_report
from openreview_ai.providers.ollama import OllamaProvider

# Set Page Config
st.set_page_config(
    page_title="OpenReviewAI - Multi-LLM Code Review & Correction",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.3rem;
        font-weight: 700;
        color: #1E3A8A;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #4B5563;
        margin-bottom: 1.5rem;
    }
    .agent-card {
        padding: 1.2rem;
        border-radius: 10px;
        margin-bottom: 1rem;
        border-left: 6px solid #3B82F6;
        background-color: #F8FAFC;
    }
    .badge-approved {
        background-color: #DEF7EC;
        color: #03543F;
        padding: 0.25rem 0.6rem;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .badge-changes {
        background-color: #FDE8E8;
        color: #9B1C1C;
        padding: 0.25rem 0.6rem;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .badge-critical {
        background-color: #EF4444;
        color: white;
        padding: 0.15rem 0.4rem;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: bold;
    }
    .badge-major {
        background-color: #F59E0B;
        color: white;
        padding: 0.15rem 0.4rem;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: bold;
    }
    .badge-minor {
        background-color: #3B82F6;
        color: white;
        padding: 0.15rem 0.4rem;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)


# Sidebar Configuration
st.sidebar.title("⚙️ Engine Configuration")

# Provider Selection
provider_option = st.sidebar.selectbox(
    "LLM Provider",
    options=["mock", "ollama", "huggingface", "openai_compat"],
    format_func=lambda x: {
        "mock": "⚡ Smart Simulator (Instant Demo / Offline)",
        "ollama": "🦙 Ollama (Local Open-Source Runner)",
        "huggingface": "🤗 Hugging Face Inference API",
        "openai_compat": "🌐 OpenAI-Compatible API (Groq / DeepSeek / vLLM)"
    }.get(x, x),
    index=0
)

# Model Presets (as specified by Druidot Consulting: Gemma, Mistral, Bonsai, Qwen, DeepSeek)
st.sidebar.subheader("🤖 Model Selection (Open-Source)")

flat_models = WorkflowConfig.get_supported_model_list()

generator_model = st.sidebar.selectbox(
    "LLM 1: Code Generator",
    options=["qwen2.5:0.5b", "qwen2.5-coder:1.5b", "deepseek-coder:1.3b", "gemma2:2b", "mistral:latest"] + [m for m in flat_models if m not in ["qwen2.5:0.5b", "qwen2.5-coder:1.5b", "deepseek-coder:1.3b", "gemma2:2b", "mistral:latest"]],
    index=0,
    help="Responsible for generating initial code and refactoring bugs."
)

reviewer_model = st.sidebar.selectbox(
    "LLM 2: Code Reviewer",
    options=["mistral:latest", "gemma2:2b", "deepseek-coder:1.3b", "qwen2.5-coder:1.5b"] + [m for m in flat_models if m not in ["mistral:latest", "gemma2:2b", "deepseek-coder:1.3b", "qwen2.5-coder:1.5b"]],
    index=0,
    help="Performs strict code review, identifying edge cases and algorithmic flaws."
)

enable_validator = st.sidebar.checkbox("Enable LLM 3 (Validator / Arbiter)", value=True)
validator_model = None
if enable_validator:
    validator_model = st.sidebar.selectbox(
        "LLM 3: Security & Arbiter",
        options=["deepseek-coder:1.3b", "bonsai:latest", "gemma2:2b", "mistral:latest"] + [m for m in flat_models if m not in ["deepseek-coder:1.3b", "bonsai:latest", "gemma2:2b", "mistral:latest"]],
        index=0,
        help="Audits security risks and confirms review consensus."
    )

# Execution Controls
st.sidebar.subheader("🔄 Loop Controls")
max_retries = st.sidebar.slider("Maximum Review Cycles (Retries)", min_value=1, max_value=6, value=3)
enable_sandbox = st.sidebar.checkbox("Enable Automated Sandbox Testing", value=True)
temperature = st.sidebar.slider("Sampling Temperature", min_value=0.0, max_value=1.0, value=0.2, step=0.05)

# Optional credentials if provider requires
if provider_option == "huggingface":
    hf_token = st.sidebar.text_input("Hugging Face API Token", type="password")
    if hf_token:
        os.environ["HUGGINGFACEHUB_API_TOKEN"] = hf_token
elif provider_option == "openai_compat":
    api_base = st.sidebar.text_input("Base URL", value="https://api.groq.com/openai/v1")
    api_key = st.sidebar.text_input("API Key", type="password")
    if api_base:
        os.environ["OPENAI_COMPATIBLE_BASE_URL"] = api_base
    if api_key:
        os.environ["OPENAI_COMPATIBLE_API_KEY"] = api_key


# Main Header
st.markdown('<div class="main-header">🛡️ OpenReviewAI Studio</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Multi-LLM Collaborative Code Generation, Automated Review & Iterative Bug Correction Engine</div>', unsafe_allow_html=True)

# Preset Templates
preset_tasks = {
    "Palindrome Checker (Edge-case flaw)": "Write a python function to check if a string is a palindrome. It must ignore punctuation, casing, and spaces, and handle empty or None input gracefully.",
    "Factorial Calculator (Recursion edge cases)": "Write a python function to compute the factorial of an integer. Must handle 0, 1, and raise a ValueError for negative numbers.",
    "Fibonacci Sequence": "Write a python function to return the nth Fibonacci number with O(n) time complexity and O(1) space complexity.",
    "Even Numbers Squared Filter": "Write a python function solve_task(data) that filters even numbers and returns their squares. Must handle None and empty list safely.",
    "Custom Prompt": ""
}

selected_preset = st.selectbox("💡 Quick Task Templates", list(preset_tasks.keys()), index=0)

default_prompt = preset_tasks[selected_preset] if selected_preset != "Custom Prompt" else ""
task_prompt = st.text_area(
    "Task Requirements / Specification",
    value=default_prompt,
    height=120,
    placeholder="Describe the function, algorithm, or script you want the multi-LLM team to build..."
)

with st.expander("🧪 Optional: Automated Unit Tests (Test Suite)"):
    unit_tests = st.text_area(
        "Unit Test Assertions (appended to code in sandbox)",
        value="",
        height=90,
        placeholder="assert is_palindrome('A man, a plan, a canal: Panama') == True\nassert is_palindrome(None) == False"
    )

start_button = st.button("🚀 Start Multi-LLM Review Workflow", type="primary", use_container_width=True)

# Session State for storing workflow results
if "workflow_result" not in st.session_state:
    st.session_state.workflow_result = None

if start_button:
    if not task_prompt.strip():
        st.error("Please enter a task specification before launching the workflow.")
    else:
        config = WorkflowConfig(
            provider_type=provider_option,
            generator_model=generator_model,
            reviewer_model=reviewer_model,
            validator_model=validator_model or "",
            max_retries=max_retries,
            enable_sandbox_execution=enable_sandbox,
            enable_third_llm_validator=enable_validator,
            temperature=temperature
        )

        progress_bar = st.progress(0, text="Initializing Multi-LLM Agents...")
        status_box = st.empty()

        def on_event(event_name: str, data: dict):
            if event_name == "generation_started":
                progress_bar.progress(15, text=f"Round {data.get('round')}: LLM 1 ({generator_model}) is generating code...")
            elif event_name == "generation_completed":
                progress_bar.progress(35, text="Initial code generated. Passing to verification...")
            elif event_name == "execution_started":
                progress_bar.progress(45, text=f"Running Round {data.get('round')} code in safe sandbox...")
            elif event_name == "review_started":
                progress_bar.progress(60, text=f"LLM 2 ({reviewer_model}) is conducting code review...")
            elif event_name == "validation_started":
                progress_bar.progress(75, text=f"LLM 3 ({validator_model}) is conducting security audit...")
            elif event_name == "fix_started":
                progress_bar.progress(85, text=f"Bugs detected! Passing feedback to LLM 1 for Round {data.get('round')} fixes...")
            elif event_name == "workflow_completed":
                progress_bar.progress(100, text="Workflow completed!")

        try:
            with st.spinner("Multi-LLM Debate and Review in progress..."):
                orchestrator = WorkflowOrchestrator(config=config)
                result = orchestrator.run(
                    task_prompt=task_prompt,
                    target_language="python",
                    unit_tests=unit_tests if unit_tests.strip() else None,
                    on_event=on_event
                )
                st.session_state.workflow_result = result
                st.success(f"Workflow Complete: Status `{result.status}` in {result.rounds_count} round(s)!")
        except Exception as e:
            st.error(f"Error executing workflow: {str(e)}")
            if provider_option == "ollama":
                st.info("Tip: If local Ollama has missing server binaries, switch LLM Provider to '⚡ Smart Simulator' in the sidebar to test immediately!")


# Render Results
if st.session_state.workflow_result:
    res: WorkflowResult = st.session_state.workflow_result

    st.divider()

    # Top Metrics Bar
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Workflow Status", res.status, delta="Final Result")
    with col2:
        st.metric("Total Iterations", f"{res.rounds_count} Round(s)")
    with col3:
        st.metric("Bugs Flagged", res.total_bugs_detected)
    with col4:
        st.metric("Bugs Resolved", res.total_bugs_fixed)

    # Tabs for structured viewing
    tab_debate, tab_diff, tab_code, tab_sandbox, tab_audit = st.tabs([
        "💬 Multi-LLM Debate & Feedback",
        "🔍 Code Evolution & Diffs",
        "🏆 Final Approved Code",
        "🧪 Sandbox Execution",
        "📄 Audit Report & Export"
    ])

    with tab_debate:
        st.subheader("Multi-Agent Dialogue & Iteration History")
        for step in res.iterations:
            with st.expander(f"📍 Round {step.round_idx} - Status: `{step.status}`", expanded=(step.round_idx == len(res.iterations)-1)):
                st.markdown(f"**LLM 1 (Generator - `{res.generator_model}`) Explanation:**")
                st.info(step.generator_explanation or "Initial implementation.")

                st.markdown("**Reviewer Feedback & Bug Reports:**")
                for rev in step.reviews:
                    status_badge = '<span class="badge-approved">APPROVED</span>' if rev.status == ReviewStatus.APPROVED else '<span class="badge-changes">CHANGES REQUESTED</span>'
                    st.markdown(f"**{rev.reviewer_name}** (`{rev.reviewer_model}`): {status_badge} — *Score: {rev.overall_score}/10*", unsafe_allow_html=True)
                    st.write(rev.summary)

                    if rev.bugs:
                        st.markdown(f"##### Issues Identified ({len(rev.bugs)}):")
                        for bug in rev.bugs:
                            sev_class = f"badge-{bug.severity.lower()}"
                            line_str = f"Line {bug.line_number}: " if bug.line_number else ""
                            st.markdown(
                                f"- <span class=\"{sev_class}\">{bug.severity}</span> `[{bug.category}]` {line_str}**{bug.description}**<br/>"
                                f"  *Suggested Fix:* `{bug.suggested_fix}`",
                                unsafe_allow_html=True
                            )

    with tab_diff:
        st.subheader("Code Changes Across Iterations")
        if len(res.iterations) > 1:
            initial = res.iterations[0].code
            final = res.final_code
            diff_text = compute_unified_diff(initial, final, "Round 0 (Initial)", f"Round {res.rounds_count} (Final)")
            st.code(diff_text, language="diff")
        else:
            st.info("The code was approved on the first round without requiring code modifications!")

    with tab_code:
        st.subheader("Final Validated Source Code")
        st.code(res.final_code, language=res.target_language)
        st.download_button(
            "⬇️ Download Python Script",
            data=res.final_code,
            file_name="solution.py",
            mime="text/x-python"
        )

    with tab_sandbox:
        st.subheader("Sandbox Execution & Unit Tests")
        if res.final_execution:
            fe = res.final_execution
            if fe.success:
                st.success(f"Sandbox Execution Passed! (Runtime: {fe.execution_time_ms:.2f}ms)")
            else:
                st.error(f"Sandbox Execution Failed (Exit Code: {fe.exit_code})")

            st.markdown("**Standard Output (stdout):**")
            st.code(fe.stdout if fe.stdout else "(No output)")

            if fe.stderr:
                st.markdown("**Standard Error (stderr):**")
                st.code(fe.stderr)
        else:
            st.info("Automated sandbox execution was disabled for this run.")

    with tab_audit:
        st.subheader("Comprehensive Audit Trail")
        report_md = export_markdown_report(res)
        st.markdown(report_md)
        st.download_button(
            "⬇️ Download Markdown Audit Report",
            data=report_md,
            file_name=f"audit_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
            mime="text/markdown"
        )
