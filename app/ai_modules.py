from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean, pstdev
from typing import Any
import hashlib
import json
import math
import re

from sqlmodel import Session, select

from .relevance import relevance_score, normalize_category_hint

from .models import (
    AIModuleRun,
    EvidenceTier,
    LegalChange,
    OfficialMovement,
    OfficialProfile,
    RawItem,
    SourceType,
    WorkSignal,
)


TIER_SCORE = {
    EvidenceTier.official_confirmed: 1.0,
    EvidenceTier.govt_probable: 0.78,
    EvidenceTier.reported_not_confirmed: 0.58,
    EvidenceTier.chatter_unverified: 0.22,
    EvidenceTier.insufficient: 0.08,
}

MODULE_CATALOG: list[dict[str, Any]] = [
    {
        "id": "entity_extraction",
        "name": "Entity Extraction AI",
        "purpose": "Extracts states, dates, fees, order numbers, officials, roles, departments, permit/licence terms and policy keywords from official orders, news and forwards.",
        "output": "entities, confidence, human-review flag",
    },
    {
        "id": "update_classifier",
        "name": "Excise Update Classifier",
        "purpose": "Classifies updates into policy, licence, fee/duty, MRP/pricing, dry day, permit/transport, enforcement, tender, court and admin buckets.",
        "output": "change type, severity, affected functions",
    },
    {
        "id": "evidence_ranker",
        "name": "Evidence Ranker",
        "purpose": "Ranks sources from official confirmed to chatter unverified so conclusive answers are never based only on gossip.",
        "output": "evidence tier, confidence, definitive eligibility",
    },
    {
        "id": "rag_answer",
        "name": "RAG Answer Engine",
        "purpose": "Searches the local legal changes, officer movements and workstream database and gives source-backed answers.",
        "output": "answer, source ledger, definitive flag",
    },
    {
        "id": "conclusive_synthesis",
        "name": "Conclusive Synthesis AI",
        "purpose": "Combines official orders, news, chatter, officer signals and law changes into a final answer status: confirmed, reported only, chatter only, conflicting, or insufficient.",
        "output": "definitive conclusion, conflict count, source counts",
    },
    {
        "id": "chatter_credibility",
        "name": "Chatter Credibility AI",
        "purpose": "Scores WhatsApp/Telegram/market forwards and separates early trade signal from actionable compliance truth.",
        "output": "credibility score, red flags, verification checklist",
    },
    {
        "id": "conflict_detector",
        "name": "Conflict Detector AI",
        "purpose": "Finds contradictions between official, news and forward data such as licence fee increase vs no fee increase, or postponed vs effective.",
        "output": "conflicts, affected state, source mismatch",
    },
    {
        "id": "impact_analyzer",
        "name": "Business Impact AI",
        "purpose": "Converts a legal/policy update into business impact across compliance, inventory, pricing, permits, sales, finance and field operations.",
        "output": "impact matrix, priority, action owner",
    },
    {
        "id": "compliance_checklist",
        "name": "Compliance Checklist AI",
        "purpose": "Turns updates into executable SOP steps for legal, depot, sales, finance and leadership teams.",
        "output": "checklist, blocker items, deadlines",
    },
    {
        "id": "officer_workmap",
        "name": "Officer Workmap AI",
        "purpose": "Maps CM, excise minister, principal secretary, commissioner, MD and district officer signals to likely policy workstreams.",
        "output": "role-to-workstream map, verified vs chatter labels",
    },
    {
        "id": "telegram_digest_ai",
        "name": "Telegram Digest AI",
        "purpose": "Formats all-India or state-wise alerts into Telegram-safe summaries with evidence labels and conclusive status.",
        "output": "Telegram-ready digest",
    },
    {
        "id": "demand_forecast",
        "name": "Demand Forecast AI",
        "purpose": "Uses historical volume to forecast next-period demand and trend risk for planning inventory after policy or seasonality changes.",
        "output": "forecast, trend, confidence, reorder signal",
    },
    {
        "id": "retailer_risk",
        "name": "Retailer / Dispatch Risk AI",
        "purpose": "Scores retailer, permit, licence, payment and dispatch risk before stock movement.",
        "output": "risk score, risk tier, mitigation steps",
    },
    {
        "id": "fraud_anomaly",
        "name": "Fraud & Diversion Anomaly AI",
        "purpose": "Detects unusual quantity spikes, duplicate invoices, route mismatch, repeated breakage and suspicious retailer/depot patterns.",
        "output": "anomalies, severity, investigation queue",
    },
]

STATE_NAMES = {
    "AP": "Andhra Pradesh", "AR": "Arunachal Pradesh", "AS": "Assam", "BR": "Bihar", "CG": "Chhattisgarh",
    "GA": "Goa", "GJ": "Gujarat", "HR": "Haryana", "HP": "Himachal Pradesh", "JH": "Jharkhand",
    "KA": "Karnataka", "KL": "Kerala", "MP": "Madhya Pradesh", "MH": "Maharashtra", "MN": "Manipur",
    "ML": "Meghalaya", "MZ": "Mizoram", "NL": "Nagaland", "OD": "Odisha", "PB": "Punjab",
    "RJ": "Rajasthan", "SK": "Sikkim", "TN": "Tamil Nadu", "TS": "Telangana", "TR": "Tripura",
    "UP": "Uttar Pradesh", "UK": "Uttarakhand", "WB": "West Bengal", "AN": "Andaman and Nicobar Islands",
    "CH": "Chandigarh", "DNHDD": "Dadra and Nagar Haveli and Daman and Diu", "DL": "Delhi", "JK": "Jammu and Kashmir",
    "LA": "Ladakh", "LD": "Lakshadweep", "PY": "Puducherry",
}

