from __future__ import annotations
import re
from .models import ChangeType

KEYWORDS: dict[ChangeType, list[str]] = {
    ChangeType.policy: ["excise policy", "policy", "licensing year", "liquor policy", "abkari policy"],
    ChangeType.rule: ["rules", "amendment", "notification", "gazette", "go ms", "g.o.", "sro"],
    ChangeType.license: ["licence", "license", "renewal", "grant", "l-1", "fl", "bar license", "shop licence"],
    ChangeType.fee: ["fee", "duty", "levy", "tax", "rate", "registration fee"],
    ChangeType.mrp_price: ["mrp", "price", "pricing", "overpricing", "retail price"],
    ChangeType.dry_day: ["dry day", "closure", "holiday", "election", "polling", "counting"],
    ChangeType.permit_transport: ["transport", "permit", "import", "export", "movement", "pass", "challan"],
    ChangeType.enforcement: ["raid", "seizure", "crackdown", "fine", "penalty", "arrest", "suspension"],
    ChangeType.court: ["high court", "supreme court", "court", "judgment", "order", "writ"],
    ChangeType.tender: ["tender", "eoi", "rfp", "bid", "auction"],
    ChangeType.admin: ["transfer", "recruitment", "selection list", "posting", "circular"],
    ChangeType.chatter: ["rumour", "rumor", "viral", "thread", "post", "tweet", "reddit"],
}

LEGAL_SIGNAL_WORDS = [
    "excise", "abkari", "liquor", "alcohol", "beer", "wine", "imfl", "fl", "country liquor",
    "toddy", "spirit", "distillery", "brewery", "bar", "permit", "licence", "license", "mrp",
    "dry day", "bonded warehouse", "retail vend", "wholesale", "duty", "shop", "tasmac"
]

LOW_VALUE_ADMIN_WORDS = ["seniority", "recruitment", "selection list", "constable", "transfer", "posting", "typing test"]


def classify_change(title: str, snippet: str = "") -> ChangeType:
    hay = f"{title} {snippet}".lower()
    if not any(w in hay for w in LEGAL_SIGNAL_WORDS):
        # Keep tenders/admin separated because official pages are noisy.
        if any(w in hay for w in KEYWORDS[ChangeType.tender]):
            return ChangeType.tender
        if any(w in hay for w in LOW_VALUE_ADMIN_WORDS):
            return ChangeType.admin
        return ChangeType.unknown
    best = ChangeType.unknown
    best_score = 0
    for ctype, words in KEYWORDS.items():
        score = sum(1 for w in words if w in hay)
        if score > best_score:
            best, best_score = ctype, score
    return best


def is_relevant_excise_update(title: str, snippet: str = "") -> bool:
    hay = f"{title} {snippet}".lower()
    if any(w in hay for w in LEGAL_SIGNAL_WORDS):
        return True
    if "excise" in hay and not any(w in hay for w in LOW_VALUE_ADMIN_WORDS):
        return True
    return False


def extract_effective_date(text: str) -> str | None:
    patterns = [
        r"w\.e\.f\.\s*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
        r"with effect from\s*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
        r"effective from\s*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
        r"from\s*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})\s*to",
    ]
    for p in patterns:
        m = re.search(p, text, flags=re.I)
        if m:
            return m.group(1)
    return None
