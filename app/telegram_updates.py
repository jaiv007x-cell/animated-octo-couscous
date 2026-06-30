from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
import requests
from sqlmodel import Session, select

from .models import (
    EvidenceTier,
    IntelligenceBrief,
    LegalChange,
    OfficialMovement,
    SourceType,
    WorkSignal,
)
from .settings import get_settings

TELEGRAM_MAX_MESSAGE = 4096
SAFE_MESSAGE_SIZE = 3600


TIER_RANK = {
    EvidenceTier.official_confirmed: 5,
    EvidenceTier.govt_probable: 4,
    EvidenceTier.reported_not_confirmed: 3,
    EvidenceTier.chatter_unverified: 1,
    EvidenceTier.insufficient: 0,
}


def _tier_from_string(value: str | None) -> EvidenceTier:
    if not value:
        return EvidenceTier.reported_not_confirmed
    normalized = value.strip().upper()
    for tier in EvidenceTier:
        if tier.value == normalized or tier.name.upper() == normalized:
            return tier
    return EvidenceTier.reported_not_confirmed


def should_include_tier(tier: EvidenceTier, min_tier: EvidenceTier, include_chatter: bool = False) -> bool:
    if tier == EvidenceTier.chatter_unverified:
        return include_chatter
    return TIER_RANK.get(tier, 0) >= TIER_RANK.get(min_tier, 0)


def truncate(value: str | None, limit: int = 650) -> str:
    if not value:
        return ""
    value = " ".join(str(value).split())
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def split_telegram_message(text: str, max_size: int = SAFE_MESSAGE_SIZE) -> list[str]:
    if len(text) <= max_size:
        return [text]
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for para in text.split("\n"):
        para_size = len(para) + 1
        if size + para_size > max_size and current:
            chunks.append("\n".join(current))
            current = []
            size = 0
        if para_size > max_size:
            for i in range(0, len(para), max_size):
                chunks.append(para[i:i + max_size])
            continue
        current.append(para)
        size += para_size
    if current:
        chunks.append("\n".join(current))
    return chunks


def telegram_enabled() -> bool:
    settings = get_settings()
    return bool(settings.telegram_bot_token and settings.telegram_chat_id)


def send_telegram_text(text: str, dry_run: bool = False) -> dict[str, Any]:
    settings = get_settings()
    chunks = split_telegram_message(text)
    if dry_run:
        return {"sent": 0, "dry_run": True, "chunks": chunks, "errors": []}
    if not telegram_enabled():
        return {"sent": 0, "dry_run": False, "chunks": chunks, "errors": ["Telegram is not configured. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID."]}

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    sent = 0
    errors: list[str] = []
    for chunk in chunks:
        payload: dict[str, Any] = {
            "chat_id": settings.telegram_chat_id,
            "text": chunk,
            "disable_web_page_preview": settings.telegram_disable_web_page_preview,
        }
        if settings.telegram_parse_mode:
            payload["parse_mode"] = settings.telegram_parse_mode
        try:
            response = requests.post(url, json=payload, timeout=20)
            response.raise_for_status()
            sent += 1
        except Exception as exc:  # pragma: no cover - network/runtime path
            errors.append(str(exc))
    return {"sent": sent, "dry_run": False, "chunks": chunks, "errors": errors}


def format_legal_change(change: LegalChange) -> str:
    return "\n".join([
        f"[LAW] {change.state_name} ({change.state_code})",
        f"Tier: {change.evidence_tier.value}",
        f"Type: {change.change_type.value}",
        f"Title: {truncate(change.title, 220)}",
        f"Effect: {truncate(change.legal_effect or change.summary or 'Review required', 320)}",
        f"Source: {change.source_url}",
    ])


def format_movement(movement: OfficialMovement) -> str:
    bits = [
        f"[OFFICIAL MOVEMENT] {movement.state_name} ({movement.state_code})",
        f"Tier: {movement.evidence_tier.value}",
        f"Person: {movement.person_name}",
        f"Movement: {movement.movement_type.value}",
    ]
    if movement.from_designation:
        bits.append(f"From: {truncate(movement.from_designation, 180)}")
    if movement.to_designation:
        bits.append(f"To: {truncate(movement.to_designation, 180)}")
    if movement.order_no:
        bits.append(f"Order: {movement.order_no}")
    bits.append(f"Summary: {truncate(movement.summary, 320)}")
    bits.append(f"Source: {movement.source_url}")
    return "\n".join(bits)


def format_work_signal(signal: WorkSignal) -> str:
    return "\n".join([
        f"[WORKSTREAM] {signal.state_name} ({signal.state_code})",
        f"Tier: {signal.evidence_tier.value}",
        f"Signal: {signal.signal_type.value}",
        f"Person: {signal.person_name or 'Not specified'}",
        f"Title: {truncate(signal.title, 220)}",
        f"Workstream: {truncate(signal.likely_workstream or 'Review required', 260)}",
        f"Action: {truncate(signal.action_required or 'Monitor and verify before acting', 260)}",
        f"Source: {signal.source_url}",
    ])


def format_brief(brief: IntelligenceBrief) -> str:
    return "\n".join([
        f"[CONCLUSIVE BRIEF] {brief.state_name or 'All India'} ({brief.state_code or 'ALL'})",
        f"Status: {brief.answer_status.value}",
        f"Definitive: {brief.definitive}",
        f"Strongest tier: {brief.strongest_evidence_tier.value}",
        f"Conclusion: {truncate(brief.conclusion, 650)}",
        f"Sources: official={brief.official_source_count}, news={brief.news_source_count}, chatter={brief.chatter_source_count}, conflicts={brief.conflict_count}",
    ])


