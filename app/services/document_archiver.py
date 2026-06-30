from __future__ import annotations
import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable
from sqlmodel import Session
from app.models import DocumentRecord, SourceType, EvidenceTier
from app.evidence import evidence_tier
from app.settings import get_settings


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_name(text: str, max_len: int = 90) -> str:
    text = re.sub(r"[^a-zA-Z0-9._-]+", "_", text).strip("_")
    return (text or "document")[:max_len]


def detect_order_no(text: str) -> str | None:
    m = re.search(r"(?:order|notification|circular|memo|no\.?|number)\s*(?:no\.?|number)?\s*[:#-]?\s*([A-Z0-9][A-Z0-9/._-]{2,})", text, re.I)
    return m.group(1) if m else None


def detect_date(text: str):
    try:
        from dateutil.parser import parse
        m = re.search(r"(?:dated|date)\s*[:#-]?\s*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4}|[0-9]{1,2}\s+[A-Za-z]+\s+[0-9]{4})", text, re.I)
        if m:
            return parse(m.group(1), dayfirst=True).date()
    except Exception:
        return None
    return None


def archive_text_document(
    session: Session,
    *,
    state_code: str,
    state_name: str,
    title: str,
    source_url: str,
    source_name: str | None,
    source_type: SourceType,
    content: str,
) -> DocumentRecord:
    settings = get_settings()
    root = Path(settings.doc_dir)
    root.mkdir(parents=True, exist_ok=True)
    digest = sha256_bytes(content.encode("utf-8"))
    filename = f"{state_code}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{safe_name(title)}_{digest[:10]}.txt"
    path = root / filename
    path.write_text(content, encoding="utf-8")
    tier, _, _ = evidence_tier(source_type, source_url, title, content[:1000])
    existing = session.query(DocumentRecord).filter(DocumentRecord.sha256 == digest).first()
    if existing:
        return existing
    rec = DocumentRecord(
        state_code=state_code,
        state_name=state_name,
        title=title,
        source_url=source_url,
        source_name=source_name,
        source_type=source_type,
        text_path=str(path),
        sha256=digest,
        detected_order_no=detect_order_no(title + "\n" + content),
        detected_date=detect_date(title + "\n" + content),
        evidence_tier=tier,
    )
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return rec
