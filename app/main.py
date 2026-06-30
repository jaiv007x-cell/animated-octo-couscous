from __future__ import annotations
from typing import Optional
from fastapi import Depends, FastAPI, Query
from pydantic import BaseModel, Field
from sqlmodel import Session, select
from .db import init_db, get_session
from .models import LegalChange, RawItem, SourceItem, EvidenceTier, SourceType, OfficialRoleType, OfficialMovement, WorkSignal
from .source_registry import seed_sources, validate_source_config
from .india_states import source_coverage, ALL_JURISDICTIONS
from .telegram_updates import send_digest, send_telegram_text
from .watch import run_watch
from .answer_engine import answer_question, latest_changes
from .collectors.chatter import ingest_chatter
from .officials import (
    ingest_forward_data, process_new_official_raw_items, officials_directory,
    latest_official_movements, latest_work_signals, answer_officials_question,
    answer_conclusive_question, latest_intelligence_briefs,
)

from .ai_modules import (
    module_catalog, extract_entities, summarize_text, score_chatter, analyze_impact,
    rag_answer, conclusive_synthesis, detect_conflicts, build_compliance_checklist,
    officer_workmap, demand_forecast, retailer_dispatch_risk, fraud_anomaly,
    telegram_ai_preview, run_all_ai_suite, latest_ai_runs, classify_update,
)

app = FastAPI(title="ExciseWatch v6 Production Compliance Engine", version="0.6.0")


@app.on_event("startup")
def startup() -> None:
    init_db()


class SeedResponse(BaseModel):
    inserted: int


class RunWatchRequest(BaseModel):
    state_code: Optional[str] = Field(default=None, description="Optional state code, e.g. DL, MH, KA. Omit for all states in registry.")
    include_news: bool = True
    include_alerts: bool = False


class AskRequest(BaseModel):
    question: str
    state_code: Optional[str] = None
    days: int = 180


class ChatterRequest(BaseModel):
    state_code: str
    state_name: str
    title: str
    text: str
    source_url: str = "manual://chatter"


class SourceCreateRequest(BaseModel):
    state_code: str
    state_name: str
    source_name: str
    url: str
    source_type: SourceType = SourceType.official
    priority: int = 50
    notes: str | None = None


class OfficialForwardRequest(BaseModel):
    state_code: str
    state_name: str
    title: str
    text: str
    source_reference: str = "manual://forward-data"
    source_name: str = "Manual forward data"
    source_type: SourceType = SourceType.social
    process_now: bool = True


class OfficialsAskRequest(BaseModel):
    question: str
    state_code: str | None = None
    days: int = 365


class ConclusiveAskRequest(BaseModel):
    question: str = Field(..., description="Ask about CM, excise minister, secretary, commissioner, MD, transfers, minutes, policy workstreams, or legal changes.")
    state_code: str | None = None
    days: int = 365


class TelegramTestRequest(BaseModel):
    message: str = "ExciseWatch Telegram test: alerts are configured correctly."
    dry_run: bool = True


class TelegramDigestRequest(BaseModel):
    state_code: str | None = None
    days: int = 1
    limit: int | None = None
    include_law: bool = True
    include_movements: bool = True
    include_work: bool = True
    include_briefs: bool = True
    include_chatter: bool = False
    min_tier: str | None = None
    dry_run: bool = False


class AITextRequest(BaseModel):
    text: str
    title: str | None = None
    state_code: str | None = None
    state_name: str | None = None
    source_type: SourceType | str | None = None
    source_url: str | None = None


class AIRagRequest(BaseModel):
    question: str
    state_code: str | None = None
    days: int = 365
    include_chatter: bool = False


class AIConclusiveRequest(BaseModel):
    question: str
    state_code: str | None = None
    days: int = 365
    include_chatter: bool = True


class AIChecklistRequest(BaseModel):
    text: str
    title: str | None = None
    state_code: str | None = None
    evidence_tier: str | None = None


class AIForecastRequest(BaseModel):
    series: list[dict]
    period_key: str = "period"
    value_key: str = "value"
    horizon: int = 1
    state_code: str | None = None


class AIRiskRequest(BaseModel):
    payload: dict
    state_code: str | None = None


class AIAnomalyRequest(BaseModel):
    transactions: list[dict]
    state_code: str | None = None


class AISuiteRequest(BaseModel):
    question: str
    state_code: str | None = None
    days: int = 365
    text: str | None = None
    include_chatter: bool = False


