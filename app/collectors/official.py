from __future__ import annotations
from datetime import datetime
import hashlib
from pathlib import Path
from sqlmodel import Session, select
from app.models import SourceItem, RawItem, SourceType
from app.settings import get_settings
from app.collectors.http import fetch_url
from app.collectors.text import clean_text, extract_links, compact_snippet


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def save_text(prefix: str, text: str) -> str:
    settings = get_settings()
    Path(settings.doc_dir).mkdir(parents=True, exist_ok=True)
    digest = sha256(text)[:16]
    path = Path(settings.doc_dir) / f"{prefix}-{digest}.txt"
    path.write_text(text, encoding="utf-8")
    return str(path)


def collect_official_source(session: Session, source: SourceItem, max_links: int = 80) -> list[RawItem]:
    html, content_type = fetch_url(source.url)
    page_text = clean_text(html)
    rows = [{"title": source.source_name, "url": source.url, "text": page_text}]

    # Government pages usually expose changes as links. Store each link title + source page text context.
    for link in extract_links(source.url, html)[:max_links]:
        rows.append({"title": link["title"], "url": link["url"], "text": f"{link['title']}\nSource page: {page_text[:1000]}"})

    created: list[RawItem] = []
    for row in rows:
        digest = sha256(row["title"] + row["url"] + row["text"])
        exists = session.exec(select(RawItem).where(RawItem.content_hash == digest)).first()
        if exists:
            continue
        path = save_text(f"official-{source.state_code.lower()}", row["text"])
        item = RawItem(
            state_code=source.state_code,
            state_name=source.state_name,
            source_name=source.source_name,
            source_type=source.source_type,
            title=row["title"][:250] or source.source_name,
            url=row["url"],
            published_at=None,
            fetched_at=datetime.utcnow(),
            content_hash=digest,
            snippet=compact_snippet(row["text"]),
            full_text_path=path,
        )
        session.add(item)
        created.append(item)
    session.commit()
    return created