CHANGE_KEYWORDS = {
    "policy": ["policy", "abkari policy", "liquor policy", "excise policy", "licensing year"],
    "license": ["licence", "license", "renewal", "l-1", "fl", "bar licence", "retail vend", "shop"],
    "fee_duty": ["fee", "fees", "duty", "excise duty", "levy", "tax", "cess", "assessment fee"],
    "mrp_price": ["mrp", "price", "pricing", "margin", "wholesale price", "retail price", "landing price"],
    "dry_day": ["dry day", "closure of shops", "prohibition day", "no liquor sale"],
    "permit_transport": ["permit", "transport", "import", "export", "challan", "pass", "transit", "movement"],
    "enforcement": ["raid", "seizure", "inspection", "crackdown", "penalty", "suspended", "illicit"],
    "digital": ["track and trace", "barcode", "qr", "portal", "online", "e-governance", "digital", "e-abkari"],
    "tender": ["tender", "rfp", "eoi", "bid", "procurement", "vendor"],
    "court": ["court", "writ", "judgment", "order of the court", "high court", "supreme court"],
    "admin": ["transfer", "posting", "appointment", "portfolio", "additional charge", "minutes", "cabinet"],
}

BUSINESS_FUNCTION_KEYWORDS = {
    "Compliance / legal": ["policy", "rule", "notification", "gazette", "court", "licence", "license", "minutes"],
    "Pricing / finance": ["mrp", "price", "duty", "fee", "levy", "tax", "margin", "revenue"],
    "Depot / inventory": ["stock", "warehouse", "depot", "bonded", "inventory", "label", "batch"],
    "Permit / logistics": ["permit", "transport", "challan", "vehicle", "route", "import", "export", "movement"],
    "Sales / retailer": ["retailer", "shop", "vend", "bar", "restaurant", "hotel", "scheme", "renewal"],
    "Enforcement / audit": ["raid", "inspection", "seizure", "penalty", "suspension", "illicit", "audit"],
    "Leadership watch": ["chief minister", "minister", "cabinet", "secretary", "commissioner", "md", "principal secretary"],
}

ROLE_PATTERNS = {
    "chief_minister": ["chief minister", "cm", "cmo"],
    "excise_minister": ["excise minister", "minister for excise", "minister of excise", "abkari minister", "prohibition minister"],
    "principal_secretary": ["principal secretary", "acs", "additional chief secretary", "secretary excise", "secretary, excise"],
    "excise_commissioner": ["excise commissioner", "commissioner excise", "commissioner of excise", "prohibition commissioner"],
    "managing_director": ["managing director", "cmd", "chairman", "beverages corporation", "beverage corporation", "tasmac"],
    "district_officer": ["district excise officer", "deputy commissioner", "assistant excise commissioner", "collector excise", "superintendent excise"],
}

DATE_RE = re.compile(r"\b(\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{4})\b", re.I)
MONEY_RE = re.compile(r"(?:₹|Rs\.?|INR)\s?([0-9][0-9,]*(?:\.\d+)?)\s?(crore|cr|lakh|lac|k|thousand|million)?", re.I)
ORDER_RE = re.compile(r"\b(?:order|notification|circular|g\.o\.|go|memo|minutes|proceedings)\s*(?:no\.?|number)?\s*[:\-]?\s*([A-Z0-9/._\-]{3,})", re.I)
NAME_RE = re.compile(r"\b(?:Shri|Sri|Smt|Ms|Mrs|Mr|Dr)\.?\s+([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){0,4})(?:,?\s*(IAS|IPS|IRS|DANICS|PCS|HCS|KAS|RAS|WBCS|MCS|GCS|SCS))?", re.I)
URL_RE = re.compile(r'https?://[^\s)>"]+', re.I)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def clean_text(text: str | None, limit: int | None = None) -> str:
    val = " ".join(str(text or "").replace("\n", " ").split())
    if limit and len(val) > limit:
        return val[: limit - 3].rstrip() + "..."
    return val


def _tokens(text: str) -> list[str]:
    return [t for t in re.sub(r"[^a-z0-9]+", " ", text.lower()).split() if len(t) > 2]


def _tier_from_source(source_type: str | SourceType | None, url: str | None = None, text: str | None = None) -> EvidenceTier:
    st = str(source_type.value if isinstance(source_type, SourceType) else (source_type or "")).lower()
    hay = f"{url or ''} {text or ''}".lower()
    if st in {"official", "gazette", "court", "regulator"}:
        return EvidenceTier.official_confirmed
    if "gov.in" in hay or "nic.in" in hay or "gov" in st:
        return EvidenceTier.govt_probable
    if st == "news":
        return EvidenceTier.reported_not_confirmed
    if st in {"social", "manual"} or any(x in hay for x in ["whatsapp", "telegram", "forward", "market chatter"]):
        return EvidenceTier.chatter_unverified
    return EvidenceTier.insufficient


def _module_log(session: Session | None, module_name: str, result: dict[str, Any], state_code: str | None = None, question: str | None = None, input_text: str = "") -> None:
    if not session:
        return
    try:
        run = AIModuleRun(
            module_name=module_name,
            state_code=state_code.upper() if state_code else None,
            question=question,
            input_hash=sha256(input_text or json.dumps(result, sort_keys=True, default=str)),
            result_json=json.dumps(result, ensure_ascii=False, default=str),
            summary=clean_text(result.get("summary") or result.get("answer") or result.get("conclusion"), 500),
            evidence_tier=EvidenceTier(result.get("evidence_tier", EvidenceTier.insufficient.value)) if isinstance(result.get("evidence_tier"), str) else result.get("evidence_tier", EvidenceTier.insufficient),
            confidence_score=float(result.get("confidence", result.get("confidence_score", 0.0)) or 0.0),
            definitive=bool(result.get("definitive", False)),
        )
        session.add(run)
        session.commit()
    except Exception:
        session.rollback()


def module_catalog() -> dict[str, Any]:
    return {"count": len(MODULE_CATALOG), "modules": MODULE_CATALOG}


