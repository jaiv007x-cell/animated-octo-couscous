from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Any
import re

from .models import ChangeType

# Words that should never make a legal answer conclusive by themselves.
# They describe the system/query style, not the legal subject being asked about.
STOPWORDS = {
    "what", "when", "where", "which", "who", "whom", "whose", "why", "how",
    "is", "are", "was", "were", "be", "been", "being", "the", "a", "an", "and", "or", "of", "to", "for", "in", "on", "by", "with", "from", "as", "at", "it", "this", "that", "there", "any", "all", "latest", "recent", "currently", "current", "confirmed", "official", "definite", "definitive", "conclusive", "update", "updates", "change", "changes", "changed", "status", "information", "details", "tell", "show", "give", "answer", "india", "indian", "state", "states", "govt", "government", "department", "source", "sources",
    # domain-generic words: useful for routing, unsafe for conclusiveness alone
    "excise", "liquor", "alcohol", "spirits", "wine", "beer", "abkari", "prohibition", "law", "laws", "rule", "rules", "order", "orders", "circular", "notification", "gazette",
}

CATEGORY_KEYWORDS: dict[str, set[str]] = {
    "license": {"licence", "license", "licensing", "renewal", "renew", "retailer", "retail", "vend", "vends", "shop", "bar", "fl", "l1", "l-1"},
    "fee_duty": {"fee", "fees", "duty", "duties", "tax", "taxes", "levy", "levies", "cess", "assessment", "excise duty"},
    "mrp_price": {"mrp", "price", "prices", "pricing", "margin", "margins", "rate", "rates", "landing", "minimum", "maximum"},
    "dry_day": {"dry", "day", "days", "closure", "closed", "holiday", "ban", "sale", "sales", "restricted"},
    "permit_transport": {"permit", "permits", "transport", "import", "export", "movement", "pass", "passes", "challan", "route", "dispatch", "consignment"},
    "policy": {"policy", "policies", "amendment", "amended", "scheme", "rules", "regulation", "framework", "annual"},
    "enforcement": {"raid", "raids", "seizure", "inspection", "penalty", "penalties", "suspension", "cancelled", "cancellation", "illicit", "enforcement", "crackdown"},
    "court": {"court", "judgment", "judgement", "writ", "petition", "stay", "stayed", "tribunal", "supreme", "high court"},
    "tender": {"tender", "rfp", "eoi", "bid", "procurement", "vendor"},
    "digital": {"portal", "online", "digital", "track", "trace", "track-and-trace", "qr", "barcode", "escims", "e-abkari"},
    "admin": {"chief", "minister", "cm", "cmo", "secretary", "commissioner", "director", "md", "chairman", "transfer", "posting", "posted", "appointment", "charge", "portfolio", "cabinet", "minutes", "meeting"},
}

# Action-direction groups must match too. This prevents a dry-day or renewal order from
# confirming a specific "fee increase" query merely because both are official excise items.
INTENT_GROUPS: dict[str, set[str]] = {
    "increase": {"increase", "increased", "hike", "hiked", "raised", "enhanced", "higher", "upward", "rise"},
    "decrease": {"decrease", "decreased", "reduced", "lowered", "cut", "waived", "waiver", "rollback", "withdrawn"},
    "ban_suspend": {"ban", "banned", "prohibited", "suspended", "cancelled", "cancelled", "cancel", "closure", "closed"},
    "allow_renew": {"allowed", "permitted", "approved", "renewed", "renewal", "granted", "extended", "extension"},
    "effective_date": {"effective", "implemented", "enforced", "w.e.f", "date", "dated"},
}

BROAD_QUERY_TERMS = {"latest", "recent", "updates", "update", "all", "summary", "brief", "digest", "what", "changed", "changes", "movement", "workstream", "overview"}

CHANGE_TYPE_TO_CATEGORY = {
    ChangeType.license: "license",
    ChangeType.fee: "fee_duty",
    ChangeType.mrp_price: "mrp_price",
    ChangeType.dry_day: "dry_day",
    ChangeType.permit_transport: "permit_transport",
    ChangeType.policy: "policy",
    ChangeType.rule: "policy",
    ChangeType.enforcement: "enforcement",
    ChangeType.court: "court",
    ChangeType.tender: "tender",
    ChangeType.admin: "admin",
    ChangeType.officer_movement: "admin",
    ChangeType.official_workstream: "admin",
    ChangeType.chatter: "admin",
}


def tokens(text: str) -> list[str]:
    raw = [t for t in re.split(r"[^a-zA-Z0-9\-]+", (text or "").lower()) if len(t) > 1]
    normalized: list[str] = []
    for t in raw:
        if t == "licence":
            t = "license"
        elif t == "licences":
            t = "licenses"
        normalized.append(t)
    return normalized


