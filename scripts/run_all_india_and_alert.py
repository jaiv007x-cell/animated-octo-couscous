from __future__ import annotations

import argparse
from sqlmodel import Session
from app.db import engine, init_db
from app.source_registry import seed_sources
from app.watch import run_watch
from app.telegram_updates import send_digest


def main() -> None:
    parser = argparse.ArgumentParser(description="Run all-India ExciseWatch monitor and send Telegram digest")
    parser.add_argument("--days", type=int, default=1)
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--include-news", action="store_true", default=True)
    parser.add_argument("--include-chatter", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    init_db()
    with Session(engine) as session:
        seed_sources(session, force=False)
        watch = run_watch(session, state_code=None, include_news=args.include_news, include_alerts=False)
        digest = send_digest(
            session,
            dry_run=args.dry_run,
            days=args.days,
            limit=args.limit,
            include_chatter=args.include_chatter,
        )
    print({"watch": watch, "telegram": digest})


if __name__ == "__main__":
    main()