def extract_entities(text: str, title: str | None = None, state_code: str | None = None, state_name: str | None = None, source_type: str | SourceType | None = None, source_url: str | None = None, session: Session | None = None) -> dict[str, Any]:
    full = f"{title or ''}\n{text or ''}"
    hay = full.lower()
    states = []
    if state_code:
        states.append({"state_code": state_code.upper(), "state_name": state_name or STATE_NAMES.get(state_code.upper())})
    for code, name in STATE_NAMES.items():
        if name.lower() in hay and code not in {s.get("state_code") for s in states}:
            states.append({"state_code": code, "state_name": name})

    officials = []
    seen_names = set()
    for m in NAME_RE.finditer(full):
        name = clean_text(m.group(1), 120)
        if name.lower() in seen_names:
            continue
        seen_names.add(name.lower())
        window = full[max(0, m.start() - 120): m.end() + 160]
        role = "unknown"
        for role_id, patterns in ROLE_PATTERNS.items():
            if any(p in window.lower() for p in patterns):
                role = role_id
                break
        officials.append({"name": name, "cadre": (m.group(2) or "").upper() or None, "role_hint": role, "context": clean_text(window, 260)})

    roles = [role_id for role_id, patterns in ROLE_PATTERNS.items() if any(p in hay for p in patterns)]
    dates = sorted(set(m.group(1) for m in DATE_RE.finditer(full)))
    money = [{"amount": m.group(1), "unit": m.group(2)} for m in MONEY_RE.finditer(full)]
    orders = sorted(set(m.group(1).strip(".-") for m in ORDER_RE.finditer(full)))
    urls = sorted(set(URL_RE.findall(full)))
    update_types = classify_update(full)["matched_categories"]
    evidence = _tier_from_source(source_type, source_url, full)

    result = {
        "states": states,
        "officials": officials,
        "roles": sorted(set(roles)),
        "dates": dates,
        "money_amounts": money,
        "order_numbers": orders,
        "urls": urls,
        "update_categories": update_types,
        "evidence_tier": evidence.value,
        "confidence": round(min(0.95, 0.25 + 0.08 * len(update_types) + 0.06 * len(dates) + 0.08 * len(orders) + TIER_SCORE[evidence] * 0.4), 2),
        "needs_human_review": evidence != EvidenceTier.official_confirmed or not orders,
        "summary": f"Extracted {len(update_types)} category signal(s), {len(officials)} official/person mention(s), {len(dates)} date(s), and {len(orders)} order/reference number(s).",
    }
    _module_log(session, "entity_extraction", result, state_code, None, full)
    return result


def classify_update(text: str) -> dict[str, Any]:
    hay = text.lower()
    matched = []
    scores = {}
    for category, words in CHANGE_KEYWORDS.items():
        score = sum(1 for w in words if w in hay)
        if score:
            matched.append(category)
            scores[category] = score
    primary = max(scores, key=scores.get) if scores else "unknown"
    severity = "low"
    if primary in {"fee_duty", "mrp_price", "license", "policy", "permit_transport"}:
        severity = "high"
    if any(w in hay for w in ["immediate", "with immediate effect", "suspended", "cancelled", "penalty", "increase", "hike", "cabinet approved"]):
        severity = "critical"
    affected = affected_business_functions(text)
    return {
        "primary_category": primary,
        "matched_categories": matched,
        "category_scores": scores,
        "severity": severity,
        "affected_functions": affected,
    }


def summarize_text(text: str, title: str | None = None, max_points: int = 5, session: Session | None = None, state_code: str | None = None) -> dict[str, Any]:
    full = clean_text(f"{title or ''}. {text or ''}")
    sentences = re.split(r"(?<=[.!?])\s+", full)
    keyword_tokens = set()
    for words in CHANGE_KEYWORDS.values():
        for phrase in words:
            keyword_tokens.update(_tokens(phrase))
    scored = []
    for sent in sentences:
        toks = _tokens(sent)
        if not toks:
            continue
        score = sum(2 for t in toks if t in keyword_tokens) + min(len(toks), 35) / 35
        scored.append((score, sent))
    top = [clean_text(s, 260) for _, s in sorted(scored, key=lambda x: x[0], reverse=True)[:max_points]]
    if not top and full:
        top = [clean_text(full, 500)]
    classification = classify_update(full)
    result = {
        "summary": " ".join(top[:2]) if top else "No meaningful text supplied.",
        "key_points": top,
        "classification": classification,
        "confidence": 0.72 if top else 0.1,
        "evidence_tier": EvidenceTier.insufficient.value,
    }
    _module_log(session, "summarizer", result, state_code, None, full)
    return result


def affected_business_functions(text: str) -> list[dict[str, Any]]:
    hay = text.lower()
    rows = []
    for function, words in BUSINESS_FUNCTION_KEYWORDS.items():
        hits = [w for w in words if w in hay]
        if hits:
            rows.append({"function": function, "matched_terms": hits, "impact_level": "high" if len(hits) >= 2 else "medium"})
    if not rows:
        rows.append({"function": "Compliance / legal", "matched_terms": [], "impact_level": "review"})
    return rows


def analyze_impact(text: str, title: str | None = None, state_code: str | None = None, evidence_tier: str | EvidenceTier | None = None, session: Session | None = None) -> dict[str, Any]:
    full = f"{title or ''}\n{text or ''}"
    classification = classify_update(full)
    tier = EvidenceTier(evidence_tier) if isinstance(evidence_tier, str) and evidence_tier in [e.value for e in EvidenceTier] else (evidence_tier if isinstance(evidence_tier, EvidenceTier) else EvidenceTier.insufficient)
    functions = classification["affected_functions"]
    priority = classification["severity"]
    if tier == EvidenceTier.official_confirmed and priority == "high":
        priority = "critical"
    owners = []
    for f in functions:
        fn = f["function"]
        if "Pricing" in fn:
            owner = "Finance + pricing team"
        elif "Depot" in fn:
            owner = "Depot / warehouse head"
        elif "Permit" in fn:
            owner = "Logistics + excise desk"
        elif "Sales" in fn:
            owner = "Sales head + retailer operations"
        elif "Leadership" in fn:
            owner = "Founder/management office"
        elif "Enforcement" in fn:
            owner = "Audit + compliance"
        else:
            owner = "Legal + compliance"
        owners.append({**f, "suggested_owner": owner})
    result = {
        "state_code": state_code.upper() if state_code else None,
        "primary_category": classification["primary_category"],
        "severity": classification["severity"],
        "priority": priority,
        "impact_matrix": owners,
        "immediate_action": _immediate_action(classification["primary_category"], tier),
        "evidence_tier": tier.value,
        "confidence": round(0.45 + TIER_SCORE[tier] * 0.35 + min(len(owners), 5) * 0.04, 2),
        "summary": f"{classification['primary_category']} update with {priority} priority affecting {', '.join(o['function'] for o in owners[:4])}.",
    }
    _module_log(session, "impact_analyzer", result, state_code, None, full)
    return result


