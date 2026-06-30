from sqlmodel import Session
from app.db import init_db, engine
from app.source_registry import seed_sources
from app.watch import run_watch

if __name__ == "__main__":
    init_db()
    with Session(engine) as session:
        seed_sources(session)
        result = run_watch(session, include_news=True, include_alerts=False)
        print(result)
