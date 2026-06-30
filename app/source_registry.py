from pathlib import Path
from typing import Any
import yaml
from sqlmodel import Session, select
from .models import SourceItem, SourceType
from .settings import get_settings
from .india_states import validate_all_india_coverage


def load_source_config(path: str | None = None) -> dict[str, Any]:
    settings = get_settings()
    cfg_path = Path(path or settings.source_config_path)
    if not cfg_path.exists():
        raise FileNotFoundError(f"Source config not found: {cfg_path}")
    return yaml.safe_load(cfg_path.read_text(encoding="utf-8"))



def validate_source_config(path: str | None = None) -> dict:
    cfg = load_source_config(path)
    codes = {str(state.get("code", "")).upper() for state in cfg.get("states", []) if state.get("code")}
    coverage = validate_all_india_coverage(codes)
    coverage["source_config_path"] = str(Path(path or get_settings().source_config_path))
    coverage["configured_codes"] = sorted(codes)
    return coverage

def seed_sources(session: Session, force: bool = False) -> int:
    existing = session.exec(select(SourceItem)).first()
    if existing and not force:
        return 0
    if force:
        for item in session.exec(select(SourceItem)).all():
            session.delete(item)
        session.commit()
    cfg = load_source_config()
    count = 0
    for state in cfg.get("states", []):
        for source in state.get("sources", []):
            item = SourceItem(
                state_code=state["code"],
                state_name=state["name"],
                source_name=source["name"],
                url=source["url"],
                source_type=SourceType(source.get("type", "official")),
                priority=int(source.get("priority", 50)),
                is_active=bool(source.get("active", True)),
                notes=source.get("notes"),
            )
            session.add(item)
            count += 1
    session.commit()
    return count


def get_active_sources(session: Session, state_code: str | None = None, types: list[SourceType] | None = None) -> list[SourceItem]:
    stmt = select(SourceItem).where(SourceItem.is_active == True)  # noqa: E712
    if state_code:
        stmt = stmt.where(SourceItem.state_code == state_code.upper())
    if types:
        stmt = stmt.where(SourceItem.source_type.in_(types))
    return list(session.exec(stmt).all())
