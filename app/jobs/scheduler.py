from __future__ import annotations
import json
from datetime import datetime
from sqlmodel import Session
from app.models import JobRun
from app.services.live_source_validator import validate_sources
from app.services.news_feed_service import run_latest_news_feed
from app.watch import run_watch
from app.services.review_service import generate_review_tasks
from app.telegram_updates import send_digest


def run_named_job(session: Session, job_name: str, state_code: str | None = None, dry_run: bool = True) -> dict:
    run = JobRun(job_name=job_name, state_code=state_code, status="running")
    session.add(run)
    session.commit()
    session.refresh(run)
    try:
        if job_name == "validate_sources":
            result = validate_sources(session, state_code=state_code, live_fetch=not dry_run)
        elif job_name == "watch_sources":
            result = run_watch(session, state_code=state_code, include_news=True, include_alerts=False)
        elif job_name == "generate_review_tasks":
            result = generate_review_tasks(session, state_code=state_code)
        elif job_name == "telegram_digest":
            result = send_digest(session, state_code=state_code, dry_run=dry_run, include_chatter=False)
        elif job_name == "latest_news_feed":
            result = run_latest_news_feed(
                session,
                state_code=state_code,
                max_items_per_state=10,
                days=7,
                send_telegram=not dry_run,
            )
        else:
            raise ValueError(f"Unknown job: {job_name}")
        run.status = "success"
        run.result_json = json.dumps(result, default=str)[:200000]
    except Exception as exc:
        run.status = "failed"
        run.error = str(exc)[:1000]
        result = {"error": str(exc)}
    run.finished_at = datetime.utcnow()
    session.add(run)
    session.commit()
    return {"job_run_id": run.id, "job_name": job_name, "status": run.status, "result": result}


JOB_NAMES = ["validate_sources", "watch_sources", "latest_news_feed", "generate_review_tasks", "telegram_digest"]
