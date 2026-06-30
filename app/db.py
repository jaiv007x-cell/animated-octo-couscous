from pathlib import Path
from sqlmodel import SQLModel, Session, create_engine
from .settings import get_settings

_settings = get_settings()
Path("storage").mkdir(exist_ok=True)
connect_args = {"check_same_thread": False} if _settings.database_url.startswith("sqlite") else {}
engine = create_engine(_settings.database_url, connect_args=connect_args)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
