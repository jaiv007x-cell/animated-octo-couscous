from __future__ import annotations

import argparse
from sqlmodel import Session
from app.db import engine, init_db
from app.telegram_updates import send_digest


def main() -> None:
    parser = argparse.ArgumentParser(description="Send ExciseWatch Telegram digest")
    parser.add_argument("--state-code", default=None, help="Optional state/UT code, e.g. DL, MH, KA. Omit for all India.")
    parser.add_argument("--days", type=int, default=1, help="Lookback window in days.")
    parser.add_argument("--limit", type=int, default=None, help="Max items per section.")
    parser.add_argument("--include-chatter", action="store_true", help="Include CHATTER_UNVERIFIED items.")
    parser.add_argument("--min-tier", default=None, help="Minimum evidence tier, e.g. OFFICIAL_CONFIRMED, GOVT_PROBABLE, REPORTED_NOT_CONFIRMED.")
    parser.add_argument("--dry-run", action="store_true", help="Do not send; print preview payload.")
    args = parser.parse_args()

    init_db()
    with Session(engine) as session:
        result = send_digest(
            session,
            dry_run=args.dry_run,
            state_code=args.state_code,
            days=args.days,
            limit=args.limit,
            include_chatter=args.include_chatter,
            min_tier=args.min_tier,
        )
    print(result)


if __name__ == "__main__":
    main()