def meaningful_tokens(text: str) -> list[str]:
    return [t for t in tokens(text) if len(t) > 2 and t not in STOPWORDS]


def categories_in_text(text: str, category_hint: str | None = None) -> set[str]:
    hay = f" {text or ''} ".lower().replace("licence", "license")
    cats: set[str] = set()
    if category_hint:
        hint = category_hint.value if hasattr(category_hint, "value") else str(category_hint)
        if hint in CHANGE_TYPE_TO_CATEGORY.values():
            cats.add(hint)
        elif hint in ChangeType.__members__:
            cats.add(CHANGE_TYPE_TO_CATEGORY.get(ChangeType[hint], hint))
        else:
            # values like "dry_day" / "mrp_price"
            try:
                cats.add(CHANGE_TYPE_TO_CATEGORY.get(ChangeType(hint), hint))
            except Exception:
                cats.add(hint)
    for cat, words in CATEGORY_KEYWORDS.items():
        if any((" " + w.replace("licence", "license") + " ") in hay or w.replace("licence", "license") in hay for w in words):
            cats.add(cat)
    return cats


def intent_groups_in_text(text: str) -> set[str]:
    hay = f" {text or ''} ".lower().replace("licence", "license")
    groups = set()
    for group, words in INTENT_GROUPS.items():
        if any((" " + w + " ") in hay or w in hay for w in words):
            groups.add(group)
    return groups


def is_broad_latest_query(question: str) -> bool:
    q_tokens = set(tokens(question))
    m_tokens = set(meaningful_tokens(question))
    q_cats = categories_in_text(question)
    # Broad overview queries should return multiple updates; specific subject queries should not.
    if not q_cats and len(m_tokens) <= 1:
        return True
    if q_cats <= {"admin"} and {"latest", "updates", "movement", "workstream", "overview", "digest"} & q_tokens:
        return True
    return False


@dataclass
class RelevanceResult:
    score: float
    passed: bool
    reason: str
    token_hits: list[str]
    question_categories: set[str]
    text_categories: set[str]
    question_intents: set[str]
    missing_intents: set[str]


def relevance_score(question: str, text: str, category_hint: str | None = None, *, min_score: float = 0.26) -> RelevanceResult:
    q_meaningful = set(meaningful_tokens(question))
    t_tokens = set(tokens(text))
    token_hits = sorted(q_meaningful & t_tokens)
    q_cats = categories_in_text(question)
    t_cats = categories_in_text(text, category_hint=category_hint)
    q_intents = intent_groups_in_text(question)
    t_intents = intent_groups_in_text(text)

    broad = is_broad_latest_query(question)
    if broad:
        return RelevanceResult(0.45 + min(len(token_hits), 5) * 0.04, True, "broad_overview_query", token_hits, q_cats, t_cats, q_intents, set())

    cat_overlap = q_cats & t_cats
    missing_intents = q_intents - t_intents

    score = 0.0
    if q_meaningful:
        score += min(0.35, len(token_hits) / max(1, len(q_meaningful)) * 0.35)
    if cat_overlap:
        score += 0.42 + min(0.12, (len(cat_overlap) - 1) * 0.04)
    if q_intents:
        score += max(0.0, (len(q_intents & t_intents) / len(q_intents)) * 0.23)

    # Category-specific questions require category overlap. For specific legal
    # subjects, require full coverage: "licence fee increase" must match fee
    # evidence too, not only a licence/retail-adjacent dry-day order.
    if q_cats and not cat_overlap:
        return RelevanceResult(score, False, "category_mismatch", token_hits, q_cats, t_cats, q_intents, missing_intents)
    specific_q_cats = q_cats - {"admin", "policy"}
    if specific_q_cats and not specific_q_cats.issubset(t_cats):
        return RelevanceResult(score, False, "category_incomplete", token_hits, q_cats, t_cats, q_intents, missing_intents)

    # Directional questions require directional text support.
    # Exception: "effective_date" is a weak support group; it should not block by itself.
    hard_missing = missing_intents - {"effective_date"}
    if hard_missing:
        return RelevanceResult(score, False, "missing_directional_intent", token_hits, q_cats, t_cats, q_intents, hard_missing)

    # If the user asked no category but named a person/role, token overlap is enough.
    passed = score >= min_score or (not q_cats and len(token_hits) >= 2)
    return RelevanceResult(score, passed, "passed" if passed else "low_relevance", token_hits, q_cats, t_cats, q_intents, missing_intents)


def normalize_category_hint(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "value"):
        value = value.value
    value = str(value)
    try:
        return CHANGE_TYPE_TO_CATEGORY.get(ChangeType(value), value)
    except Exception:
        return value