def latest_for_digest(
    session: Session,
    state_code: str | None = None,
    days: int = 1,
    limit: int = 25,
    include_chatter: bool = False,
    min_tier: EvidenceTier | None = None,
) -> dict[str, list[Any]]:
    settings = get_settings()
    min_tier = min_tier or _tier_from_string(settings.telegram_min_tier)
    since = datetime.utcnow() - timedelta(days=days)

    def maybe_state(stmt):
        if state_code:
            return stmt.where(stmt.selected_columns.state_code == state_code.upper())
        return stmt

    law_stmt = select(LegalChange).where(LegalChange.detected_at >= since).order_by(LegalChange.detected_at.desc()).limit(limit)
    movement_stmt = select(OfficialMovement).where(OfficialMovement.detected_at >= since).order_by(OfficialMovement.detected_at.desc()).limit(limit)
    work_stmt = select(WorkSignal).where(WorkSignal.detected_at >= since).order_by(WorkSignal.detected_at.desc()).limit(limit)
    brief_stmt = select(IntelligenceBrief).where(IntelligenceBrief.created_at >= since).order_by(IntelligenceBrief.created_at.desc()).limit(limit)
    if state_code:
        code = state_code.upper()
        law_stmt = law_stmt.where(LegalChange.state_code == code)
        movement_stmt = movement_stmt.where(OfficialMovement.state_code == code)
        work_stmt = work_stmt.where(WorkSignal.state_code == code)
        brief_stmt = brief_stmt.where(IntelligenceBrief.state_code == code)

    law = [x for x in session.exec(law_stmt).all() if should_include_tier(x.evidence_tier, min_tier, include_chatter)]
    movements = [x for x in session.exec(movement_stmt).all() if should_include_tier(x.evidence_tier, min_tier, include_chatter)]
    work = [x for x in session.exec(work_stmt).all() if should_include_tier(x.evidence_tier, min_tier, include_chatter)]
    briefs = [x for x in session.exec(brief_stmt).all() if should_include_tier(x.strongest_evidence_tier, min_tier, include_chatter)]
    return {"law": law, "movements": movements, "work_signals": work, "briefs": briefs}


def build_digest_text(
    session: Session,
    state_code: str | None = None,
    days: int = 1,
    limit: int | None = None,
    include_law: bool = True,
    include_movements: bool = True,
    include_work: bool = True,
    include_briefs: bool = True,
    include_chatter: bool | None = None,
    min_tier: str | None = None,
) -> str:
    settings = get_settings()
    limit = limit or settings.telegram_digest_limit
    include_chatter = settings.telegram_include_chatter_by_default if include_chatter is None else include_chatter
    min_evidence = _tier_from_string(min_tier or settings.telegram_min_tier)
    items = latest_for_digest(session, state_code=state_code, days=days, limit=limit, include_chatter=include_chatter, min_tier=min_evidence)

    scope = state_code.upper() if state_code else "ALL INDIA"
    lines = [
        f"ExciseWatch Telegram Digest — {scope}",
        f"Lookback: {days} day(s) | Min tier: {min_evidence.value} | Chatter included: {include_chatter}",
        f"Generated: {datetime.utcnow().isoformat(timespec='seconds')} UTC",
        "",
    ]

    if include_briefs:
        lines.append(f"Conclusive briefs: {len(items['briefs'])}")
        for item in items["briefs"][:limit]:
            lines.append(format_brief(item))
            lines.append("---")

    if include_law:
        lines.append(f"Legal changes: {len(items['law'])}")
        for item in items["law"][:limit]:
            lines.append(format_legal_change(item))
            lines.append("---")

    if include_movements:
        lines.append(f"Official movements: {len(items['movements'])}")
        for item in items["movements"][:limit]:
            lines.append(format_movement(item))
            lines.append("---")

    if include_work:
        lines.append(f"Workstream signals: {len(items['work_signals'])}")
        for item in items["work_signals"][:limit]:
            lines.append(format_work_signal(item))
            lines.append("---")

    if all(len(v) == 0 for v in items.values()):
        lines.append("No matching updates found in the local database for this lookback window.")
        lines.append("Run /api/watch/run or ingest official/forward data, then send the digest again.")

    return "\n".join(lines).strip()


def send_digest(session: Session, dry_run: bool = False, **kwargs) -> dict[str, Any]:
    text = build_digest_text(session, **kwargs)
    result = send_telegram_text(text, dry_run=dry_run)
    result["preview"] = text[:1500]
    return result


def send_items_as_telegram(items: list[Any], dry_run: bool = False) -> dict[str, Any]:
    formatted = []
    for item in items:
        if isinstance(item, LegalChange):
            formatted.append(format_legal_change(item))
        elif isinstance(item, OfficialMovement):
            formatted.append(format_movement(item))
        elif isinstance(item, WorkSignal):
            formatted.append(format_work_signal(item))
        elif isinstance(item, IntelligenceBrief):
            formatted.append(format_brief(item))
    if not formatted:
        return {"sent": 0, "dry_run": dry_run, "chunks": [], "errors": []}
    return send_telegram_text("\n\n---\n\n".join(formatted), dry_run=dry_run)
