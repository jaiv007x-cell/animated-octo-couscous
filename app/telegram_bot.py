from __future__ import annotations

import time
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import requests
from sqlmodel import Session, select

from .ai_modules import conclusive_synthesis
from .answer_engine import answer_question
from .db import engine, init_db
from .models import (
    IntelligenceBrief,
    LegalChange,
    OfficialMovement,
    RawItem,
    SourceType,
    SourceItem,
    WatchRun,
    WorkSignal,
)
from .processor import process_new_raw_items
from .collectors.news import is_excise_news_text
from .settings import get_settings
from .services.news_feed_service import run_latest_news_feed
from .source_registry import seed_sources
from .telegram_updates import build_digest_text, split_telegram_message
from .watch import run_watch


HELP_TEXT = """ExciseWatch bot is online.

Commands:
/id - show this chat id
/health - check bot and database
/status - show local database counts
/latest [STATE] - show latest fetched source items
/news [STATE] - show latest reported news intelligence
/feednews [STATE|ALL] [MAX] [DAYS] - ingest latest news and send digest
/digest [STATE] [DAYS] - send latest digest, e.g. /digest DL 7
/ask [STATE] question - ask the local compliance database
/conclusive STATE question - give evidence-ranked final status
/hunt STATE question - fetch, process, then run conclusive status
/process - classify fetched raw items into legal changes
/watch STATE - fetch one state only, e.g. /watch DL
"""


@dataclass
class ParsedCommand:
    command: str
    args: list[str]


def parse_command(text: str) -> ParsedCommand | None:
    text = (text or "").strip()
    if not text.startswith("/"):
        return None
    parts = text.split()
    command = parts[0].split("@", 1)[0].lower()
    return ParsedCommand(command=command, args=parts[1:])


def parse_state_days(args: list[str], default_days: int = 1) -> tuple[str | None, int]:
    state_code: str | None = None
    days = default_days
    if args:
        first = args[0].upper()
        if first.isalpha() and 2 <= len(first) <= 5:
            state_code = first
            args = args[1:]
    if args:
        try:
            days = max(1, min(int(args[0]), 365))
        except ValueError:
            days = default_days
    return state_code, days


def parse_state_question(args: list[str]) -> tuple[str | None, str]:
    if args and args[0].isalpha() and 2 <= len(args[0]) <= 5:
        return args[0].upper(), " ".join(args[1:]).strip()
    return None, " ".join(args).strip()


def format_conclusive_result(result: dict[str, Any], state_code: str | None, question: str) -> str:
    lines = [
        f"Conclusive check: {state_code or 'ALL'}",
        f"Question: {question}",
        f"Status: {result.get('answer_status')}",
        f"Definitive: {result.get('definitive')}",
        f"Evidence tier: {result.get('evidence_tier')} | Confidence: {result.get('confidence')}",
        f"Sources: official={result.get('official_source_count', 0)}, govt_probable={result.get('govt_probable_count', 0)}, news={result.get('news_source_count', 0)}, chatter={result.get('chatter_source_count', 0)}, conflicts={result.get('conflict_count', 0)}",
        "",
        str(result.get("conclusion") or "No conclusion returned."),
    ]
    top_sources = result.get("top_sources") or []
    if top_sources:
        lines.append("")
        lines.append("Top sources:")
        for item in top_sources[:5]:
            lines.append(f"- [{item.get('tier')}] {item.get('state')}: {item.get('title')}")
            if item.get("url"):
                lines.append(f"  {item.get('url')}")
    if not result.get("definitive"):
        lines.extend([
            "",
            "Not conclusive means: do not act as law yet. Hunt again after official order/gazette/circular is available, or add the official document manually.",
        ])
    return "\n".join(lines)


def _api_url(token: str, method: str) -> str:
    return f"https://api.telegram.org/bot{token}/{method}"


