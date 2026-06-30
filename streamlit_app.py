from __future__ import annotations

from datetime import datetime
from pathlib import Path
import csv
import os
import subprocess
import sys
import time
from typing import Any

import pandas as pd
import requests
import streamlit as st


st.set_page_config(
    page_title="ExciseWatch Cloud",
    page_icon="EW",
    layout="wide",
    initial_sidebar_state="expanded",
)


DEFAULT_API = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
LEADS_FILE = Path("storage") / "saas_leads.csv"
API_PROCESS: subprocess.Popen | None = None


@st.cache_resource
def ensure_internal_api() -> bool:
    if api_base() != "http://127.0.0.1:8000":
        return False
    try:
        requests.get(f"{api_base()}/health", timeout=2)
        return False
    except Exception:
        pass

    Path("storage").mkdir(exist_ok=True)
    out = open(Path("storage") / "streamlit_internal_api.out.log", "a", encoding="utf-8")
    err = open(Path("storage") / "streamlit_internal_api.err.log", "a", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
        stdout=out,
        stderr=err,
    )
    globals()["API_PROCESS"] = proc
    for _ in range(20):
        try:
            requests.get(f"{api_base()}/health", timeout=2)
            return True
        except Exception:
            time.sleep(0.5)
    return True


def css() -> None:
    st.markdown(
        """
        <style>
        :root {
          --ew-ink: #14213d;
          --ew-muted: #5f6c7b;
          --ew-border: #d9e1ea;
          --ew-bg: #f6f8fb;
          --ew-panel: #ffffff;
          --ew-good: #0f7b63;
          --ew-warn: #a15c08;
          --ew-bad: #a83232;
          --ew-accent: #176b87;
        }
        .stApp { background: var(--ew-bg); color: var(--ew-ink); }
        section[data-testid="stSidebar"] { background: #ffffff; border-right: 1px solid var(--ew-border); }
        h1, h2, h3 { letter-spacing: 0 !important; color: var(--ew-ink); }
        h1 { font-size: 2rem !important; margin-bottom: .1rem !important; }
        h2 { font-size: 1.35rem !important; }
        h3 { font-size: 1.05rem !important; }
        div[data-testid="stMetric"] {
          background: var(--ew-panel);
          border: 1px solid var(--ew-border);
          padding: 14px 16px;
          border-radius: 8px;
        }
        div[data-testid="stMetricValue"] { font-size: 1.35rem; }
        .ew-band {
          background: #ffffff;
          border: 1px solid var(--ew-border);
          border-radius: 8px;
          padding: 18px 20px;
          margin: 10px 0 14px 0;
        }
        .ew-title-row {
          display: flex;
          justify-content: space-between;
          gap: 16px;
          align-items: flex-start;
          border-bottom: 1px solid var(--ew-border);
          padding-bottom: 14px;
          margin-bottom: 16px;
        }
        .ew-product {
          font-size: .78rem;
          text-transform: uppercase;
          font-weight: 700;
          color: var(--ew-accent);
          letter-spacing: .08em;
        }
        .ew-subtle { color: var(--ew-muted); font-size: .95rem; }
        .ew-pill {
          display: inline-block;
          border: 1px solid var(--ew-border);
          border-radius: 999px;
          padding: 4px 10px;
          font-size: .78rem;
          background: #f8fafc;
          color: var(--ew-muted);
          margin-right: 6px;
          margin-bottom: 6px;
        }
        .ew-plan {
          background: #ffffff;
          border: 1px solid var(--ew-border);
          border-radius: 8px;
          min-height: 280px;
          padding: 18px;
        }
        .ew-plan strong { font-size: 1.15rem; }
        .ew-price { font-size: 1.75rem; font-weight: 700; margin: 10px 0; color: var(--ew-ink); }
        .ew-good { color: var(--ew-good); font-weight: 700; }
        .ew-warn { color: var(--ew-warn); font-weight: 700; }
        .ew-bad { color: var(--ew-bad); font-weight: 700; }
        .block-container { padding-top: 1.5rem; padding-bottom: 3rem; }
        .stTabs [data-baseweb="tab-list"] { gap: 4px; }
        .stTabs [data-baseweb="tab"] {
          background: #ffffff;
          border: 1px solid var(--ew-border);
          border-radius: 8px 8px 0 0;
          padding: 10px 14px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def api_base() -> str:
    return st.session_state.get("api_base", DEFAULT_API).rstrip("/")


def request_json(method: str, path: str, *, timeout: int = 30, **kwargs: Any) -> tuple[dict | list | None, str | None]:
    url = f"{api_base()}{path}"
    try:
        response = requests.request(method, url, timeout=timeout, **kwargs)
        response.raise_for_status()
        return response.json(), None
    except Exception as exc:
        if "127.0.0.1:8000" in url:
            ensure_internal_api()
            try:
                response = requests.request(method, url, timeout=timeout, **kwargs)
                response.raise_for_status()
                return response.json(), None
            except Exception:
                pass
        return None, str(exc)


def df_from(rows: Any) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    if isinstance(rows, dict):
        rows = [rows]
    return pd.DataFrame(rows)


def evidence_badge(value: str | None) -> str:
    value = str(value or "UNKNOWN")
    klass = "ew-good" if value == "OFFICIAL_CONFIRMED" else "ew-warn" if value in {"GOVT_PROBABLE", "REPORTED_NOT_CONFIRMED"} else "ew-bad"
    return f'<span class="{klass}">{value}</span>'


def save_lead(row: dict[str, str]) -> None:
    LEADS_FILE.parent.mkdir(parents=True, exist_ok=True)
    exists = LEADS_FILE.exists()
    with LEADS_FILE.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(row.keys()))
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def load_status() -> dict[str, Any]:
    readiness, _ = request_json("GET", "/api/v6/readiness", timeout=10)
    changes, _ = request_json("GET", "/api/changes", params={"days": 30, "limit": 500}, timeout=20)
    briefs, _ = request_json("GET", "/api/conclusive/briefs", params={"limit": 200}, timeout=20)
    jobs, _ = request_json("GET", "/api/jobs/status", params={"limit": 5}, timeout=20)
    return {
        "readiness": readiness or {},
        "changes": changes or [],
        "briefs": briefs or [],
        "jobs": jobs or [],
    }


def render_header() -> None:
    st.markdown(
        """
        <div class="ew-title-row">
          <div>
            <div class="ew-product">ExciseWatch Cloud</div>
            <h1>Regulatory Intelligence SaaS for excise, liquor and public-office compliance</h1>
            <div class="ew-subtle">
              Official-source monitoring, evidence ranking, human review, Telegram alerts and audit-ready compliance guidance.
            </div>
          </div>
          <div>
            <span class="ew-pill">All India coverage</span>
            <span class="ew-pill">Official evidence gates</span>
            <span class="ew-pill">Enterprise ready</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar() -> tuple[str | None, int]:
    st.sidebar.markdown("### ExciseWatch Cloud")
    st.sidebar.text_input("API base URL", DEFAULT_API, key="api_base")
    st.sidebar.markdown("#### Workspace")
    company = st.sidebar.text_input("Organisation", "Demo Distributor")
    plan = st.sidebar.selectbox("Subscription", ["Pilot", "Professional", "Enterprise", "Government"])
    st.sidebar.caption("This local build simulates tenancy. Production should enforce tenant isolation in auth and database policies.")
    st.sidebar.markdown("#### Intelligence scope")
    state = st.sidebar.text_input("State / UT code", "KA")
    days = st.sidebar.number_input("Lookback days", min_value=1, max_value=1095, value=365)
    st.sidebar.markdown("#### Evidence policy")
    st.sidebar.checkbox("Require official source for CONFIRMED", True, disabled=True)
    st.sidebar.checkbox("Human approval before guidance", True, disabled=True)
    st.sidebar.markdown(f"**Tenant:** {company}<br>**Plan:** {plan}", unsafe_allow_html=True)
    return state.strip().upper() or None, int(days)


def render_overview(state_code: str | None, days: int) -> None:
    status = load_status()
    readiness = status["readiness"]
    counts = readiness.get("counts", {})
    changes = status["changes"]
    briefs = status["briefs"]
    jobs = status["jobs"]

    st.markdown('<div class="ew-band">', unsafe_allow_html=True)
    st.markdown("### Operations Command Center")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Sources", counts.get("sources", 0))
    c2.metric("Raw intelligence", len(changes))
    c3.metric("Review tasks", counts.get("review_tasks", 0))
    c4.metric("Guidance records", counts.get("guidance", 0))
    c5.metric("Conclusive briefs", len(briefs))

    gates = readiness.get("production_layers", {})
    gate_cols = st.columns(4)
    for idx, (name, value) in enumerate(gates.items()):
        gate_cols[idx % 4].markdown(f"**{name.replace('_', ' ').title()}**  \n{'Ready' if value else 'Needs setup'}")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("### Latest Intelligence")
    payload, err = request_json("GET", "/api/changes", params={"state_code": state_code, "days": days, "limit": 100}, timeout=20)
    if err:
        st.error(err)
    df = df_from(payload)
    if not df.empty:
        cols = ["detected_at", "state_name", "change_type", "evidence_tier", "title", "legal_effect", "source_url", "needs_human_review"]
        st.dataframe(df[[c for c in cols if c in df.columns]], use_container_width=True, height=360)
    else:
        st.info("No intelligence rows for this scope yet. Run a news feed or source watch.")

    with st.expander("Recent platform jobs", expanded=False):
        jobs_df = df_from(jobs)
        if jobs_df.empty:
            st.caption("No job history yet.")
        else:
            st.dataframe(jobs_df, use_container_width=True)


def render_intelligence(state_code: str | None, days: int) -> None:
    st.markdown("### Feed the Intelligence Engine")
    st.caption("Run state-specific monitoring in production. All-India sweeps should be scheduled server-side, not inside Telegram.")
    c1, c2, c3 = st.columns([1, 1, 2])
    include_news = c1.checkbox("Include news", True)
    include_alerts = c2.checkbox("Send alerts", False)
    if c3.button("Run state watch", use_container_width=True):
        payload = {"state_code": state_code, "include_news": include_news, "include_alerts": include_alerts}
        with st.spinner("Fetching and classifying state intelligence..."):
            result, err = request_json("POST", "/api/watch/run", json=payload, timeout=180)
        st.error(err) if err else st.json(result)

    n1, n2, n3 = st.columns([1, 1, 2])
    news_scope = n1.selectbox("Latest news scope", ["Selected state", "All India"])
    send_telegram = n2.checkbox("Send Telegram digest", True)
    if n3.button("Run latest news feed", use_container_width=True):
        payload = {
            "job_name": "latest_news_feed",
            "state_code": None if news_scope == "All India" else state_code,
            "dry_run": not send_telegram,
        }
        with st.spinner("Pulling latest reported news and classifying intelligence..."):
            result, err = request_json("POST", "/api/jobs/run-now", json=payload, timeout=240)
        st.error(err) if err else st.json(result)

    st.markdown("### Reported News Intelligence")
    rows, err = request_json("GET", "/api/changes", params={"state_code": state_code, "days": days, "tier": "REPORTED_NOT_CONFIRMED", "limit": 100}, timeout=20)
    if err:
        st.error(err)
    df = df_from(rows)
    if df.empty:
        st.info("No reported news rows found for this scope.")
    else:
        cols = ["detected_at", "state_name", "change_type", "evidence_tier", "title", "summary", "source_url"]
        st.dataframe(df[[c for c in cols if c in df.columns]], use_container_width=True, height=420)


def render_conclusive(state_code: str | None, days: int) -> None:
    st.markdown("### Conclusive Answer Desk")
    st.caption("This is the buyer-facing core: answers are marked CONFIRMED only when official evidence is relevant and not contradicted.")
    question = st.text_area(
        "Compliance question",
        f"Is there a confirmed licence fee increase in {state_code or 'this state'}?",
        height=90,
    )
    c1, c2 = st.columns([1, 1])
    if c1.button("Run conclusive check", use_container_width=True):
        payload = {"question": question, "state_code": state_code, "days": days, "include_chatter": False}
        result, err = request_json("POST", "/api/ai/conclusive", json=payload, timeout=60)
        if err:
            st.error(err)
        else:
            st.markdown(f"#### Status: {result.get('answer_status')} | Definitive: {result.get('definitive')}")
            st.markdown(evidence_badge(result.get("evidence_tier")), unsafe_allow_html=True)
            st.write(result.get("conclusion"))
            src_df = df_from(result.get("top_sources"))
            if not src_df.empty:
                st.dataframe(src_df, use_container_width=True)
            if result.get("conflicts"):
                st.warning("Conflicting evidence found")
                st.json(result.get("conflicts"))

    if c2.button("Generate full AI suite", use_container_width=True):
        payload = {"question": question, "state_code": state_code, "days": days, "include_chatter": False}
        result, err = request_json("POST", "/api/ai/suite", json=payload, timeout=90)
        if err:
            st.error(err)
        else:
            st.json(result.get("final_decision", {}))
            with st.expander("Impact analysis", expanded=True):
                st.json(result.get("impact", {}))
            with st.expander("Compliance checklist", expanded=True):
                st.json(result.get("checklist", {}))

    st.markdown("### Stored Conclusive Briefs")
    briefs, err = request_json("GET", "/api/conclusive/briefs", params={"state_code": state_code, "limit": 100}, timeout=20)
    if err:
        st.error(err)
    df = df_from(briefs)
    if df.empty:
        st.info("No stored briefs yet.")
    else:
        cols = ["created_at", "state_name", "answer_status", "definitive", "strongest_evidence_tier", "question", "conclusion", "official_source_count", "news_source_count", "conflict_count"]
        st.dataframe(df[[c for c in cols if c in df.columns]], use_container_width=True, height=340)


def render_review_and_publish(state_code: str | None) -> None:
    st.markdown("### Review Queue and Publication Controls")
    st.caption("Official evidence becomes internal guidance only after review. Telegram publication is gated by approval state.")
    c1, c2 = st.columns([1, 1])
    if c1.button("Generate review tasks", use_container_width=True):
        result, err = request_json("POST", "/api/review/generate", json={"state_code": state_code, "limit": 250}, timeout=60)
        st.error(err) if err else st.json(result)
    if c2.button("Preview Telegram digest", use_container_width=True):
        payload = {"state_code": state_code, "days": 7, "limit": 10, "dry_run": True, "include_chatter": False}
        result, err = request_json("POST", "/api/telegram/digest", json=payload, timeout=60)
        if err:
            st.error(err)
        else:
            st.json({k: v for k, v in result.items() if k != "chunks"})
            for idx, chunk in enumerate(result.get("chunks", [])[:3], 1):
                st.text_area(f"Digest chunk {idx}", chunk, height=220)

    tasks, err = request_json("GET", "/api/review/tasks", params={"state_code": state_code, "limit": 100}, timeout=20)
    if err:
        st.error(err)
    df = df_from(tasks)
    if df.empty:
        st.info("No review tasks for this scope.")
    else:
        cols = ["id", "state_code", "title", "evidence_tier", "confidence_score", "decision_recommendation", "status", "created_at", "source_url"]
        st.dataframe(df[[c for c in cols if c in df.columns]], use_container_width=True, height=360)

    st.markdown("### Telegram Control")
    with st.form("telegram_digest_form"):
        dry_run = st.checkbox("Dry run", True)
        min_tier = st.selectbox("Minimum tier", ["OFFICIAL_CONFIRMED", "GOVT_PROBABLE", "REPORTED_NOT_CONFIRMED"])
        submitted = st.form_submit_button("Send digest")
        if submitted:
            payload = {"state_code": state_code, "days": 7, "limit": 25, "dry_run": dry_run, "include_chatter": False, "min_tier": min_tier}
            result, err = request_json("POST", "/api/telegram/digest", json=payload, timeout=120)
            st.error(err) if err else st.json({k: v for k, v in result.items() if k != "chunks"})


def render_plans() -> None:
    st.markdown("### Subscription Plans")
    st.caption("Commercial packaging for distributors, advisory firms, state corporations and government departments.")
    plans = [
        {
            "name": "Pilot",
            "price": "INR 25k/mo",
            "buyer": "Single-state compliance team",
            "items": ["1 state/UT", "Daily news and official-source monitoring", "Telegram alerts", "Conclusive answer desk"],
        },
        {
            "name": "Professional",
            "price": "INR 75k/mo",
            "buyer": "Multi-state distributor",
            "items": ["Up to 8 states", "Review workflow", "Evidence ledger exports", "Priority source validation"],
        },
        {
            "name": "Enterprise",
            "price": "Custom",
            "buyer": "National alco-bev company",
            "items": ["All India coverage", "SSO and RBAC", "PostgreSQL deployment", "SLA and dedicated onboarding"],
        },
        {
            "name": "Government",
            "price": "Procurement",
            "buyer": "Excise department / corporation",
            "items": ["Official circular monitoring", "Officer workstream intelligence", "Audit logs", "On-prem or sovereign cloud"],
        },
    ]
    cols = st.columns(4)
    for col, plan in zip(cols, plans):
        html = [f'<div class="ew-plan"><strong>{plan["name"]}</strong>', f'<div class="ew-price">{plan["price"]}</div>', f'<div class="ew-subtle">{plan["buyer"]}</div>', "<hr>"]
        html.extend(f"<div>• {item}</div>" for item in plan["items"])
        html.append("</div>")
        col.markdown("\n".join(html), unsafe_allow_html=True)

    st.markdown("### Security and Procurement Readiness")
    c1, c2, c3 = st.columns(3)
    c1.markdown("**Evidence Governance**  \nOfficial, reported, chatter and insufficient evidence are separated before guidance.")
    c2.markdown("**Audit Trail**  \nReview decisions, approvals and publication events are recorded for internal audit.")
    c3.markdown("**Deployment Choices**  \nLocal pilot, private cloud, on-premise or government-controlled infrastructure.")


def render_onboarding() -> None:
    st.markdown("### Request Enterprise Onboarding")
    st.caption("Store prospects locally for follow-up. Production should connect this form to CRM and billing.")
    with st.form("lead_form"):
        c1, c2 = st.columns(2)
        organisation = c1.text_input("Organisation")
        contact = c2.text_input("Contact name")
        email = c1.text_input("Work email")
        phone = c2.text_input("Phone")
        segment = c1.selectbox("Segment", ["Distributor", "Manufacturer", "Retail chain", "Advisory / legal", "Government", "Other"])
        plan = c2.selectbox("Interested plan", ["Pilot", "Professional", "Enterprise", "Government"])
        states = st.text_input("States / UTs needed", "KA, KL, DL, MH")
        note = st.text_area("Use case", "Daily excise intelligence, licence-fee tracking, official notifications, Telegram alerts and review workflow.")
        submitted = st.form_submit_button("Save onboarding request")
        if submitted:
            row = {
                "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                "organisation": organisation,
                "contact": contact,
                "email": email,
                "phone": phone,
                "segment": segment,
                "plan": plan,
                "states": states,
                "note": note,
            }
            save_lead(row)
            st.success("Onboarding request saved locally.")

    if LEADS_FILE.exists():
        st.markdown("### Local Pipeline")
        st.dataframe(pd.read_csv(LEADS_FILE), use_container_width=True, height=260)


def render_admin(state_code: str | None) -> None:
    st.markdown("### Platform Administration")
    c1, c2, c3 = st.columns(3)
    if c1.button("Seed source registry", use_container_width=True):
        result, err = request_json("POST", "/api/admin/seed-sources", timeout=30)
        st.error(err) if err else st.json(result)
    if c2.button("Check readiness", use_container_width=True):
        result, err = request_json("GET", "/api/v6/readiness", timeout=20)
        st.error(err) if err else st.json(result)
    if c3.button("Validate sources dry run", use_container_width=True):
        result, err = request_json("POST", "/api/sources/validate-live", json={"state_code": state_code, "live_fetch": False, "archive_documents": True}, timeout=60)
        st.error(err) if err else st.json(result)

    st.markdown("### Source Registry")
    sources, err = request_json("GET", "/api/sources", params={"state_code": state_code}, timeout=20)
    if err:
        st.error(err)
    df = df_from(sources)
    if not df.empty:
        st.dataframe(df, use_container_width=True, height=340)

    with st.expander("Add source"):
        with st.form("source_form"):
            name = st.text_input("Source name")
            url = st.text_input("URL")
            source_type = st.selectbox("Source type", ["official", "gazette", "court", "regulator", "news", "industry", "social", "manual"])
            priority = st.number_input("Priority", min_value=1, max_value=100, value=50)
            notes = st.text_area("Notes")
            submitted = st.form_submit_button("Add source")
            if submitted:
                payload = {
                    "state_code": state_code or "DL",
                    "state_name": state_code or "Delhi",
                    "source_name": name,
                    "url": url,
                    "source_type": source_type,
                    "priority": priority,
                    "notes": notes,
                }
                result, err = request_json("POST", "/api/sources", json=payload, timeout=30)
                st.error(err) if err else st.json(result)


def main() -> None:
    css()
    ensure_internal_api()
    state_code, days = render_sidebar()
    render_header()

    tabs = st.tabs([
        "Command Center",
        "Intelligence Feed",
        "Conclusive AI",
        "Review & Publish",
        "Plans",
        "Onboarding",
        "Admin",
    ])
    with tabs[0]:
        render_overview(state_code, days)
    with tabs[1]:
        render_intelligence(state_code, days)
    with tabs[2]:
        render_conclusive(state_code, days)
    with tabs[3]:
        render_review_and_publish(state_code)
    with tabs[4]:
        render_plans()
    with tabs[5]:
        render_onboarding()
    with tabs[6]:
        render_admin(state_code)


if __name__ == "__main__":
    main()
