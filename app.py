"""
OpenReviewAI — Multi-LLM Code Review & Self-Correction System
Global-level, production-ready Streamlit application.
Developed by Aman Varma | Druidot Consulting Pvt. Ltd.
"""
import os
import json
import time
import base64
import traceback
from pathlib import Path
from datetime import datetime

import streamlit as st

from openreview_ai.config import WorkflowConfig, OPENSOURCE_MODEL_FAMILIES
from openreview_ai.engine import WorkflowOrchestrator
from openreview_ai.schema import WorkflowResult, ReviewStatus, SeverityLevel
from openreview_ai.utils.diff_viewer import compute_unified_diff
from openreview_ai.utils.report_exporter import export_markdown_report
from openreview_ai.providers.ollama import OllamaProvider
from openreview_ai.sandbox.syntax_checker import check_syntax

# ─────────────────────────────────────────────────────────────────────
#  PAGE CONFIG  (must be first Streamlit call)
# ─────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="OpenReviewAI — Multi-LLM Code Review",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={"About": "### OpenReviewAI v1.0.0\nMulti-LLM Code Review & Auto-Correction Engine"},
)

# ─────────────────────────────────────────────────────────────────────
#  LOGO HELPER
# ─────────────────────────────────────────────────────────────────────
def _svg_b64(path: str) -> str:
    """Convert SVG file to base64 inline img src."""
    try:
        data = Path(path).read_bytes()
        return "data:image/svg+xml;base64," + base64.b64encode(data).decode()
    except Exception:
        return ""

LOGO_SRC = _svg_b64(str(Path(__file__).parent / "assets" / "logo.svg"))

# ─────────────────────────────────────────────────────────────────────
#  GLOBAL STYLESHEET — Premium Dark Theme (Humana-inspired)
# ─────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,300;0,400;0,500;0,600;0,700;0,800;0,900;1,400&family=JetBrains+Mono:wght@400;500;600;700&display=swap');

/* ═══════════════════════════ ROOT TOKENS ═══════════════════════════ */
:root{
  --bg0:#05080F; --bg1:#080D18; --bg2:#0C1220; --bg3:#111827;
  --bg4:#1A2338; --bg5:#1E293B;
  --border:#1E2D42; --border2:#2A3F58;
  --blue:#3B82F6; --blue-lt:#60A5FA; --blue-dim:rgba(59,130,246,.12);
  --purple:#8B5CF6; --purple-lt:#A78BFA; --purple-dim:rgba(139,92,246,.12);
  --green:#10B981; --green-lt:#34D399; --green-dim:rgba(16,185,129,.12);
  --amber:#F59E0B; --amber-lt:#FCD34D; --amber-dim:rgba(245,158,11,.12);
  --red:#EF4444; --red-lt:#FCA5A5; --red-dim:rgba(239,68,68,.12);
  --t1:#F1F5F9; --t2:#94A3B8; --t3:#64748B; --t4:#334155;
  --mono:'JetBrains Mono',monospace;
  --radius:12px; --radius-sm:8px; --radius-xs:6px;
}

/* ═══════════════════════════ BASE RESET ════════════════════════════ */
html,body,[class*="css"]{
  font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif!important;
  background:var(--bg0)!important; color:var(--t1)!important;
}
#MainMenu,footer,header{visibility:hidden;}
.block-container{padding-top:1.2rem!important;max-width:1480px;padding-left:1.5rem!important;padding-right:1.5rem!important;}

/* ═══════════════════════════ SIDEBAR ═══════════════════════════════ */
section[data-testid="stSidebar"]{
  background:linear-gradient(180deg,var(--bg1) 0%,var(--bg0) 100%)!important;
  border-right:1px solid var(--border)!important;
  width:300px!important;
}
section[data-testid="stSidebar"] *{color:var(--t2)!important;}
section[data-testid="stSidebar"] strong{color:var(--t1)!important;}

/* Sidebar inputs */
section[data-testid="stSidebar"] .stSelectbox>div>div,
section[data-testid="stSidebar"] .stTextInput>div>div{
  background:var(--bg3)!important; border:1px solid var(--border)!important;
  color:var(--t1)!important; border-radius:var(--radius-sm)!important; font-size:.82rem!important;
}
section[data-testid="stSidebar"] .stSelectbox>div>div:hover,
section[data-testid="stSidebar"] .stTextInput>div>div:hover{border-color:var(--blue)!important;}
section[data-testid="stSidebar"] .stCheckbox span{color:var(--t1)!important;font-size:.83rem!important;}
section[data-testid="stSidebar"] .stSlider .stMarkdown p{color:var(--t2)!important;font-size:.8rem!important;}
[role="slider"]{background:var(--blue)!important;}

/* ════════════════ SIDEBAR BRAND ════════════════════════════════════ */
.sb-brand{
  background:linear-gradient(135deg,#0A1628 0%,#0D1E38 100%);
  border:1px solid #1E3358; border-radius:var(--radius);
  padding:.85rem 1rem .8rem; margin-bottom:.9rem;
  position:relative; overflow:hidden;
}
.sb-brand::before{
  content:''; position:absolute; top:0;left:0;right:0; height:2px;
  background:linear-gradient(90deg,var(--blue),var(--purple),var(--green));
}
.sb-brand-row{display:flex;align-items:center;gap:.6rem;margin-bottom:.3rem;}
.sb-logo{width:32px;height:32px;flex-shrink:0;}
.sb-name{font-size:.98rem;font-weight:800;color:var(--t1);letter-spacing:-.02em;line-height:1.1;}
.sb-tagline{font-size:.7rem;color:var(--t3);line-height:1.5;margin-bottom:.45rem;}
.sb-dev{font-size:.72rem;color:var(--blue-lt);font-weight:600;}
.sb-company{font-size:.68rem;color:var(--t4);margin-top:.05rem;}

/* ════════════════ SIDEBAR SECTION HEADERS ══════════════════════════ */
.sb-sect{
  display:flex;align-items:center;gap:.4rem;
  font-size:.68rem;font-weight:700;text-transform:uppercase;letter-spacing:.08em;
  color:var(--blue);margin:1rem 0 .4rem;padding-bottom:.3rem;
  border-bottom:1px solid var(--border);
}
.sb-sect-num{
  width:17px;height:17px;border-radius:50%;background:var(--blue-dim);
  border:1px solid rgba(59,130,246,.3);color:var(--blue-lt);
  display:flex;align-items:center;justify-content:center;
  font-size:.65rem;font-weight:800;flex-shrink:0;
}

/* ════════════════ STATUS PILL ═══════════════════════════════════════ */
.pill{
  display:inline-flex;align-items:center;gap:.3rem;
  padding:.22rem .65rem;border-radius:100px;font-size:.73rem;font-weight:600;
}
.pill-green{background:var(--green-dim);color:var(--green-lt);border:1px solid rgba(16,185,129,.3);}
.pill-blue {background:var(--blue-dim); color:var(--blue-lt); border:1px solid rgba(59,130,246,.3);}
.pill-amber{background:var(--amber-dim);color:var(--amber-lt);border:1px solid rgba(245,158,11,.3);}
.pill-red  {background:var(--red-dim);  color:var(--red-lt);  border:1px solid rgba(239,68,68,.3);}

/* ════════════════ HERO BANNER ═══════════════════════════════════════ */
.hero{
  background:linear-gradient(135deg,#070D1C 0%,#0B1625 55%,#080E1C 100%);
  border:1px solid #1A3050; border-radius:16px;
  padding:1.8rem 2.2rem 1.5rem; margin-bottom:1.3rem;
  position:relative; overflow:hidden;
}
.hero::before{
  content:'';position:absolute;top:0;left:0;right:0;height:3px;
  background:linear-gradient(90deg,var(--blue) 0%,var(--purple) 45%,var(--green) 100%);
}
.hero::after{
  content:'';position:absolute;top:-80px;right:-60px;
  width:260px;height:260px;
  background:radial-gradient(circle,rgba(59,130,246,.06) 0%,transparent 70%);
  pointer-events:none;
}
.hero-inner{display:flex;align-items:flex-start;gap:1.2rem;}
.hero-logo{width:58px;height:58px;flex-shrink:0;margin-top:.1rem;}
.hero-h1{
  font-size:2rem;font-weight:900;letter-spacing:-.035em;
  color:var(--t1);line-height:1.1;margin-bottom:.25rem;
}
.hero-h1 em{font-style:normal;color:var(--blue-lt);}
.hero-sub{font-size:.9rem;color:var(--t2);line-height:1.65;max-width:680px;margin-bottom:.9rem;}
.hero-badges{display:flex;flex-wrap:wrap;gap:.4rem;align-items:center;}
.hb{
  display:inline-flex;align-items:center;gap:.28rem;
  padding:.22rem .6rem;border-radius:var(--radius-xs);
  font-size:.7rem;font-weight:600;font-family:var(--mono);
}
.hb-blue  {background:var(--blue-dim);  color:var(--blue-lt);  border:1px solid rgba(59,130,246,.2);}
.hb-purple{background:var(--purple-dim);color:var(--purple-lt);border:1px solid rgba(139,92,246,.2);}
.hb-green {background:var(--green-dim); color:var(--green-lt); border:1px solid rgba(16,185,129,.2);}
.hb-amber {background:var(--amber-dim); color:var(--amber-lt); border:1px solid rgba(245,158,11,.2);}
.hb-red   {background:var(--red-dim);   color:var(--red-lt);   border:1px solid rgba(239,68,68,.2);}

/* ════════════════ PIPELINE FLOW ════════════════════════════════════ */
.pipe-wrap{
  display:flex;align-items:center;overflow-x:auto;gap:0;
  background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius);
  padding:.8rem 1.4rem;margin-bottom:1.2rem;
}
.pipe-node{display:flex;flex-direction:column;align-items:center;min-width:78px;text-align:center;}
.pipe-ico{
  width:40px;height:40px;border-radius:50%;border:2px solid;
  display:flex;align-items:center;justify-content:center;
  font-size:1.1rem;margin-bottom:.3rem;
}
.pi-blue  {background:var(--blue-dim);  border-color:rgba(59,130,246,.4);}
.pi-purple{background:var(--purple-dim);border-color:rgba(139,92,246,.4);}
.pi-green {background:var(--green-dim); border-color:rgba(16,185,129,.4);}
.pi-amber {background:var(--amber-dim); border-color:rgba(245,158,11,.4);}
.pi-red   {background:var(--red-dim);   border-color:rgba(239,68,68,.4);}
.pipe-lbl{font-size:.68rem;font-weight:700;color:var(--t2);}
.pipe-sub{font-size:.62rem;color:var(--t4);margin-top:.05rem;}
.pipe-arr{color:var(--t4);padding:0 .25rem;margin-bottom:1rem;font-size:.9rem;flex-shrink:0;}

/* ════════════════ AGENT CARDS ═══════════════════════════════════════ */
.acard{
  background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius);
  padding:.9rem 1rem;height:100%;display:flex;flex-direction:column;
  transition:border-color .2s,box-shadow .2s;position:relative;overflow:hidden;
}
.acard::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;}
.acard:hover{box-shadow:0 0 24px rgba(59,130,246,.12);}
.ac-blue  ::before,.ac-blue  {border-top-color:var(--blue)!important;}
.ac-purple::before,.ac-purple{border-top-color:var(--purple)!important;}
.ac-green ::before,.ac-green {border-top-color:var(--green)!important;}
.ac-amber ::before,.ac-amber {border-top-color:var(--amber)!important;}
.acard::before{background:currentColor;}
.ac-blue  {border-top:2px solid var(--blue);}
.ac-purple{border-top:2px solid var(--purple);}
.ac-green {border-top:2px solid var(--green);}
.ac-amber {border-top:2px solid var(--amber);}
.ac-icon{font-size:1.4rem;margin-bottom:.35rem;}
.ac-tag{font-size:.64rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:var(--t4);margin-bottom:.1rem;}
.ac-name{font-size:.88rem;font-weight:700;color:var(--t1);margin-bottom:.28rem;}
.ac-desc{font-size:.76rem;color:var(--t2);line-height:1.5;flex-grow:1;}
.ac-model{
  margin-top:.55rem;font-family:var(--mono);font-size:.67rem;
  color:var(--t3);background:var(--bg3);border:1px solid var(--border);
  padding:.2rem .45rem;border-radius:var(--radius-xs);
  display:inline-block;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
}

