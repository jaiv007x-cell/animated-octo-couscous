from __future__ import annotations
from datetime import datetime
from sqlmodel import Session, select
from .models import SourceType, WatchRun, SourceItem
from .source_registry import get_active_sources
from .collectors.official import collect_official_source
from .collectors.news import collect_google_news
from .processor import process_new_raw_items
from .officials import process_new_official_raw_items
from .alerts import send_alerts


def run_watch(session: Session, state_code: str | None = None, include_news: bool = True, include_alerts: bool = False) -> dict:
    run = WatchRun(states_requested=state_code or "ALL")
    session.add(run)
    session.commit()
    errors: list[str] = []
    official_count = 0
    news_count = 0

    try:
        official_sources = get_active_sources(
            session,
            state_code=state_code,
            types=[SourceType.official, SourceType.gazette, SourceType.regulator, SourceType.court],
        )
        for src in official_sources:
            try:
                official_count += len(collect_official_source(session, src))
            except Exception as e:
                errors.append(f"{src.state_code} {src.source_name}: {e}")

        if include_news:
            states = {}
            if state_code:
                srcs = list(session.exec(select(SourceItem).where(SourceItem.state_code == state_code.upper())).all())
            else:
                srcs = list(session.exec(select(SourceItem)).all())
            for src in srcs:
                states[src.state_code] = src.state_name
            for code, name in states.items():
                try:
                    news_count += len(collect_google_news(session, code, name))
                except Exception as e:
                    errors.append(f"news {code}: {e}")

        changes = process_new_raw_items(session)
        official_result = process_new_official_raw_items(session)
        if include_alerts and changes:
            alert_result = send_alerts(changes)
            if alert_result.get("errors"):
                errors.extend(alert_result["errors"])

        run.status = "ok" if not errors else "partial"
        run.official_items = official_count
        run.news_items = news_count
        run.changes_created = len(changes)
        run.errors = "\n".join(errors) if errors else None
        run.finished_at = datetime.utcnow()
        session.add(run)
        session.commit()
        return {
            "status": run.status,
            "official_items": official_count,
            "news_items": news_count,
            "changes_created": len(changes),
            "official_movements_created": official_result.get("movements_created", 0),
            "official_work_signals_created": official_result.get("work_signals_created", 0),
            "errors": errors,
        }
    except Exception as e:
        run.status = "error"
        run.errors = str(e)
        run.finished_at = datetime.utcnow()
        session.add(run)
        session.commit()
        raise
