from __future__ import annotations
from urllib.parse import urlparse
from .models import SourceType, EvidenceTier

OFFICIAL_HOST_SIGNALS = [
    ".gov.in", ".nic.in", "indiacode.nic.in", "egazette", "gazette", "govt", "government"
]

REPUTED_NEWS_HOSTS = [
    "reuters.com", "thehindu.com", "indianexpress.com", "timesofindia.indiatimes.com",
    "hindustantimes.com", "business-standard.com", "livemint.com", "moneycontrol.com",
    "deccanherald.com", "telegraphindia.com", "ptinews.com"
]


def host(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def evidence_tier(source_type: SourceType, url: str, title: str = "", snippet: str = "") -> tuple[EvidenceTier, float, bool]:
    h = host(url)
    hay = f"{title} {snippet} {h}".lower()

    if source_type in {SourceType.official, SourceType.gazette, SourceType.regulator, SourceType.court}:
        if any(sig in h for sig in OFFICIAL_HOST_SIGNALS) or source_type in {SourceType.gazette, SourceType.court}:
            return EvidenceTier.official_confirmed, 0.92, False
        return EvidenceTier.govt_probable, 0.76, True

    if source_type == SourceType.news:
        if any(n in h for n in REPUTED_NEWS_HOSTS):
            if "official" in hay or "notification" in hay or "order" in hay:
                return EvidenceTier.reported_not_confirmed, 0.66, True
            return EvidenceTier.reported_not_confirmed, 0.58, True
        return EvidenceTier.reported_not_confirmed, 0.48, True

    if source_type in {SourceType.social, SourceType.industry}:
        return EvidenceTier.chatter_unverified, 0.25, True

    return EvidenceTier.insufficient, 0.1, True


def certainty_sentence(tier: EvidenceTier) -> str:
    if tier == EvidenceTier.official_confirmed:
        return "Definite: confirmed from an official/government source."
    if tier == EvidenceTier.govt_probable:
        return "Likely: appears to be from a government-adjacent source, but needs manual verification."
    if tier == EvidenceTier.reported_not_confirmed:
        return "Reported: covered by news/third-party sources; not treated as law until confirmed officially."
    if tier == EvidenceTier.chatter_unverified:
        return "Chatter only: useful signal, not reliable legal information."
    return "Insufficient evidence: no reliable source found."
