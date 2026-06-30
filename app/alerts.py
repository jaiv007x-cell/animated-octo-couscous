from __future__ import annotations
import requests
from .settings import get_settings
from .models import LegalChange
from .telegram_updates import send_telegram_text


def format_change(change: LegalChange) -> str:
    return (
        f"[{change.evidence_tier}] {change.state_name}: {change.title}\n"
        f"Type: {change.change_type}\n"
        f"Effect: {change.legal_effect or 'Review required'}\n"
        f"Source: {change.source_url}"
    )


def send_slack(change: LegalChange) -> bool:
    settings = get_settings()
    if not settings.slack_webhook_url:
        return False
    resp = requests.post(settings.slack_webhook_url, json={"text": format_change(change)}, timeout=15)
    resp.raise_for_status()
    return True


def send_telegram(change: LegalChange) -> bool:
    result = send_telegram_text(format_change(change))
    if result.get("errors"):
        raise RuntimeError("; ".join(result["errors"]))
    return bool(result.get("sent"))


def send_alerts(changes: list[LegalChange]) -> dict:
    sent = {"slack": 0, "telegram": 0, "errors": []}
    for ch in changes:
        try:
            if send_slack(ch):
                sent["slack"] += 1
        except Exception as e:
            sent["errors"].append(f"slack: {e}")
        try:
            if send_telegram(ch):
                sent["telegram"] += 1
        except Exception as e:
            sent["errors"].append(f"telegram: {e}")
    return sent
