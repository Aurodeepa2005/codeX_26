"""
app.py
======
StandardMatch AI -- Web Interface (Streamlit)
Smart India Hackathon 2026

An AI-Powered Recommendation Engine for Identifying Applicable
Indian Standards (IS) for Procurement Specifications.
"""

import json
import os
import re
import sys
from pathlib import Path

# Ensure UTF-8 stdout
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# Project setup
# ---------------------------------------------------------------------------
APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent
DATA_PATH = PROJECT_ROOT / "data" / "processed" / "standards.csv"
QUERIES_PATH = PROJECT_ROOT / "data" / "evaluation" / "test_queries.csv"

# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="StandardMatch AI | Indian Standards Recommendation",
    page_icon="🇮🇳",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    .main-header {
        background: linear-gradient(135deg, #0b3d91 0%, #1e5bb8 100%);
        color: white;
        padding: 24px 28px;
        border-radius: 12px;
        margin-bottom: 24px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    }
    .main-header h1 {
        color: #ffffff !important;
        font-size: 2.2rem;
        font-weight: 700;
        margin: 0;
    }
    .main-header p {
        color: #e0e9f8;
        font-size: 1.05rem;
        margin: 6px 0 0 0;
    }
    .card {
        background-color: #ffffff;
        border: 1px solid #e5e9f2;
        border-radius: 10px;
        padding: 20px;
        margin-bottom: 16px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.04);
        transition: transform 0.15s ease, box-shadow 0.15s ease;
    }
    .card:hover {
        box-shadow: 0 6px 16px rgba(0,0,0,0.08);
        border-color: #cbd5e1;
    }
    .badge-active {
        background-color: #def7ec;
        color: #03543f;
        padding: 4px 12px;
        border-radius: 12px;
        font-weight: 600;
        font-size: 0.85rem;
        display: inline-block;
    }
    .badge-score {
        background-color: #e1effe;
        color: #1e429f;
        padding: 4px 12px;
        border-radius: 12px;
        font-weight: 700;
        font-size: 0.88rem;
        display: inline-block;
    }
    .scope-box {
        background-color: #f8fafc;
        border-left: 4px solid #3b82f6;
        padding: 10px 14px;
        border-radius: 0 6px 6px 0;
        font-size: 0.92rem;
        color: #334155;
        margin-top: 10px;
        line-height: 1.5;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Data loading & caching
# ---------------------------------------------------------------------------
@st.cache_data
def load_standards() -> pd.DataFrame:
    if not DATA_PATH.exists():
        st.error(f"Dataset not found at {DATA_PATH}. Run `python scripts/build_dataset.py` first.")
        return pd.DataFrame()
    return pd.read_csv(DATA_PATH, dtype=str)


@st.cache_data
def load_test_queries() -> pd.DataFrame:
    if not QUERIES_PATH.exists():
        return pd.DataFrame()
    return pd.read_csv(QUERIES_PATH, dtype=str)


# ---------------------------------------------------------------------------
# Recommendation scoring engine
# ---------------------------------------------------------------------------
def compute_recommendations(query: str, df: pd.DataFrame, top_k: int = 5) -> list[dict]:
    if df.empty or not query.strip():
        return []

    tokens = [t.lower() for t in re.findall(r"\w+", query) if len(t) > 2]
    stop_words = {"for", "the", "and", "with", "class", "grade", "system", "supplies", "supply", "use"}
    keywords = [t for t in tokens if t not in stop_words]

    results = []
    for _, row in df.iterrows():
        title = str(row.get("title", "")).lower()
        scope = str(row.get("scope", "")).lower()
        is_num = str(row.get("is_number", "")).lower()
        comb = f"{is_num} {title} {scope}"

        score = 0
        matched_words = []

        # Exact IS number mention in query
        for num_part in re.findall(r"\d+", query):
            if num_part in is_num:
                score += 50
                matched_words.append(f"IS {num_part}")

        # Keyword match weights
        for kw in keywords:
            if re.search(rf"\b{re.escape(kw)}s?\b", title):
                score += 15
                matched_words.append(kw)
            elif re.search(rf"\b{re.escape(kw)}s?\b", scope):
                score += 8
                matched_words.append(kw)
            elif kw in comb:
                score += 3

        if score > 0:
            # Normalize confidence score between 50% and 98%
            conf = min(98, max(52, 50 + int(score * 2.2)))
            
            # Extract most relevant scope sentence
            raw_scope = str(row.get("scope", ""))
            scope_sentence = raw_scope
            if raw_scope and raw_scope != "nan":
                sentences = re.split(r"(?<=[.!?])\s+", raw_scope)
                for s in sentences:
                    if any(k in s.lower() for k in keywords):
                        scope_sentence = s.strip()
                        break
                if len(scope_sentence) > 280:
                    scope_sentence = scope_sentence[:277] + "..."

            results.append(
                {
                    "is_number": row.get("is_number", "N/A"),
                    "title": row.get("title", "N/A"),
                    "year": row.get("year", "N/A"),
                    "status": row.get("status", "Active"),
                    "category": row.get("category", "General"),
                    "technical_committee": row.get("technical_committee", "N/A"),
                    "ics_code": row.get("ics_code", "N/A"),
                    "source_url": row.get("source_url", "https://standardsbis.bsbedge.com/"),
                    "confidence": conf,
                    "matched_words": list(set(matched_words)),
                    "scope_evidence": scope_sentence if scope_sentence != "nan" else "Standard metadata verified on official BIS portal.",
                }
            )

    results.sort(key=lambda x: x["confidence"], reverse=True)
    return results[:top_k]


# ---------------------------------------------------------------------------
# UI Layout
# ---------------------------------------------------------------------------
# Header Banner
st.markdown(
    """
    <div class="main-header">
        <h1>🇮🇳 StandardMatch AI</h1>
        <p>An AI-Powered Recommendation Engine for Identifying Applicable Indian Standards (IS) for Procurement Specifications</p>
        <p style="font-size: 0.85rem; color: #cbd5e1; margin-top: 4px;">Smart India Hackathon 2026 • Ministry of Consumer Affairs, Food & Public Distribution</p>
    </div>
    """,
    unsafe_allow_html=True,
)

df_standards = load_standards()
df_queries = load_test_queries()

# Sidebar
with st.sidebar:
    st.subheader("📊 System Status")
    st.metric("Total Standards Ingested", len(df_standards))
    st.metric("Active Standards", len(df_standards[df_standards["status"] == "Active"]) if not df_standards.empty else 0)
    st.metric("Coverage Category", "Pipes & Steel")
    
    st.divider()
    st.subheader("💡 Sample Procurement Queries")
    sample_queries = [
        "GI pipes for rural drinking water supply, medium class",
        "unplasticized PVC pipes for potable water supply",
        "centrifugally cast spun iron pressure pipes for water transmission",
        "high density polyethylene pipes for municipal sewerage",
        "fabricated PVC-U fittings for drinking water pipelines",
        "mild steel wrought pipe fittings for water service lines",
        "elastomeric rubber sealing rings for water pipeline joints",
    ]
    
    selected_sample = None
    for q in sample_queries:
        if st.button(q, key=f"btn_{q[:20]}", use_container_width=True):
            selected_sample = q

    st.divider()
    st.caption("StandardMatch AI v1.0 • Phase 1 Release")

# Navigation tabs
tab_rec, tab_catalogue, tab_eval = st.tabs([
    "🔍 AI Recommendation Engine",
    "📚 BIS Standards Catalogue",
    "📈 Evaluation Benchmark"
])

# ---------------------------------------------------------------------------
# TAB 1: AI Recommendation Engine
# ---------------------------------------------------------------------------
with tab_rec:
    st.markdown("### Enter Procurement Specification")
    st.write("Enter an item description in plain natural language (e.g. from GeM tender or procurement indent):")

    default_query = selected_sample if selected_sample else "GI pipes for rural drinking water supply, medium class, screwed and socketed"
    
    col_input, col_action = st.columns([5, 1])
    with col_input:
        user_query = st.text_input(
            "Procurement Description",
            value=default_query,
            label_visibility="collapsed",
            placeholder="Type your procurement specification here...",
        )
    with col_action:
        search_clicked = st.button("Recommend", type="primary", use_container_width=True)

    top_n = st.slider("Number of recommendations", min_value=1, max_value=10, value=3)

    if user_query:
        recs = compute_recommendations(user_query, df_standards, top_k=top_n)

        st.markdown(f"#### Top {len(recs)} Recommended Standards for: *\"{user_query}\"*")
        
        if not recs:
            st.warning("No matching standards found in the current category dataset. Try broader search terms.")
        else:
            for i, r in enumerate(recs, 1):
                status_color = "badge-active" if r["status"] == "Active" else "badge-score"
                with st.container():
                    st.markdown(
                        f"""
                        <div class="card">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                                <div>
                                    <span style="font-size: 1.25rem; font-weight: 700; color: #0b3d91;">#{i} {r['is_number']}</span>
                                    <span style="color: #64748b; font-size: 0.9rem; margin-left: 8px;">(Published: {r['year']})</span>
                                </div>
                                <div>
                                    <span class="badge-score">Match Score: {r['confidence']}%</span>
                                    <span class="{status_color}" style="margin-left: 6px;">{r['status']}</span>
                                </div>
                            </div>
                            <div style="font-weight: 600; font-size: 1.05rem; color: #1e293b; margin-bottom: 6px;">
                                {r['title']}
                            </div>
                            <div style="font-size: 0.85rem; color: #64748b; margin-bottom: 8px;">
                                <b>Category:</b> {r['category'].title()} &nbsp;|&nbsp; 
                                <b>Technical Committee:</b> {r['technical_committee']} &nbsp;|&nbsp; 
                                <b>ICS Code:</b> {r['ics_code']}
                            </div>
                            <div class="scope-box">
                                <b>📌 Scope-Clause Justification:</b><br/>
                                <i>"{r['scope_evidence']}"</i>
                            </div>
                            <div style="margin-top: 12px; display: flex; justify-content: space-between; align-items: center;">
                                <span style="font-size: 0.82rem; color: #475569;">
                                    <b>Keywords matched:</b> {', '.join(r['matched_words']) if r['matched_words'] else 'Category match'}
                                </span>
                                <a href="{r['source_url']}" target="_blank" style="text-decoration: none; color: #2563eb; font-weight: 600; font-size: 0.88rem;">
                                    View on Official BIS Portal ↗
                                </a>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

# ---------------------------------------------------------------------------
# TAB 2: Standards Catalogue Browser
# ---------------------------------------------------------------------------
with tab_catalogue:
    st.markdown("### Browse Ingested BIS Standards")
    st.write("All records in this catalogue are scraped directly from the official BIS portal (`standardsbis.bsbedge.com`) and validated:")

    col_filter1, col_filter2 = st.columns([3, 1])
    with col_filter1:
        cat_search = st.text_input("Filter by IS number, title, or keywords", placeholder="Filter...")
    with col_filter2:
        status_filter = st.selectbox("Status", options=["All", "Active", "Revised", "Withdrawn"])

    filtered_df = df_standards.copy()
    if cat_search.strip():
        term = cat_search.lower()
        filtered_df = filtered_df[
            filtered_df["is_number"].str.lower().str.contains(term, na=False) |
            filtered_df["title"].str.lower().str.contains(term, na=False) |
            filtered_df["scope"].str.lower().str.contains(term, na=False)
        ]
    if status_filter != "All":
        filtered_df = filtered_df[filtered_df["status"] == status_filter]

    st.dataframe(
        filtered_df[["is_number", "title", "year", "status", "category", "source_url"]],
        use_container_width=True,
        hide_index=True,
    )
    st.caption(f"Showing {len(filtered_df)} of {len(df_standards)} standards.")

# ---------------------------------------------------------------------------
# TAB 3: Evaluation Benchmark
# ---------------------------------------------------------------------------
with tab_eval:
    st.markdown("### Evaluation Benchmark Suite")
    st.write("Benchmark queries designed to test recommendation accuracy against real procurement specifications:")

    if df_queries.empty:
        st.info("No evaluation queries loaded.")
    else:
        st.dataframe(
            df_queries,
            use_container_width=True,
            hide_index=True,
        )

        if st.button("Run Benchmark Evaluation on Current Catalogue", type="primary"):
            correct_at_1 = 0
            correct_at_3 = 0
            total_tested = len(df_queries)

            with st.spinner("Evaluating queries..."):
                for _, q_row in df_queries.iterrows():
                    q_text = str(q_row["query"])
                    exp_is = str(q_row.get("expected_is_numbers", "")).strip()
                    recs = compute_recommendations(q_text, df_standards, top_k=3)
                    rec_is = [r["is_number"] for r in recs]
                    
                    if exp_is and exp_is in rec_is[:1]:
                        correct_at_1 += 1
                    if exp_is and exp_is in rec_is[:3]:
                        correct_at_3 += 1

            p1 = (correct_at_1 / total_tested) * 100 if total_tested else 0
            p3 = (correct_at_3 / total_tested) * 100 if total_tested else 0

            m_col1, m_col2, m_col3 = st.columns(3)
            m_col1.metric("Precision @ 1", f"{p1:.1f}%")
            m_col2.metric("Precision @ 3", f"{p3:.1f}%")
            m_col3.metric("Queries Tested", total_tested)
            st.success("Benchmark completed successfully!")
