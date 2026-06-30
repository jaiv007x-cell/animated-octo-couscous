from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
import re

from sqlmodel import Session, select

from app.collectors.news import collect_google_news, is_excise_news_text
from app.india_states import ALL_JURISDICTIONS, JURISDICTION_BY_CODE
from app.models import LegalChange, SourceType
from app.officials import process_new_official_raw_items
from app.processor import process_new_raw_items
from app.telegram_updates import send_telegram_text, truncate


def _title_key(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def _targets(state_code: str | None):
    if state_code:
        code = state_code.upper()
        jurisdiction = JURISDICTION_BY_CODE.get(code)
        if not jurisdiction:
            raise ValueError(f"Unknown state/UT code: {state_code}")
        return [jurisdiction]
    return list(ALL_JURISDICTIONS)


def build_latest_news_text(session: Session, state_code: str | None = None, days: int = 7, limit: int = 20) -> str:
    since = datetime.utcnow() - timedelta(days=days)
    stmt = (
        select(LegalChange)
        .where(LegalChange.source_type == SourceType.news, LegalChange.published_at >= since)
        .order_by(LegalChange.published_at.desc())
        .limit(limit * 4)
    )
    if state_code:
        stmt = (
            select(LegalChange)
            .where(LegalChange.source_type == SourceType.news, LegalChange.state_code == state_code.upper(), LegalChange.published_at >= since)
            .order_by(LegalChange.published_at.desc())
            .limit(limit * 4)
        )
    items = []
    seen_titles: set[str] = set()
    for item in session.exec(stmt).all():
        key = _title_key(item.title)
        if not key or key in seen_titles or not is_excise_news_text(item.title):
            continue
        seen_titles.add(key)
        items.append(item)
        if len(items) >= limit:
            break
    scope = state_code.upper() if state_code else "ALL INDIA"
    lines = [
        f"ExciseWatch Latest News Feed - {scope}",
        f"Lookback: {days} day(s)",
        "Evidence label: REPORTED_NOT_CONFIRMED unless matched to official source.",
        f"Generated: {datetime.utcnow().isoformat(timespec='seconds')} UTC",
        "",
    ]
    if not items:
        lines.append("No reported news items found in the current lookback window.")
        return "\n".join(lines)
    for idx, item in enumerate(items, 1):
        published = item.published_at.date().isoformat() if item.published_at else "date not found"
        lines.extend([
            f"{idx}. {item.state_name} ({item.state_code}) [{item.evidence_tier.value}]",
            f"Type: {item.change_type.value} | Published: {published}",
            f"Title: {truncate(item.title, 220)}",
            f"Effect: {truncate(item.legal_effect or item.summary, 260)}",
            f"Source: {item.source_url}",
            "",
        ])
    return "\n".join(lines).strip()


def run_latest_news_feed(
    session: Session,
    state_code: str | None = None,
    max_items_per_state: int = 10,
    days: int = 7,
    send_telegram: bool = False,
) -> dict[str, Any]:
    raw_created = 0
    states_with_news: list[dict[str, Any]] = []
    errors: list[str] = []
    for jurisdiction in _targets(state_code):
        try:
            rows = collect_google_news(
                session,
                jurisdiction.code,
                jurisdiction.name,
                max_items=max_items_per_state,
                recent_days=days,
            )
            raw_created += len(rows)
            if rows:
                states_with_news.append({"state_code": jurisdiction.code, "state_name": jurisdiction.name, "raw_items": len(rows)})
        except Exception as exc:
            errors.append(f"{jurisdiction.code}: {exc}")
    changes = process_new_raw_items(session)
    official_result = process_new_official_raw_items(session)
    text = build_latest_news_text(session, state_code=state_code, days=days, limit=25)
    telegram = send_telegram_text(text, dry_run=False) if send_telegram else {"sent": 0, "dry_run": True, "errors": []}
    return {
        "state_code": state_code.upper() if state_code else None,
        "states_checked": len(_targets(state_code)),
        "states_with_news": states_with_news,
        "raw_items_created": raw_created,
        "legal_changes_created": len(changes),
        "official_movements_created": official_result.get("movements_created", 0),
        "work_signals_created": official_result.get("work_signals_created", 0),
        "errors": errors,
        "telegram": telegram,
        "preview": text[:1500],
    }
