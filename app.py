"""
OpenReview AI — Multi-LLM Code Generation, Review & Self-Correction System
========================================================================
Production-Grade Enterprise Interface.
Developed by Aman Varma · Druidot Consulting Pvt. Ltd.
"""
import os
import json
import time
import uuid
import base64
import traceback
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

import streamlit as st

from openreview_ai.config import WorkflowConfig, OPENSOURCE_MODEL_FAMILIES
from openreview_ai.engine import WorkflowOrchestrator
from openreview_ai.schema import (
    WorkflowResult,
    IterationStep,
    AgentMessage,
    ReviewFeedback,
    ExecutionResult,
    BugItem,
    ReviewStatus,
    SeverityLevel,
    BugCategory,
)
from openreview_ai.utils.diff_viewer import compute_unified_diff, compute_line_changes
from openreview_ai.utils.report_exporter import export_markdown_report
from openreview_ai.providers.ollama import OllamaProvider
from openreview_ai.sandbox.syntax_checker import check_syntax

from models.schemas import (
    WorkflowReport,
    WorkflowStatus,
    IterationRecord,
    ReviewVerdict,
    TestStatus,
    SyntaxCheckResult,
    TestExecutionResult,
    ReviewResult,
    ReviewIssue,
    IssueSeverity,
)
from storage.history_store import HistoryStore
from storage.report_generator import generate_markdown_report

# ─────────────────────────────────────────────────────────────────────────────
#  1. PAGE CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────
FAVICON_PATH = Path(__file__).parent / "assets" / "favicon.png"
if not FAVICON_PATH.exists():
    FAVICON_PATH = Path(__file__).parent / "assets" / "logo_icon.svg"

st.set_page_config(
    page_title="OpenReview AI — Multi-LLM Code Review Studio",
    page_icon=str(FAVICON_PATH) if FAVICON_PATH.exists() else "🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "About": "### OpenReview AI v2.1.0\nMulti-LLM Autonomous Code Generation, Review & Self-Correction Studio.\nDeveloped by Aman Varma."
    },
)

# ─────────────────────────────────────────────────────────────────────────────
#  2. ASSET HELPERS & LOGO
# ─────────────────────────────────────────────────────────────────────────────
def _svg_b64(path: str) -> str:
    """Converts local SVG asset to base64 inline data URI."""
    try:
        p = Path(path)
        if p.exists():
            data = p.read_bytes()
            return "data:image/svg+xml;base64," + base64.b64encode(data).decode()
    except Exception:
        pass
    return ""

LOGO_ICON_SRC = _svg_b64(str(Path(__file__).parent / "assets" / "logo_icon.svg"))
LOGO_PRIMARY_SRC = _svg_b64(str(Path(__file__).parent / "assets" / "logo.svg"))

# ─────────────────────────────────────────────────────────────────────────────
#  3. SESSION STATE INITIALIZATION
# ─────────────────────────────────────────────────────────────────────────────
if "theme_mode" not in st.session_state:
    st.session_state.theme_mode = "light"  # Default is clean, human light theme

if "active_page" not in st.session_state:
    st.session_state.active_page = "Dashboard"

if "workflow_result" not in st.session_state:
    st.session_state.workflow_result = None

if "provider_choice" not in st.session_state:
    st.session_state.provider_choice = "mock"  # Smart Simulator works out-of-the-box

if "gen_model_setting" not in st.session_state:
    st.session_state.gen_model_setting = "qwen2.5:0.5b"

if "rev_model_setting" not in st.session_state:
    st.session_state.rev_model_setting = "mistral:latest"

if "val_model_setting" not in st.session_state:
    st.session_state.val_model_setting = "deepseek-coder:1.3b"

if "max_retries_setting" not in st.session_state:
    st.session_state.max_retries_setting = 3

if "sandbox_enabled" not in st.session_state:
    st.session_state.sandbox_enabled = True

if "ast_syntax_enabled" not in st.session_state:
    st.session_state.ast_syntax_enabled = True

if "temperature_setting" not in st.session_state:
    st.session_state.temperature_setting = 0.2

if "ollama_url_setting" not in st.session_state:
    st.session_state.ollama_url_setting = "http://localhost:11434"

# ─────────────────────────────────────────────────────────────────────────────
#  4. DYNAMIC HUMAN DESIGN SYSTEM (LIGHT & DARK THEMES)
# ─────────────────────────────────────────────────────────────────────────────
is_dark = st.session_state.theme_mode == "dark"

if not is_dark:
    # ── LIGHT THEME DESIGN TOKENS (Natural, Professional, Human Product) ──
    css_theme = """
    :root {
        --bg-base: #F8FAFC;
        --bg-surface: #FFFFFF;
        --bg-surface-alt: #F1F5F9;
        --bg-input: #FFFFFF;
        --border-subtle: #E2E8F0;
        --border-strong: #CBD5E1;
        --text-primary: #0F172A;
        --text-secondary: #334155;
        --text-muted: #64748B;
        --text-subtle: #94A3B8;
        --primary: #2563EB;
        --primary-hover: #1D4ED8;
        --primary-light: #EFF6FF;
        --primary-border: #BFDBFE;
        --success: #059669;
        --success-bg: #ECFDF5;
        --success-border: #A7F3D0;
        --warning: #D97706;
        --warning-bg: #FFFBEB;
        --warning-border: #FDE68A;
        --danger: #DC2626;
        --danger-bg: #FEF2F2;
        --danger-border: #FECACA;
        --sidebar-bg: #FFFFFF;
        --sidebar-border: #E2E8F0;
        --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
        --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.06), 0 2px 4px -2px rgba(0, 0, 0, 0.04);
        --shadow-card: 0 1px 3px 0 rgba(0, 0, 0, 0.05), 0 1px 2px -1px rgba(0, 0, 0, 0.03);
        --code-bg: #0F172A;
        --code-color: #E2E8F0;
    }
    """
else:
    # ── DARK THEME DESIGN TOKENS (Refined, Restrained Slate/Charcoal) ────
    css_theme = """
    :root {
        --bg-base: #0B0F17;
        --bg-surface: #131B2A;
        --bg-surface-alt: #1A2436;
        --bg-input: #131B2A;
        --border-subtle: #233045;
        --border-strong: #334460;
        --text-primary: #F8FAFC;
        --text-secondary: #CBD5E1;
        --text-muted: #94A3B8;
        --text-subtle: #64748B;
        --primary: #3B82F6;
        --primary-hover: #60A5FA;
        --primary-light: rgba(59, 130, 246, 0.12);
        --primary-border: rgba(59, 130, 246, 0.3);
        --success: #10B981;
        --success-bg: rgba(16, 185, 129, 0.1);
        --success-border: rgba(16, 185, 129, 0.25);
        --warning: #F59E0B;
        --warning-bg: rgba(245, 158, 11, 0.1);
        --warning-border: rgba(245, 158, 11, 0.25);
        --danger: #EF4444;
        --danger-bg: rgba(239, 68, 68, 0.1);
        --danger-border: rgba(239, 68, 68, 0.25);
        --sidebar-bg: #0E1522;
        --sidebar-border: #1E2B3E;
        --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.3);
        --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.4);
        --shadow-card: 0 1px 3px 0 rgba(0, 0, 0, 0.3);
        --code-bg: #070B12;
        --code-color: #F1F5F9;
    }
    """

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

{css_theme}

/* ── Base App Reset & Typography ── */
html, body, [class*="css"] {{
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
    background-color: var(--bg-base) !important;
    color: var(--text-primary) !important;
}}

#MainMenu, footer, header {{
    visibility: hidden;
}}

.block-container {{
    padding-top: 1.2rem !important;
    padding-bottom: 2.5rem !important;
    max-width: 1440px !important;
    padding-left: 2rem !important;
    padding-right: 2rem !important;
}}

/* ── Left Sidebar Navigation ── */
section[data-testid="stSidebar"] {{
    background-color: var(--sidebar-bg) !important;
    border-right: 1px solid var(--sidebar-border) !important;
    box-shadow: 1px 0 3px rgba(0, 0, 0, 0.02) !important;
    width: 290px !important;
}}

section[data-testid="stSidebar"] .block-container {{
    padding-left: 1rem !important;
    padding-right: 1rem !important;
    padding-top: 1.2rem !important;
}}

/* ── Sidebar Brand Header ── */
.sb-brand-box {{
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.5rem 0.5rem 1rem;
    margin-bottom: 0.8rem;
    border-bottom: 1px solid var(--border-subtle);
}}

.sb-brand-logo {{
    width: 38px;
    height: 38px;
    border-radius: 8px;
    flex-shrink: 0;
}}

.sb-brand-title {{
    font-size: 1.05rem;
    font-weight: 800;
    color: var(--text-primary);
    line-height: 1.15;
    letter-spacing: -0.02em;
}}

.sb-brand-title span {{
    color: var(--primary);
}}

.sb-brand-tagline {{
    font-size: 0.68rem;
    color: var(--text-muted);
    font-weight: 500;
    margin-top: 0.15rem;
    letter-spacing: 0.02em;
}}

/* ── Navigation Section Label ── */
.sb-nav-label {{
    font-size: 0.65rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-muted);
    margin: 0.8rem 0.5rem 0.4rem;
}}

