from datetime import datetime

from sqlmodel import Session, SQLModel, create_engine

from app.ai_modules import conclusive_synthesis, rag_answer
from app.officials import answer_conclusive_question
from app.models import LegalChange, ChangeType, EvidenceTier, SourceType


def make_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/relevance.db", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def add_change(session, change_type, title, summary, effect=None, hash_suffix="x"):
    change = LegalChange(
        state_code="DL",
        state_name="Delhi",
        change_type=change_type,
        title=title,
        summary=summary,
        legal_effect=effect,
        published_at=datetime.utcnow(),
        evidence_tier=EvidenceTier.official_confirmed,
        confidence_score=0.95,
        source_name="Delhi Excise",
        source_type=SourceType.official,
        source_url=f"https://excise.delhi.gov.in/{hash_suffix}",
        content_hash=f"hash-{hash_suffix}",
        needs_human_review=True,
    )
    session.add(change)
    session.commit()
    return change


def test_unrelated_official_dry_day_does_not_confirm_fee_increase(tmp_path):
    session = make_session(tmp_path)
    add_change(
        session,
        ChangeType.dry_day,
        "Official dry day order for Delhi",
        "Retail sale of liquor shall remain closed on specified dry days.",
        "Block affected retail sale and dispatch dates.",
        "dry-day",
    )
    ans = conclusive_synthesis(session, "Is there a confirmed licence fee increase in Delhi?", state_code="DL", days=365)
    assert ans["definitive"] is False
    assert ans["answer_status"] == "INSUFFICIENT"
    assert ans["official_source_count"] == 0
    assert ans["top_sources"] == []


def test_relevant_official_fee_increase_can_confirm(tmp_path):
    session = make_session(tmp_path)
    add_change(
        session,
        ChangeType.fee,
        "Official licence fee increase order",
        "Annual licence fee for retail vends has been increased with effect from 1 July 2026.",
        "Update licence fee, retailer billing and compliance checklist.",
        "fee-increase",
    )
    ans = conclusive_synthesis(session, "Is there a confirmed licence fee increase in Delhi?", state_code="DL", days=365)
    assert ans["definitive"] is True
    assert ans["answer_status"] == "CONFIRMED"
    assert ans["official_source_count"] == 1
    assert "fee" in " ".join(ans["top_sources"][0]["matched_categories"])


def test_rag_answer_uses_relevance_gate_before_definitive(tmp_path):
    session = make_session(tmp_path)
    add_change(
        session,
        ChangeType.dry_day,
        "Official dry day order for Delhi",
        "Retail sale of liquor shall remain closed on specified dry days.",
        "Block affected dates.",
        "dry-day-rag",
    )
    ans = rag_answer(session, "Is licence fee increased?", state_code="DL", days=365)
    assert ans["definitive"] is False
    assert ans["answer_status"] == "INSUFFICIENT"


def test_public_office_conclusive_question_respects_relevance_gate(tmp_path):
    session = make_session(tmp_path)
    add_change(
        session,
        ChangeType.dry_day,
        "Official dry day order for Delhi",
        "Retail sale of liquor shall remain closed on specified dry days.",
        "Block affected dates.",
        "dry-day-officials",
    )
    ans = answer_conclusive_question(session, "confirmed licence fee increase", state_code="DL", days=365)
    assert ans["definitive"] is False
    assert ans["answer_status"] == "INSUFFICIENT"
    assert ans["counts"]["official_sources"] == 0