def send_message(token: str, chat_id: int | str, text: str) -> dict[str, Any]:
    settings = get_settings()
    sent = 0
    errors: list[str] = []
    for chunk in split_telegram_message(text):
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": chunk,
            "disable_web_page_preview": settings.telegram_disable_web_page_preview,
        }
        if settings.telegram_parse_mode:
            payload["parse_mode"] = settings.telegram_parse_mode
        try:
            response = requests.post(_api_url(token, "sendMessage"), json=payload, timeout=20)
            response.raise_for_status()
            sent += 1
        except Exception as exc:
            errors.append(str(exc))
    return {"sent": sent, "errors": errors}


def run_watch_background(chat_id: int | str, state_code: str) -> None:
    token = get_settings().telegram_bot_token or ""
    try:
        init_db()
        with Session(engine) as session:
            seed_sources(session, force=False)
            result = run_watch(session, state_code=state_code, include_news=True, include_alerts=False)
            raw_count = len(session.exec(select(RawItem).where(RawItem.state_code == state_code)).all())
            change_count = len(session.exec(select(LegalChange).where(LegalChange.state_code == state_code)).all())
        send_message(token, chat_id, f"Watch complete for {state_code}: {result}\nLocal totals: raw_items={raw_count}, legal_changes={change_count}")
    except Exception as exc:
        send_message(token, chat_id, f"Watch failed for {state_code}: {exc}")


def run_hunt_background(chat_id: int | str, state_code: str, question: str) -> None:
    token = get_settings().telegram_bot_token or ""
    try:
        init_db()
        with Session(engine) as session:
            seed_sources(session, force=False)
            watch_result = run_watch(session, state_code=state_code, include_news=True, include_alerts=False)
            changes = process_new_raw_items(session)
            result = conclusive_synthesis(session, question, state_code=state_code, days=365, include_chatter=False)
        prefix = (
            f"Hunt complete for {state_code}: "
            f"official_items={watch_result.get('official_items', 0)}, "
            f"news_items={watch_result.get('news_items', 0)}, "
            f"new_changes={watch_result.get('changes_created', 0) + len(changes)}"
        )
        errors = watch_result.get("errors") or []
        error_text = "\nFetch warnings:\n" + "\n".join(f"- {err}" for err in errors[:5]) if errors else ""
        send_message(token, chat_id, f"{prefix}{error_text}\n\n{format_conclusive_result(result, state_code, question)}")
    except Exception as exc:
        send_message(token, chat_id, f"Hunt failed for {state_code}: {exc}")


def run_feednews_background(chat_id: int | str, state_code: str | None, max_items_per_state: int = 10, days: int = 7) -> None:
    token = get_settings().telegram_bot_token or ""
    try:
        init_db()
        with Session(engine) as session:
            result = run_latest_news_feed(
                session,
                state_code=state_code,
                max_items_per_state=max_items_per_state,
                days=days,
                send_telegram=True,
            )
        summary = (
            f"Latest news feed complete: states_checked={result['states_checked']}, "
            f"raw_created={result['raw_items_created']}, changes_created={result['legal_changes_created']}, "
            f"telegram_chunks={result['telegram'].get('sent', 0)}, errors={len(result['errors'])}"
        )
        if result["errors"]:
            summary += "\nWarnings:\n" + "\n".join(f"- {err}" for err in result["errors"][:8])
        send_message(token, chat_id, summary)
    except Exception as exc:
        send_message(token, chat_id, f"Latest news feed failed: {exc}")


def start_daemon(target, *args: Any) -> None:
    thread = threading.Thread(target=target, args=args, daemon=True)
    thread.start()


def latest_update_offset(token: str) -> int | None:
    try:
        response = requests.get(_api_url(token, "getUpdates"), params={"limit": 1, "offset": -1}, timeout=20)
        response.raise_for_status()
        updates = response.json().get("result", [])
    except Exception:
        return None
    if not updates:
        return None
    return int(updates[-1]["update_id"]) + 1


