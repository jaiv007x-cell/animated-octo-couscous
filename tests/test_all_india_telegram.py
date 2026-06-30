from pathlib import Path
import yaml
from datetime import datetime

from sqlmodel import Session, SQLModel, create_engine

from app.india_states import ALL_CODES, STATE_CODES, UNION_TERRITORY_CODES, validate_all_india_coverage
from app.models import LegalChange, ChangeType, EvidenceTier, SourceType
from app.telegram_updates import build_digest_text, send_telegram_text, split_telegram_message


def make_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/test.db", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_all_india_registry_has_28_states_8_uts():
    assert len(STATE_CODES) == 28
    assert len(UNION_TERRITORY_CODES) == 8
    assert len(ALL_CODES) == 36
    coverage = validate_all_india_coverage(set(ALL_CODES))
    assert coverage["complete"] is True
    assert coverage["missing_codes"] == []


def test_sources_yaml_covers_every_state_and_ut():
    path = Path(__file__).resolve().parents[1] / "data" / "sources.yaml"
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    codes = {row["code"] for row in cfg["states"]}
    assert set(ALL_CODES).issubset(codes)
    assert "TR" in codes


def test_telegram_dry_run_and_digest(tmp_path):
    session = make_session(tmp_path)
    change = LegalChange(
        state_code="DL",
        state_name="Delhi",
        change_type=ChangeType.license,
        title="Official: Excise licence renewal order issued",
        summary="Official source says licence renewal order issued.",
        legal_effect="May affect renewal workflow.",
        published_at=datetime.utcnow(),
        detected_at=datetime.utcnow(),
        evidence_tier=EvidenceTier.official_confirmed,
        confidence_score=0.95,
        source_name="Delhi Excise",
        source_type=SourceType.official,
        source_url="https://excise.delhi.gov.in/notifications",
        content_hash="abc123",
        needs_human_review=False,
    )
    session.add(change)
    session.commit()
    text = build_digest_text(session, state_code="DL", days=1, include_chatter=False)
    assert "ExciseWatch Telegram Digest" in text
    assert "Official: Excise licence renewal order issued" in text
    result = send_telegram_text(text, dry_run=True)
    assert result["dry_run"] is True
    assert result["sent"] == 0
    assert result["chunks"]


def test_split_telegram_message_keeps_chunks_under_limit():
    chunks = split_telegram_message("x" * 9000, max_size=3500)
    assert len(chunks) >= 3
    assert all(len(chunk) <= 3500 for chunk in chunks)
