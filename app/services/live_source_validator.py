from __future__ import annotations
import hashlib
from pathlib import Path
from typing import Any
import requests
from bs4 import BeautifulSoup
from sqlmodel import Session, select
from app.models import SourceItem, SourceSnapshot, SourceHealthStatus, SourceType
from app.settings import get_settings
from app.services.document_archiver import archive_text_document


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def _extract_text(content: str, content_type: str | None) -> str:
    if "html" in (content_type or "").lower() or content.lstrip().startswith("<"):
        soup = BeautifulSoup(content, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        return "\n".join(line.strip() for line in soup.get_text("\n").splitlines() if line.strip())[:200000]
    return content[:200000]


def validate_sources(
    session: Session,
    *,
    state_code: str | None = None,
    live_fetch: bool | None = None,
    max_sources: int | None = None,
    archive_documents: bool = True,
) -> dict[str, Any]:
    settings = get_settings()
    live_fetch = settings.source_live_fetch_default if live_fetch is None else live_fetch
    max_sources = max_sources or settings.source_validation_max_sources
    stmt = select(SourceItem).where(SourceItem.is_active == True).order_by(SourceItem.priority).limit(max_sources)
    if state_code:
        stmt = select(SourceItem).where(SourceItem.is_active == True, SourceItem.state_code == state_code.upper()).order_by(SourceItem.priority).limit(max_sources)
    sources = list(session.exec(stmt).all())
    results = []
    docs = 0
    changed = 0
    failed = 0
    for src in sources:
        previous = session.exec(select(SourceSnapshot).where(SourceSnapshot.url == src.url).order_by(SourceSnapshot.checked_at.desc())).first()
        previous_hash = previous.content_hash if previous else None
        content_hash = None
        content_path = None
        http_status = None
        error = None
        status = SourceHealthStatus.dry_run
        is_changed = False
        text = f"DRY RUN: {src.source_name} {src.url}"
        if live_fetch:
            try:
                resp = requests.get(src.url, timeout=settings.http_timeout_seconds, headers={"User-Agent": settings.user_agent})
                http_status = resp.status_code
                resp.raise_for_status()
                text = _extract_text(resp.text, resp.headers.get("content-type"))
                content_hash = _hash(text)
                is_changed = bool(previous_hash and previous_hash != content_hash)
                status = SourceHealthStatus.changed if is_changed else (SourceHealthStatus.unchanged if previous_hash else SourceHealthStatus.live)
                root = Path(settings.snapshot_dir)
                root.mkdir(parents=True, exist_ok=True)
                path = root / f"source_{src.id}_{content_hash[:12]}.txt"
                path.write_text(text, encoding="utf-8")
                content_path = str(path)
                if archive_documents and text.strip():
                    archive_text_document(
                        session,
                        state_code=src.state_code,
                        state_name=src.state_name,
                        title=src.source_name,
                        source_url=src.url,
                        source_name=src.source_name,
                        source_type=src.source_type,
                        content=text,
                    )
                    docs += 1
            except Exception as exc:
                status = SourceHealthStatus.failed
                error = str(exc)[:500]
                failed += 1
        else:
            content_hash = _hash(text)
        snap = SourceSnapshot(
            source_item_id=src.id,
            state_code=src.state_code,
            state_name=src.state_name,
            source_name=src.source_name,
            url=src.url,
            source_type=src.source_type,
            status=status,
            http_status=http_status,
            content_hash=content_hash,
            previous_hash=previous_hash,
            changed=is_changed,
            content_path=content_path,
            error=error,
        )
        session.add(snap)
        session.commit()
        session.refresh(snap)
        if is_changed:
            changed += 1
        results.append({"source_id": src.id, "snapshot_id": snap.id, "state_code": src.state_code, "source_name": src.source_name, "status": status.value, "changed": is_changed, "http_status": http_status, "error": error})
    return {
        "state_code": state_code.upper() if state_code else "ALL",
        "live_fetch": live_fetch,
        "sources_checked": len(sources),
        "live_sources_working": sum(1 for r in results if r["status"] in {"LIVE", "CHANGED", "UNCHANGED"}),
        "changed_sources": changed,
        "documents_archived": docs,
        "failed_sources": failed,
        "results": results,
    }