def _immediate_action(primary: str, tier: EvidenceTier) -> str:
    prefix = "Act now" if tier == EvidenceTier.official_confirmed else "Verify before acting"
    actions = {
        "fee_duty": "freeze pricing changes until finance validates duty/fee impact and MRP master is updated.",
        "mrp_price": "validate approved MRP/landing price before invoices are generated.",
        "license": "check affected licence categories, renewal dates and retailer eligibility before dispatch.",
        "permit_transport": "block risky movement until permit validity, route and quantity are verified.",
        "dry_day": "update dispatch calendar and alert sales/depot teams.",
        "enforcement": "notify audit team and preserve source evidence.",
        "digital": "assign IT/excise desk to check portal/track-and-trace requirements.",
        "admin": "update officer/minister watchlist and map likely policy workstreams.",
        "policy": "open policy-impact review with legal, pricing, depot and sales owners.",
    }
    return f"{prefix}: {actions.get(primary, 'send to compliance desk for review.')}"


def score_chatter(text: str, title: str | None = None, source_name: str | None = None, source_url: str | None = None, session: Session | None = None, state_code: str | None = None) -> dict[str, Any]:
    full = f"{title or ''}\n{text or ''}\n{source_name or ''}\n{source_url or ''}"
    hay = full.lower()
    score = 35
    positives = []
    negatives = []
    for term, pts in [("order no", 8), ("notification", 8), ("circular", 8), ("gov.in", 14), ("nic.in", 14), ("dated", 5), ("signed", 5), ("cabinet", 4), ("minutes", 4), ("attached", 3)]:
        if term in hay:
            score += pts
            positives.append(term)
    for term, pts in [("forwarded", -8), ("whatsapp", -10), ("telegram", -8), ("not verified", -15), ("rumour", -18), ("market says", -8), ("heard", -6), ("expected", -4), ("may", -3)]:
        if term in hay:
            score += pts
            negatives.append(term)
    if URL_RE.search(full):
        score += 6
        positives.append("url_present")
    if ORDER_RE.search(full):
        score += 8
        positives.append("order_reference_present")
    score = max(0, min(100, score))
    if score >= 75:
        label = "strong_signal_needs_official_copy"
    elif score >= 50:
        label = "medium_signal_verify"
    elif score >= 25:
        label = "weak_chatter"
    else:
        label = "very_weak_chatter"
    result = {
        "credibility_score": score,
        "label": label,
        "evidence_tier": EvidenceTier.chatter_unverified.value,
        "definitive": False,
        "confidence": round(score / 100, 2),
        "positive_indicators": positives,
        "negative_indicators": negatives,
        "verification_checklist": [
            "Find matching official excise department order/gazette/circular.",
            "Verify order number, date, signatory and department URL.",
            "Check whether the item changes law/policy or is only market expectation.",
            "Do not update dispatch, pricing or licence workflow until official evidence exists.",
        ],
        "summary": f"Forward credibility is {score}/100 and cannot be treated as conclusive law.",
    }
    _module_log(session, "chatter_credibility", result, state_code, None, full)
    return result


def _search_rows(session: Session, question: str, state_code: str | None, days: int, limit: int = 80) -> list[dict[str, Any]]:
    """Search rows with a semantic relevance gate.

    v6.0 bug fixed here: official evidence no longer receives a free pass.
    A row must match the user's subject/category/intent before it can contribute
    to RAG or a conclusive answer.
    """
    since = datetime.utcnow() - timedelta(days=days)
    code = state_code.upper() if state_code else None
    rows: list[dict[str, Any]] = []

    def add_row(base: dict[str, Any], text: str, category_hint: str | None = None) -> None:
        rel = relevance_score(question, text, category_hint=category_hint)
        if not rel.passed:
            return
        tier = base["tier"]
        # Relevance dominates; evidence tier is only a secondary sort signal.
        base["relevance_score"] = round(rel.score, 4)
        base["relevance_reason"] = rel.reason
        base["matched_tokens"] = rel.token_hits
        base["matched_categories"] = sorted(rel.question_categories & rel.text_categories)
        base["score"] = rel.score * 10 + TIER_SCORE[tier] * 1.25
        rows.append(base)

    stmt = select(LegalChange).where(LegalChange.detected_at >= since)
    if code:
        stmt = stmt.where(LegalChange.state_code == code)
    for r in session.exec(stmt.order_by(LegalChange.detected_at.desc()).limit(limit)).all():
        text = f"{r.title} {r.summary} {r.legal_effect or ''} {r.change_type.value}"
        add_row({
            "kind": "legal_change", "tier": r.evidence_tier, "title": r.title, "summary": r.summary,
            "effect": r.legal_effect, "state_code": r.state_code, "state_name": r.state_name,
            "source_url": r.source_url, "detected_at": r.detected_at.isoformat(), "raw": r,
        }, text, category_hint=normalize_category_hint(r.change_type))

    stmt = select(OfficialMovement).where(OfficialMovement.detected_at >= since)
    if code:
        stmt = stmt.where(OfficialMovement.state_code == code)
    for r in session.exec(stmt.order_by(OfficialMovement.detected_at.desc()).limit(limit)).all():
        text = f"{r.person_name} {r.summary} {r.to_designation or ''} {r.from_designation or ''} {r.movement_type.value} {r.department or ''}"
        add_row({
            "kind": "official_movement", "tier": r.evidence_tier, "title": f"{r.person_name}: {r.movement_type.value}",
            "summary": r.summary, "effect": r.to_designation, "state_code": r.state_code, "state_name": r.state_name,
            "source_url": r.source_url, "detected_at": r.detected_at.isoformat(), "raw": r,
        }, text, category_hint="admin")

    stmt = select(WorkSignal).where(WorkSignal.detected_at >= since)
    if code:
        stmt = stmt.where(WorkSignal.state_code == code)
    for r in session.exec(stmt.order_by(WorkSignal.detected_at.desc()).limit(limit)).all():
        text = f"{r.title} {r.summary} {r.likely_workstream or ''} {r.signal_type.value} {r.designation or ''} {r.person_name or ''}"
        add_row({
            "kind": "work_signal", "tier": r.evidence_tier, "title": r.title, "summary": r.summary,
            "effect": r.likely_workstream, "state_code": r.state_code, "state_name": r.state_name,
            "source_url": r.source_url, "detected_at": r.detected_at.isoformat(), "raw": r,
        }, text, category_hint="admin")

    rows.sort(key=lambda x: (x["score"], TIER_SCORE[x["tier"]], x["detected_at"]), reverse=True)
    return rows[:limit]

