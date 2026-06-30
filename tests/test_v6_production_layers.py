from datetime import datetime
from sqlmodel import Session, SQLModel, create_engine

from app.auth.security import hash_password, verify_password, create_access_token, decode_access_token
from app.models import (
    SourceItem, SourceType, LegalChange, ChangeType, EvidenceTier,
    ReviewStatus, PublishedGuidance
)
from app.services.live_source_validator import validate_sources
from app.services.review_service import generate_review_tasks, list_review_tasks, decide_review
from app.models import ApprovalDecision
from app.services.decision_engine import decide_action


def make_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/test_v6.db", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_password_hash_and_token_roundtrip():
    hashed = hash_password("StrongPass123")
    assert verify_password("StrongPass123", hashed)
    token = create_access_token("admin", "super_admin", minutes=5)
    payload = decode_access_token(token)
    assert payload["sub"] == "admin"
    assert payload["role"] == "super_admin"


def test_live_source_validator_dry_run_creates_snapshot(tmp_path):
    session = make_session(tmp_path)
    session.add(SourceItem(state_code="DL", state_name="Delhi", source_name="Delhi Excise", url="https://excise.delhi.gov.in/notifications", source_type=SourceType.official))
    session.commit()
    result = validate_sources(session, state_code="DL", live_fetch=False)
    assert result["sources_checked"] == 1
    assert result["results"][0]["status"] == "DRY_RUN"


def test_decision_engine_blocks_chatter_and_requires_review_for_official_unapproved():
    chatter = decide_action(evidence_tier=EvidenceTier.chatter_unverified)
    assert chatter["outcome"] == "BLOCK_ACTION"
    official = decide_action(evidence_tier=EvidenceTier.official_confirmed, document_archived=True, human_approved=False)
    assert official["outcome"] == "REVIEW_REQUIRED"
    approved = decide_action(evidence_tier=EvidenceTier.official_confirmed, document_archived=True, human_approved=True)
    assert approved["outcome"] == "ALLOW_PUBLICATION"


def test_review_approval_creates_guidance(tmp_path):
    session = make_session(tmp_path)
    change = LegalChange(
        state_code="DL",
        state_name="Delhi",
        change_type=ChangeType.dry_day,
        title="Official dry day order",
        summary="Official dry day order issued.",
        legal_effect="Block affected dispatch/sales.",
        published_at=datetime.utcnow(),
        evidence_tier=EvidenceTier.official_confirmed,
        confidence_score=0.95,
        source_name="Delhi Excise",
        source_type=SourceType.official,
        source_url="https://excise.delhi.gov.in/notifications",
        content_hash="hash123",
        needs_human_review=True,
    )
    session.add(change)
    session.commit()
    generated = generate_review_tasks(session, state_code="DL")
    assert generated["created_or_existing"] == 1
    task = list_review_tasks(session, state_code="DL")[0]
    assert task.status == ReviewStatus.needs_review
    result = decide_review(session, task.id, ApprovalDecision.approve, actor="legal_head", actor_role="compliance_head", note="Approved after official PDF review")
    assert result["status"] == "APPROVED"
    assert result["guidance_id"] is not None
    guidance = session.get(PublishedGuidance, result["guidance_id"])
    assert guidance.approved_by == "legal_head"
    assert guidance.evidence_tier == EvidenceTier.official_confirmed
