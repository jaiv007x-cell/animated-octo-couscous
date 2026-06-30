from __future__ import annotations
import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta
from typing import Any
from fastapi import Depends, Header, HTTPException, status
from sqlmodel import Session, select
from app.db import get_session
from app.models import UserAccount, UserRole, APIKey
from app.settings import get_settings


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def hash_password(password: str) -> str:
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 260_000)
    return "pbkdf2_sha256$260000$" + _b64(salt) + "$" + _b64(digest)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        scheme, rounds, salt_b64, digest_b64 = password_hash.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        salt = _unb64(salt_b64)
        expected = _unb64(digest_b64)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(rounds))
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def create_access_token(subject: str, role: str, minutes: int | None = None) -> str:
    settings = get_settings()
    now = datetime.utcnow()
    exp = now + timedelta(minutes=minutes or settings.access_token_expire_minutes)
    header = {"alg": "HS256", "typ": "EWT"}
    payload = {"sub": subject, "role": role, "iat": int(now.timestamp()), "exp": int(exp.timestamp())}
    signing_input = _b64(json.dumps(header, separators=(",", ":")).encode()) + "." + _b64(json.dumps(payload, separators=(",", ":")).encode())
    sig = hmac.new(settings.jwt_secret_key.encode(), signing_input.encode(), hashlib.sha256).digest()
    return signing_input + "." + _b64(sig)


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        head_b64, payload_b64, sig_b64 = token.split(".")
        signing_input = head_b64 + "." + payload_b64
        expected = hmac.new(settings.jwt_secret_key.encode(), signing_input.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _unb64(sig_b64)):
            raise ValueError("Bad signature")
        payload = json.loads(_unb64(payload_b64))
        if int(payload.get("exp", 0)) < int(datetime.utcnow().timestamp()):
            raise ValueError("Token expired")
        return payload
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token") from exc


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()


def generate_api_key() -> str:
    return "ew_" + secrets.token_urlsafe(32)


ROLE_PERMISSIONS: dict[UserRole, set[str]] = {
    UserRole.super_admin: {"*"},
    UserRole.compliance_head: {"read", "review", "approve", "publish", "sources", "jobs"},
    UserRole.legal_reviewer: {"read", "review", "approve"},
    UserRole.state_manager: {"read", "review", "sources"},
    UserRole.analyst: {"read", "sources", "jobs", "ingest"},
    UserRole.ops_user: {"read"},
    UserRole.viewer: {"read"},
}


def has_permission(role: UserRole | str, permission: str) -> bool:
    role_enum = role if isinstance(role, UserRole) else UserRole(role)
    perms = ROLE_PERMISSIONS.get(role_enum, set())
    return "*" in perms or permission in perms


def current_user(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> UserAccount:
    if x_api_key:
        rec = session.exec(select(APIKey).where(APIKey.key_hash == hash_api_key(x_api_key), APIKey.is_active == True)).first()
        if rec:
            from datetime import datetime
            rec.last_used_at = datetime.utcnow()
            session.add(rec)
            session.commit()
            return UserAccount(username=f"api:{rec.name}", display_name=rec.name, password_hash="", role=rec.role, state_scope=rec.state_scope, is_active=True)
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token or API key")
    payload = decode_access_token(authorization.split(" ", 1)[1])
    username = payload["sub"]
    user = session.exec(select(UserAccount).where(UserAccount.username == username, UserAccount.is_active == True)).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return user


def require_permission(permission: str):
    def dep(user: UserAccount = Depends(current_user)) -> UserAccount:
        if not has_permission(user.role, permission):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Missing permission: {permission}")
        return user
    return dep