def rag_answer(session: Session, question: str, state_code: str | None = None, days: int = 365, include_chatter: bool = False) -> dict[str, Any]:
    rows = _search_rows(session, question, state_code, days, limit=80)
    if not include_chatter:
        rows = [r for r in rows if r["tier"] != EvidenceTier.chatter_unverified]
    top = rows[:10]
    if not top:
        result = {
            "answer": "No matching evidence found in the local database. Run the watcher, ingest official orders, or add forward data first.",
            "definitive": False,
            "answer_status": "INSUFFICIENT",
            "evidence_tier": EvidenceTier.insufficient.value,
            "sources": [],
            "confidence": 0.05,
        }
        _module_log(session, "rag_answer", result, state_code, question, question)
        return result
    strongest = max(top, key=lambda r: (TIER_SCORE[r["tier"]], r["score"]))
    definitive = strongest["tier"] == EvidenceTier.official_confirmed
    source_lines = [f"- {r['kind']}: {r['title']} [{r['tier'].value}]" for r in top[:5]]
    if definitive:
        answer = f"Definite answer based on official-confirmed evidence: {strongest['title']}. {clean_text(strongest.get('effect') or strongest.get('summary'), 500)}"
        status = "CONFIRMED"
    else:
        answer = f"Not conclusive yet. Strongest available evidence is {strongest['tier'].value}: {strongest['title']}. Verify official order/gazette before acting."
        status = "REPORTED_ONLY" if strongest["tier"] == EvidenceTier.reported_not_confirmed else "OFFICIAL_BUT_INCOMPLETE" if strongest["tier"] == EvidenceTier.govt_probable else "CHATTER_ONLY"
    result = {
        "answer": answer,
        "answer_status": status,
        "definitive": definitive,
        "evidence_tier": strongest["tier"].value,
        "confidence": round(min(0.96, TIER_SCORE[strongest["tier"]] * 0.75 + min(strongest["score"], 8) * 0.03), 2),
        "source_ledger": source_lines,
        "sources": [{k: v for k, v in r.items() if k != "raw" and k != "score" and k != "tier"} | {"evidence_tier": r["tier"].value, "score": round(r["score"], 2)} for r in top[:10]],
        "summary": answer,
    }
    _module_log(session, "rag_answer", result, state_code, question, question)
    return result


def conclusive_synthesis(session: Session, question: str, state_code: str | None = None, days: int = 365, include_chatter: bool = True) -> dict[str, Any]:
    rows = _search_rows(session, question, state_code, days, limit=120)
    if not include_chatter:
        rows = [r for r in rows if r["tier"] != EvidenceTier.chatter_unverified]
    counts = Counter(r["tier"] for r in rows)
    conflicts = detect_conflicts(session, state_code=state_code, days=days, question=question)["conflicts"]
    strongest = max(rows, key=lambda r: (TIER_SCORE[r["tier"]], r["score"]), default=None)
    if not strongest:
        status = "INSUFFICIENT"
        conclusion = "No evidence found in the local ExciseWatch database."
        definitive = False
        tier = EvidenceTier.insufficient
    elif conflicts and counts[EvidenceTier.official_confirmed] == 0:
        status = "CONFLICTING_EVIDENCE"
        conclusion = "Conflicting non-official evidence exists. Do not treat this as conclusive until an official order/gazette/circular is found."
        definitive = False
        tier = strongest["tier"]
    elif counts[EvidenceTier.official_confirmed] > 0:
        official_rows = [r for r in rows if r["tier"] == EvidenceTier.official_confirmed]
        official_best = max(official_rows, key=lambda r: (r.get("relevance_score", 0), r["score"]), default=strongest)
        status = "CONFIRMED"
        conclusion = f"Confirmed by relevant official evidence: {official_best['title']}. {clean_text(official_best.get('effect') or official_best.get('summary'), 450)}"
        definitive = True
        tier = EvidenceTier.official_confirmed
    elif counts[EvidenceTier.govt_probable] > 0:
        status = "OFFICIAL_BUT_INCOMPLETE"
        conclusion = f"Government-adjacent evidence found, but not enough for final compliance action: {strongest['title']}."
        definitive = False
        tier = strongest["tier"]
    elif counts[EvidenceTier.reported_not_confirmed] > 0:
        status = "REPORTED_ONLY"
        conclusion = f"Only news/reported evidence found: {strongest['title']}."
        definitive = False
        tier = strongest["tier"]
    else:
        status = "CHATTER_ONLY"
        conclusion = "Only forward/market chatter found. This is not conclusive and cannot be acted on as law."
        definitive = False
        tier = EvidenceTier.chatter_unverified

    result = {
        "answer_status": status,
        "definitive": definitive,
        "conclusion": conclusion,
        "evidence_tier": tier.value,
        "official_source_count": counts[EvidenceTier.official_confirmed],
        "govt_probable_count": counts[EvidenceTier.govt_probable],
        "news_source_count": counts[EvidenceTier.reported_not_confirmed],
        "chatter_source_count": counts[EvidenceTier.chatter_unverified],
        "conflict_count": len(conflicts),
        "conflicts": conflicts[:8],
        "top_sources": [{"kind": r["kind"], "title": r["title"], "state": r["state_name"], "tier": r["tier"].value, "url": r["source_url"], "detected_at": r["detected_at"], "relevance_score": r.get("relevance_score"), "relevance_reason": r.get("relevance_reason"), "matched_categories": r.get("matched_categories", [])} for r in rows[:10]],
        "confidence": round(TIER_SCORE[tier], 2),
        "summary": conclusion,
    }
    _module_log(session, "conclusive_synthesis", result, state_code, question, question)
    return result


