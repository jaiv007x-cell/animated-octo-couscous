from __future__ import annotations
import requests
from .text import clean_text
from app.settings import get_settings


def fetch_url(url: str) -> tuple[str, str]:
    settings = get_settings()
    headers = {"User-Agent": settings.user_agent}
    resp = requests.get(url, timeout=settings.http_timeout_seconds, headers=headers)
    resp.raise_for_status()
    content_type = resp.headers.get("Content-Type", "")
    return resp.text, content_type


def safe_fetch_text(url: str) -> str:
    html, _ = fetch_url(url)
    return clean_text(html)
