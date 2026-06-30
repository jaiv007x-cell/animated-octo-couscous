from __future__ import annotations
from datetime import datetime, timedelta
from sqlmodel import Session, select
from .models import LegalChange, EvidenceTier
from .evidence import certainty_sentence


def _tier_rank(tier: EvidenceTier) -> int:
    return {
        EvidenceTier.official_confirmed: 5,
        EvidenceTier.govt_probable: 4,
        EvidenceTier.reported_not_confirmed: 3,
        EvidenceTier.chatter_unverified: 1,
        EvidenceTier.insufficient: 0,
    }.get(tier, 0)


def latest_changes(session: Session, state_code: str | None = None, days: int = 30, limit: int = 50) -> list[LegalChange]:
    since = datetime.utcnow() - timedelta(days=days)
    stmt = select(LegalChange).where(LegalChange.detected_at >= since)
    if state_code:
        stmt = stmt.where(LegalChange.state_code == state_code.upper())
    stmt = stmt.order_by(LegalChange.detected_at.desc()).limit(limit)
    return list(session.exec(stmt).all())


def answer_question(session: Session, question: str, state_code: str | None = None, days: int = 180) -> dict:
    q = question.lower()
    rows = latest_changes(session, state_code=state_code, days=days, limit=100)
    if q.strip():
        tokens = [t for t in q.replace("?", " ").replace(",", " ").split() if len(t) > 2]
        scored = []
        for r in rows:
            hay = f"{r.title} {r.summary} {r.legal_effect}".lower()
            score = sum(1 for t in tokens if t in hay) + _tier_rank(r.evidence_tier)
            if score > 0:
                scored.append((score, r))
        rows = [r for _, r in sorted(scored, key=lambda x: x[0], reverse=True)[:10]]
    else:
        rows = rows[:10]

    if not rows:
        return {
            "answer": "No reliable matching update is currently in the local ExciseWatch database. Run /api/watch/run or add official sources, then ask again.",
            "definitive": False,
            "evidence_tier": EvidenceTier.insufficient,
            "sources": [],
        }

    best = max(rows, key=lambda r: (_tier_rank(r.evidence_tier), r.confidence_score, r.detected_at.timestamp()))
    definitive = best.evidence_tier == EvidenceTier.official_confirmed
    sources = [
        {
            "title": r.title,
            "state": r.state_name,
            "tier": r.evidence_tier,
            "confidence": r.confidence_score,
            "url": r.source_url,
            "detected_at": r.detected_at.isoformat(),
            "published_at": r.published_at.isoformat() if r.published_at else None,
            "legal_effect": r.legal_effect,
        }
        for r in rows[:8]
    ]
    if definitive:
        answer = f"Definite answer: {best.title}. {best.legal_effect or ''} Evidence is official-confirmed."
    else:
        answer = f"Not definitive yet: strongest evidence is {best.evidence_tier}. {certainty_sentence(best.evidence_tier)} Strongest item: {best.title}."
    return {
        "answer": answer,
        "definitive": definitive,
        "evidence_tier": best.evidence_tier,
        "sources": sources,
    }
