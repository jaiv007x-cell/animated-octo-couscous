from __future__ import annotations
from datetime import datetime, timedelta
from typing import Iterable
from sqlmodel import Session, select
from app.models import (
    LegalChange, OfficialMovement, WorkSignal, IntelligenceBrief, ReviewTask, ReviewStatus, ReviewEntityType,
    Approval, ApprovalDecision, EvidenceTier, UserRole, PublishedGuidance, GuidanceStatus
)
from app.services.decision_engine import decide_action
from app.services.audit import audit

ENTITY_MODEL = {
    ReviewEntityType.legal_change: LegalChange,
    ReviewEntityType.official_movement: OfficialMovement,
    ReviewEntityType.work_signal: WorkSignal,
    ReviewEntityType.intelligence_brief: IntelligenceBrief,
}


def _existing_task(session: Session, entity_type: ReviewEntityType, entity_id: int):
    return session.exec(select(ReviewTask).where(ReviewTask.entity_type == entity_type, ReviewTask.entity_id == entity_id)).first()


def create_task_for_entity(session: Session, entity, entity_type: ReviewEntityType, assigned_to_role: UserRole = UserRole.compliance_head) -> ReviewTask:
    existing = _existing_task(session, entity_type, entity.id)
    if existing:
        return existing
    tier = getattr(entity, "evidence_tier", EvidenceTier.insufficient)
    confidence = float(getattr(entity, "confidence_score", 0.0) or 0.0)
    title = getattr(entity, "title", None) or getattr(entity, "question", None) or getattr(entity, "summary", "Review item")[:120]
    summary = getattr(entity, "summary", None) or getattr(entity, "conclusion", None) or getattr(entity, "legal_effect", None)
    state_code = getattr(entity, "state_code", None)
    decision = decide_action(evidence_tier=tier, document_archived=True, human_approved=False, source_count=1)
    task = ReviewTask(
        entity_type=entity_type,
        entity_id=entity.id,
        state_code=state_code,
        title=title[:240],
        summary=(summary or "")[:3000],
        evidence_tier=tier,
        confidence_score=confidence,
        decision_recommendation=decision["outcome"],
        status=ReviewStatus.needs_review,
        assigned_to_role=assigned_to_role,
        due_at=datetime.utcnow() + timedelta(days=2),
        source_url=getattr(entity, "source_url", None),
    )
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


def generate_review_tasks(session: Session, state_code: str | None = None, limit: int = 250) -> dict:
    created = []
    targets = [
        (LegalChange, ReviewEntityType.legal_change),
        (OfficialMovement, ReviewEntityType.official_movement),
        (WorkSignal, ReviewEntityType.work_signal),
    ]
    for model, entity_type in targets:
        stmt = select(model).limit(limit)
        if hasattr(model, "needs_human_review"):
            stmt = select(model).where(model.needs_human_review == True).limit(limit)
        if state_code and hasattr(model, "state_code"):
            stmt = stmt.where(model.state_code == state_code.upper())
        for entity in session.exec(stmt).all():
            task = create_task_for_entity(session, entity, entity_type)
            created.append(task.id)
    return {"created_or_existing": len(created), "task_ids": created}


def list_review_tasks(session: Session, *, state_code: str | None = None, status: ReviewStatus | None = None, limit: int = 100):
    stmt = select(ReviewTask).order_by(ReviewTask.created_at.desc()).limit(limit)
    if state_code:
        stmt = select(ReviewTask).where(ReviewTask.state_code == state_code.upper()).order_by(ReviewTask.created_at.desc()).limit(limit)
    rows = list(session.exec(stmt).all())
    if status:
        rows = [r for r in rows if r.status == status]
    return rows


def _target_for_task(session: Session, task: ReviewTask):
    model = ENTITY_MODEL.get(task.entity_type)
    return session.get(model, task.entity_id) if model else None


def decide_review(session: Session, task_id: int, decision: ApprovalDecision, actor: str, actor_role: str | None = None, note: str | None = None) -> dict:
    task = session.get(ReviewTask, task_id)
    if not task:
        return {"status": "not_found", "task_id": task_id}
    now = datetime.utcnow()
    task.reviewed_by = actor
    task.reviewed_at = now
    task.review_note = note
    task.updated_at = now
    if decision == ApprovalDecision.approve:
        task.status = ReviewStatus.approved
    elif decision == ApprovalDecision.reject:
        task.status = ReviewStatus.rejected
    elif decision == ApprovalDecision.escalate:
        task.status = ReviewStatus.escalated
    elif decision == ApprovalDecision.supersede:
        task.status = ReviewStatus.superseded
    target = _target_for_task(session, task)
    if target and hasattr(target, "needs_human_review") and decision == ApprovalDecision.approve:
        target.needs_human_review = False
        if hasattr(target, "reviewed_by"):
            target.reviewed_by = actor
        if hasattr(target, "reviewed_at"):
            target.reviewed_at = now
        if hasattr(target, "review_note"):
            target.review_note = note
        session.add(target)
    approval = Approval(review_task_id=task.id, decision=decision, decided_by=actor, decided_role=actor_role, note=note)
    session.add(task)
    session.add(approval)
    session.commit()
    audit(session, actor=actor, actor_role=actor_role, action=f"review.{decision.value.lower()}", entity_type=task.entity_type.value, entity_id=task.entity_id, state_code=task.state_code, details={"task_id": task.id, "note": note})
    guidance_id = None
    if decision == ApprovalDecision.approve:
        guidance = PublishedGuidance(
            review_task_id=task.id,
            state_code=task.state_code,
            title=task.title,
            body=f"{task.title}\n\nStatus: APPROVED\nEvidence: {task.evidence_tier.value}\n\n{task.summary or ''}\n\nAction: Treat as approved internal compliance intelligence. Apply only to affected state/business process after SOP mapping.",
            evidence_tier=task.evidence_tier,
            status=GuidanceStatus.approved,
            approved_by=actor,
        )
        session.add(guidance)
        session.commit()
        session.refresh(guidance)
        guidance_id = guidance.id
    return {"status": task.status.value, "task_id": task.id, "decision": decision.value, "guidance_id": guidance_id}