/* ── Sidebar Navigation Buttons ── */
section[data-testid="stSidebar"] .stButton > button {{
    width: 100% !important;
    text-align: left !important;
    justify-content: flex-start !important;
    background-color: transparent !important;
    border: 1px solid transparent !important;
    color: var(--text-secondary) !important;
    font-size: 0.84rem !important;
    font-weight: 500 !important;
    padding: 0.5rem 0.75rem !important;
    border-radius: 8px !important;
    transition: all 0.15s ease-in-out !important;
    margin-bottom: 0.2rem !important;
}}

section[data-testid="stSidebar"] .stButton > button:hover {{
    background-color: var(--bg-surface-alt) !important;
    color: var(--text-primary) !important;
    border-color: var(--border-subtle) !important;
}}

/* Active Page Highlight Button */
section[data-testid="stSidebar"] .stButton > button.active-nav {{
    background-color: var(--primary-light) !important;
    color: var(--primary) !important;
    font-weight: 700 !important;
    border: 1px solid var(--primary-border) !important;
    box-shadow: var(--shadow-sm) !important;
}}

/* ── Card Surfaces & Containers ── */
.pro-card {{
    background: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    border-radius: 10px;
    padding: 1.25rem 1.4rem;
    margin-bottom: 1rem;
    box-shadow: var(--shadow-card);
    transition: box-shadow 0.2s ease, border-color 0.2s ease;
}}

.pro-card:hover {{
    box-shadow: var(--shadow-md);
    border-color: var(--border-strong);
}}

/* ── Top Header Section ── */
.app-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.75rem 0 1.2rem;
    border-bottom: 1px solid var(--border-subtle);
    margin-bottom: 1.5rem;
}}

.app-title-block {{
    display: flex;
    align-items: center;
    gap: 0.9rem;
}}

.app-header-logo {{
    width: 44px;
    height: 44px;
    flex-shrink: 0;
}}

.app-title {{
    font-size: 1.45rem;
    font-weight: 800;
    color: var(--text-primary);
    letter-spacing: -0.025em;
    line-height: 1.15;
    margin: 0;
}}

.app-subtitle {{
    font-size: 0.82rem;
    color: var(--text-muted);
    font-weight: 500;
    margin-top: 0.2rem;
}}

/* ── Status Pills & Badges ── */
.pro-pill {{
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.25rem 0.65rem;
    border-radius: 9999px;
    font-size: 0.73rem;
    font-weight: 600;
    border: 1px solid transparent;
}}

.pill-online {{
    background: var(--success-bg);
    color: var(--success);
    border-color: var(--success-border);
}}

.pill-simulator {{
    background: var(--primary-light);
    color: var(--primary);
    border-color: var(--primary-border);
}}

.pill-warning {{
    background: var(--warning-bg);
    color: var(--warning);
    border-color: var(--warning-border);
}}

.pill-danger {{
    background: var(--danger-bg);
    color: var(--danger);
    border-color: var(--danger-border);
}}

/* ── Metric Stat Cards ── */
.stat-card {{
    background: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    border-radius: 10px;
    padding: 1rem 1.15rem;
    box-shadow: var(--shadow-sm);
    height: 100%;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
}}

.stat-label {{
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-muted);
    margin-bottom: 0.35rem;
}}

.stat-value {{
    font-size: 1.65rem;
    font-weight: 800;
    letter-spacing: -0.02em;
    color: var(--text-primary);
    line-height: 1.1;
    margin-bottom: 0.2rem;
}}

.stat-sub {{
    font-size: 0.74rem;
    color: var(--text-muted);
}}

/* ── Bug Severity Cards ── */
.bug-card {{
    background: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    border-left: 4px solid var(--primary);
    border-radius: 6px;
    padding: 0.85rem 1rem;
    margin-bottom: 0.65rem;
    box-shadow: var(--shadow-sm);
}}

