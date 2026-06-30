from __future__ import annotations
from datetime import datetime
from sqlmodel import Session, select
from dateutil import parser as dateparser
from .models import RawItem, LegalChange, ChangeType
from .classifier import classify_change, is_relevant_excise_update, extract_effective_date
from .evidence import evidence_tier


def process_raw_item(session: Session, raw: RawItem) -> LegalChange | None:
    title = raw.title or "Untitled update"
    snippet = raw.snippet or ""
    if not is_relevant_excise_update(title, snippet):
        ctype = classify_change(title, snippet)
        if ctype in {ChangeType.admin, ChangeType.unknown}:
            return None
    exists = session.exec(select(LegalChange).where(LegalChange.content_hash == raw.content_hash)).first()
    if exists:
        return None

    ctype = classify_change(title, snippet)
    tier, score, needs_review = evidence_tier(raw.source_type, raw.url, title, snippet)
    eff_date = None
    extracted = extract_effective_date(f"{title} {snippet}")
    if extracted:
        try:
            eff_date = dateparser.parse(extracted, dayfirst=True).date()
        except Exception:
            eff_date = None
    summary = snippet[:500] if snippet else title
    legal_effect = infer_legal_effect(ctype, tier, title, snippet)
    change = LegalChange(
        state_code=raw.state_code,
        state_name=raw.state_name,
        change_type=ctype,
        title=title,
        summary=summary,
        legal_effect=legal_effect,
        effective_date=eff_date,
        published_at=raw.published_at,
        detected_at=datetime.utcnow(),
        evidence_tier=tier,
        confidence_score=score,
        source_name=raw.source_name,
        source_type=raw.source_type,
        source_url=raw.url,
        raw_item_id=raw.id,
        content_hash=raw.content_hash,
        needs_human_review=needs_review,
    )
    session.add(change)
    session.commit()
    session.refresh(change)
    return change


def process_new_raw_items(session: Session, limit: int = 500) -> list[LegalChange]:
    raw_items = list(session.exec(select(RawItem).order_by(RawItem.fetched_at.desc()).limit(limit)).all())
    created: list[LegalChange] = []
    for raw in raw_items:
        change = process_raw_item(session, raw)
        if change:
            created.append(change)
    return created


def infer_legal_effect(ctype: ChangeType, tier, title: str, snippet: str) -> str:
    base = {
        ChangeType.policy: "May affect licensing year terms, retail/wholesale conditions, fees, pricing, or supply-chain structure.",
        ChangeType.rule: "May change statutory or subordinate-rule obligations. Verify the notification text before implementation.",
        ChangeType.license: "May affect licence grant/renewal, eligibility, fee payment, or operating conditions.",
        ChangeType.fee: "May affect cost, duty, licence fee, registration fee, or payment workflow.",
        ChangeType.mrp_price: "May affect registered MRP, retailer billing, overpricing risk, or price display compliance.",
        ChangeType.dry_day: "May block sale/dispatch on notified dates and should be pushed to dispatch controls.",
        ChangeType.permit_transport: "May affect import/export/transport permits, challans, validity, or route documentation.",
        ChangeType.enforcement: "Operational risk signal; check whether an official circular/order changes compliance requirements.",
        ChangeType.court: "Court/legal development; compliance team should review before policy change.",
        ChangeType.tender: "Procurement/technology signal; usually not a direct compliance obligation unless linked to traceability or licensing.",
        ChangeType.admin: "Administrative update; usually low compliance impact.",
        ChangeType.chatter: "Market signal only; not law without official confirmation.",
        ChangeType.unknown: "Potential update; needs review.",
    }.get(ctype, "Potential update; needs review.")
    return base
