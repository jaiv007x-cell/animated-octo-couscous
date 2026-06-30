from __future__ import annotations
from datetime import datetime
from sqlmodel import Session, select
from app.models import UserAccount, UserRole
from app.auth.security import hash_password


def bootstrap_admin(session: Session, username: str, password: str, email: str | None = None, display_name: str | None = None) -> dict:
    existing = session.exec(select(UserAccount).where(UserAccount.username == username)).first()
    if existing:
        return {"created": False, "username": username, "role": existing.role.value}
    user = UserAccount(
        username=username,
        email=email,
        display_name=display_name or username,
        password_hash=hash_password(password),
        role=UserRole.super_admin,
        state_scope="ALL",
        is_active=True,
        created_at=datetime.utcnow(),
    )
    session.add(user)
    session.commit()
    return {"created": True, "username": username, "role": user.role.value}
