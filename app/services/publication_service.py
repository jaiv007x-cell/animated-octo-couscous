from __future__ import annotations
from datetime import datetime
from sqlmodel import Session, select
from app.models import PublishedGuidance, GuidanceStatus, EvidenceTier
from app.telegram_updates import send_telegram_text


def publish_guidance_to_telegram(session: Session, guidance_id: int, *, dry_run: bool = True) -> dict:
    guidance = session.get(PublishedGuidance, guidance_id)
    if not guidance:
        return {"status": "not_found", "guidance_id": guidance_id}
    if guidance.evidence_tier == EvidenceTier.chatter_unverified:
        return {"status": "blocked", "reason": "Chatter cannot be published as guidance."}
    text = f"🚨 ExciseWatch Approved Guidance\n\n{guidance.body}"
    result = send_telegram_text(text, dry_run=dry_run)
    if not dry_run and result.get("sent", 0) > 0:
        guidance.telegram_sent = True
        guidance.status = GuidanceStatus.sent
        guidance.sent_at = datetime.utcnow()
        session.add(guidance)
        session.commit()
    return {"status": "dry_run" if dry_run else "sent", "guidance_id": guidance_id, "telegram": result}