def detect_conflicts(session: Session, state_code: str | None = None, days: int = 365, question: str | None = None) -> dict[str, Any]:
    rows = _search_rows(session, question or "fee duty price license permit dry day policy", state_code, days, limit=200)
    opposites = [
        (("increase", "hike", "raised", "enhanced"), ("decrease", "reduced", "lowered", "cut")),
        (("allowed", "permitted", "approved", "renewed"), ("banned", "prohibited", "cancelled", "suspended")),
        (("effective", "implemented", "enforced"), ("postponed", "deferred", "stayed", "withdrawn")),
    ]
    by_state_cat: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        cat = classify_update(f"{r['title']} {r.get('summary','')} {r.get('effect','')}")["primary_category"]
        by_state_cat[(r["state_code"], cat)].append(r)
    conflicts = []
    for (code, cat), items in by_state_cat.items():
        texts = [(i, f"{i['title']} {i.get('summary','')} {i.get('effect','') or ''}".lower()) for i in items]
        for pos, neg in opposites:
            pos_items = [i for i, t in texts if any(w in t for w in pos)]
            neg_items = [i for i, t in texts if any(w in t for w in neg)]
            if pos_items and neg_items:
                conflicts.append({
                    "state_code": code,
                    "category": cat,
                    "positive_signal": clean_text(pos_items[0]["title"], 220),
                    "negative_signal": clean_text(neg_items[0]["title"], 220),
                    "positive_tier": pos_items[0]["tier"].value,
                    "negative_tier": neg_items[0]["tier"].value,
                    "recommended_action": "Do not act until official source resolves the contradiction." if pos_items[0]["tier"] != EvidenceTier.official_confirmed and neg_items[0]["tier"] != EvidenceTier.official_confirmed else "Prefer official-confirmed source; archive conflicting lower-tier evidence.",
                })
    result = {"conflict_count": len(conflicts), "conflicts": conflicts, "summary": f"Detected {len(conflicts)} potential conflict(s).", "evidence_tier": EvidenceTier.insufficient.value, "confidence": 0.7 if conflicts else 0.4}
    _module_log(session, "conflict_detector", result, state_code, question, question or "")
    return result


def build_compliance_checklist(text: str, title: str | None = None, state_code: str | None = None, evidence_tier: str | EvidenceTier | None = None, session: Session | None = None) -> dict[str, Any]:
    full = f"{title or ''}\n{text or ''}"
    impact = analyze_impact(full, state_code=state_code, evidence_tier=evidence_tier, session=None)
    primary = impact["primary_category"]
    base = [
        {"owner": "Compliance desk", "task": "Save source PDF/order/news/forward and label evidence tier.", "blocker": False},
        {"owner": "Compliance desk", "task": "Check whether the update is effective immediately or from a future date.", "blocker": True},
        {"owner": "Management", "task": "Approve action only if evidence is official-confirmed or reviewed by counsel/compliance head.", "blocker": True},
    ]
    extra = {
        "fee_duty": [
            {"owner": "Finance", "task": "Recalculate duty, landing price, margins and cash-flow impact.", "blocker": True},
            {"owner": "Pricing team", "task": "Update MRP/pricing master after official confirmation.", "blocker": True},
        ],
        "mrp_price": [
            {"owner": "Sales ops", "task": "Pause invoices for affected SKUs until price master is validated.", "blocker": True},
        ],
        "license": [
            {"owner": "Licence desk", "task": "Identify impacted licence categories, renewal dates and documents.", "blocker": True},
            {"owner": "Sales head", "task": "Alert retailers whose licence category or renewal status may be affected.", "blocker": False},
        ],
        "permit_transport": [
            {"owner": "Logistics", "task": "Validate permit route, validity, quantity balance and challan workflow before dispatch.", "blocker": True},
        ],
        "dry_day": [
            {"owner": "Depot", "task": "Block dispatch/retail movement on restricted dates and notify field team.", "blocker": True},
        ],
        "enforcement": [
            {"owner": "Audit", "task": "Review affected districts, retailers, vehicles and past dispatches for exposure.", "blocker": False},
        ],
        "digital": [
            {"owner": "IT + excise desk", "task": "Check portal, QR, barcode or track-and-trace onboarding requirement.", "blocker": False},
        ],
        "admin": [
            {"owner": "Leadership watch", "task": "Map officer/minister movement to policy workstream and monitor official follow-up.", "blocker": False},
        ],
    }.get(primary, [])
    checklist = base + extra
    result = {
        "state_code": state_code.upper() if state_code else None,
        "primary_category": primary,
        "priority": impact["priority"],
        "checklist": checklist,
        "blocker_count": sum(1 for i in checklist if i["blocker"]),
        "evidence_tier": impact["evidence_tier"],
        "confidence": impact["confidence"],
        "summary": f"Generated {len(checklist)} SOP task(s), including {sum(1 for i in checklist if i['blocker'])} blocker(s).",
    }
    _module_log(session, "compliance_checklist", result, state_code, None, full)
    return result