/* ════════════════ METRIC CARDS ══════════════════════════════════════ */
.mcard{
  background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius);
  padding:.85rem 1rem;text-align:center;
}
.mcard-val{font-size:1.75rem;font-weight:800;letter-spacing:-.03em;line-height:1;margin-bottom:.2rem;}
.mcard-lbl{font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:var(--t4);}
.mcard-sub{font-size:.68rem;color:var(--t3);margin-top:.1rem;}

/* ════════════════ BUG ITEMS ═════════════════════════════════════════ */
.bug{
  border-left:3px solid;border-radius:0 var(--radius-sm) var(--radius-sm) 0;
  padding:.65rem .9rem;margin-bottom:.45rem;background:var(--bg3);
}
.bug-critical{border-left-color:var(--red);}
.bug-major   {border-left-color:var(--amber);}
.bug-minor   {border-left-color:var(--blue);}
.bug-suggestion{border-left-color:var(--purple);}
.bug-hdr{display:flex;align-items:center;gap:.38rem;margin-bottom:.28rem;flex-wrap:wrap;}
.bug-desc{font-size:.81rem;color:var(--t2);line-height:1.5;}
.bug-fix{font-size:.76rem;color:var(--green-lt);font-family:var(--mono);margin-top:.22rem;}

/* ════════════════ BADGE ═════════════════════════════════════════════ */
.bdg{
  display:inline-block;padding:.1rem .4rem;border-radius:4px;
  font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em;
}
.bdg-critical  {background:var(--red-dim);   color:var(--red-lt);   border:1px solid rgba(239,68,68,.3);}
.bdg-major     {background:var(--amber-dim); color:var(--amber-lt); border:1px solid rgba(245,158,11,.3);}
.bdg-minor     {background:var(--blue-dim);  color:var(--blue-lt);  border:1px solid rgba(59,130,246,.3);}
.bdg-suggestion{background:var(--purple-dim);color:var(--purple-lt);border:1px solid rgba(139,92,246,.3);}
.bdg-approved  {background:var(--green-dim); color:var(--green-lt); border:1px solid rgba(16,185,129,.3);}
.bdg-changes   {background:var(--amber-dim); color:var(--amber-lt); border:1px solid rgba(245,158,11,.3);}
.bdg-security  {background:var(--red-dim);   color:var(--red-lt);   border:1px solid rgba(239,68,68,.3);}

/* ════════════════ CHAT BUBBLES ══════════════════════════════════════ */
.cb{border-radius:var(--radius-sm);padding:.65rem .9rem;margin-bottom:.5rem;border:1px solid;}
.cb-gen {background:rgba(59,130,246,.05); border-color:rgba(59,130,246,.18);}
.cb-rev {background:rgba(139,92,246,.05); border-color:rgba(139,92,246,.18);}
.cb-val {background:rgba(16,185,129,.05); border-color:rgba(16,185,129,.18);}
.cb-sys {background:rgba(245,158,11,.05); border-color:rgba(245,158,11,.18);}
.cb-hdr{display:flex;align-items:center;gap:.4rem;margin-bottom:.3rem;flex-wrap:wrap;}
.cb-who{font-size:.76rem;font-weight:700;}
.cb-mdl{font-size:.65rem;color:var(--t4);font-family:var(--mono);background:var(--bg3);padding:.08rem .3rem;border-radius:4px;}
.cb-ts {font-size:.64rem;color:var(--t4);margin-left:auto;}
.cb-body{font-size:.82rem;color:var(--t2);line-height:1.55;white-space:pre-wrap;}

/* ════════════════ SCORE BAR ═════════════════════════════════════════ */
.sbr{display:flex;align-items:center;gap:.5rem;}
.sbr-track{flex:1;height:5px;border-radius:3px;background:var(--border);overflow:hidden;}
.sbr-fill{height:100%;border-radius:3px;transition:width .4s ease;}
.sbr-val{font-size:.8rem;font-weight:700;min-width:30px;text-align:right;}

/* ════════════════ MAIN INPUT STYLING ═══════════════════════════════ */
.stTextArea textarea,.stTextInput input{
  background:var(--bg2)!important;border:1px solid var(--border)!important;
  color:var(--t1)!important;border-radius:var(--radius-sm)!important;font-size:.87rem!important;
  font-family:'Inter',sans-serif!important;
}
.stTextArea textarea:focus,.stTextInput input:focus{
  border-color:var(--blue)!important;box-shadow:0 0 0 3px rgba(59,130,246,.15)!important;
}
.stTextArea label,.stTextInput label,.stSelectbox label{color:var(--t2)!important;font-size:.8rem!important;}
.stSelectbox>div>div{
  background:var(--bg2)!important;border:1px solid var(--border)!important;
  color:var(--t1)!important;border-radius:var(--radius-sm)!important;
}
.stSelectbox>div>div:hover{border-color:var(--blue)!important;}

