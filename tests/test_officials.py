from datetime import datetime
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

from app.models import RawItem, SourceType, MovementType, WorkSignalType, OfficialMovement, WorkSignal, OfficialProfile
from app.officials import process_raw_for_officials, ingest_forward_data, normalize_name


def make_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/test.db", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_forward_transfer_chatter_creates_movement_and_profile(tmp_path):
    session = make_session(tmp_path)
    item = ingest_forward_data(
        session,
        "DL",
        "Delhi",
        "Forward: Excise transfer chatter",
        "Forward says Shri Rakesh Kumar, IAS has been posted as Excise Commissioner after a review meeting on liquor policy.",
        "manual://whatsapp-forward",
    )
    movements, work = process_raw_for_officials(session, item)
    assert len(movements) == 1
    assert movements[0].movement_type in {MovementType.posting, MovementType.transfer, MovementType.chatter}
    assert movements[0].evidence_tier == "CHATTER_UNVERIFIED"
    assert "Excise Commissioner" in (movements[0].to_designation or "")
    assert session.query(OfficialProfile).count() == 1
    assert len(work) == 1
    assert work[0].signal_type in {WorkSignalType.policy, WorkSignalType.transfer_admin, WorkSignalType.meeting_review, WorkSignalType.chatter}


def test_normalize_name_removes_honorific_and_cadre():
    assert normalize_name("Shri Rakesh Kumar, IAS") == "rakesh kumar"

from app.models import EvidenceTier
from app.officials import answer_conclusive_question


def test_cm_minister_forward_stays_chatter_and_conclusive_is_false(tmp_path):
    session = make_session(tmp_path)
    item = ingest_forward_data(
        session,
        "DL",
        "Delhi",
        "Forward: CMO excise review chatter",
        "Forward says the Chief Minister and Excise Minister reviewed licence renewal, duty changes, permit digitisation and officer transfers. Not verified.",
        "manual://whatsapp-forward",
    )
    process_raw_for_officials(session, item)
    ans = answer_conclusive_question(session, "Chief Minister Excise Minister licence renewal", state_code="DL", days=365)
    assert ans["definitive"] is False
    assert ans["answer_status"] in {"CHATTER_ONLY", "REPORTED_ONLY", "INSUFFICIENT"}
    assert ans["counts"]["chatter_sources"] >= 1


def test_official_minister_source_can_be_conclusive(tmp_path):
    session = make_session(tmp_path)
    item = ingest_forward_data(
        session,
        "DL",
        "Delhi",
        "Official: Excise Minister review meeting",
        "Official release says Shri Rakesh Kumar, IAS, Principal Secretary Excise and the Excise Minister reviewed licence renewal and excise revenue. Order No ABC/123 dated 01-07-2026.",
        "https://excise.delhi.gov.in/official-release",
        "State official release",
        SourceType.official,
    )
    process_raw_for_officials(session, item)
    ans = answer_conclusive_question(session, "Excise Minister Principal Secretary licence renewal", state_code="DL", days=365)
    assert ans["definitive"] is True
    assert ans["answer_status"] == "CONFIRMED"
    assert ans["counts"]["official_sources"] >= 1