def officer_workmap(session: Session, state_code: str | None = None, days: int = 365) -> dict[str, Any]:
    since = datetime.utcnow() - timedelta(days=days)
    code = state_code.upper() if state_code else None
    stmt = select(WorkSignal).where(WorkSignal.detected_at >= since)
    if code:
        stmt = stmt.where(WorkSignal.state_code == code)
    signals = list(session.exec(stmt.order_by(WorkSignal.detected_at.desc()).limit(300)).all())
    role_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for s in signals:
        role = "unknown"
        hay = f"{s.designation or ''} {s.person_name or ''} {s.title} {s.summary}".lower()
        for role_id, pats in ROLE_PATTERNS.items():
            if any(p in hay for p in pats):
                role = role_id
                break
        role_map[role].append({
            "state_code": s.state_code,
            "state_name": s.state_name,
            "person_name": s.person_name,
            "designation": s.designation,
            "signal_type": s.signal_type.value,
            "title": s.title,
            "workstream": s.likely_workstream,
            "tier": s.evidence_tier.value,
            "source_url": s.source_url,
            "detected_at": s.detected_at.isoformat(),
        })
    result = {
        "state_code": code,
        "roles_found": sorted(role_map.keys()),
        "workmap": {k: v[:10] for k, v in role_map.items()},
        "signal_count": len(signals),
        "evidence_tier": EvidenceTier.insufficient.value if not signals else max((s.evidence_tier for s in signals), key=lambda t: TIER_SCORE[t]).value,
        "confidence": round(min(0.9, 0.25 + len(signals) * 0.02), 2),
        "summary": f"Mapped {len(signals)} workstream signal(s) across {len(role_map)} role bucket(s).",
    }
    _module_log(session, "officer_workmap", result, state_code, None, state_code or "ALL")
    return result


def demand_forecast(series: list[dict[str, Any]], period_key: str = "period", value_key: str = "value", horizon: int = 1, session: Session | None = None, state_code: str | None = None) -> dict[str, Any]:
    points = []
    for row in series:
        try:
            points.append({"period": str(row.get(period_key, len(points) + 1)), "value": float(row.get(value_key, 0))})
        except Exception:
            continue
    if not points:
        return {"forecast": [], "trend": "insufficient_data", "confidence": 0.0, "evidence_tier": EvidenceTier.insufficient.value, "summary": "No numeric series supplied."}
    values = [p["value"] for p in points]
    last = values[-1]
    n = min(4, len(values))
    avg = mean(values[-n:])
    trend_delta = (values[-1] - values[0]) / max(1, len(values) - 1) if len(values) > 1 else 0
    forecast = []
    for i in range(1, horizon + 1):
        pred = max(0, avg + trend_delta * i)
        forecast.append({"period": f"next_{i}", "forecast_value": round(pred, 2)})
    trend = "rising" if trend_delta > max(1, abs(avg) * 0.03) else "falling" if trend_delta < -max(1, abs(avg) * 0.03) else "stable"
    volatility = (pstdev(values) / avg) if len(values) > 1 and avg else 0
    reorder_signal = "increase_stock" if trend == "rising" and last >= avg else "reduce_or_watch" if trend == "falling" else "normal"
    result = {
        "input_points": points,
        "forecast": forecast,
        "trend": trend,
        "trend_delta_per_period": round(trend_delta, 2),
        "volatility": round(volatility, 3),
        "reorder_signal": reorder_signal,
        "confidence": round(max(0.25, min(0.85, 0.75 - volatility * 0.5 + min(len(points), 12) * 0.01)), 2),
        "evidence_tier": EvidenceTier.insufficient.value,
        "summary": f"Demand trend is {trend}; recommended signal is {reorder_signal}.",
    }
    _module_log(session, "demand_forecast", result, state_code, None, json.dumps(series, default=str))
    return result


def retailer_dispatch_risk(payload: dict[str, Any], session: Session | None = None, state_code: str | None = None) -> dict[str, Any]:
    risk = 0
    reasons = []
    def add(points: int, reason: str):
        nonlocal risk
        risk += points
        reasons.append({"points": points, "reason": reason})
    if not payload.get("retailer_license_active", True):
        add(35, "Retailer licence is inactive or not verified.")
    if not payload.get("permit_valid", True):
        add(30, "Transport/import/export permit is missing or invalid.")
    if payload.get("dry_day", False):
        add(30, "Dispatch date appears to be a dry/restricted day.")
    if payload.get("quantity_cases", 0) and payload.get("permit_balance_cases") is not None and float(payload.get("quantity_cases", 0)) > float(payload.get("permit_balance_cases", 0)):
        add(25, "Quantity exceeds permit balance.")
    if payload.get("payment_overdue_days", 0) > 30:
        add(18, "Retailer payment overdue exceeds 30 days.")
    if payload.get("route_mismatch", False):
        add(20, "Vehicle/depot/retailer route mismatch.")
    if payload.get("declared_mrp", 0) and payload.get("registered_mrp", 0) and float(payload["declared_mrp"]) > float(payload["registered_mrp"]):
        add(20, "Declared MRP exceeds registered MRP.")
    if payload.get("chatter_only_basis", False):
        add(15, "Action appears based only on unverified chatter.")
    score = max(0, min(100, risk))
    tier = "high" if score >= 65 else "medium" if score >= 35 else "low"
    result = {
        "risk_score": score,
        "risk_tier": tier,
        "block_dispatch": score >= 65,
        "reasons": reasons or [{"points": 0, "reason": "No major rule-based risk detected."}],
        "mitigation_steps": [
            "Verify licence, permit, route, quantity and MRP before dispatch.",
            "Escalate high-risk dispatch to compliance head.",
            "Keep source documents and audit trail with invoice/challan.",
        ],
        "evidence_tier": EvidenceTier.insufficient.value,
        "confidence": 0.75,
        "summary": f"Dispatch risk is {tier} with score {score}/100.",
    }
    _module_log(session, "retailer_dispatch_risk", result, state_code, None, json.dumps(payload, default=str))
    return result