/* ════════════════ BUTTONS ═══════════════════════════════════════════ */
.stButton>button[kind="primary"]{
  background:linear-gradient(135deg,#1D4ED8,#3B82F6)!important;
  border:none!important;color:#fff!important;font-weight:700!important;
  font-size:.9rem!important;border-radius:var(--radius-sm)!important;
  padding:.6rem 1.4rem!important;
  box-shadow:0 4px 15px rgba(59,130,246,.3)!important;transition:all .2s!important;
}
.stButton>button[kind="primary"]:hover{
  background:linear-gradient(135deg,#1E40AF,#2563EB)!important;
  transform:translateY(-1px)!important;box-shadow:0 6px 20px rgba(59,130,246,.4)!important;
}
.stButton>button[kind="secondary"]{
  background:var(--bg3)!important;border:1px solid var(--border)!important;
  color:var(--t2)!important;border-radius:var(--radius-sm)!important;font-weight:600!important;font-size:.85rem!important;
}
.stButton>button[kind="secondary"]:hover{border-color:var(--blue)!important;color:var(--blue-lt)!important;}
.stDownloadButton>button{
  background:var(--bg3)!important;border:1px solid var(--border)!important;
  color:var(--t2)!important;border-radius:var(--radius-sm)!important;
  font-size:.8rem!important;font-weight:600!important;
}
.stDownloadButton>button:hover{border-color:var(--green)!important;color:var(--green-lt)!important;}

/* ════════════════ TABS ══════════════════════════════════════════════ */
.stTabs [data-baseweb="tab-list"]{
  background:var(--bg2)!important;border:1px solid var(--border)!important;
  border-bottom:none!important;border-radius:var(--radius) var(--radius) 0 0!important;
  padding:.3rem .4rem 0!important;gap:.15rem!important;
}
.stTabs [data-baseweb="tab"]{
  background:transparent!important;color:var(--t3)!important;
  border-radius:var(--radius-sm) var(--radius-sm) 0 0!important;
  font-size:.8rem!important;font-weight:600!important;padding:.5rem .9rem!important;border:none!important;
}
.stTabs [aria-selected="true"]{
  background:var(--blue-dim)!important;color:var(--blue-lt)!important;
  border-bottom:2px solid var(--blue)!important;
}
.stTabs [data-baseweb="tab-panel"]{
  background:var(--bg2)!important;border:1px solid var(--border)!important;
  border-radius:0 0 var(--radius) var(--radius)!important;padding:1.3rem 1.5rem!important;
}

/* ════════════════ EXPANDER ══════════════════════════════════════════ */
.stExpander{background:var(--bg2)!important;border:1px solid var(--border)!important;border-radius:var(--radius-sm)!important;}
.stExpander summary{color:var(--t2)!important;font-size:.83rem!important;font-weight:600!important;}

/* ════════════════ CODE BLOCKS ═══════════════════════════════════════ */
.stCodeBlock pre{background:#020508!important;border:1px solid var(--border)!important;font-size:.78rem!important;border-radius:var(--radius-sm)!important;}

/* ════════════════ ALERTS ════════════════════════════════════════════ */
[data-testid="stAlert"]{background:var(--bg2)!important;border-radius:var(--radius-sm)!important;}

/* ════════════════ RADIO ═════════════════════════════════════════════ */
.stRadio label span{color:var(--t2)!important;font-size:.84rem!important;}

/* ════════════════ PROGRESS ══════════════════════════════════════════ */
.stProgress>div{background:var(--border)!important;border-radius:100px!important;}
.stProgress>div>div{background:linear-gradient(90deg,var(--blue),var(--purple))!important;border-radius:100px!important;}

/* ════════════════ HR ════════════════════════════════════════════════ */
hr{border-color:var(--border)!important;margin:1.2rem 0!important;}

/* ════════════════ FILE UPLOADER ═════════════════════════════════════ */
[data-testid="stFileUploader"]{
  background:var(--bg2)!important;border:1.5px dashed var(--border)!important;border-radius:var(--radius)!important;
}
[data-testid="stFileUploader"]:hover{border-color:var(--blue)!important;}

/* ════════════════ EMPTY STATE ═══════════════════════════════════════ */
.empty-state{text-align:center;padding:3.5rem 1rem;color:var(--t4);}
.empty-state-icon{font-size:3rem;margin-bottom:.7rem;}
.empty-state-title{font-size:1.05rem;font-weight:700;color:var(--t3);margin-bottom:.35rem;}
.empty-state-sub{font-size:.85rem;color:var(--t4);max-width:480px;margin:0 auto;line-height:1.7;}

/* ════════════════ REAL-WORLD SCENARIO CARD ══════════════════════════ */
.scenario-card{
  background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius);
  padding:.8rem 1rem;cursor:pointer;transition:border-color .2s,background .2s;
  margin-bottom:.5rem;
}
.scenario-card:hover{border-color:var(--blue);background:var(--bg3);}
.sc-tag{font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:var(--blue-lt);margin-bottom:.2rem;}
.sc-title{font-size:.84rem;font-weight:700;color:var(--t1);margin-bottom:.2rem;}
.sc-desc{font-size:.75rem;color:var(--t3);line-height:1.45;}

/* ════════════════ DIFF STAT BAR ══════════════════════════════════════ */
.diff-stat{display:flex;gap:.6rem;align-items:center;margin-bottom:.7rem;flex-wrap:wrap;}
.diff-added  {font-size:.8rem;font-weight:700;color:var(--green-lt);}
.diff-removed{font-size:.8rem;font-weight:700;color:var(--red-lt);}
.diff-files  {font-size:.8rem;color:var(--t3);}

/* ════════════════ MISC ══════════════════════════════════════════════ */
.stMarkdown h3{color:var(--t1)!important;font-weight:700!important;font-size:1rem!important;margin-bottom:.6rem!important;}
.stMarkdown p{color:var(--t2)!important;font-size:.88rem!important;line-height:1.6!important;}
small,.stCaptionContainer{color:var(--t4)!important;font-size:.74rem!important;}

/* ════════════════ QUICK-START BOX ═══════════════════════════════════ */
.qs-box{
  background:linear-gradient(135deg,rgba(16,185,129,.08) 0%,rgba(59,130,246,.08) 100%);
  border:1.5px solid rgba(16,185,129,.35);border-radius:var(--radius);
  padding:.85rem 1rem;margin-bottom:.7rem;
}
.qs-title{font-size:.78rem;font-weight:800;color:var(--green-lt);
  text-transform:uppercase;letter-spacing:.07em;margin-bottom:.5rem;}
.qs-step{display:flex;align-items:flex-start;gap:.45rem;
  font-size:.75rem;color:var(--t2);margin-bottom:.32rem;line-height:1.4;}
.qs-num{width:16px;height:16px;border-radius:50%;background:var(--green-dim);
  border:1px solid rgba(16,185,129,.4);color:var(--green-lt);
  display:flex;align-items:center;justify-content:center;
  font-size:.62rem;font-weight:800;flex-shrink:0;margin-top:.05rem;}

/* ════════════════ FIX BANNER ════════════════════════════════════════ */
.fix-banner{
  background:linear-gradient(135deg,rgba(245,158,11,.08),rgba(59,130,246,.08));
  border:1.5px solid rgba(245,158,11,.4);border-radius:var(--radius);
  padding:1rem 1.2rem;
}
.fix-title{font-size:.9rem;font-weight:800;color:var(--amber-lt);margin-bottom:.4rem;}
.fix-body {font-size:.8rem;color:var(--t2);line-height:1.6;}
.fix-code {font-family:var(--mono);font-size:.75rem;background:var(--bg3);
  padding:.2rem .5rem;border-radius:4px;color:var(--green-lt);}

/* ════════════════ OLLAMA STATUS BOX ════════════════════════════════ */
.ol-status{
  border-radius:var(--radius-sm);padding:.55rem .8rem;
  font-size:.74rem;font-weight:600;margin-bottom:.6rem;
  display:flex;align-items:center;gap:.4rem;
}
.ol-ok {background:var(--green-dim);border:1px solid rgba(16,185,129,.3);color:var(--green-lt);}
.ol-err{background:var(--amber-dim);border:1px solid rgba(245,158,11,.3); color:var(--amber-lt);}
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────
def _score_color(s: int) -> str:
    if s >= 9:  return "#10B981"
    if s >= 7:  return "#3B82F6"
    if s >= 5:  return "#F59E0B"
    return "#EF4444"

def _sev_class(sev: str) -> str:
    return {"CRITICAL":"critical","MAJOR":"major","MINOR":"minor","SUGGESTION":"suggestion"}.get(sev.upper(),"minor")

def _status_icon(st_: str) -> str:
    return {"APPROVED":"✅","CHANGES_REQUESTED":"🔄","REJECTED":"❌"}.get(st_,"⏳")

def _score_bar(score: int) -> str:
    c = _score_color(score)
    return f"""
    <div class="sbr">
      <div class="sbr-track"><div class="sbr-fill" style="width:{score*10}%;background:{c};"></div></div>
      <span class="sbr-val" style="color:{c};">{score}/10</span>
    </div>"""

def _bubble_class(role: str) -> tuple:
    return {
        "Generator":   ("cb-gen","👨‍💻","#60A5FA"),
        "Reviewer":    ("cb-rev","🧐","#A78BFA"),
        "Validator":   ("cb-val","🛡️","#34D399"),
        "User/System": ("cb-sys","📋","#FCD34D"),
    }.get(role, ("cb-sys","🤖","#94A3B8"))


# ─────────────────────────────────────────────────────────────────────
#  OLLAMA STATUS (cached 30s)
# ─────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=30, show_spinner=False)
def _ollama_status():
    try:
        p = OllamaProvider("_probe")
        if p.check_health():
            return True, p.get_available_models()
        return False, []
    except Exception:
        return False, []

ollama_ok, ollama_models = _ollama_status()


# ─────────────────────────────────────────────────────────────────────
#  REAL-WORLD SCENARIO PRESETS
# ─────────────────────────────────────────────────────────────────────
SCENARIOS = {
    # ── Core algorithms ──────────────────────────────────────────────
    "🔤 Palindrome Checker (NLP pre-processing)": {
        "domain": "String Processing",
        "prompt": (
            "Write a Python function `is_palindrome(s: str) -> bool` that checks if a string is a palindrome. "
            "Must ignore punctuation, whitespace, and casing. Handle `None`, empty strings, and Unicode characters."
        ),
        "tests": "assert is_palindrome('A man, a plan, a canal: Panama') == True\nassert is_palindrome('race a car') == False\nassert is_palindrome('') == True\nassert is_palindrome(None) == False",
        "lang": "python",
    },
    "🔢 Factorial Function (Math APIs)": {
        "domain": "Mathematics",
        "prompt": (
            "Write a Python function `factorial(n: int) -> int` that computes n! iteratively. "
            "Raise `ValueError` for negative inputs and `TypeError` for non-integer types. Handle n=0 and n=1."
        ),
        "tests": "assert factorial(0)==1\nassert factorial(5)==120\nassert factorial(1)==1\ntry:\n    factorial(-1)\nexcept ValueError: pass",
        "lang": "python",
    },
    "📈 Fibonacci (Finance / Signal Processing)": {
        "domain": "Dynamic Programming",
        "prompt": (
            "Write a Python function `fibonacci(n: int) -> int` returning the nth Fibonacci number "
            "using O(n) time and O(1) space. Raise ValueError for negative n."
        ),
        "tests": "assert fibonacci(0)==0\nassert fibonacci(1)==1\nassert fibonacci(10)==55",
        "lang": "python",
    },
    "🔍 Binary Search (Search Engines)": {
        "domain": "Search Algorithms",
        "prompt": (
            "Write a Python function `binary_search(arr: list, target: int) -> int` using iterative binary search "
            "on a sorted list. Return the index if found, -1 otherwise. Handle empty arrays, `None`, and duplicates."
        ),
        "tests": "assert binary_search([1,3,5,7,9],5)==2\nassert binary_search([],3)==-1\nassert binary_search([1,2,3],99)==-1",
        "lang": "python",
    },
    "🔀 Merge Sort (Data Pipelines)": {
        "domain": "Sorting Algorithms",
        "prompt": (
            "Write a Python function `merge_sort(arr: list) -> list` implementing a stable merge sort. "
            "Handle empty arrays, single-element lists, and duplicate values. Return a new sorted list."
        ),
        "tests": "assert merge_sort([3,1,2])==[1,2,3]\nassert merge_sort([])==[]\nassert merge_sort([1])==[1]",
        "lang": "python",
    },
    "⚡ LRU Cache (API / Database Layer)": {
        "domain": "System Design",
        "prompt": (
            "Implement an `LRUCache` class in Python with `get(key)` returning -1 on miss and "
            "`put(key, value)` in O(1) time using `collections.OrderedDict`. Evict the LRU item when at capacity. "
            "Include full type annotations and docstring."
        ),
        "tests": "c=LRUCache(2)\nc.put(1,1)\nc.put(2,2)\nassert c.get(1)==1\nc.put(3,3)\nassert c.get(2)==-1",
        "lang": "python",
    },
    "🔐 SQL Injection Validator (Security)": {
        "domain": "Web Security",
        "prompt": (
            "Write a Python function `is_safe_query(user_input: str) -> bool` that detects common SQL injection "
            "patterns (UNION, DROP, --, ;, xp_, etc.) using regex. Return False if dangerous. Handle None."
        ),
        "tests": "assert is_safe_query(\"Robert'); DROP TABLE\") == False\nassert is_safe_query('John Smith') == True\nassert is_safe_query(None) == False",
        "lang": "python",
    },
    "📊 Moving Average (Time-Series / Finance)": {
        "domain": "Data Science",
        "prompt": (
            "Write a Python function `moving_average(data: list, window: int) -> list` that computes a "
            "simple moving average. Handle edge cases: empty list, window > len(data), window <= 0, and None. "
            "Return a list of floats."
        ),
        "tests": "assert moving_average([1,2,3,4,5],3)==[2.0,3.0,4.0]\nassert moving_average([],3)==[]\nassert moving_average([1,2],5)==[]",
        "lang": "python",
    },
    "📁 File Path Sanitizer (Cloud Storage)": {
        "domain": "Cloud / Storage",
        "prompt": (
            "Write a Python function `sanitize_path(path: str) -> str` that prevents directory traversal attacks "
            "(e.g. `../`), removes null bytes, strips dangerous characters, and normalises the path. Raise ValueError if path is None or unsafe."
        ),
        "tests": "assert '/' not in sanitize_path('normal_file.txt').split('/')[-1]\ntry:\n    sanitize_path('../etc/passwd')\nexcept ValueError: pass",
        "lang": "python",
    },
    "🌐 URL Validator (Web Crawler / API)": {
        "domain": "Networking",
        "prompt": (
            "Write a Python function `is_valid_url(url: str) -> bool` using regex or urllib.parse to validate "
            "URLs. Must accept http/https schemes, reject empty strings, None, and malformed URLs with proper type checking."
        ),
        "tests": "assert is_valid_url('https://example.com') == True\nassert is_valid_url('not-a-url') == False\nassert is_valid_url(None) == False",
        "lang": "python",
    },
    "✏️ Custom Task Prompt": {
        "domain": "Custom",
        "prompt": "",
        "tests": "",
        "lang": "python",
    },
}

# ─────────────────────────────────────────────────────────────────────
#  SIDEBAR
# ─────────────────────────────────────────────────────────────────────
with st.sidebar:

    # ── Brand ──────────────────────────────────────────────────────
    logo_html = f'<img src="{LOGO_SRC}" class="sb-logo"/>' if LOGO_SRC else "🛡️"
    st.markdown(f"""
    <div class="sb-brand">
        <div class="sb-brand-row">
            {logo_html}
            <div>
                <div class="sb-name">OpenReviewAI</div>
            </div>
        </div>
        <div class="sb-tagline">Multi-LLM Code Review &amp; Self-Correction System<br/>
        Druidot Consulting Pvt. Ltd.</div>
        <div class="sb-dev">👨‍💻 Aman Varma</div>
        <div class="sb-company">Python Development Internship · v1.0.0</div>
    </div>
    """, unsafe_allow_html=True)

    # ── Quick Start Guide ──────────────────────────────────────────
    st.markdown("""
    <div class="qs-box">
      <div class="qs-title">⚡ Quick Start Guide</div>
      <div class="qs-step"><div class="qs-num">1</div><span>Select <strong>⚡ Smart Simulator</strong> below — works instantly, no GPU needed</span></div>
      <div class="qs-step"><div class="qs-num">2</div><span>Pick a real-world scenario from the main panel</span></div>
      <div class="qs-step"><div class="qs-num">3</div><span>Click <strong>🚀 Start Multi-LLM Review Workflow</strong></span></div>
      <div class="qs-step"><div class="qs-num">4</div><span>View results in the tabs: Chat · Diff · Code · Audit</span></div>
    </div>
    """, unsafe_allow_html=True)

    # ── Engine Status ──────────────────────────────────────────────
    if ollama_ok and ollama_models:
        st.markdown(
            f'<div class="ol-status ol-ok">🟢 Ollama Online — {len(ollama_models)} model(s) ready</div>',
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            '<div class="ol-status ol-err">⚠️ Ollama offline / no models — use Smart Simulator</div>',
            unsafe_allow_html=True
        )

    # ── 1. Provider ────────────────────────────────────────────────
    st.markdown("""<div class="sb-sect"><span class="sb-sect-num">1</span>LLM Engine Provider</div>""", unsafe_allow_html=True)

    # Session-state driven provider so "Switch to Simulator" button works
    if "provider_choice" not in st.session_state:
        st.session_state.provider_choice = "mock"   # ← ALWAYS default to mock

    provider_choice = st.selectbox(
        "provider",
        ["mock", "ollama", "openai_compat", "huggingface"],
        format_func=lambda x: {
            "mock":          "⚡ Smart Simulator — Instant, No GPU",
            "ollama":        "🦙 Ollama — Local Open-Source Models",
            "openai_compat": "🌐 Cloud API — Groq / DeepSeek / vLLM",
            "huggingface":   "🤗 HuggingFace Inference API",
        }.get(x, x),
        index=["mock","ollama","openai_compat","huggingface"].index(
            st.session_state.provider_choice
        ),
        key="provider_select",
        label_visibility="collapsed",
        help="⚡ Smart Simulator works instantly — no models to download!"
    )
    st.session_state.provider_choice = provider_choice

    if provider_choice == "mock":
        st.success("⚡ **Smart Simulator active** — generates realistic bugs, reviews & fixes. No download needed!", icon="✅")
    elif provider_choice == "ollama" and not ollama_ok:
        st.warning("⚠️ Ollama not detected. Start Ollama Desktop or run `ollama serve`, then refresh.", icon="🦙")
    elif provider_choice == "ollama" and ollama_ok and not ollama_models:
        st.warning("⚠️ Ollama running but no models downloaded. Use the Pull panel below.", icon="📥")

    # ── 2. Models ──────────────────────────────────────────────────
    st.markdown("""<div class="sb-sect"><span class="sb-sect-num">2</span>Open-Source Models</div>""", unsafe_allow_html=True)
    st.caption("Gemma · Mistral · Bonsai · Qwen · DeepSeek · CodeLlama")

    # If Ollama is online, show actual downloaded models at the top
    if ollama_ok and ollama_models:
        top_gen  = ollama_models + ["qwen2.5:0.5b","qwen2.5-coder:1.5b","deepseek-coder:1.3b","gemma2:2b","mistral:latest"]
        top_rev  = ollama_models + ["mistral:latest","gemma2:2b","deepseek-coder:1.3b"]
        top_val  = ollama_models + ["deepseek-coder:1.3b","gemma2:2b","mistral:latest"]
    else:
        top_gen  = ["qwen2.5:0.5b","qwen2.5-coder:1.5b","deepseek-coder:1.3b","gemma2:2b","mistral:latest"]
        top_rev  = ["mistral:latest","gemma2:2b","deepseek-coder:1.3b","qwen2.5-coder:1.5b"]
        top_val  = ["deepseek-coder:1.3b","bonsai:latest","gemma2:2b","mistral:latest"]

    # deduplicate
    all_m = WorkflowConfig.get_supported_model_list()
    def _dedup(lst): seen=set(); return [x for x in lst+all_m if not (x in seen or seen.add(x))]

    gen_model = st.selectbox("LLM 1: Code Generator & Fixer", _dedup(top_gen), index=0,
        help="Writes & iteratively fixes code")
    rev_model = st.selectbox("LLM 2: Code Reviewer",          _dedup(top_rev), index=0,
        help="Static analysis & bug detection")

    enable_val = st.checkbox("Enable LLM 3: Security Validator", value=True)
    val_model  = "deepseek-coder:1.3b"
    if enable_val:
        val_model = st.selectbox("LLM 3: Validator", _dedup(top_val), index=0,
            help="Security audit & final approval")

    # ── 3. Guardrails ──────────────────────────────────────────────
    st.markdown("""<div class="sb-sect"><span class="sb-sect-num">3</span>Workflow Guardrails</div>""", unsafe_allow_html=True)
    max_retries    = st.slider("Max Review Cycles", 1, 5, 3,
        help="Finite bound — prevents infinite loops. Stops after K retries.")
    enable_sandbox = st.checkbox("Sandbox Code Execution", value=True,
        help="Run code in safe subprocess with timeout guard")
    temperature    = st.slider("Temperature", 0.0, 0.8, 0.2, 0.05,
        help="Higher = more creative (may introduce bugs)")

    # ── 4. API Credentials (conditional) ──────────────────────────
    if provider_choice == "openai_compat":
        st.markdown("""<div class="sb-sect"><span class="sb-sect-num">4</span>Cloud API Settings</div>""", unsafe_allow_html=True)
        api_base = st.text_input("Base URL", value=os.getenv("OPENAI_COMPATIBLE_BASE_URL","https://api.groq.com/openai/v1"))
        api_key  = st.text_input("API Key",  type="password", value=os.getenv("OPENAI_COMPATIBLE_API_KEY",""))
        if api_base: os.environ["OPENAI_COMPATIBLE_BASE_URL"] = api_base
        if api_key:  os.environ["OPENAI_COMPATIBLE_API_KEY"]  = api_key
    elif provider_choice == "huggingface":
        st.markdown("""<div class="sb-sect"><span class="sb-sect-num">4</span>HuggingFace Token</div>""", unsafe_allow_html=True)
        hf_tok = st.text_input("HF Token", type="password", value=os.getenv("HUGGINGFACEHUB_API_TOKEN",""))
        if hf_tok: os.environ["HUGGINGFACEHUB_API_TOKEN"] = hf_tok

    # ── 5. Ollama Model Pull ───────────────────────────────────────
    st.markdown("""<div class="sb-sect"><span class="sb-sect-num">5</span>Pull Ollama Model</div>""", unsafe_allow_html=True)
    if provider_choice == "ollama":
        pull_name = st.text_input("Model to pull", placeholder="e.g. qwen2.5:0.5b", label_visibility="collapsed")
        if st.button("⬇️ Pull Model", use_container_width=True):
            if pull_name.strip():
                import subprocess
                ollama_exe = r"C:\Users\AMAN VARMA\AppData\Local\Programs\Ollama\ollama.exe"
                if not Path(ollama_exe).exists():
                    ollama_exe = "ollama"
                with st.spinner(f"Pulling {pull_name}… (may take a few minutes)"):
                    try:
                        r = subprocess.run([ollama_exe,"pull",pull_name.strip()],
                            capture_output=True, text=True, timeout=600)
                        if r.returncode == 0:
                            st.success(f"✅ `{pull_name}` pulled!")
                            st.cache_data.clear()
                        else:
                            st.error(f"Pull failed: {r.stderr[:300]}")
                    except FileNotFoundError:
                        st.error("Ollama CLI not found. Install from https://ollama.com")
                    except Exception as e:
                        st.error(str(e))
            else:
                st.warning("Enter a model name first.")

        # One-click recommended models
        st.caption("Recommended tiny models (fast, CPU-friendly):")
        rc1, rc2 = st.columns(2)
        with rc1:
            if st.button("qwen2.5:0.5b", use_container_width=True, help="Smallest Qwen coder ~400MB"):
                st.session_state._pull_name = "qwen2.5:0.5b"
        with rc2:
            if st.button("gemma2:2b", use_container_width=True, help="Google Gemma 2B ~1.6GB"):
                st.session_state._pull_name = "gemma2:2b"
    else:
        st.markdown("""
        <div style="font-size:.75rem;color:#475569;padding:.4rem 0;line-height:1.7;">
        Switch to <strong style="color:#60A5FA;">🦙 Ollama</strong> provider above to pull models.<br/>
        <span style="color:#10B981;">⚡ Smart Simulator</span> needs no downloads.
        </div>
        """, unsafe_allow_html=True)

    # ── Footer ─────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("""
    <div style="font-size:.7rem;color:#475569;text-align:center;line-height:2;">
        🧪 19/19 Pytest Tests Passing<br/>
        🌐 100% Open-Source · No Cloud Lock-in<br/>
        🛡️ Subprocess Sandbox · Finite Retry Bound<br/>
        📄 Full Audit Trail · JSON &amp; Markdown Export
    </div>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────
#  HERO BANNER
# ─────────────────────────────────────────────────────────────────────
engine_lbl = (f"🦙 Ollama · {len(ollama_models)} model(s)"
              if provider_choice=="ollama" and ollama_ok else
              "⚡ Smart Simulator")

logo_hero = f'<img src="{LOGO_SRC}" class="hero-logo"/>' if LOGO_SRC else '<span style="font-size:3rem;">🛡️</span>'

st.markdown(f"""
<div class="hero">
  <div class="hero-inner">
    {logo_hero}
    <div>
      <div class="hero-h1">Open<em>Review</em>AI</div>
      <div class="hero-sub">
        A professional multi-agent AI system where open-source LLMs collaborate to <strong>generate</strong>,
        <strong>inspect</strong>, <strong>debug</strong>, and <strong>iteratively self-correct</strong> code —
        with full audit trails, AST security scanning, subprocess sandbox execution, and exportable reports.
        Ready for real-world, global-level software engineering workflows.
      </div>
      <div class="hero-badges">
        <span class="hb hb-blue">👨‍💻 Generator — {gen_model}</span>
        <span class="hb hb-purple">🧐 Reviewer — {rev_model}</span>
        <span class="hb hb-green">🛡️ Validator{'' if enable_val else ' — off'}</span>
        <span class="hb hb-amber">⚡ {engine_lbl}</span>
        <span class="hb hb-green">✅ Max {max_retries} Retry Cycles</span>
        <span class="hb hb-blue">🔒 AST Security Scan</span>
        <span class="hb hb-purple">📄 Full Audit Trail</span>
      </div>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────
#  PIPELINE FLOW DIAGRAM
# ─────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="pipe-wrap">
  <div class="pipe-node"><div class="pipe-ico pi-amber">📝</div><div class="pipe-lbl">Prompt</div><div class="pipe-sub">Task Spec</div></div>
  <div class="pipe-arr">→</div>
  <div class="pipe-node"><div class="pipe-ico pi-blue">👨‍💻</div><div class="pipe-lbl">LLM 1</div><div class="pipe-sub">Generator</div></div>
  <div class="pipe-arr">→</div>
  <div class="pipe-node"><div class="pipe-ico pi-amber">⚡</div><div class="pipe-lbl">Sandbox</div><div class="pipe-sub">Subprocess</div></div>
  <div class="pipe-arr">→</div>
  <div class="pipe-node"><div class="pipe-ico pi-purple">🧐</div><div class="pipe-lbl">LLM 2</div><div class="pipe-sub">Reviewer</div></div>
  <div class="pipe-arr">→</div>
  <div class="pipe-node"><div class="pipe-ico pi-green">🛡️</div><div class="pipe-lbl">LLM 3</div><div class="pipe-sub">Validator</div></div>
  <div class="pipe-arr">→</div>
  <div class="pipe-node"><div class="pipe-ico pi-red">🔁</div><div class="pipe-lbl">Fix Loop</div><div class="pipe-sub">≤ K rounds</div></div>
  <div class="pipe-arr">→</div>
  <div class="pipe-node"><div class="pipe-ico pi-green">🏆</div><div class="pipe-lbl">Approved</div><div class="pipe-sub">Final Code</div></div>
</div>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────
#  AGENT ROLE CARDS
# ─────────────────────────────────────────────────────────────────────
ca, cb_, cc, cd = st.columns(4)
_cards = [
    (ca, "ac-blue",   "👨‍💻", "LLM 1 · Generator & Fixer", "Code Author Agent",
     "Writes the initial implementation from the task spec. Applies targeted iterative fixes based on reviewer feedback.", gen_model),
    (cb_, "ac-purple", "🧐", "LLM 2 · Inspector",         "Code Reviewer Agent",
     "Performs static and semantic analysis. Flags logic errors, edge cases, runtime crashes, and security anti-patterns with severity levels.", rev_model),
    (cc, "ac-green",  "🛡️", "LLM 3 · Arbiter",           "Security & QA Validator",
     "Security auditor checking for CWE-95 (eval/exec injection), unsafe imports, and system calls. Issues final approval or escalation.", val_model if enable_val else "Disabled"),
    (cd, "ac-amber",  "⚡", "Automated Sandbox",          "Subprocess Test Runner",
     "Executes generated code in an isolated subprocess with timeout guard. Captures stdout/stderr and assertion failures.", "Python Subprocess · AST"),
]
for col, cls, icon, tag, name, desc, mdl in _cards:
    with col:
        st.markdown(f"""
        <div class="acard {cls}">
          <div class="ac-icon">{icon}</div>
          <div class="ac-tag">{tag}</div>
          <div class="ac-name">{name}</div>
          <div class="ac-desc">{desc}</div>
          <code class="ac-model">{mdl}</code>
        </div>
        """, unsafe_allow_html=True)

st.write("")


# ─────────────────────────────────────────────────────────────────────
#  WORKFLOW MODE
# ─────────────────────────────────────────────────────────────────────
wf_mode = st.radio(
    "**Workflow Mode**",
    ["💡 Generate Code from Prompt", "📂 Review & Auto-Fix Existing Code"],
    horizontal=True,
)
st.write("")

existing_code = None
task_prompt   = ""
custom_tests  = ""
target_lang   = "python"

# ─────────────────────────────────────────────────────────────────────
#  MODE A: GENERATE FROM PROMPT
# ─────────────────────────────────────────────────────────────────────
if "Generate" in wf_mode:
    col_l, col_r = st.columns([3,1])
    with col_l:
        scenario_name = st.selectbox(
            "Real-World Scenario",
            list(SCENARIOS.keys()),
            index=0,
            help="Pre-built tasks from real engineering domains (security, data science, APIs, algorithms)",
        )
    with col_r:
        target_lang = st.selectbox("Language", ["python","javascript","go","cpp","typescript"], index=0)

    sc = SCENARIOS[scenario_name]
    if sc["domain"] != "Custom":
        st.markdown(
            f'<span class="bdg bdg-minor" style="margin-bottom:.5rem;display:inline-block;">🏷 {sc["domain"]}</span>',
            unsafe_allow_html=True
        )

    task_prompt = st.text_area(
        "Coding Task Prompt",
        value=sc["prompt"],
        height=105,
        help="Be specific. Include type constraints, edge cases, and performance requirements for best results.",
        placeholder="Describe what function or module you want the multi-LLM team to write and review…",
    )

    with st.expander("🧪 Unit Tests / Assertions (Optional — runs in sandbox)", expanded=bool(sc["tests"])):
        st.caption("These assertions are appended and executed in the sandbox after every generation cycle.")
        custom_tests = st.text_area(
            "Unit tests",
            value=sc["tests"],
            height=90,
            label_visibility="collapsed",
            placeholder="assert my_function(input) == expected_output",
        )

# ─────────────────────────────────────────────────────────────────────
#  MODE B: REVIEW EXISTING CODE
# ─────────────────────────────────────────────────────────────────────
else:
    st.info(
        "📂 Upload or paste any script. LLM 2 & LLM 3 will audit it for **bugs, security flaws, and edge cases**. "
        "LLM 1 will then apply fixes automatically.",
        icon="ℹ️"
    )
    uc1, uc2 = st.columns([1,2])
    with uc1:
        uploaded = st.file_uploader("Upload .py / .js / .ts file", type=["py","js","ts","go","cpp","c"])
    with uc2:
        DEFAULT_BUGGY = '''# ⚠️  Code with Multiple Real-World Security & Edge-Case Bugs
import os

def process_user_query(raw_expr):
    """Process user expression."""
    # BUG 1: eval() — Remote Code Execution vulnerability (CWE-95)
    return eval(raw_expr)

def read_file(filename):
    """Read file content."""
    # BUG 2: Path traversal — No sanitization of filename
    return open("/data/" + filename).read()

def divide(a, b):
    """Divide a by b."""
    # BUG 3: ZeroDivisionError — missing guard
    return a / b

def get_element(arr, idx):
    """Get element at index."""
    # BUG 4: IndexError — no bounds check
    return arr[idx]

if __name__ == "__main__":
    print(process_user_query("[1, 2, 3]"))
    print(divide(10, 0))
'''
        pasted = st.text_area(
            "Or paste code here",
            value=uploaded.getvalue().decode("utf-8") if uploaded else DEFAULT_BUGGY,
            height=200,
            label_visibility="collapsed",
        )
    existing_code = pasted
    task_prompt   = (
        "Perform a comprehensive security and quality review of this code. "
        "Fix ALL security vulnerabilities (eval/exec injection, path traversal, CWE-95), "
        "handle all edge cases (division by zero, index out of bounds, None inputs), "
        "add type annotations, docstrings, and ensure the code is production-safe."
    )
    target_lang   = "python"
    custom_tests  = ""


# ─────────────────────────────────────────────────────────────────────
#  LAUNCH BUTTONS
# ─────────────────────────────────────────────────────────────────────
st.write("")
bc1, bc2, bc3 = st.columns([5,1,1])
with bc1:
    run_btn = st.button("🚀  Start Multi-LLM Review Workflow", type="primary", use_container_width=True)
with bc2:
    if st.button("🔄 Reset", use_container_width=True):
        st.session_state.workflow_result = None
        st.session_state.pop("last_task", None)
        st.rerun()
with bc3:
    history_count = len(st.session_state.get("history", []))
    if st.button(f"📜 History ({history_count})", use_container_width=True):
        st.session_state["show_history"] = not st.session_state.get("show_history", False)
        st.rerun()

if "workflow_result" not in st.session_state:
    st.session_state.workflow_result = None
if "history" not in st.session_state:
    st.session_state.history = []


# ─────────────────────────────────────────────────────────────────────
#  WORKFLOW HISTORY PANEL
# ─────────────────────────────────────────────────────────────────────
if st.session_state.get("show_history") and st.session_state.history:
    with st.expander(f"📜 Workflow History — {len(st.session_state.history)} run(s)", expanded=True):
        for i, h in enumerate(reversed(st.session_state.history)):
            col_h1, col_h2, col_h3, col_h4 = st.columns([3,1,1,1])
            with col_h1: st.write(f"**{h['prompt'][:70]}…**" if len(h["prompt"])>70 else f"**{h['prompt']}**")
            with col_h2: st.write(f"`{h['status']}`")
            with col_h3: st.write(f"{h['rounds']} rounds")
            with col_h4: st.write(h["time"])


# ─────────────────────────────────────────────────────────────────────
#  EXECUTION ENGINE
# ─────────────────────────────────────────────────────────────────────
if run_btn:
    if not task_prompt.strip() and not existing_code:
        st.error("⚠️  Please enter a task prompt or paste code to review.")
    else:
        # ── Build config ──────────────────────────────────────────
        config = WorkflowConfig(
            provider_type=provider_choice,
            generator_model=gen_model,
            reviewer_model=rev_model,
            validator_model=val_model if enable_val else "",
            max_retries=max_retries,
            enable_sandbox_execution=enable_sandbox,
            enable_third_llm_validator=enable_val,
            temperature=temperature,
        )

        prog_ph = st.empty()
        log_ph  = st.empty()

        EVENTS = {
            "workflow_started":    (5,  "🚀 Initialising multi-LLM workflow…"),
            "generation_started":  (15, f"✍️  LLM 1 ({gen_model}) writing initial code…"),
            "generation_completed":(35, "✅ Code written — sending to sandbox…"),
            "execution_started":   (45, "⚡ Executing in secure subprocess sandbox…"),
            "execution_completed": (55, "✅ Sandbox run complete — passing to reviewers…"),
            "review_started":      (65, f"🧐 LLM 2 ({rev_model}) inspecting code…"),
            "review_completed":    (73, "📋 Review complete — running security validator…"),
            "validation_started":  (81, f"🛡️  LLM 3 ({val_model}) performing security audit…"),
            "validation_completed":(88, "✅ Validation complete — checking approval…"),
            "fix_started":         (91, "🔧 Bugs found — LLM 1 applying targeted fixes…"),
            "fix_completed":       (94, "✅ Fix applied — re-running review cycle…"),
            "round_approved":      (98, "🏆 Code APPROVED!"),
            "max_retries_reached": (99, "⚠️  Max retry cycles reached — returning best code."),
            "workflow_completed":  (100,"🎉 Workflow completed!"),
        }

        def on_event(evt: str, data: dict):
            if evt in EVENTS:
                pct, msg = EVENTS[evt]
                prog_ph.progress(pct, text=msg)

        try:
            with st.spinner("Multi-LLM agents communicating, reviewing, and iteratively fixing…"):
                t_start      = time.time()
                orchestrator = WorkflowOrchestrator(config=config)
                result = orchestrator.run(
                    task_prompt=task_prompt,
                    target_language=target_lang,
                    unit_tests=custom_tests.strip() or None,
                    existing_code=existing_code,
                    on_event=on_event,
                )
                elapsed = time.time() - t_start

            prog_ph.empty()
            st.session_state.workflow_result = result

            # Save to history
            st.session_state.history.append({
                "prompt": task_prompt[:100],
                "status": result.status,
                "rounds": result.rounds_count,
                "bugs":   result.total_bugs_detected,
                "time":   datetime.now().strftime("%H:%M:%S"),
                "elapsed": f"{elapsed:.1f}s",
            })

            st.toast(f"✅ Workflow done in {elapsed:.1f}s!", icon="🏆")

        except Exception as e:
            prog_ph.empty()
            err_msg = str(e)

            # ── Smart Error Recovery Banner ──────────────────────
            is_llama_err  = "llama-server" in err_msg.lower() or "binary not found" in err_msg.lower()
            is_model_err  = "not pulled" in err_msg.lower() or "not available" in err_msg.lower()
            is_conn_err   = "connection" in err_msg.lower() or "not reachable" in err_msg.lower()

            if is_llama_err or is_model_err or is_conn_err:
                if is_llama_err:
                    fix_title = "🔧 Ollama llama-server binary not found"
                    fix_body  = (
                        "Your Ollama installation is missing the GPU inference binary. "
                        "This happens when Ollama installs without a GPU backend.<br/><br/>"
                        "<strong>Fastest fix:</strong> Click the button below to instantly switch to "
                        "<span class='fix-code'>⚡ Smart Simulator</span> — same features, no GPU needed."
                    )
                elif is_model_err:
                    fix_title = "📥 Model not downloaded"
                    fix_body  = (
                        f"The model <span class='fix-code'>{gen_model}</span> hasn't been pulled yet.<br/><br/>"
                        "Use the sidebar <strong>Pull Ollama Model</strong> panel to download it, "
                        "or switch to Smart Simulator below."
                    )
                else:
                    fix_title = "🔌 Ollama server not running"
                    fix_body  = (
                        "Ollama is not running. Start the <strong>Ollama Desktop</strong> app "
                        "or run <span class='fix-code'>ollama serve</span> in a terminal, then try again.<br/><br/>"
                        "Or instantly switch to Smart Simulator — no setup needed."
                    )

                st.markdown(f"""
                <div class="fix-banner">
                  <div class="fix-title">{fix_title}</div>
                  <div class="fix-body">{fix_body}</div>
                </div>
                """, unsafe_allow_html=True)

                fix_c1, fix_c2 = st.columns([2,3])
                with fix_c1:
                    if st.button("⚡ Switch to Smart Simulator", type="primary", use_container_width=True):
                        st.session_state.provider_choice = "mock"
                        st.rerun()
                with fix_c2:
                    st.markdown(
                        "<small>Smart Simulator = same multi-LLM workflow, realistic bugs & reviews, "
                        "no GPU or internet required.</small>",
                        unsafe_allow_html=True
                    )
            else:
                st.error(f"❌ Workflow Error: {err_msg}", icon="❌")

            with st.expander("🐛 Full Error Details (for debugging)"):
                st.code(traceback.format_exc(), language="python")


# ─────────────────────────────────────────────────────────────────────
#  RESULTS DASHBOARD
# ─────────────────────────────────────────────────────────────────────
if st.session_state.workflow_result:
    res: WorkflowResult = st.session_state.workflow_result

    st.markdown("---")

    # ── Status banner ─────────────────────────────────────────────
    status_cfg = {
        "APPROVED":           ("#10B981", "✅", "Code passed all reviews and was approved!"),
        "MAX_RETRIES_REACHED":("#F59E0B", "⚠️", f"Max retry cycles ({max_retries}) reached. Returning best version."),
    }.get(res.status, ("#EF4444","❌","Workflow did not complete successfully."))
    st.markdown(
        f'<div style="background:{status_cfg[0]}18;border:1px solid {status_cfg[0]}44;border-radius:10px;'
        f'padding:.7rem 1.1rem;margin-bottom:.9rem;display:flex;align-items:center;gap:.6rem;">'
        f'<span style="font-size:1.3rem;">{status_cfg[1]}</span>'
        f'<span style="font-weight:700;color:{status_cfg[0]};font-size:.92rem;">{status_cfg[2]}</span>'
        f'</div>',
        unsafe_allow_html=True
    )

    # ── Metrics ───────────────────────────────────────────────────
    runtime_ms  = res.final_execution.execution_time_ms if res.final_execution else 0
    all_bugs    = [b for step in res.iterations for r in step.reviews for b in r.bugs]
    critical_ct = sum(1 for b in all_bugs if b.severity.upper() == "CRITICAL")
    avg_score   = (sum(r.overall_score for step in res.iterations for r in step.reviews) /
                   max(1, sum(len(step.reviews) for step in res.iterations)))

    m1, m2, m3, m4, m5, m6, m7 = st.columns(7)
    _mdata = [
        (m1, res.status,                       "Final Verdict",      status_cfg[0],  ""),
        (m2, str(res.rounds_count),             "Review Rounds",      "#3B82F6",      ""),
        (m3, str(res.total_bugs_detected),      "Bugs Detected",      "#EF4444",      ""),
        (m4, str(res.total_bugs_fixed),         "Bugs Fixed",         "#10B981",      ""),
        (m5, str(critical_ct),                  "Critical Issues",    "#F59E0B",      ""),
        (m6, f"{avg_score:.1f}/10",             "Avg Review Score",   "#8B5CF6",      ""),
        (m7, f"{runtime_ms:.0f}ms",             "Sandbox Runtime",    "#60A5FA",      ""),
    ]
    for col, val, lbl, col_s, sub in _mdata:
        with col:
            st.markdown(
                f'<div class="mcard"><div class="mcard-val" style="color:{col_s};">{val}</div>'
                f'<div class="mcard-lbl">{lbl}</div></div>',
                unsafe_allow_html=True
            )

    st.write("")

    # ── TABS ─────────────────────────────────────────────────────
    t1, t2, t3, t4, t5, t6, t7 = st.tabs([
        "💬 Multi-LLM Chat",
        "🔍 Code Diff",
        "🏆 Final Code",
        "📊 Quality & Security",
        "🧪 Sandbox Log",
        "📄 Audit Report",
        "📥 Export",
    ])

    # ══════════ TAB 1: MULTI-LLM CONVERSATION ════════════════════
    with t1:
        st.markdown("### 💬 Multi-LLM Agent Communication History")
        st.caption(
            f"{len(res.iterations)} round(s) · {len(res.messages)} agent messages · "
            f"Generator: `{res.generator_model}` · Reviewer: `{res.reviewer_model}`"
        )

        for step in res.iterations:
            is_last  = (step.round_idx == len(res.iterations)-1)
            st_icon  = "✅" if step.status=="APPROVED" else "🔄"
            step_bugs = [b for r in step.reviews for b in r.bugs]

            with st.expander(
                f"📍 Round {step.round_idx}  ·  {st_icon} {step.status}  ·  "
                f"{len(step_bugs)} bug(s) found",
                expanded=is_last
            ):
                # Agent messages
                step_msgs = [m for m in res.messages if m.round_idx == step.round_idx]
                if step_msgs:
                    for msg in step_msgs:
                        cls, ico, col_m = _bubble_class(msg.sender_role)
                        body = msg.content[:500] + ("…" if len(msg.content)>500 else "")
                        st.markdown(f"""
                        <div class="cb {cls}">
                          <div class="cb-hdr">
                            <span style="font-size:.95rem;">{ico}</span>
                            <span class="cb-who" style="color:{col_m};">{msg.sender_role}</span>
                            <span class="cb-mdl">{msg.sender_model}</span>
                            <span class="cb-ts">⏱ {msg.timestamp}</span>
                          </div>
                          <div class="cb-body">{body}</div>
                        </div>
                        """, unsafe_allow_html=True)

                # Review score bars
                if step.reviews:
                    st.markdown("**Review Scores:**")
                    rc = st.columns(len(step.reviews))
                    for i, rev in enumerate(step.reviews):
                        with rc[i]:
                            sc_lbl = "✅ APPROVED" if rev.status=="APPROVED" else "🔄 CHANGES REQUESTED"
                            sc_col = "#10B981" if rev.status=="APPROVED" else "#F59E0B"
                            st.markdown(
                                f'**{rev.reviewer_name}**<br/>'
                                f'<span style="font-size:.75rem;color:{sc_col};font-weight:700;">{sc_lbl}</span>',
                                unsafe_allow_html=True
                            )
                            st.markdown(_score_bar(rev.overall_score), unsafe_allow_html=True)
                            st.caption(rev.summary[:200])

                # Bug list
                if step_bugs:
                    st.markdown("**🐛 Bugs Detected This Round:**")
                    for b in step_bugs:
                        sev = b.severity.lower() if hasattr(b.severity,"lower") else str(b.severity).lower()
                        line_txt = f"`Line {b.line_number}` " if b.line_number else ""
                        st.markdown(f"""
                        <div class="bug bug-{sev}">
                          <div class="bug-hdr">
                            <span class="bdg bdg-{sev}">{b.severity}</span>
                            <span style="font-size:.74rem;font-weight:700;color:#94A3B8;">[{b.category}]</span>
                            <span style="font-size:.72rem;color:#64748B;font-family:var(--mono);">{line_txt}</span>
                          </div>
                          <div class="bug-desc">{b.description}</div>
                          <div class="bug-fix">💡 {b.suggested_fix}</div>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.success("✅ No bugs in this round!", icon="✅")

    # ══════════ TAB 2: CODE DIFF ══════════════════════════════════
    with t2:
        st.markdown("### 🔍 Code Changes (Diff View)")
        if len(res.iterations) > 1:
            rounds = list(range(len(res.iterations)-1))
            dr = st.selectbox("Compare", rounds, format_func=lambda r: f"Round {r} → Round {r+1}", index=len(rounds)-1)
            code_a = res.iterations[dr].code
            code_b = res.iterations[dr+1].code
            diff   = compute_unified_diff(code_a, code_b, f"Round {dr}", f"Round {dr+1}")

            added   = sum(1 for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++"))
            removed = sum(1 for l in diff.splitlines() if l.startswith("-") and not l.startswith("---"))
            st.markdown(
                f'<div class="diff-stat">'
                f'<span class="diff-added">+{added} lines added</span>'
                f'<span class="diff-removed">−{removed} lines removed</span>'
                f'<span class="diff-files">1 file changed</span>'
                f'</div>',
                unsafe_allow_html=True
            )
            st.code(diff, language="diff")
        else:
            st.success("✅ Code approved in Round 0 — no changes needed!", icon="🏆")

    # ══════════ TAB 3: FINAL CODE ═════════════════════════════════
    with t3:
        st.markdown("### 🏆 Final Approved Source Code")
        fc1, fc2 = st.columns([4,1])
        with fc1:
            st.markdown(
                f'Provider: `{res.provider}` · Generator: `{res.generator_model}` · '
                f'Language: `{res.target_language}` · '
                f'<span class="bdg bdg-{"approved" if res.status=="APPROVED" else "changes"}">'
                f'{"✅ APPROVED" if res.status=="APPROVED" else "⚠️ "+res.status}</span>',
                unsafe_allow_html=True
            )
        with fc2:
            loc = len([l for l in res.final_code.splitlines() if l.strip()])
            st.metric("Lines of Code", loc)

        st.code(res.final_code, language=res.target_language)

    # ══════════ TAB 4: QUALITY & SECURITY ════════════════════════
    with t4:
        st.markdown("### 📊 Code Quality & Security Analysis")
        is_valid, syn_err, meta = check_syntax(res.final_code, res.target_language)

        # Top metrics
        qm1, qm2, qm3, qm4, qm5 = st.columns(5)
        with qm1: st.metric("Syntax Valid",        "✅ Yes" if is_valid else "❌ No")
        with qm2: st.metric("Security Score",       f"{meta.get('security_score',100)}/100")
        with qm3: st.metric("Complexity",           meta.get("cyclomatic_complexity",1))
        with qm4: st.metric("Functions",            meta.get("num_functions",0))
        with qm5: st.metric("Docstrings",           meta.get("docstring_count",0))

        st.write("")

        # Security findings
        if meta.get("security_flags"):
            st.warning("⚠️ **Security Findings:**", icon="🔴")
            for f_ in meta["security_flags"]:
                st.markdown(f"- 🔴 `{f_}`")
        else:
            st.success("🛡️ **Security Clean** — No dangerous functions (eval, exec, shell injection) detected.", icon="✅")

        if not is_valid and syn_err:
            st.error(f"❌ Syntax Error: `{syn_err}`")

        # Bug breakdown
        if all_bugs:
            st.markdown("#### Bug Distribution")
            ba1, ba2 = st.columns(2)
            with ba1:
                st.markdown("**By Severity**")
                sev_ct: dict = {}
                for b in all_bugs:
                    k = str(b.severity)
                    sev_ct[k] = sev_ct.get(k,0)+1
                colors = {"CRITICAL":"#EF4444","MAJOR":"#F59E0B","MINOR":"#3B82F6","SUGGESTION":"#8B5CF6"}
                for sev, cnt in sorted(sev_ct.items(), key=lambda x:-x[1]):
                    c = colors.get(sev.upper(),"#94A3B8")
                    st.markdown(
                        f'<span style="color:{c};font-weight:700;">{sev}</span> — {cnt} bug(s)',
                        unsafe_allow_html=True
                    )
            with ba2:
                st.markdown("**By Category**")
                cat_ct: dict = {}
                for b in all_bugs:
                    k = str(b.category)
                    cat_ct[k] = cat_ct.get(k,0)+1
                for cat, cnt in sorted(cat_ct.items(), key=lambda x:-x[1]):
                    st.markdown(f'`{cat}` — {cnt}')

        with st.expander("📋 Full AST Metadata"):
            st.json(meta)

    # ══════════ TAB 5: SANDBOX LOG ════════════════════════════════
    with t5:
        st.markdown("### 🧪 Sandbox Subprocess Execution Log")
        if res.final_execution:
            fe = res.final_execution
            if fe.success:
                st.success(f"✅ Execution passed in **{fe.execution_time_ms:.1f}ms** (Exit Code: {fe.exit_code})", icon="⚡")
            else:
                st.error(f"❌ Execution failed (Exit Code: {fe.exit_code})", icon="❌")

            sl1, sl2 = st.columns(2)
            with sl1:
                st.markdown("**📤 stdout**")
                st.code(fe.stdout.strip() or "(no output)", language="text")
            with sl2:
                st.markdown("**⚠️ stderr**")
                st.code(fe.stderr.strip() or "(no errors)", language="text")

            if fe.syntax_error:
                st.error(f"Syntax Error: `{fe.syntax_error}`")

            # Per-round table
            if len(res.iterations) > 1:
                st.markdown("#### Per-Round Execution Summary")
                for step in res.iterations:
                    if step.execution:
                        col_r = "#10B981" if step.execution.success else "#EF4444"
                        ico   = "✅" if step.execution.success else "❌"
                        st.markdown(
                            f'<span style="color:{col_r};">{ico} **Round {step.round_idx}** — '
                            f'{step.execution.execution_time_ms:.1f}ms · Exit `{step.execution.exit_code}`</span>',
                            unsafe_allow_html=True
                        )
        else:
            st.info("Sandbox execution was disabled in sidebar settings.", icon="ℹ️")

    # ══════════ TAB 6: AUDIT REPORT ═══════════════════════════════
    with t6:
        st.markdown("### 📄 Multi-LLM Audit Report")
        report_md = export_markdown_report(res)
        st.markdown(report_md)

    # ══════════ TAB 7: EXPORT ════════════════════════════════════
    with t7:
        st.markdown("### 📥 Export Workflow Results")
        st.write("")
        e1, e2, e3, e4 = st.columns(4)
        with e1:
            st.download_button(
                "⬇️ Python Script (.py)",
                data=res.final_code,
                file_name=f"solution_{datetime.now().strftime('%Y%m%d_%H%M%S')}.py",
                mime="text/x-python",
                use_container_width=True,
            )
        with e2:
            st.download_button(
                "⬇️ Audit Report (.md)",
                data=export_markdown_report(res),
                file_name=f"audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                mime="text/markdown",
                use_container_width=True,
            )
        with e3:
            json_data = json.dumps(res.model_dump(mode="json"), indent=2, default=str)
            st.download_button(
                "⬇️ Full Workflow (.json)",
                data=json_data,
                file_name=f"workflow_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json",
                use_container_width=True,
            )
        with e4:
            # Generate diff as patch file
            if len(res.iterations) > 1:
                diff_patch = compute_unified_diff(
                    res.iterations[0].code, res.final_code, "original", "fixed"
                )
                st.download_button(
                    "⬇️ Code Diff (.patch)",
                    data=diff_patch,
                    file_name=f"changes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.patch",
                    mime="text/plain",
                    use_container_width=True,
                )
            else:
                st.button("⬇️ Code Diff (.patch)", disabled=True, use_container_width=True)

        st.write("")
        st.markdown("#### 📋 Workflow Summary")
        st.markdown(f"""
| Field | Value |
|:---|:---|
| **Status** | `{res.status}` |
| **Provider** | `{res.provider}` |
| **Generator** | `{res.generator_model}` |
| **Reviewer** | `{res.reviewer_model}` |
| **Validator** | `{res.validator_model or 'disabled'}` |
| **Rounds** | `{res.rounds_count}` |
| **Bugs Detected** | `{res.total_bugs_detected}` |
| **Bugs Fixed** | `{res.total_bugs_fixed}` |
| **Final Language** | `{res.target_language}` |
| **Sandbox Runtime** | `{res.final_execution.execution_time_ms:.1f} ms` if {bool(res.final_execution)} else `N/A` |
""")


# ─────────────────────────────────────────────────────────────────────
#  EMPTY STATE
# ─────────────────────────────────────────────────────────────────────
elif not run_btn:
    logo_es = f'<img src="{LOGO_SRC}" style="width:56px;height:56px;margin-bottom:.7rem;opacity:.5;"/>' if LOGO_SRC else '<div style="font-size:3rem;margin-bottom:.7rem;">🛡️</div>'
    st.markdown(f"""
    <div class="empty-state">
        {logo_es}
        <div class="empty-state-title">Ready to Review</div>
        <div class="empty-state-sub">
            Select a real-world scenario from the dropdown above (or write a custom prompt),
            configure your LLM agents in the sidebar, then click
            <strong>🚀 Start Multi-LLM Review Workflow</strong> to begin.<br/><br/>
            <strong>No GPU needed</strong> — select <em>⚡ Smart Simulator</em> to demo instantly.
        </div>
    </div>
    """, unsafe_allow_html=True)
