from __future__ import annotations
"""
Chatter connectors.

Production note:
- Do not make legal decisions from chatter.
- Use this only for early warning signals: social posts, industry WhatsApp/Telegram forwards, association notes.
- The cleanest production integration is: email/Telegram forward -> manual_ingest endpoint -> classified as CHATTER_UNVERIFIED.

This module intentionally avoids scraping restricted social platforms.
"""
from datetime import datetime
import hashlib
from pathlib import Path
from sqlmodel import Session, select
from app.models import RawItem, SourceType
from app.settings import get_settings
from app.collectors.text import compact_snippet


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def ingest_chatter(session: Session, state_code: str, state_name: str, title: str, text: str, source_url: str = "manual://chatter") -> RawItem | None:
    settings = get_settings()
    Path(settings.doc_dir).mkdir(parents=True, exist_ok=True)
    digest = sha256(state_code + title + text + source_url)
    if session.exec(select(RawItem).where(RawItem.content_hash == digest)).first():
        return None
    path = Path(settings.doc_dir) / f"chatter-{state_code.lower()}-{digest[:16]}.txt"
    path.write_text(f"{title}\n{source_url}\n{text}", encoding="utf-8")
    item = RawItem(
        state_code=state_code,
        state_name=state_name,
        source_name="Manual chatter ingest",
        source_type=SourceType.social,
        title=title[:250],
        url=source_url,
        published_at=None,
        fetched_at=datetime.utcnow(),
        content_hash=digest,
        snippet=compact_snippet(text),
        full_text_path=str(path),
    )
    session.add(item)
    session.commit()
    return item