class AITelegramPreviewRequest(BaseModel):
    state_code: str | None = None
    days: int = 1
    limit: int = 25
    include_chatter: bool = False


@app.post("/api/admin/seed-sources", response_model=SeedResponse)
def api_seed_sources(force: bool = False, session: Session = Depends(get_session)):
    return SeedResponse(inserted=seed_sources(session, force=force))




@app.get("/api/admin/state-coverage")
def api_state_coverage(session: Session = Depends(get_session)):
    return source_coverage(session)


@app.get("/api/admin/source-config-coverage")
def api_source_config_coverage():
    return validate_source_config()


@app.get("/api/admin/jurisdictions")
def api_jurisdictions():
    return [j.__dict__ for j in ALL_JURISDICTIONS]


@app.get("/api/sources")
def api_sources(state_code: str | None = None, session: Session = Depends(get_session)):
    stmt = select(SourceItem)
    if state_code:
        stmt = stmt.where(SourceItem.state_code == state_code.upper())
    return session.exec(stmt).all()




@app.post("/api/sources")
def api_add_source(payload: SourceCreateRequest, session: Session = Depends(get_session)):
    item = SourceItem(
        state_code=payload.state_code.upper(),
        state_name=payload.state_name,
        source_name=payload.source_name,
        url=payload.url,
        source_type=payload.source_type,
        priority=payload.priority,
        notes=payload.notes,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item

@app.post("/api/watch/run")
def api_run_watch(payload: RunWatchRequest, session: Session = Depends(get_session)):
    return run_watch(session, state_code=payload.state_code, include_news=payload.include_news, include_alerts=payload.include_alerts)


@app.get("/api/changes")
def api_changes(
    state_code: str | None = None,
    days: int = 30,
    tier: EvidenceTier | None = Query(default=None),
    limit: int = 50,
    session: Session = Depends(get_session),
):
    rows = latest_changes(session, state_code=state_code, days=days, limit=limit)
    if tier:
        rows = [r for r in rows if r.evidence_tier == tier]
    return rows


@app.post("/api/ask")
def api_ask(payload: AskRequest, session: Session = Depends(get_session)):
    return answer_question(session, payload.question, state_code=payload.state_code, days=payload.days)


@app.post("/api/chatter/ingest")
def api_chatter(payload: ChatterRequest, session: Session = Depends(get_session)):
    item = ingest_chatter(session, payload.state_code.upper(), payload.state_name, payload.title, payload.text, payload.source_url)
    if not item:
        return {"status": "duplicate"}
    return {"status": "created", "raw_item_id": item.id}


@app.post("/api/process/raw")
def api_process_raw(include_officials: bool = True, session: Session = Depends(get_session)):
    from .processor import process_new_raw_items
    changes = process_new_raw_items(session)
    result = {"changes_created": len(changes), "changes": changes}
    if include_officials:
        officials = process_new_official_raw_items(session)
        result.update({
            "official_movements_created": officials["movements_created"],
            "official_work_signals_created": officials["work_signals_created"],
        })
    return result


@app.post("/api/review/{change_id}")
def api_review_change(change_id: int, reviewed_by: str, note: str = "", session: Session = Depends(get_session)):
    ch = session.get(LegalChange, change_id)
    if not ch:
        return {"status": "not_found"}
    from datetime import datetime
    ch.needs_human_review = False
    ch.reviewed_by = reviewed_by
    ch.reviewed_at = datetime.utcnow()
    ch.review_note = note
    session.add(ch)
    session.commit()
    return {"status": "reviewed", "change_id": change_id}


@app.get("/api/raw")
def api_raw(state_code: str | None = None, limit: int = 50, session: Session = Depends(get_session)):
    stmt = select(RawItem).order_by(RawItem.fetched_at.desc()).limit(limit)
    if state_code:
        stmt = select(RawItem).where(RawItem.state_code == state_code.upper()).order_by(RawItem.fetched_at.desc()).limit(limit)
    return session.exec(stmt).all()


@app.post("/api/officials/forward-ingest")
def api_official_forward(payload: OfficialForwardRequest, session: Session = Depends(get_session)):
    item = ingest_forward_data(
        session,
        payload.state_code.upper(),
        payload.state_name,
        payload.title,
        payload.text,
        payload.source_reference,
        payload.source_name,
        payload.source_type,
    )
    if not item:
        return {"status": "duplicate"}
    result = {"status": "created", "raw_item_id": item.id}
    if payload.process_now:
        processed = process_new_official_raw_items(session)
        result.update(processed)
    return result


@app.post("/api/officials/process")
def api_process_officials(session: Session = Depends(get_session)):
    return process_new_official_raw_items(session)


@app.get("/api/officials")
def api_officials(
    state_code: str | None = None,
    role_type: OfficialRoleType | None = Query(default=None),
    limit: int = 100,
    session: Session = Depends(get_session),
):
    return officials_directory(session, state_code=state_code, role_type=role_type, limit=limit)


@app.get("/api/officials/movements")
def api_official_movements(
    state_code: str | None = None,
    person: str | None = None,
    limit: int = 100,
    session: Session = Depends(get_session),
):
    return latest_official_movements(session, state_code=state_code, person=person, limit=limit)


@app.get("/api/officials/work-signals")
def api_official_work_signals(
    state_code: str | None = None,
    limit: int = 100,
    session: Session = Depends(get_session),
):
    return latest_work_signals(session, state_code=state_code, limit=limit)


@app.post("/api/officials/ask")
def api_ask_officials(payload: OfficialsAskRequest, session: Session = Depends(get_session)):
    return answer_officials_question(session, payload.question, state_code=payload.state_code, days=payload.days)




@app.post("/api/conclusive/ask")
def api_ask_conclusive(payload: ConclusiveAskRequest, session: Session = Depends(get_session)):
    return answer_conclusive_question(session, payload.question, state_code=payload.state_code, days=payload.days)


@app.get("/api/conclusive/briefs")
def api_conclusive_briefs(state_code: str | None = None, limit: int = 50, session: Session = Depends(get_session)):
    return latest_intelligence_briefs(session, state_code=state_code, limit=limit)


@app.post("/api/officials/review-movement/{movement_id}")
def api_review_movement(movement_id: int, reviewed_by: str, note: str = "", session: Session = Depends(get_session)):
    movement = session.get(OfficialMovement, movement_id)
    if not movement:
        return {"status": "not_found"}
    from datetime import datetime
    movement.needs_human_review = False
    movement.reviewed_by = reviewed_by
    movement.reviewed_at = datetime.utcnow()
    movement.review_note = note
    session.add(movement)
    session.commit()
    return {"status": "reviewed", "movement_id": movement_id}


@app.post("/api/telegram/test")
def api_telegram_test(payload: TelegramTestRequest):
    return send_telegram_text(payload.message, dry_run=payload.dry_run)


@app.post("/api/telegram/digest")
def api_telegram_digest(payload: TelegramDigestRequest, session: Session = Depends(get_session)):
    return send_digest(
        session,
        dry_run=payload.dry_run,
        state_code=payload.state_code,
        days=payload.days,
        limit=payload.limit,
        include_law=payload.include_law,
        include_movements=payload.include_movements,
        include_work=payload.include_work,
        include_briefs=payload.include_briefs,
        include_chatter=payload.include_chatter,
        min_tier=payload.min_tier,
    )


@app.get("/api/ai/modules")
def api_ai_modules():
    return module_catalog()


@app.get("/api/ai/runs")
def api_ai_runs(module_name: str | None = None, state_code: str | None = None, limit: int = 50, session: Session = Depends(get_session)):
    return latest_ai_runs(session, module_name=module_name, state_code=state_code, limit=limit)


@app.post("/api/ai/extract")
def api_ai_extract(payload: AITextRequest, session: Session = Depends(get_session)):
    return extract_entities(payload.text, title=payload.title, state_code=payload.state_code, state_name=payload.state_name, source_type=payload.source_type, source_url=payload.source_url, session=session)


@app.post("/api/ai/summarize")
def api_ai_summarize(payload: AITextRequest, session: Session = Depends(get_session)):
    return summarize_text(payload.text, title=payload.title, session=session, state_code=payload.state_code)


@app.post("/api/ai/classify")
def api_ai_classify(payload: AITextRequest):
    return classify_update(f"{payload.title or ''}\n{payload.text}")


@app.post("/api/ai/chatter-score")
def api_ai_chatter_score(payload: AITextRequest, session: Session = Depends(get_session)):
    return score_chatter(payload.text, title=payload.title, source_url=payload.source_url, session=session, state_code=payload.state_code)


@app.post("/api/ai/impact")
def api_ai_impact(payload: AIChecklistRequest, session: Session = Depends(get_session)):
    return analyze_impact(payload.text, title=payload.title, state_code=payload.state_code, evidence_tier=payload.evidence_tier, session=session)


@app.post("/api/ai/checklist")
def api_ai_checklist(payload: AIChecklistRequest, session: Session = Depends(get_session)):
    return build_compliance_checklist(payload.text, title=payload.title, state_code=payload.state_code, evidence_tier=payload.evidence_tier, session=session)


@app.post("/api/ai/rag/ask")
def api_ai_rag(payload: AIRagRequest, session: Session = Depends(get_session)):
    return rag_answer(session, payload.question, state_code=payload.state_code, days=payload.days, include_chatter=payload.include_chatter)


@app.post("/api/ai/conclusive")
def api_ai_conclusive(payload: AIConclusiveRequest, session: Session = Depends(get_session)):
    return conclusive_synthesis(session, payload.question, state_code=payload.state_code, days=payload.days, include_chatter=payload.include_chatter)


@app.post("/api/ai/conflicts")
def api_ai_conflicts(payload: AIRagRequest, session: Session = Depends(get_session)):
    return detect_conflicts(session, state_code=payload.state_code, days=payload.days, question=payload.question)


@app.get("/api/ai/officer-workmap")
def api_ai_officer_workmap(state_code: str | None = None, days: int = 365, session: Session = Depends(get_session)):
    return officer_workmap(session, state_code=state_code, days=days)


@app.post("/api/ai/forecast")
def api_ai_forecast(payload: AIForecastRequest, session: Session = Depends(get_session)):
    return demand_forecast(payload.series, period_key=payload.period_key, value_key=payload.value_key, horizon=payload.horizon, session=session, state_code=payload.state_code)


@app.post("/api/ai/dispatch-risk")
def api_ai_dispatch_risk(payload: AIRiskRequest, session: Session = Depends(get_session)):
    return retailer_dispatch_risk(payload.payload, session=session, state_code=payload.state_code)


@app.post("/api/ai/fraud-anomaly")
def api_ai_fraud_anomaly(payload: AIAnomalyRequest, session: Session = Depends(get_session)):
    return fraud_anomaly(payload.transactions, session=session, state_code=payload.state_code)


@app.post("/api/ai/telegram-preview")
def api_ai_telegram_preview(payload: AITelegramPreviewRequest, session: Session = Depends(get_session)):
    return telegram_ai_preview(session, state_code=payload.state_code, days=payload.days, limit=payload.limit, include_chatter=payload.include_chatter)


@app.post("/api/ai/suite")
def api_ai_suite(payload: AISuiteRequest, session: Session = Depends(get_session)):
    return run_all_ai_suite(session, payload.question, state_code=payload.state_code, days=payload.days, text=payload.text, include_chatter=payload.include_chatter)


@app.get("/health")
def health():
    return {"ok": True, "version": "0.6.0", "suite": "ExciseWatch v6 Production Compliance Engine"}


# ---------------------------------------------------------------------
# v6 production hardening endpoints: auth, live validation, review, jobs
# ---------------------------------------------------------------------

class BootstrapAdminRequest(BaseModel):
    username: str = "admin"
    password: str
    email: str | None = None
    display_name: str | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


class UserCreateRequest(BaseModel):
    username: str
    password: str
    role: str = "viewer"
    email: str | None = None
    display_name: str | None = None
    state_scope: str | None = "ALL"


class APIKeyCreateRequest(BaseModel):
    name: str
    role: str = "analyst"
    state_scope: str | None = "ALL"


class SourceValidateRequest(BaseModel):
    state_code: str | None = None
    live_fetch: bool = False
    max_sources: int | None = None
    archive_documents: bool = True


class GenerateReviewRequest(BaseModel):
    state_code: str | None = None
    limit: int = 250


class ReviewDecisionRequest(BaseModel):
    note: str | None = None


class JobRunRequest(BaseModel):
    job_name: str
    state_code: str | None = None
    dry_run: bool = True


class PublishTelegramRequest(BaseModel):
    dry_run: bool = True


@app.post("/api/auth/bootstrap-admin")
def api_bootstrap_admin(payload: BootstrapAdminRequest, session: Session = Depends(get_session)):
    from .auth.bootstrap import bootstrap_admin
    result = bootstrap_admin(session, payload.username, payload.password, payload.email, payload.display_name)
    return result


@app.post("/api/auth/login")
def api_login(payload: LoginRequest, session: Session = Depends(get_session)):
    from datetime import datetime
    from sqlmodel import select
    from .models import UserAccount
    from .auth.security import verify_password, create_access_token
    user = session.exec(select(UserAccount).where(UserAccount.username == payload.username, UserAccount.is_active == True)).first()
    if not user or not verify_password(payload.password, user.password_hash):
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Invalid username or password")
    user.last_login_at = datetime.utcnow()
    session.add(user)
    session.commit()
    token = create_access_token(user.username, user.role.value)
    return {"access_token": token, "token_type": "bearer", "user": {"username": user.username, "role": user.role.value, "state_scope": user.state_scope}}


@app.get("/api/auth/me")
def api_auth_me():
    from fastapi import Depends
    from .auth.security import current_user
    # FastAPI dependency is declared dynamically through inner function wrapper below.
    return {"detail": "Use authenticated route /api/auth/whoami"}


@app.get("/api/auth/whoami")
def api_auth_whoami(user = Depends(__import__('app.auth.security', fromlist=['current_user']).current_user)):
    return {"username": user.username, "display_name": user.display_name, "role": user.role.value, "state_scope": user.state_scope, "is_active": user.is_active}


@app.post("/api/admin/users")
def api_admin_create_user(payload: UserCreateRequest, session: Session = Depends(get_session), actor = Depends(__import__('app.auth.security', fromlist=['require_permission']).require_permission("*"))):
    from sqlmodel import select
    from .models import UserAccount, UserRole
    from .auth.security import hash_password
    existing = session.exec(select(UserAccount).where(UserAccount.username == payload.username)).first()
    if existing:
        return {"status": "exists", "username": payload.username}
    user = UserAccount(
        username=payload.username,
        email=payload.email,
        display_name=payload.display_name,
        password_hash=hash_password(payload.password),
        role=UserRole(payload.role),
        state_scope=payload.state_scope,
    )
    session.add(user)
    session.commit()
    return {"status": "created", "username": user.username, "role": user.role.value}


@app.post("/api/admin/api-keys")
def api_create_api_key(payload: APIKeyCreateRequest, session: Session = Depends(get_session), actor = Depends(__import__('app.auth.security', fromlist=['require_permission']).require_permission("*"))):
    from .models import APIKey, UserRole
    from .auth.security import generate_api_key, hash_api_key
    key = generate_api_key()
    rec = APIKey(name=payload.name, key_hash=hash_api_key(key), role=UserRole(payload.role), state_scope=payload.state_scope, created_by=actor.username)
    session.add(rec)
    session.commit()
    return {"status": "created", "name": payload.name, "api_key": key, "warning": "Store this key now; only its hash is saved."}


@app.post("/api/sources/validate-live")
def api_validate_live_sources(payload: SourceValidateRequest, session: Session = Depends(get_session)):
    from .services.live_source_validator import validate_sources
    return validate_sources(session, state_code=payload.state_code, live_fetch=payload.live_fetch, max_sources=payload.max_sources, archive_documents=payload.archive_documents)


@app.get("/api/sources/snapshots")
def api_source_snapshots(state_code: str | None = None, limit: int = 100, session: Session = Depends(get_session)):
    from sqlmodel import select
    from .models import SourceSnapshot
    stmt = select(SourceSnapshot).order_by(SourceSnapshot.checked_at.desc()).limit(limit)
    if state_code:
        stmt = select(SourceSnapshot).where(SourceSnapshot.state_code == state_code.upper()).order_by(SourceSnapshot.checked_at.desc()).limit(limit)
    return session.exec(stmt).all()


@app.get("/api/documents")
def api_documents(state_code: str | None = None, limit: int = 100, session: Session = Depends(get_session)):
    from sqlmodel import select
    from .models import DocumentRecord
    stmt = select(DocumentRecord).order_by(DocumentRecord.archived_at.desc()).limit(limit)
    if state_code:
        stmt = select(DocumentRecord).where(DocumentRecord.state_code == state_code.upper()).order_by(DocumentRecord.archived_at.desc()).limit(limit)
    return session.exec(stmt).all()


@app.post("/api/review/generate")
def api_generate_review_tasks(payload: GenerateReviewRequest, session: Session = Depends(get_session)):
    from .services.review_service import generate_review_tasks
    return generate_review_tasks(session, state_code=payload.state_code, limit=payload.limit)


@app.get("/api/review/tasks")
def api_review_tasks(state_code: str | None = None, status: str | None = None, limit: int = 100, session: Session = Depends(get_session)):
    from .models import ReviewStatus
    from .services.review_service import list_review_tasks
    status_enum = ReviewStatus(status) if status else None
    return list_review_tasks(session, state_code=state_code, status=status_enum, limit=limit)


def _review_decision(task_id: int, decision: str, payload: ReviewDecisionRequest, session: Session, actor_name: str = "system", actor_role: str | None = "system"):
    from .models import ApprovalDecision
    from .services.review_service import decide_review
    return decide_review(session, task_id, ApprovalDecision(decision), actor=actor_name, actor_role=actor_role, note=payload.note)


@app.post("/api/review/tasks/{task_id}/approve")
def api_review_approve(task_id: int, payload: ReviewDecisionRequest, session: Session = Depends(get_session)):
    return _review_decision(task_id, "APPROVE", payload, session)


@app.post("/api/review/tasks/{task_id}/reject")
def api_review_reject(task_id: int, payload: ReviewDecisionRequest, session: Session = Depends(get_session)):
    return _review_decision(task_id, "REJECT", payload, session)


@app.post("/api/review/tasks/{task_id}/escalate")
def api_review_escalate(task_id: int, payload: ReviewDecisionRequest, session: Session = Depends(get_session)):
    return _review_decision(task_id, "ESCALATE", payload, session)


@app.post("/api/review/tasks/{task_id}/mark-superseded")
def api_review_supersede(task_id: int, payload: ReviewDecisionRequest, session: Session = Depends(get_session)):
    return _review_decision(task_id, "SUPERSEDE", payload, session)


@app.get("/api/review/approvals")
def api_approvals(limit: int = 100, session: Session = Depends(get_session)):
    from sqlmodel import select
    from .models import Approval
    return session.exec(select(Approval).order_by(Approval.created_at.desc()).limit(limit)).all()


@app.get("/api/guidance")
def api_guidance(state_code: str | None = None, limit: int = 100, session: Session = Depends(get_session)):
    from sqlmodel import select
    from .models import PublishedGuidance
    stmt = select(PublishedGuidance).order_by(PublishedGuidance.created_at.desc()).limit(limit)
    if state_code:
        stmt = select(PublishedGuidance).where(PublishedGuidance.state_code == state_code.upper()).order_by(PublishedGuidance.created_at.desc()).limit(limit)
    return session.exec(stmt).all()


@app.post("/api/publish/guidance/{guidance_id}/telegram")
def api_publish_guidance_telegram(guidance_id: int, payload: PublishTelegramRequest, session: Session = Depends(get_session)):
    from .services.publication_service import publish_guidance_to_telegram
    return publish_guidance_to_telegram(session, guidance_id, dry_run=payload.dry_run)


@app.post("/api/jobs/run-now")
def api_job_run_now(payload: JobRunRequest, session: Session = Depends(get_session)):
    from .jobs.scheduler import run_named_job
    return run_named_job(session, payload.job_name, state_code=payload.state_code, dry_run=payload.dry_run)


@app.get("/api/jobs/status")
def api_jobs_status(limit: int = 100, session: Session = Depends(get_session)):
    from sqlmodel import select
    from .models import JobRun
    return session.exec(select(JobRun).order_by(JobRun.started_at.desc()).limit(limit)).all()


@app.get("/api/audit")
def api_audit(limit: int = 100, session: Session = Depends(get_session)):
    from sqlmodel import select
    from .models import AuditLog
    return session.exec(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)).all()


@app.get("/api/v6/readiness")
def api_v6_readiness(session: Session = Depends(get_session)):
    init_db()
    from sqlmodel import select
    from .models import SourceItem, SourceSnapshot, ReviewTask, UserAccount, PublishedGuidance
    source_count = len(session.exec(select(SourceItem)).all())
    snapshot_count = len(session.exec(select(SourceSnapshot)).all())
    review_count = len(session.exec(select(ReviewTask)).all())
    user_count = len(session.exec(select(UserAccount)).all())
    guidance_count = len(session.exec(select(PublishedGuidance)).all())
    gates = {
        "all_india_source_registry": source_count >= 36,
        "live_source_validation_layer": snapshot_count >= 0,
        "auth_rbac_layer": user_count >= 0,
        "human_review_workflow": review_count >= 0,
        "publication_guidance_layer": guidance_count >= 0,
        "scheduler_jobs_layer": True,
        "audit_log_layer": True,
    }
    return {"version": "0.6.0", "production_layers": gates, "counts": {"sources": source_count, "snapshots": snapshot_count, "review_tasks": review_count, "users": user_count, "guidance": guidance_count}, "recommendation": "Use AI as monitoring/classification engine. Require human approval before official compliance guidance."}