def fraud_anomaly(transactions: list[dict[str, Any]], session: Session | None = None, state_code: str | None = None) -> dict[str, Any]:
    anomalies = []
    seen_invoice = defaultdict(list)
    qtys = []
    for idx, tx in enumerate(transactions):
        inv = str(tx.get("invoice_no") or tx.get("invoice") or "").strip().lower()
        if inv:
            seen_invoice[inv].append(idx)
        try:
            qtys.append(float(tx.get("quantity_cases", tx.get("quantity", 0)) or 0))
        except Exception:
            qtys.append(0.0)
    avg = mean(qtys) if qtys else 0
    sd = pstdev(qtys) if len(qtys) > 1 else 0
    for inv, ids in seen_invoice.items():
        if len(ids) > 1:
            anomalies.append({"type": "duplicate_invoice", "severity": "high", "invoice_no": inv, "rows": ids, "reason": "Same invoice appears more than once."})
    for idx, tx in enumerate(transactions):
        qty = qtys[idx] if idx < len(qtys) else 0
        if sd and qty > avg + 2.5 * sd:
            anomalies.append({"type": "quantity_spike", "severity": "medium", "row": idx, "quantity_cases": qty, "reason": "Quantity is a statistical outlier versus batch average."})
        if tx.get("route_mismatch") or tx.get("off_route"):
            anomalies.append({"type": "route_mismatch", "severity": "high", "row": idx, "reason": "Vehicle/depot/retailer route mismatch flagged."})
        if float(tx.get("breakage_cases", 0) or 0) > max(2, qty * 0.03):
            anomalies.append({"type": "high_breakage", "severity": "medium", "row": idx, "reason": "Breakage exceeds expected tolerance."})
        if tx.get("permit_id") in {None, "", "NA"}:
            anomalies.append({"type": "missing_permit", "severity": "high", "row": idx, "reason": "No permit ID present."})
    result = {
        "transaction_count": len(transactions),
        "anomaly_count": len(anomalies),
        "anomalies": anomalies,
        "investigation_required": any(a["severity"] == "high" for a in anomalies),
        "evidence_tier": EvidenceTier.insufficient.value,
        "confidence": 0.7 if transactions else 0.0,
        "summary": f"Found {len(anomalies)} anomaly/anomalies across {len(transactions)} transaction(s).",
    }
    _module_log(session, "fraud_anomaly", result, state_code, None, json.dumps(transactions, default=str))
    return result


def telegram_ai_preview(session: Session, state_code: str | None = None, days: int = 1, limit: int = 25, include_chatter: bool = False) -> dict[str, Any]:
    from .telegram_updates import build_digest_text, split_telegram_message
    text = build_digest_text(session, state_code=state_code, days=days, limit=limit, include_chatter=include_chatter)
    chunks = split_telegram_message(text)
    result = {
        "preview": text,
        "chunk_count": len(chunks),
        "chunks": chunks,
        "evidence_tier": EvidenceTier.insufficient.value,
        "confidence": 0.8,
        "summary": f"Telegram digest preview built with {len(chunks)} message chunk(s).",
    }
    _module_log(session, "telegram_digest_ai", result, state_code, None, f"{state_code}:{days}:{limit}:{include_chatter}")
    return result


def run_all_ai_suite(session: Session, question: str, state_code: str | None = None, days: int = 365, text: str | None = None, include_chatter: bool = False) -> dict[str, Any]:
    rag = rag_answer(session, question, state_code=state_code, days=days, include_chatter=include_chatter)
    conclusive = conclusive_synthesis(session, question, state_code=state_code, days=days, include_chatter=include_chatter)
    conflicts = detect_conflicts(session, state_code=state_code, days=days, question=question)
    workmap = officer_workmap(session, state_code=state_code, days=days)
    text_payload = text or question
    entities = extract_entities(text_payload, state_code=state_code, source_type="manual", session=session)
    impact = analyze_impact(text_payload, state_code=state_code, evidence_tier=conclusive.get("evidence_tier"), session=session)
    checklist = build_compliance_checklist(text_payload, state_code=state_code, evidence_tier=conclusive.get("evidence_tier"), session=session)
    result = {
        "suite": "ExciseWatch v5 AI Suite",
        "state_code": state_code.upper() if state_code else "ALL",
        "question": question,
        "conclusive": conclusive,
        "rag_answer": rag,
        "entities": entities,
        "impact": impact,
        "checklist": checklist,
        "conflicts": conflicts,
        "officer_workmap": workmap,
        "final_decision": {
            "definitive": conclusive["definitive"],
            "status": conclusive["answer_status"],
            "can_act_operationally": conclusive["definitive"] and conclusive["conflict_count"] == 0,
            "recommended_next_step": "Act through compliance SOP and update masters." if conclusive["definitive"] and conclusive["conflict_count"] == 0 else "Verify official order/gazette/circular before any pricing, dispatch, licence or policy action.",
        },
        "summary": conclusive["conclusion"],
        "evidence_tier": conclusive["evidence_tier"],
        "confidence": conclusive["confidence"],
    }
    _module_log(session, "all_ai_suite", result, state_code, question, (text or "") + question)
    return result


def latest_ai_runs(session: Session, module_name: str | None = None, state_code: str | None = None, limit: int = 50) -> list[AIModuleRun]:
    stmt = select(AIModuleRun).order_by(AIModuleRun.created_at.desc()).limit(limit)
    if module_name:
        stmt = select(AIModuleRun).where(AIModuleRun.module_name == module_name).order_by(AIModuleRun.created_at.desc()).limit(limit)
    if state_code:
        code = state_code.upper()
        if module_name:
            stmt = select(AIModuleRun).where(AIModuleRun.module_name == module_name, AIModuleRun.state_code == code).order_by(AIModuleRun.created_at.desc()).limit(limit)
        else:
            stmt = select(AIModuleRun).where(AIModuleRun.state_code == code).order_by(AIModuleRun.created_at.desc()).limit(limit)
    return list(session.exec(stmt).all())