def handle_text(chat_id: int | str, text: str) -> str:
    parsed = parse_command(text)
    if not parsed:
        return "Send /help to see available commands."

    if parsed.command in {"/start", "/help"}:
        return HELP_TEXT

    if parsed.command == "/id":
        return f"Chat id: {chat_id}"

    if parsed.command == "/health":
        init_db()
        with Session(engine) as session:
            inserted = seed_sources(session, force=False)
        return f"OK. Database initialized. Source seed inserted: {inserted}."

    if parsed.command == "/status":
        init_db()
        with Session(engine) as session:
            counts = {
                "sources": len(session.exec(select(SourceItem)).all()),
                "raw_items": len(session.exec(select(RawItem)).all()),
                "legal_changes": len(session.exec(select(LegalChange)).all()),
                "official_movements": len(session.exec(select(OfficialMovement)).all()),
                "work_signals": len(session.exec(select(WorkSignal)).all()),
                "briefs": len(session.exec(select(IntelligenceBrief)).all()),
            }
            last_watch = session.exec(select(WatchRun).order_by(WatchRun.started_at.desc()).limit(1)).first()
        lines = ["ExciseWatch status:"]
        lines.extend(f"{key}: {value}" for key, value in counts.items())
        if last_watch:
            lines.append(
                f"last_watch: {last_watch.status} | states={last_watch.states_requested} | "
                f"official={last_watch.official_items} | news={last_watch.news_items} | changes={last_watch.changes_created}"
            )
        if counts["legal_changes"] == 0 and counts["raw_items"] > 0:
            lines.append("Tip: run /process to classify fetched raw items.")
        return "\n".join(lines)

    if parsed.command == "/latest":
        state_code, _days = parse_state_days(parsed.args, default_days=1)
        init_db()
        with Session(engine) as session:
            stmt = select(LegalChange).order_by(LegalChange.detected_at.desc()).limit(5)
            raw_stmt = select(RawItem).order_by(RawItem.fetched_at.desc()).limit(5)
            if state_code:
                stmt = select(LegalChange).where(LegalChange.state_code == state_code).order_by(LegalChange.detected_at.desc()).limit(5)
                raw_stmt = select(RawItem).where(RawItem.state_code == state_code).order_by(RawItem.fetched_at.desc()).limit(5)
            changes = session.exec(stmt).all()
            raw_items = session.exec(raw_stmt).all()
        lines = [f"Latest items for {state_code or 'ALL'}:"]
        if changes:
            lines.append("Processed legal changes:")
            lines.extend(f"- {item.state_code}: {item.title}" for item in changes)
        if raw_items:
            lines.append("Fetched raw items:")
            lines.extend(f"- {item.state_code}: {item.title}\n  {item.url}" for item in raw_items)
        if not changes and not raw_items:
            lines.append("No local items yet. Run /watch DL for a state-specific fetch.")
        return "\n".join(lines)

    if parsed.command == "/news":
        state_code, days = parse_state_days(parsed.args, default_days=7)
        since = datetime.utcnow() - timedelta(days=days)
        init_db()
        with Session(engine) as session:
            stmt = select(LegalChange).where(LegalChange.source_type == SourceType.news, LegalChange.published_at >= since).order_by(LegalChange.published_at.desc()).limit(40)
            if state_code:
                stmt = select(LegalChange).where(LegalChange.source_type == SourceType.news, LegalChange.state_code == state_code, LegalChange.published_at >= since).order_by(LegalChange.published_at.desc()).limit(40)
            items = [
                item for item in session.exec(stmt).all()
                if is_excise_news_text(item.title)
            ][:10]
        lines = [
            f"Latest news intelligence for {state_code or 'ALL'} ({days} day lookback)",
            "Evidence label: REPORTED_NOT_CONFIRMED unless official source confirms.",
            "",
        ]
        if not items:
            lines.append("No recent news items found yet. Run /feednews ALL 8 or /feednews KA 10.")
        for idx, item in enumerate(items, 1):
            lines.extend([
                f"{idx}. {item.state_name} ({item.state_code}) [{item.evidence_tier.value}]",
                item.title,
                f"Type: {item.change_type.value}",
                f"Source: {item.source_url}",
                "",
            ])
        return "\n".join(lines).strip()

    if parsed.command == "/feednews":
        state_code = None
        max_items = 10
        days = 7
        args = list(parsed.args)
        if args:
            first = args.pop(0).upper()
            if first != "ALL":
                state_code = first
        if args:
            try:
                max_items = max(1, min(int(args[0]), 30))
            except ValueError:
                max_items = 10
        if args:
            try:
                days = max(1, min(int(args[0]), 90))
            except ValueError:
                days = 7
        start_daemon(run_feednews_background, chat_id, state_code, max_items, days)
        scope = state_code or "ALL INDIA"
        return f"Latest news feed started for {scope} ({days} day lookback). I will send the digest and completion summary when done. Use /news while it runs."

    if parsed.command == "/digest":
        state_code, days = parse_state_days(parsed.args, default_days=1)
        init_db()
        with Session(engine) as session:
            return build_digest_text(session, state_code=state_code, days=days)

    if parsed.command == "/ask":
        state_code, question = parse_state_question(parsed.args)
        if not question:
            return "Usage: /ask [STATE] your question"
        init_db()
        with Session(engine) as session:
            result = answer_question(session, question, state_code=state_code)
        sources = result.get("sources", [])
        source_lines = [f"- {s.get('title')} ({s.get('tier')})" for s in sources[:3]]
        suffix = "\n\nTop sources:\n" + "\n".join(source_lines) if source_lines else ""
        return f"{result.get('answer')}{suffix}"

    if parsed.command == "/conclusive":
        state_code, question = parse_state_question(parsed.args)
        if not state_code or not question:
            return "Usage: /conclusive STATE question, e.g. /conclusive DL licence fee increase"
        init_db()
        with Session(engine) as session:
            result = conclusive_synthesis(session, question, state_code=state_code, days=365, include_chatter=False)
        return format_conclusive_result(result, state_code, question)

    if parsed.command == "/hunt":
        state_code, question = parse_state_question(parsed.args)
        if not state_code or not question:
            return "Usage: /hunt STATE question, e.g. /hunt DL licence fee increase"
        start_daemon(run_hunt_background, chat_id, state_code, question)
        return f"Hunt started for {state_code}. I will send the conclusive result when fetching/processing finishes. Meanwhile /status and /latest will still work."

    if parsed.command == "/process":
        init_db()
        with Session(engine) as session:
            changes = process_new_raw_items(session)
            lines = [f"- {item.state_code}: {item.title}" for item in changes[:10]]
        if not changes:
            return "No new legal changes were classified from the fetched raw items."
        return "Classified legal changes:\n" + "\n".join(lines)

    if parsed.command == "/watch":
        if not parsed.args:
            return "Please provide a state code, e.g. /watch DL. All-India watch is disabled inside Telegram so the bot stays responsive."
        if parsed.args[0].upper() == "ALL":
            return "All-India watch is disabled inside Telegram because it can block replies for several minutes. Use a state code like /watch KA, or run all-India from the local API/server job."
        else:
            state_code, _days = parse_state_days(parsed.args, default_days=1)
            if not state_code:
                return "Please provide a valid state code, e.g. /watch DL."
        start_daemon(run_watch_background, chat_id, state_code)
        return f"Watch started for {state_code}. I will send completion details when it finishes. Meanwhile /status and /latest will still work."

    return "Unknown command. Send /help to see available commands."


def run_polling(poll_interval: float = 2.0) -> None:
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured.")

    token = settings.telegram_bot_token
    offset: int | None = latest_update_offset(token)
    init_db()
    print("ExciseWatch Telegram polling bot started.")
    while True:
        params: dict[str, Any] = {"timeout": 30, "allowed_updates": ["message"]}
        if offset is not None:
            params["offset"] = offset
        try:
            response = requests.get(_api_url(token, "getUpdates"), params=params, timeout=35)
            response.raise_for_status()
            updates = response.json().get("result", [])
        except Exception as exc:
            print(f"Polling error: {exc}")
            time.sleep(poll_interval)
            continue

        for update in updates:
            offset = int(update["update_id"]) + 1
            message = update.get("message") or {}
            chat = message.get("chat") or {}
            chat_id = chat.get("id")
            text = message.get("text") or ""
            if chat_id is None or not text:
                continue
            try:
                reply = handle_text(chat_id, text)
            except Exception as exc:
                reply = f"Command failed: {exc}"
            result = send_message(token, chat_id, reply)
            if result["errors"]:
                print(f"Send error for chat {chat_id}: {result['errors']}")

        time.sleep(poll_interval)