.bug-card.critical {{ border-left-color: var(--danger); }}
.bug-card.major {{ border-left-color: var(--warning); }}
.bug-card.minor {{ border-left-color: var(--primary); }}
.bug-card.suggestion {{ border-left-color: #8B5CF6; }}

.bug-header {{
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.35rem;
    flex-wrap: wrap;
}}

.bug-desc {{
    font-size: 0.82rem;
    color: var(--text-secondary);
    line-height: 1.5;
    margin-bottom: 0.4rem;
}}

.bug-fix-box {{
    background: var(--bg-surface-alt);
    border: 1px solid var(--border-subtle);
    border-radius: 6px;
    padding: 0.45rem 0.75rem;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.77rem;
    color: var(--text-primary);
}}

/* ── Workflow Stepper ── */
.flow-stepper {{
    display: flex;
    align-items: center;
    overflow-x: auto;
    background: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    border-radius: 10px;
    padding: 0.9rem 1.2rem;
    margin-bottom: 1.3rem;
    gap: 0.3rem;
}}

.flow-step-node {{
    display: flex;
    flex-direction: column;
    align-items: center;
    min-width: 95px;
    text-align: center;
}}

.flow-step-icon {{
    width: 36px;
    height: 36px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1rem;
    margin-bottom: 0.35rem;
    border: 1.5px solid var(--border-strong);
    background: var(--bg-surface-alt);
}}

.flow-step-icon.active {{
    background: var(--primary-light);
    border-color: var(--primary);
    color: var(--primary);
}}

.flow-step-icon.done {{
    background: var(--success-bg);
    border-color: var(--success);
    color: var(--success);
}}

.flow-step-name {{
    font-size: 0.72rem;
    font-weight: 700;
    color: var(--text-secondary);
}}

.flow-step-sub {{
    font-size: 0.65rem;
    color: var(--text-muted);
    margin-top: 0.1rem;
}}

.flow-step-arrow {{
    color: var(--text-subtle);
    font-size: 0.9rem;
    margin-bottom: 1.2rem;
    flex-shrink: 0;
}}

/* ── Empty State ── */
.empty-box {{
    text-align: center;
    padding: 3.5rem 1.5rem;
    background: var(--bg-surface);
    border: 1.5px dashed var(--border-strong);
    border-radius: 12px;
    margin: 1rem 0;
}}

.empty-icon {{
    font-size: 2.8rem;
    margin-bottom: 0.8rem;
    color: var(--text-muted);
}}

.empty-title {{
    font-size: 1.1rem;
    font-weight: 700;
    color: var(--text-primary);
    margin-bottom: 0.35rem;
}}

.empty-sub {{
    font-size: 0.84rem;
    color: var(--text-muted);
    max-width: 500px;
    margin: 0 auto 1.2rem;
    line-height: 1.6;
}}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
#  5. BACKEND CONNECTIONS & DATA HELPERS
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=20, show_spinner=False)
def probe_ollama_status(url: str = "http://localhost:11434"):
    """Live probe to local Ollama API without crashing."""
    try:
        p = OllamaProvider(model_name="_probe", base_url=url)
        if p.check_health():
            models = p.get_available_models()
            return True, models, "Online"
        return False, [], "Offline (Service unreachable)"
    except Exception as e:
        return False, [], f"Offline ({str(e)[:45]})"

ollama_online, ollama_models, ollama_status_msg = probe_ollama_status(
    st.session_state.ollama_url_setting
)

history_store = HistoryStore()

def save_result_to_history(result: WorkflowResult, elapsed_sec: float) -> str:
    """Bridges WorkflowResult and persists cleanly to HistoryStore as a WorkflowReport."""
    run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    now_iso = datetime.now(timezone.utc).isoformat()
    
    # Map final status
    if result.status == "APPROVED":
        fin_status = WorkflowStatus.PASSED
        stop_reason = "Code passed all multi-agent reviews and automated verification."
    elif result.status == "MAX_RETRIES_REACHED":
        fin_status = WorkflowStatus.RETRY_LIMIT_REACHED
        stop_reason = f"Maximum attempt bound ({result.rounds_count}) reached."
    else:
        fin_status = WorkflowStatus.REVIEW_FAILED
        stop_reason = f"Workflow halted: {result.status}"

    iteration_records: List[IterationRecord] = []
    for step in result.iterations:
        # Execution result
        if step.execution:
            texec = TestExecutionResult(
                status=TestStatus.PASSED if step.execution.success else TestStatus.FAILED,
                total_tests=1,
                passed_tests=1 if step.execution.success else 0,
                failed_tests=0 if step.execution.success else 1,
                stdout=step.execution.stdout or "",
                stderr=step.execution.stderr or "",
                duration_seconds=step.execution.execution_time_ms / 1000.0,
            )
            syn = SyntaxCheckResult(
                is_valid=step.execution.syntax_valid,
                error_message=step.execution.syntax_error,
            )
        else:
            texec = TestExecutionResult(status=TestStatus.NOT_RUN)
            syn = SyntaxCheckResult(is_valid=True)

        # Review Result
        issues = []
        rev_verdict = ReviewVerdict.PASS
        rev_summary = "All criteria satisfied."
        if step.reviews:
            rev = step.reviews[0]
            rev_verdict = ReviewVerdict.PASS if rev.status == ReviewStatus.APPROVED else ReviewVerdict.FAIL
            rev_summary = rev.summary
            for b in rev.bugs:
                cat_val = b.category.value if hasattr(b.category, "value") else str(b.category)
                sev_val = b.severity.value if hasattr(b.severity, "value") else str(b.severity)
                try:
                    sev_enum = IssueSeverity(sev_val.upper())
                except Exception:
                    sev_enum = IssueSeverity.MEDIUM
                issues.append(ReviewIssue(
                    issue_type=cat_val,
                    severity=sev_enum,
                    line_number=b.line_number,
                    description=b.description,
                    suggested_fix=b.suggested_fix,
                ))

        rres = ReviewResult(
            verdict=rev_verdict,
            summary=rev_summary,
            issues=issues,
            requirements_met=(rev_verdict == ReviewVerdict.PASS),
        )

        iteration_records.append(IterationRecord(
            iteration_number=step.round_idx + 1,
            code=step.code,
            generator_model=result.generator_model,
            reviewer_model=result.reviewer_model,
            syntax_result=syn,
            test_result=texec,
            review_result=rres,
            duration_seconds=round(elapsed_sec / max(1, len(result.iterations)), 2),
            timestamp=now_iso,
        ))

    report = WorkflowReport(
        run_id=run_id,
        task_description=result.task_prompt,
        generator_model=result.generator_model,
        reviewer_model=result.reviewer_model,
        iterations=iteration_records,
        final_status=fin_status,
        stop_reason=stop_reason,
        final_code=result.final_code,
        total_attempts=result.rounds_count,
        max_attempts=st.session_state.max_retries_setting,
        start_time=now_iso,
        end_time=now_iso,
        total_duration_seconds=round(elapsed_sec, 2),
        unresolved_issues=[],
        test_suite_provided=bool(result.final_execution and result.final_execution.test_results),
    )

    history_store.save_report(report)
    history_store.save_final_code(run_id, result.final_code)
    for idx, it in enumerate(iteration_records):
        history_store.save_code_iteration(run_id, idx + 1, it.code)

    return run_id

def load_run_to_active_state(run_id: str) -> bool:
    """Loads a historical run from disk into active session state for deep inspection."""
    report = history_store.load_report(run_id)
    if not report:
        return False

    iterations = []
    messages = []
    all_bugs_detected = 0

    for it in report.iterations:
        bugs = []
        if it.review_result and it.review_result.issues:
            for iss in it.review_result.issues:
                all_bugs_detected += 1
                try:
                    cat_e = getattr(BugCategory, iss.issue_type.upper(), BugCategory.LOGIC)
                except Exception:
                    cat_e = BugCategory.LOGIC
                try:
                    sev_e = getattr(SeverityLevel, iss.severity.value.upper(), SeverityLevel.MAJOR)
                except Exception:
                    sev_e = SeverityLevel.MAJOR
                bugs.append(BugItem(
                    line_number=iss.line_number,
                    category=cat_e,
                    severity=sev_e,
                    description=iss.description,
                    suggested_fix=iss.suggested_fix or "",
                    resolved=False,
                ))

        rf = ReviewFeedback(
            reviewer_name="Reviewer Agent",
            reviewer_model=it.reviewer_model,
            status=ReviewStatus.APPROVED if (it.review_result and it.review_result.verdict == ReviewVerdict.PASS) else ReviewStatus.CHANGES_REQUESTED,
            has_bugs=len(bugs) > 0,
            summary=it.review_result.summary if it.review_result else "Completed review.",
            bugs=bugs,
            overall_score=9 if (it.review_result and it.review_result.verdict == ReviewVerdict.PASS) else 6,
        )

        ex = ExecutionResult(
            success=it.test_result.status == TestStatus.PASSED,
            stdout=it.test_result.stdout or "",
            stderr=it.test_result.stderr or "",
            exit_code=0 if it.test_result.status == TestStatus.PASSED else 1,
            execution_time_ms=it.test_result.duration_seconds * 1000.0,
            syntax_valid=it.syntax_result.is_valid,
            syntax_error=it.syntax_result.error_message,
        )

        iterations.append(IterationStep(
            round_idx=it.iteration_number - 1,
            code=it.code,
            generator_explanation=f"Iteration {it.iteration_number} solution snapshot.",
            execution=ex,
            reviews=[rf],
            status="APPROVED" if rf.status == ReviewStatus.APPROVED else "CHANGES_REQUESTED",
        ))

        # Reconstruct transcript messages
        messages.append(AgentMessage(
            sender_role="Generator",
            sender_model=it.generator_model,
            round_idx=it.iteration_number - 1,
            content=f"Generated code candidate for iteration {it.iteration_number}.",
        ))
        messages.append(AgentMessage(
            sender_role="Reviewer",
            sender_model=it.reviewer_model,
            round_idx=it.iteration_number - 1,
            content=rf.summary,
        ))

    final_st = "APPROVED" if report.final_status == WorkflowStatus.PASSED else (
        "MAX_RETRIES_REACHED" if report.final_status == WorkflowStatus.RETRY_LIMIT_REACHED else "FAILED"
    )

    wf_res = WorkflowResult(
        task_prompt=report.task_description,
        target_language="python",
        final_code=report.final_code,
        status=final_st,
        rounds_count=report.total_attempts,
        iterations=iterations,
        messages=messages,
        total_bugs_detected=all_bugs_detected,
        total_bugs_fixed=all_bugs_detected if final_st == "APPROVED" else max(0, all_bugs_detected - 1),
        final_execution=iterations[-1].execution if iterations else None,
        generator_model=report.generator_model,
        reviewer_model=report.reviewer_model,
        provider="persisted",
    )

    st.session_state.workflow_result = wf_res
    return True

# ─────────────────────────────────────────────────────────────────────────────
#  6. REAL-WORLD SCENARIO PRESETS
# ─────────────────────────────────────────────────────────────────────────────
SCENARIO_PRESETS = {
    "Palindrome Checker (NLP & String Processing)": {
        "domain": "String Processing & Sanitation",
        "prompt": (
            "Write a Python function `is_palindrome(s: str) -> bool` that checks if a string is a palindrome. "
            "Must ignore punctuation, whitespace, and casing. Correctly handle None, empty strings, and Unicode characters."
        ),
        "tests": (
            "assert is_palindrome('A man, a plan, a canal: Panama') == True\n"
            "assert is_palindrome('race a car') == False\n"
            "assert is_palindrome('') == True\n"
            "assert is_palindrome(None) == False"
        ),
    },
    "Factorial Function (Math APIs & Edge Guards)": {
        "domain": "Mathematics & Boundaries",
        "prompt": (
            "Write a Python function `factorial(n: int) -> int` that computes n! iteratively. "
            "Raise ValueError for negative inputs and TypeError for non-integer types. Handle n=0 and n=1."
        ),
        "tests": (
            "assert factorial(0) == 1\n"
            "assert factorial(5) == 120\n"
            "try:\n    factorial(-1)\n    assert False, 'Expected ValueError'\nexcept ValueError:\n    pass"
        ),
    },
    "Fibonacci Generator (Dynamic Programming O(1) Space)": {
        "domain": "Algorithms & Optimization",
        "prompt": (
            "Write a Python function `fibonacci(n: int) -> int` returning the nth Fibonacci number "
            "using O(n) time and O(1) space. Raise ValueError for negative n. Handle n=0 and n=1."
        ),
        "tests": "assert fibonacci(0) == 0\nassert fibonacci(1) == 1\nassert fibonacci(10) == 55",
    },
    "Binary Search (Search Engine Indexing)": {
        "domain": "Search Algorithms",
        "prompt": (
            "Write a Python function `binary_search(arr: list, target: int) -> int` using iterative binary search "
            "on a sorted list. Return the index if found, -1 otherwise. Safely handle empty arrays, None, and duplicates."
        ),
        "tests": (
            "assert binary_search([1,3,5,7,9], 5) == 2\n"
            "assert binary_search([], 3) == -1\n"
            "assert binary_search([1,2,3], 99) == -1"
        ),
    },
    "Merge Sort (Data Pipeline Ingestion)": {
        "domain": "Sorting & Stability",
        "prompt": (
            "Write a Python function `merge_sort(arr: list) -> list` implementing a stable merge sort. "
            "Handle empty arrays, single-element lists, and duplicate values. Return a newly sorted list without mutating input."
        ),
        "tests": (
            "assert merge_sort([3,1,2]) == [1,2,3]\n"
            "assert merge_sort([]) == []\n"
            "assert merge_sort([5]) == [5]"
        ),
    },
    "LRU Cache (High-Performance Caching Layer)": {
        "domain": "System Design",
        "prompt": (
            "Implement an `LRUCache` class in Python with `get(key)` returning -1 on miss and "
            "`put(key, value)` in O(1) time using collections.OrderedDict. Evict the LRU item when at capacity."
        ),
        "tests": (
            "c = LRUCache(2)\n"
            "c.put(1, 1)\n"
            "c.put(2, 2)\n"
            "assert c.get(1) == 1\n"
            "c.put(3, 3)\n"
            "assert c.get(2) == -1"
        ),
    },
    "SQL Injection Sanitizer (Security Guardrail)": {
        "domain": "Application Security (CWE-89)",
        "prompt": (
            "Write a Python function `is_safe_query(user_input: str) -> bool` that detects SQL injection "
            "patterns (UNION, DROP, --, ;, xp_, OR 1=1) using regex. Return False if malicious. Handle None gracefully."
        ),
        "tests": (
            "assert is_safe_query(\"Robert'); DROP TABLE users;--\") == False\n"
            "assert is_safe_query('John Smith') == True\n"
            "assert is_safe_query(None) == False"
        ),
    },
    "Moving Average (Time-Series & Financial Signal)": {
        "domain": "Data Science & Finance",
        "prompt": (
            "Write a Python function `moving_average(data: list, window: int) -> list` that computes a "
            "simple moving average. Handle edge cases: empty list, window > len(data), window <= 0, and None."
        ),
        "tests": (
            "assert moving_average([1,2,3,4,5], 3) == [2.0, 3.0, 4.0]\n"
            "assert moving_average([], 3) == []\n"
            "assert moving_average([1,2], 5) == []"
        ),
    },
    "File Path Sanitizer (Cloud Storage CWE-22)": {
        "domain": "Security & Storage",
        "prompt": (
            "Write a Python function `sanitize_path(path: str) -> str` that prevents directory traversal attacks "
            "(e.g. `../`), removes null bytes, and normalizes the path. Raise ValueError if path is None or unsafe."
        ),
        "tests": (
            "assert '/' not in sanitize_path('normal_file.txt').split('/')[-1]\n"
            "try:\n    sanitize_path('../etc/passwd')\n    assert False\nexcept ValueError:\n    pass"
        ),
    },
    "Custom Engineering Specification": {
        "domain": "Custom Spec",
        "prompt": "",
        "tests": "",
    },
}

# ─────────────────────────────────────────────────────────────────────────────
#  6B. PRESETS FOR CODE UPLOAD & IMPROVISATION / REFACTORING
# ─────────────────────────────────────────────────────────────────────────────
IMPROVISE_PRESETS = {
    "🛡️ Security Hardening (Fix CWE-95 eval, traversal, injections)": {
        "title": "Security Hardening",
        "badge": "CWE-95 / Injection Defense",
        "description": "Scrutinize and remediate dangerous vulnerabilities, unsafe eval/exec, path traversal, and unhandled exceptions.",
        "sample_code": (
            "# Vulnerable script with arbitrary code execution and missing input validation\n"
            "def evaluate_query(raw_expr):\n"
            "    # CRITICAL: CWE-95 Remote Code Execution\n"
            "    return eval(raw_expr)\n\n"
            "def read_file(name):\n"
            "    # CRITICAL: Path traversal risk\n"
            "    return open('/data/' + name).read()\n\n"
            "def divide(a, b):\n"
            "    # Missing ZeroDivisionError and TypeError guards\n"
            "    return a / b\n"
        ),
        "prompt": (
            "Improvise and audit this code: eliminate security vulnerabilities (replace unsafe eval with safe AST parser, "
            "neutralize path traversal), harden edge-case guards (ZeroDivisionError, None inputs), add type annotations, and fix all defects."
        ),
        "tests": (
            "try:\n"
            "    evaluate_query('__import__(\"os\").system(\"echo hacked\")')\n"
            "    assert False, 'Should prevent arbitrary code execution'\n"
            "except Exception:\n"
            "    pass"
        ),
    },
    "⚡ Performance & Algorithmic Optimization (O(N²) ➔ O(N))": {
        "title": "Performance Optimization",
        "badge": "Algorithmic Speedup",
        "description": "Eliminate quadratic bottlenecks, redundant iteration, and reduce memory overhead using optimal data structures.",
        "sample_code": (
            "# Inefficient quadratic duplicate finder\n"
            "def find_duplicates(items):\n"
            "    # O(N^2) nested loop causes severe latency on large datasets\n"
            "    dups = []\n"
            "    for i in range(len(items)):\n"
            "        for j in range(i + 1, len(items)):\n"
            "            if items[i] == items[j] and items[i] not in dups:\n"
            "                dups.append(items[i])\n"
            "    return dups\n"
        ),
        "prompt": (
            "Improvise and optimize this code: eliminate the quadratic O(N^2) nested loop bottleneck, "
            "refactor to linear O(N) time complexity using hash sets/maps, add typing annotations, and preserve first-seen order."
        ),
        "tests": (
            "assert find_duplicates([1, 2, 3, 2, 4, 3, 5]) == [2, 3]\n"
            "assert find_duplicates([]) == []\n"
            "assert find_duplicates([1, 2, 3]) == []"
        ),
    },
    "🧹 Clean Code, Modernization & PEP 8 Refactoring": {
        "title": "Clean Code & Modernization",
        "badge": "PEP 8 & Typing",
        "description": "Refactor monolithic functions into clean, modular, typed, and well-documented Pythonic code.",
        "sample_code": (
            "# Untyped monolithic function with cryptic variable names and zero docstrings\n"
            "def p_data(d, f=None):\n"
            "    r = []\n"
            "    for x in d:\n"
            "        if f and not f(x):\n"
            "            continue\n"
            "        r.append(x * 2)\n"
            "    return r\n"
        ),
        "prompt": (
            "Improvise and refactor this code: modernize syntax, add comprehensive typing annotations (List, Optional, Callable), "
            "provide descriptive function/parameter naming, add Google-style docstrings, and handle None input safely."
        ),
        "tests": (
            "assert p_data([1, 2, 3]) == [2, 4, 6]\n"
            "assert p_data([]) == []\n"
            "assert p_data([1, 2, 3], lambda x: x % 2 == 1) == [2, 6]"
        ),
    },
    "🧪 Test-Driven Hardening & Boundary Defense": {
        "title": "Robustness & Edge-Cases",
        "badge": "Defensive Architecture",
        "description": "Fortify functions against boundary violations, negative numbers, extreme inputs, and type mismatches.",
        "sample_code": (
            "# Function lacking defensive boundary guards\n"
            "def calculate_discount(price, discount_rate):\n"
            "    # Missing checks for negative price, discount > 1.0, and non-numeric inputs\n"
            "    return price - (price * discount_rate)\n"
        ),
        "prompt": (
            "Improvise this code to handle all edge cases: reject negative prices, validate discount rate in range [0.0, 1.0], "
            "validate numeric types, handle None/invalid inputs, and add comprehensive assertions."
        ),
        "tests": (
            "assert calculate_discount(100, 0.1) == 90.0\n"
            "try:\n"
            "    calculate_discount(-50, 0.2)\n"
            "    assert False, 'Negative price must raise ValueError'\n"
            "except ValueError:\n"
            "    pass"
        ),
    },
    "🛠️ Custom Improvisation & Architecture Redesign": {
        "title": "Custom Improvisation",
        "badge": "User Defined",
        "description": "Upload any custom script and specify your exact improvement or refactoring goals.",
        "sample_code": (
            "# Paste your Python code here to improvise\n"
            "def process_pipeline(data):\n"
            "    return [item.strip() for item in data if item]\n"
        ),
        "prompt": (
            "Audit and improvise this code: improve architecture, handle edge cases, add type annotations, and write unit tests."
        ),
        "tests": "",
    },
}

# ─────────────────────────────────────────────────────────────────────────────
#  7. SIDEBAR NAVIGATION COMPONENT
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    # ── Brand Identity Header ──
    logo_icon_html = f'<img src="{LOGO_ICON_SRC}" class="sb-brand-logo"/>' if LOGO_ICON_SRC else '🛡️'
    st.markdown(f"""
    <div class="sb-brand-box">
        {logo_icon_html}
        <div>
            <div class="sb-brand-title">Open<span>Review</span> AI</div>
            <div class="sb-brand-tagline">Code Better with AI Together</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Navigation Items ──
    st.markdown('<div class="sb-nav-label">Main Navigation</div>', unsafe_allow_html=True)

    nav_items = [
        ("Dashboard", "📊 Dashboard"),
        ("New Code Task", "➕ New Code Task"),
        ("Live Workflow", "⚡ Live Workflow"),
        ("Code Comparison", "🔍 Code Comparison"),
        ("Review Results", "🛡️ Review Results"),
        ("Testing Results", "🧪 Testing Results"),
        ("History & Reports", "📜 History & Reports"),
        ("Settings", "⚙️ Settings"),
    ]

    for key, label in nav_items:
        is_active = (st.session_state.active_page == key)
        btn_type = "primary" if is_active else "secondary"
        if st.button(label, key=f"nav_{key}", use_container_width=True, type=btn_type):
            st.session_state.active_page = key
            st.rerun()

    st.markdown('<div style="margin-top:1.5rem;"></div>', unsafe_allow_html=True)
    st.markdown('<div class="sb-nav-label">System Telemetry</div>', unsafe_allow_html=True)

    # ── Real Model Status Pill ──
    if ollama_online and ollama_models:
        st.markdown(
            f'<div class="pro-pill pill-online" style="width:100%;justify-content:center;margin-bottom:0.4rem;">'
            f'🟢 Ollama Online ({len(ollama_models)} models)</div>',
            unsafe_allow_html=True,
        )
    elif st.session_state.provider_choice == "mock":
        st.markdown(
            '<div class="pro-pill pill-simulator" style="width:100%;justify-content:center;margin-bottom:0.4rem;">'
            '⚡ Smart Simulator Active</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="pro-pill pill-warning" style="width:100%;justify-content:center;margin-bottom:0.4rem;">'
            '⚠️ Ollama Offline (Port 11434)</div>',
            unsafe_allow_html=True,
        )

    # ── Compact Metadata ──
    st.markdown(f"""
    <div style="font-size:0.72rem;color:var(--text-muted);padding:0.4rem 0.5rem;line-height:1.6;border-top:1px solid var(--border-subtle);margin-top:0.6rem;">
        <div><strong>Generator:</strong> <code>{st.session_state.gen_model_setting}</code></div>
        <div><strong>Reviewer:</strong> <code>{st.session_state.rev_model_setting}</code></div>
        <div style="margin-top:0.35rem;color:var(--text-subtle);">v2.1.0 · Aman Varma</div>
    </div>
    """, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
#  8. TOP GLOBAL HEADER COMPONENT
# ─────────────────────────────────────────────────────────────────────────────
def render_header(title_suffix: str = ""):
    """Renders top header with logo, title, connection status, and theme toggle."""
    logo_hdr = f'<img src="{LOGO_ICON_SRC}" class="app-header-logo"/>' if LOGO_ICON_SRC else '🛡️'
    
    col_l, col_r = st.columns([3, 1.2])
    with col_l:
        st.markdown(f"""
        <div class="app-title-block">
            {logo_hdr}
            <div>
                <h1 class="app-title">OpenReview AI {f'— {title_suffix}' if title_suffix else ''}</h1>
                <div class="app-subtitle">Multi-LLM Autonomous Code Generation, Review &amp; Self-Correction System</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    with col_r:
        hcol1, hcol2 = st.columns([1.1, 1])
        with hcol1:
            if ollama_online:
                st.markdown('<div class="pro-pill pill-online">🟢 Ollama Live</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div class="pro-pill pill-simulator">⚡ Simulator</div>', unsafe_allow_html=True)
        with hcol2:
            theme_btn_label = "🌙 Dark" if st.session_state.theme_mode == "light" else "☀️ Light"
            if st.button(theme_btn_label, key="theme_toggle_btn", use_container_width=True):
                st.session_state.theme_mode = "dark" if st.session_state.theme_mode == "light" else "light"
                st.rerun()

    st.markdown('<div style="margin-bottom: 1.2rem;"></div>', unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
#  9. PAGE 1: DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────
def render_dashboard():
    render_header("System Overview")

    # ── Authentic Metrics from HistoryStore ──
    stats = history_store.get_summary_stats()
    runs = history_store.list_runs()

    # ── Top 4 System Status Cards (Real data, never hardcoded) ──
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st_color = "var(--success)" if ollama_online else "var(--warning)"
        st_text = "Online" if ollama_online else "Offline"
        st_sub = f"{len(ollama_models)} models detected" if ollama_online else "Using Smart Simulator"
        st.markdown(f"""
        <div class="stat-card">
            <div>
                <div class="stat-label">Ollama Engine</div>
                <div class="stat-value" style="color:{st_color};">{st_text}</div>
            </div>
            <div class="stat-sub">{st_sub}</div>
        </div>
        """, unsafe_allow_html=True)

    with c2:
        st.markdown(f"""
        <div class="stat-card">
            <div>
                <div class="stat-label">Code Generator</div>
                <div class="stat-value" style="font-size:1.15rem;padding-top:0.25rem;">{st.session_state.gen_model_setting}</div>
            </div>
            <div class="stat-sub">LLM 1 Author &amp; Fixer Agent</div>
        </div>
        """, unsafe_allow_html=True)

    with c3:
        st.markdown(f"""
        <div class="stat-card">
            <div>
                <div class="stat-label">Code Reviewer</div>
                <div class="stat-value" style="font-size:1.15rem;padding-top:0.25rem;">{st.session_state.rev_model_setting}</div>
            </div>
            <div class="stat-sub">LLM 2 Static &amp; Logic Auditor</div>
        </div>
        """, unsafe_allow_html=True)

    with c4:
        st.markdown(f"""
        <div class="stat-card">
            <div>
                <div class="stat-label">Total Workflow Runs</div>
                <div class="stat-value">{stats['total_runs']}</div>
            </div>
            <div class="stat-sub">{stats['passed_runs']} passed ({stats['pass_rate_pct']}%)</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown('<div style="margin-top:1.2rem;"></div>', unsafe_allow_html=True)

    # ── Quick Action Callout ──
    q1, q2 = st.columns([3, 1])
    with q1:
        st.markdown("""
        <div class="pro-card" style="margin-bottom:0;border-left: 4px solid var(--primary);">
            <div style="font-weight:700;font-size:1rem;color:var(--text-primary);margin-bottom:0.25rem;">
                🚀 Autonomous Multi-Agent Code Review
            </div>
            <div style="font-size:0.83rem;color:var(--text-secondary);line-height:1.5;">
                OpenReview AI orchestrates specialized open-source models to generate, statically inspect, 
                execute in isolated sandboxes, and iteratively correct code until full consensus is reached.
            </div>
        </div>
        """, unsafe_allow_html=True)
    with q2:
        st.markdown('<div style="margin-top:0.4rem;"></div>', unsafe_allow_html=True)
        if st.button("➕ Launch New Code Task", type="primary", use_container_width=True):
            st.session_state.active_page = "New Code Task"
            st.rerun()

    st.markdown('<div style="margin-top:1.4rem;"></div>', unsafe_allow_html=True)

    # ── Statistics Grid ──
    st.markdown("### 📊 Workflow Execution Telemetry")
    m1, m2, m3, m4, m5 = st.columns(5)
    with m1: st.metric("Total Executions", stats["total_runs"])
    with m2: st.metric("Passed / Approved", stats["passed_runs"])
    with m3: st.metric("Changes / Retried", stats["failed_runs"])
    with m4: st.metric("Pass Rate", f"{stats['pass_rate_pct']}%")
    with m5: st.metric("Avg Attempts", stats["avg_attempts"])

    st.markdown('<div style="margin-top:1.4rem;"></div>', unsafe_allow_html=True)

    # ── Recent Runs Table (Real data from HistoryStore) ──
    st.markdown("### 🕒 Recent Workflow Executions")
    if runs:
        for r in runs[:6]:
            with st.container():
                rc1, rc2, rc3, rc4, rc5 = st.columns([3, 1.2, 1, 1, 1])
                with rc1:
                    st.markdown(f"**{r['task']}**")
                    st.caption(f"ID: `{r['run_id']}` · {r['timestamp'][:19] if r['timestamp'] else ''}")
                with rc2:
                    st_val = r["status"]
                    pill_cls = "pill-online" if st_val == "PASSED" else ("pill-warning" if "RETRY" in st_val else "pill-danger")
                    st.markdown(f'<div class="pro-pill {pill_cls}">{st_val}</div>', unsafe_allow_html=True)
                with rc3:
                    st.markdown(f"**{r['attempts']}** / {r['max_attempts']} attempts")
                with rc4:
                    st.markdown(f"{r['duration']}s")
                with rc5:
                    if st.button("Inspect", key=f"view_dash_{r['run_id']}", use_container_width=True):
                        if load_run_to_active_state(r["run_id"]):
                            st.session_state.active_page = "Review Results"
                            st.rerun()
                st.markdown("<hr style='margin:0.4rem 0;'/>", unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="empty-box">
            <div class="empty-icon">📂</div>
            <div class="empty-title">No Historical Runs Recorded Yet</div>
            <div class="empty-sub">Submit your first coding prompt in <strong>New Code Task</strong> to initiate autonomous multi-agent review.</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown('<div style="margin-top:1.4rem;"></div>', unsafe_allow_html=True)

    # ── Architecture & Security Boundaries ──
    with st.expander("🏛️ System Architecture, Guardrails & Safe Execution"):
        st.markdown("""
        - **Multi-Agent Paradigm:** Overcomes single-LLM confirmation bias by separating the Author (LLM 1) from the Critic (LLM 2) and Security Arbiter (LLM 3).
        - **Deterministic Verification Layer:** Before presenting code to LLM 2, code is analyzed via Python AST (`ast.parse`) for syntax errors, CWE-95, and unsafe imports.
        - **Sandboxed Execution:** Executes in an isolated subprocess with explicit timeout guards (5–15s). Arbitrary shell commands are strictly blocked.
        - **Finite Stopping Condition:** Max retry limits (1–5) strictly prevent infinite self-correction loops.
        - **100% Open-Source & Local-First:** Designed for sequential CPU/GPU inference via Ollama or instant offline Smart Simulator.
        """)

# ─────────────────────────────────────────────────────────────────────────────
#  10. PAGE 2: NEW CODE TASK
# ─────────────────────────────────────────────────────────────────────────────
def render_new_code_task():
    render_header("New Code Task")

    col_l, col_r = st.columns([2.5, 1])

    with col_l:
        st.markdown("#### 1. Task Definition")

        wf_input_mode = st.radio(
            "Workflow Input Mode",
            ["💡 Generate from Specification", "🚀 Upload & Improvise Code"],
            horizontal=True,
            help="Choose whether to generate new code from scratch or upload/paste existing code to audit and improvise."
        )

        task_prompt = ""
        existing_code = None
        custom_tests = ""

        if "Generate" in wf_input_mode:
            selected_scenario_name = st.selectbox(
                "Select Engineering Scenario Preset",
                list(SCENARIO_PRESETS.keys()),
                index=0,
                help="Choose from pre-built scenarios across real engineering domains",
            )
            preset = SCENARIO_PRESETS[selected_scenario_name]
            task_prompt = st.text_area(
                "Task Specification & Requirements",
                value=preset["prompt"],
                height=130,
                placeholder="Describe the function, class, or module requirements...",
                help="Specify inputs, return types, edge cases, and performance criteria.",
            )
            with st.expander("🧪 Automated Test Assertions (Optional — executed in sandbox)", expanded=bool(preset["tests"])):
                custom_tests = st.text_area(
                    "Assertions / Pytest code",
                    value=preset["tests"],
                    height=90,
                    label_visibility="collapsed",
                    placeholder="assert my_func(input) == expected_output",
                )
        else:
            # ── Upload & Improvise Mode ──
            st.markdown(
                '<div style="font-size:0.86rem;color:var(--text-secondary);margin-bottom:0.7rem;line-height:1.5;">'
                'Upload an existing Python script or paste code below. The multi-LLM team will analyze the code, '
                'detect vulnerabilities, security flaws & performance bottlenecks, and autonomously rewrite an <strong>improved & verified version</strong>.'
                '</div>',
                unsafe_allow_html=True
            )

            # Improvisation Objective
            selected_impr_name = st.selectbox(
                "🎯 Improvisation Objective & Strategy",
                list(IMPROVISE_PRESETS.keys()),
                index=0,
                help="Select your primary improvement goal (Security, Performance O(N), Clean Refactor, or Custom)"
            )
            impr_preset = IMPROVISE_PRESETS[selected_impr_name]

            st.caption(f"💡 **Strategy:** {impr_preset['description']}")

            # Code source selector: Upload file vs Use Preset Sample vs Paste
            code_src_mode = st.radio(
                "Code Source",
                ["⚡ Preset Sample Code", "📁 Upload File (.py, .txt, .pyw)", "✍️ Paste Custom Code"],
                horizontal=True,
            )

            initial_code_to_show = impr_preset["sample_code"]

            if "Upload File" in code_src_mode:
                up_file = st.file_uploader("Upload Python script to improvise", type=["py", "txt", "pyw"], key="file_upload_input")
                if up_file:
                    try:
                        uploaded_text = up_file.getvalue().decode("utf-8")
                        initial_code_to_show = uploaded_text
                        st.success(f"📄 Loaded `{up_file.name}` ({len(uploaded_text.splitlines())} lines, {len(uploaded_text)} bytes)")
                    except Exception as e:
                        st.error(f"Failed to read uploaded file: {e}")
                else:
                    st.info("👆 Select a `.py` file from your computer to inspect and improvise.")
            elif "Paste" in code_src_mode:
                initial_code_to_show = "# Paste your Python code here to improvise\n"

            existing_code = st.text_area(
                "Source Code to Improvise",
                value=initial_code_to_show,
                height=180,
                help="Edit or review the code that will be inspected and improved by the multi-LLM team."
            )

            # Instant Static AST Pre-Check Badge
            if existing_code and existing_code.strip():
                import ast
                try:
                    parsed_tree = ast.parse(existing_code)
                    fn_count = sum(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) for n in ast.walk(parsed_tree))
                    class_count = sum(isinstance(n, ast.ClassDef) for n in ast.walk(parsed_tree))
                    line_count = len(existing_code.splitlines())
                    st.markdown(
                        f'<div style="display:flex;gap:0.5rem;align-items:center;margin-top:0.25rem;margin-bottom:0.6rem;">'
                        f'<span class="pro-pill pill-online">🟢 AST Syntax: Valid</span>'
                        f'<span class="pro-pill pill-simulator">Lines: {line_count}</span>'
                        f'<span class="pro-pill pill-simulator">Functions: {fn_count}</span>'
                        f'<span class="pro-pill pill-simulator">Classes: {class_count}</span>'
                        f'</div>',
                        unsafe_allow_html=True
                    )
                except SyntaxError as syn_err:
                    st.markdown(
                        f'<div style="display:flex;gap:0.5rem;align-items:center;margin-top:0.25rem;margin-bottom:0.6rem;">'
                        f'<span class="pro-pill pill-danger">🔴 Syntax Notice (Line {syn_err.lineno}): {syn_err.msg}</span>'
                        f'</div>',
                        unsafe_allow_html=True
                    )

            task_prompt = st.text_area(
                "Improvisation Requirements & Instructions for LLMs",
                value=impr_preset["prompt"],
                height=90,
                help="Instructions passed to LLM 1, 2, and 3 for auditing and refactoring."
            )

            with st.expander("🧪 Automated Test Assertions (Executed in sandbox to verify improvisation)", expanded=bool(impr_preset["tests"])):
                custom_tests = st.text_area(
                    "Custom Assertions / Pytest code",
                    value=impr_preset["tests"],
                    height=80,
                    label_visibility="collapsed",
                    placeholder="assert my_func(input) == expected_output",
                )

    with col_r:
        st.markdown("#### 2. Workflow Parameters")
        
        # Provider selection
        prov_options = ["mock", "ollama"]
        prov_choice = st.selectbox(
            "Execution Engine",
            prov_options,
            index=0 if st.session_state.provider_choice == "mock" else 1,
            format_func=lambda x: "⚡ Smart Simulator (Instant, No GPU)" if x == "mock" else "🦙 Ollama (Local Models)",
        )
        st.session_state.provider_choice = prov_choice

        if prov_choice == "ollama" and not ollama_online:
            st.warning("⚠️ Local Ollama server is offline. Falling back to Smart Simulator recommended.")

        # Models
        available_models = ollama_models if (ollama_online and ollama_models) else [
            "qwen2.5:0.5b", "qwen2.5-coder:1.5b", "deepseek-coder:1.3b", "gemma2:2b", "mistral:latest"
        ]
        
        gen_m = st.selectbox("LLM 1 (Generator)", available_models, index=0)
        rev_m = st.selectbox("LLM 2 (Reviewer)", available_models, index=min(1, len(available_models)-1))
        
        # Guardrails
        max_retries = st.slider("Max Review Iterations", 1, 5, st.session_state.max_retries_setting)
        enable_sandbox = st.checkbox("Subprocess Sandbox Execution", value=st.session_state.sandbox_enabled)
        enable_syntax = st.checkbox("AST Syntax Analysis", value=st.session_state.ast_syntax_enabled)

    st.markdown('<div style="margin-top:1.2rem;"></div>', unsafe_allow_html=True)

    # ── Action Buttons ──
    bcol1, bcol2 = st.columns([4, 1])
    with bcol1:
        run_submitted = st.button("🚀 Start Multi-LLM Review Workflow", type="primary", use_container_width=True)
    with bcol2:
        if st.button("🔄 Clear Inputs", use_container_width=True):
            st.session_state.workflow_result = None
            st.rerun()

    # ── Workflow Execution ──
    if run_submitted:
        if not task_prompt.strip() and not existing_code:
            st.error("⚠️ Please specify a task description or paste code to review.")
            return

        config = WorkflowConfig(
            provider_type=prov_choice,
            generator_model=gen_m,
            reviewer_model=rev_m,
            validator_model=st.session_state.val_model_setting,
            max_retries=max_retries,
            enable_sandbox_execution=enable_sandbox,
            enable_third_llm_validator=True,
            temperature=st.session_state.temperature_setting,
        )

        progress_ph = st.empty()
        status_ph = st.empty()

        events_map = {
            "workflow_started": (10, "Initialising multi-agent review network..."),
            "generation_started": (25, f"LLM 1 ({gen_m}) generating code candidate..."),
            "generation_completed": (45, "Code written — validating AST syntax..."),
            "execution_started": (55, "Executing code in isolated subprocess sandbox..."),
            "execution_completed": (65, "Sandbox execution complete — passing to reviewer..."),
            "review_started": (75, f"LLM 2 ({rev_m}) performing static audit..."),
            "review_completed": (85, "Review complete — assessing security consensus..."),
            "fix_started": (90, "Defects identified — LLM 1 applying targeted fixes..."),
            "round_approved": (98, "Consensus reached — code approved!"),
            "max_retries_reached": (98, "Max retry limit reached — compiling best version."),
            "workflow_completed": (100, "Workflow successfully finalized!"),
        }

        def on_event_callback(evt_name: str, evt_data: dict):
            if evt_name in events_map:
                pct, msg = events_map[evt_name]
                progress_ph.progress(pct, text=msg)

        try:
            with st.spinner("Multi-agent team analyzing and verifying code..."):
                t_start = time.time()
                orchestrator = WorkflowOrchestrator(config=config)
                result = orchestrator.run(
                    task_prompt=task_prompt,
                    target_language="python",
                    unit_tests=custom_tests.strip() or None,
                    existing_code=existing_code,
                    on_event=on_event_callback,
                )
                elapsed = time.time() - t_start

            progress_ph.empty()
            status_ph.empty()

            st.session_state.workflow_result = result
            run_id = save_result_to_history(result, elapsed)

            st.toast(f"✅ Workflow completed in {elapsed:.1f}s! Run saved as {run_id}", icon="🏆")
            st.success(f"🎉 **Workflow Completed!** Status: `{result.status}` in {result.rounds_count} round(s).")
            
            nav_c1, nav_c2 = st.columns(2)
            with nav_c1:
                if st.button("👉 View Review Verdict & Findings", use_container_width=True, type="primary"):
                    st.session_state.active_page = "Review Results"
                    st.rerun()
            with nav_c2:
                if st.button("👉 View Live Workflow Stepper", use_container_width=True):
                    st.session_state.active_page = "Live Workflow"
                    st.rerun()

        except Exception as e:
            progress_ph.empty()
            status_ph.empty()
            st.error(f"❌ Execution Error: {str(e)}")
            with st.expander("Technical Traceback"):
                st.code(traceback.format_exc(), language="python")

# ─────────────────────────────────────────────────────────────────────────────
#  11. PAGE 3: LIVE WORKFLOW
# ─────────────────────────────────────────────────────────────────────────────
def render_live_workflow():
    render_header("Live Workflow")

    res: Optional[WorkflowResult] = st.session_state.workflow_result
    if not res:
        st.markdown("""
        <div class="empty-box">
            <div class="empty-icon">⚡</div>
            <div class="empty-title">No Active Workflow in Memory</div>
            <div class="empty-sub">Submit a task in <strong>New Code Task</strong> or select an execution from <strong>History &amp; Reports</strong> to inspect the live multi-agent workflow.</div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("➕ Go to New Code Task", type="primary"):
            st.session_state.active_page = "New Code Task"
            st.rerun()
        return

    # ── Interactive Stepper ──
    st_approved = (res.status == "APPROVED")
    st.markdown(f"""
    <div class="flow-stepper">
        <div class="flow-step-node">
            <div class="flow-step-icon done">📝</div>
            <div class="flow-step-name">Task Spec</div>
            <div class="flow-step-sub">User Input</div>
        </div>
        <div class="flow-step-arrow">→</div>
        <div class="flow-step-node">
            <div class="flow-step-icon done">👨‍💻</div>
            <div class="flow-step-name">LLM 1 Author</div>
            <div class="flow-step-sub">{res.generator_model}</div>
        </div>
        <div class="flow-step-arrow">→</div>
        <div class="flow-step-node">
            <div class="flow-step-icon done">⚡</div>
            <div class="flow-step-name">Sandbox Run</div>
            <div class="flow-step-sub">AST &amp; Subprocess</div>
        </div>
        <div class="flow-step-arrow">→</div>
        <div class="flow-step-node">
            <div class="flow-step-icon done">🧐</div>
            <div class="flow-step-name">LLM 2 Reviewer</div>
            <div class="flow-step-sub">{res.reviewer_model}</div>
        </div>
        <div class="flow-step-arrow">→</div>
        <div class="flow-step-node">
            <div class="flow-step-icon done">🛡️</div>
            <div class="flow-step-name">LLM 3 Validator</div>
            <div class="flow-step-sub">Security Audit</div>
        </div>
        <div class="flow-step-arrow">→</div>
        <div class="flow-step-node">
            <div class="flow-step-icon {'done' if st_approved else 'active'}">{'🏆' if st_approved else '⚠️'}</div>
            <div class="flow-step-name">{'Approved' if st_approved else 'Limit Reached'}</div>
            <div class="flow-step-sub">{res.rounds_count} Rounds</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Top Metrics Bar ──
    m1, m2, m3, m4 = st.columns(4)
    with m1: st.metric("Overall Verdict", res.status)
    with m2: st.metric("Review Iterations", res.rounds_count)
    with m3: st.metric("Bugs Flagged", res.total_bugs_detected)
    with m4: st.metric("Bugs Auto-Fixed", res.total_bugs_fixed)

    st.markdown('<div style="margin-top:1.2rem;"></div>', unsafe_allow_html=True)

    # ── Multi-Agent Communication Transcript ──
    st.markdown("### 💬 Multi-Agent Conversation Transcript")
    st.caption(f"{len(res.iterations)} review cycle(s) · {len(res.messages)} agent messages")

    for it in res.iterations:
        is_latest = (it.round_idx == len(res.iterations) - 1)
        r_bugs = [b for r in it.reviews for b in r.bugs]
        with st.expander(f"📍 Iteration {it.round_idx + 1} — Verdict: {it.status} ({len(r_bugs)} issues found)", expanded=is_latest):
            # Agent messages for this round
            step_msgs = [m for m in res.messages if m.round_idx == it.round_idx]
            for m in step_msgs:
                st.markdown(f"**{m.sender_role}** (`{m.sender_model}`) · *{m.timestamp}*")
                st.info(m.content)

            # Code produced this round
            st.markdown("**Code Snapshot:**")
            st.code(it.code, language="python")

# ─────────────────────────────────────────────────────────────────────────────
#  12. PAGE 4: CODE COMPARISON
# ─────────────────────────────────────────────────────────────────────────────
def render_code_comparison():
    render_header("Code Comparison & Diff")

    res: Optional[WorkflowResult] = st.session_state.workflow_result
    if not res:
        st.markdown("""
        <div class="empty-box">
            <div class="empty-icon">🔍</div>
            <div class="empty-title">No Code Available for Comparison</div>
            <div class="empty-sub">Execute a task with multiple iterations to compare code revisions.</div>
        </div>
        """, unsafe_allow_html=True)
        return

    if len(res.iterations) <= 1:
        st.success("✅ **First-Pass Approval:** The code passed all reviews on Round 1 without requiring iterative modifications.")
        st.markdown("#### Final Approved Code")
        st.code(res.final_code, language="python")
        return

    # Iteration selection
    r_options = list(range(len(res.iterations)))
    is_uploaded = any("Loaded existing" in (it.generator_explanation or "") for it in res.iterations)
    
    def _fmt_baseline(x: int) -> str:
        if x == 0 and is_uploaded:
            return "Iteration 1 (Original Uploaded Code)"
        if x == 0:
            return "Iteration 1 (Initial Generation)"
        return f"Iteration {x+1}"

    def _fmt_revised(x: int) -> str:
        if x == len(r_options) - 1 and is_uploaded:
            return f"Iteration {x+1} (Final Improvised Code)"
        if x == len(r_options) - 1:
            return f"Iteration {x+1} (Latest Approved)"
        return f"Iteration {x+1}"

    c1, c2 = st.columns(2)
    with c1:
        idx_a = st.selectbox("Baseline Version", r_options, index=0, format_func=_fmt_baseline)
    with c2:
        idx_b = st.selectbox("Revised Version", r_options, index=len(r_options)-1, format_func=_fmt_revised)

    code_a = res.iterations[idx_a].code
    code_b = res.iterations[idx_b].code

    diff_text = compute_unified_diff(code_a, code_b, f"Iteration {idx_a+1}", f"Iteration {idx_b+1}")
    added = sum(1 for line in diff_text.splitlines() if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in diff_text.splitlines() if line.startswith("-") and not line.startswith("---"))

    st.markdown(f"""
    <div style="display:flex;gap:1rem;margin-bottom:0.8rem;align-items:center;">
        <span class="pro-pill pill-online">+{added} lines added</span>
        <span class="pro-pill pill-danger">−{removed} lines removed</span>
        <span style="font-size:0.82rem;color:var(--text-muted);">Comparing Iteration {idx_a+1} ➔ Iteration {idx_b+1}</span>
    </div>
    """, unsafe_allow_html=True)

    tab_diff, tab_side = st.tabs(["Unified Diff", "Side-by-Side View"])
    with tab_diff:
        st.code(diff_text or "# No textual differences detected", language="diff")
    with tab_side:
        col_left, col_right = st.columns(2)
        with col_left:
            st.markdown(f"**Iteration {idx_a+1}**")
            st.code(code_a, language="python")
        with col_right:
            st.markdown(f"**Iteration {idx_b+1}**")
            st.code(code_b, language="python")

# ─────────────────────────────────────────────────────────────────────────────
#  13. PAGE 5: REVIEW RESULTS
# ─────────────────────────────────────────────────────────────────────────────
def render_review_results():
    render_header("Review Results & Findings")

    res: Optional[WorkflowResult] = st.session_state.workflow_result
    if not res:
        st.markdown("""
        <div class="empty-box">
            <div class="empty-icon">🛡️</div>
            <div class="empty-title">No Review Results Available</div>
            <div class="empty-sub">Execute a review task or load a saved report from history.</div>
        </div>
        """, unsafe_allow_html=True)
        return

    # ── Verdict Header ──
    is_appr = (res.status == "APPROVED")
    v_cls = "pill-online" if is_appr else "pill-warning"
    v_ico = "✅" if is_appr else "⚠️"
    
    st.markdown(f"""
    <div class="pro-card" style="border-left: 4px solid {'var(--success)' if is_appr else 'var(--warning)'};">
        <div style="display:flex;justify-content:space-between;align-items:center;">
            <div>
                <span class="pro-pill {v_cls}">{v_ico} {res.status}</span>
                <span style="font-size:1.1rem;font-weight:800;margin-left:0.6rem;color:var(--text-primary);">
                    {'Code Passed All Checks' if is_appr else 'Review Flagged Outstanding Issues'}
                </span>
            </div>
            <div style="font-size:0.82rem;color:var(--text-muted);">
                {res.rounds_count} Round(s) · {res.total_bugs_detected} Bugs Detected · {res.total_bugs_fixed} Fixed
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Detailed Findings per Round ──
    st.markdown("### 🐛 Detailed Defect Audit Trail")
    all_bugs = [b for step in res.iterations for r in step.reviews for b in r.bugs]

    if all_bugs:
        for idx, b in enumerate(all_bugs):
            sev_str = b.severity.value.lower() if hasattr(b.severity, "value") else str(b.severity).lower()
            st.markdown(f"""
            <div class="bug-card {sev_str}">
                <div class="bug-header">
                    <span class="pro-pill pill-{'danger' if sev_str=='critical' else ('warning' if sev_str=='major' else 'simulator')}">
                        {b.severity}
                    </span>
                    <span style="font-size:0.75rem;font-weight:700;color:var(--text-muted);">[{b.category}]</span>
                    {f"<span style='font-size:0.75rem;color:var(--text-muted);'>Line {b.line_number}</span>" if b.line_number else ""}
                </div>
                <div class="bug-desc">{b.description}</div>
                <div class="bug-fix-box">💡 <strong>Suggested Fix:</strong> {b.suggested_fix}</div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.success("✅ **Zero Defects Detected:** No security vulnerabilities, edge-case regressions, or syntax defects found.")

# ─────────────────────────────────────────────────────────────────────────────
#  14. PAGE 6: TESTING RESULTS
# ─────────────────────────────────────────────────────────────────────────────
def render_testing_results():
    render_header("Testing & Verification")

    res: Optional[WorkflowResult] = st.session_state.workflow_result
    if not res:
        st.markdown("""
        <div class="empty-box">
            <div class="empty-icon">🧪</div>
            <div class="empty-title">No Execution Results Available</div>
            <div class="empty-sub">Execute a code review workflow to inspect sandbox execution logs and AST syntax verification.</div>
        </div>
        """, unsafe_allow_html=True)
        return

    # ── AST Syntax Check ──
    is_valid, syn_err, meta = check_syntax(res.final_code, "python")
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### 1. AST Static & Syntax Verification")
        syn_badge = "pill-online" if is_valid else "pill-danger"
        st.markdown(f'<div class="pro-pill {syn_badge}">{"✅ Syntax Valid" if is_valid else "❌ Syntax Error"}</div>', unsafe_allow_html=True)
        
        m_a, m_b, m_c = st.columns(3)
        with m_a: st.metric("Functions", meta.get("num_functions", 0))
        with m_b: st.metric("Docstrings", meta.get("docstring_count", 0))
        with m_c: st.metric("Complexity", meta.get("cyclomatic_complexity", 1))

        if meta.get("security_flags"):
            for sflag in meta["security_flags"]:
                st.warning(f"Security Alert: `{sflag}`")

    with col2:
        st.markdown("#### 2. Subprocess Sandbox Execution")
        if res.final_execution:
            fe = res.final_execution
            ex_badge = "pill-online" if fe.success else "pill-danger"
            st.markdown(f'<div class="pro-pill {ex_badge}">{"✅ Subprocess Exit 0" if fe.success else "❌ Subprocess Failed"}</div>', unsafe_allow_html=True)
            st.metric("Execution Runtime", f"{fe.execution_time_ms:.1f} ms")

            st.markdown("**Standard Output (stdout):**")
            st.code(fe.stdout.strip() or "(no stdout generated)", language="text")
            if fe.stderr.strip():
                st.markdown("**Standard Error (stderr):**")
                st.code(fe.stderr.strip(), language="text")
        else:
            st.info("Sandbox subprocess execution was bypassed in configuration.")

# ─────────────────────────────────────────────────────────────────────────────
#  15. PAGE 7: HISTORY & REPORTS
# ─────────────────────────────────────────────────────────────────────────────
def render_history_and_reports():
    render_header("History & Reports")

    runs = history_store.list_runs()
    
    # ── Filter Bar ──
    f1, f2 = st.columns([1.5, 3])
    with f1:
        status_filter = st.selectbox("Filter Status", ["ALL", "PASSED", "RETRY_LIMIT_REACHED", "FAILED"])
    with f2:
        search_kw = st.text_input("Search Prompts", placeholder="Type keyword...")

    filtered_runs = runs
    if status_filter != "ALL":
        filtered_runs = [r for r in filtered_runs if r["status"] == status_filter]
    if search_kw.strip():
        kw = search_kw.strip().lower()
        filtered_runs = [r for r in filtered_runs if kw in r["task"].lower() or kw in r["run_id"].lower()]

    st.markdown(f"Showing **{len(filtered_runs)}** run(s):")

    if filtered_runs:
        for r in filtered_runs:
            with st.container():
                col_info, col_actions = st.columns([3.5, 2.5])
                with col_info:
                    st_val = r["status"]
                    pill_cls = "pill-online" if st_val == "PASSED" else ("pill-warning" if "RETRY" in st_val else "pill-danger")
                    st.markdown(f"""
                    <div>
                        <span class="pro-pill {pill_cls}">{st_val}</span>
                        <strong style="margin-left:0.5rem;font-size:0.92rem;">{r['task']}</strong>
                    </div>
                    <div style="font-size:0.75rem;color:var(--text-muted);margin-top:0.25rem;">
                        Run ID: <code>{r['run_id']}</code> · {r['timestamp'][:19] if r['timestamp'] else ''} · 
                        {r['attempts']} attempts · {r['duration']}s
                    </div>
                    """, unsafe_allow_html=True)

                with col_actions:
                    btn_c1, btn_c2, btn_c3 = st.columns(3)
                    with btn_c1:
                        if st.button("Inspect", key=f"hist_view_{r['run_id']}", use_container_width=True):
                            if load_run_to_active_state(r["run_id"]):
                                st.session_state.active_page = "Review Results"
                                st.rerun()
                    with btn_c2:
                        rep = history_store.load_report(r["run_id"])
                        if rep:
                            st.download_button(
                                "📥 JSON",
                                data=rep.model_dump_json(indent=2),
                                file_name=f"{r['run_id']}.json",
                                mime="application/json",
                                key=f"dl_json_{r['run_id']}",
                                use_container_width=True,
                            )
                    with btn_c3:
                        if rep and rep.final_code:
                            st.download_button(
                                "📥 Code",
                                data=rep.final_code,
                                file_name=f"{r['run_id']}.py",
                                mime="text/x-python",
                                key=f"dl_code_{r['run_id']}",
                                use_container_width=True,
                            )
                st.markdown("<hr style='margin:0.4rem 0;'/>", unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="empty-box">
            <div class="empty-icon">📁</div>
            <div class="empty-title">No Matching Runs Found</div>
            <div class="empty-sub">Adjust your filter criteria or execute a new task.</div>
        </div>
        """, unsafe_allow_html=True)

    # ── Danger Zone ──
    with st.expander("🗑️ Danger Zone: Clear History"):
        st.warning("This will permanently remove saved execution JSONs and code files from disk.")
        confirm_del = st.checkbox("I confirm I want to clear all execution records")
        if st.button("Clear All Runs", disabled=not confirm_del, type="primary"):
            del_ct = history_store.clear_all()
            st.session_state.workflow_result = None
            st.success(f"Cleared {del_ct} run record(s) from disk.")
            st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
#  16. PAGE 8: SETTINGS
# ─────────────────────────────────────────────────────────────────────────────
def render_settings():
    render_header("Studio Settings")

    st.markdown("#### 1. Ollama Server Configuration")
    col_url, col_test = st.columns([3, 1])
    with col_url:
        ollama_url = st.text_input("Ollama Base URL", value=st.session_state.ollama_url_setting)
    with col_test:
        st.markdown('<div style="margin-top:1.8rem;"></div>', unsafe_allow_html=True)
        if st.button("🔌 Test Connection", use_container_width=True):
            ok, mdls, msg = probe_ollama_status(ollama_url)
            if ok:
                st.success(f"✅ Connected! Found {len(mdls)} installed models: {', '.join(mdls) if mdls else 'None'}")
            else:
                st.error(f"❌ Connection Failed: {msg}")

    st.markdown("#### 2. Agent Model Assignments")
    col_m1, col_m2, col_m3 = st.columns(3)
    with col_m1:
        gen_m = st.text_input("LLM 1 (Generator)", value=st.session_state.gen_model_setting)
    with col_m2:
        rev_m = st.text_input("LLM 2 (Reviewer)", value=st.session_state.rev_model_setting)
    with col_m3:
        val_m = st.text_input("LLM 3 (Validator)", value=st.session_state.val_model_setting)

    st.markdown("#### 3. Workflow Guardrails")
    col_g1, col_g2 = st.columns(2)
    with col_g1:
        retries = st.slider("Max Review Iterations", 1, 5, value=st.session_state.max_retries_setting)
        temp = st.slider("Temperature", 0.0, 0.8, value=st.session_state.temperature_setting, step=0.05)
    with col_g2:
        sb_enabled = st.checkbox("Subprocess Sandbox Execution", value=st.session_state.sandbox_enabled)
        ast_enabled = st.checkbox("AST Syntax Verification", value=st.session_state.ast_syntax_enabled)

    st.markdown('<div style="margin-top:1rem;"></div>', unsafe_allow_html=True)

    if st.button("💾 Save Settings", type="primary"):
        st.session_state.ollama_url_setting = ollama_url.strip()
        st.session_state.gen_model_setting = gen_m.strip()
        st.session_state.rev_model_setting = rev_m.strip()
        st.session_state.val_model_setting = val_m.strip()
        st.session_state.max_retries_setting = retries
        st.session_state.temperature_setting = temp
        st.session_state.sandbox_enabled = sb_enabled
        st.session_state.ast_syntax_enabled = ast_enabled
        st.toast("✅ Settings saved successfully!", icon="💾")
        st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
#  17. MAIN PAGE ROUTER
# ─────────────────────────────────────────────────────────────────────────────
PAGES = {
    "Dashboard": render_dashboard,
    "New Code Task": render_new_code_task,
    "Live Workflow": render_live_workflow,
    "Code Comparison": render_code_comparison,
    "Review Results": render_review_results,
    "Testing Results": render_testing_results,
    "History & Reports": render_history_and_reports,
    "Settings": render_settings,
}

current_page = st.session_state.active_page
render_fn = PAGES.get(current_page, render_dashboard)
render_fn()
