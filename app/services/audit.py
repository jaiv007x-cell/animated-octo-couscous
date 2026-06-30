from __future__ import annotations
import json
from sqlmodel import Session
from app.models import AuditLog


def audit(session: Session, *, actor: str, action: str, entity_type: str, entity_id: int | None = None, state_code: str | None = None, actor_role: str | None = None, details: dict | None = None) -> AuditLog:
    rec = AuditLog(
        actor=actor,
        actor_role=actor_role,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        state_code=state_code,
        details_json=json.dumps(details or {}, default=str),
    )
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return rec
