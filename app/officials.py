from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable
import hashlib
import re

from dateutil import parser as dateparser
from sqlmodel import Session, select

from .collectors.text import compact_snippet
from .evidence import certainty_sentence, evidence_tier
from .relevance import relevance_score, normalize_category_hint
from .models import (
    AnswerStatus,
    EvidenceTier,
    IntelligenceBrief,
    LegalChange,
    MovementType,
    OfficialMovement,
    OfficialProfile,
    OfficialRoleType,
    RawItem,
    SourceType,
    WorkSignal,
    WorkSignalType,
)
from .settings import get_settings


ROLE_PATTERNS: list[tuple[OfficialRoleType, list[str]]] = [
    (OfficialRoleType.chief_minister, ["chief minister", "hon'ble cm", "honble cm", "cm reviewed", "cm chaired", "cmo"]),
    (OfficialRoleType.deputy_chief_minister, ["deputy chief minister", "dy chief minister", "deputy cm"]),
    (OfficialRoleType.excise_minister, ["excise minister", "minister for excise", "minister of excise", "prohibition minister", "minister for prohibition", "abkari minister"]),
    (OfficialRoleType.minister_of_state_excise, ["minister of state for excise", "mos excise", "state minister for excise"]),
    (OfficialRoleType.finance_minister, ["finance minister", "minister for finance"]),
    (OfficialRoleType.cabinet_minister, ["cabinet minister", "minister"]),
    (OfficialRoleType.cm_office, ["chief minister's office", "chief ministers office", "cm office", "cmo"]),
    (OfficialRoleType.minister_office, ["minister office", "minister's office"]),
    (OfficialRoleType.chief_secretary, ["chief secretary"]),
    (OfficialRoleType.additional_chief_secretary, ["additional chief secretary", "acs"]),
    (OfficialRoleType.principal_secretary, ["principal secretary", "pr. secretary", "principal secy"]),
    (OfficialRoleType.secretary, ["secretary excise", "secretary, excise", "secretary prohibition", "secretary abkari", "secretary"]),
    (OfficialRoleType.commissioner_excise, ["excise commissioner", "commissioner of excise", "commissioner excise", "prohibition commissioner", "commissioner prohibition"]),
    (OfficialRoleType.managing_director, ["managing director", "md", "cmd", "chairman and managing director"]),
    (OfficialRoleType.corporation_chairman, ["chairman", "chairperson", "corporation chairman"]),
    (OfficialRoleType.director, ["director excise", "director of excise"]),
    (OfficialRoleType.collector_excise, ["collector excise", "collector of excise"]),
    (OfficialRoleType.deputy_commissioner, ["deputy commissioner", "dy. commissioner", "dc excise"]),
    (OfficialRoleType.district_excise_officer, ["district excise officer", "deo excise"]),
    (OfficialRoleType.assistant_excise_commissioner, ["assistant excise commissioner", "aec excise"]),
    (OfficialRoleType.enforcement_officer, ["enforcement officer", "superintendent excise", "inspector excise"]),
]

CADRE_PATTERN = re.compile(r"\b(IAS|IPS|IRS|DANICS|PCS|HCS|KAS|RAS|WBCS|MCS|GCS|SCS)\b", re.I)
ORDER_PATTERN = re.compile(r"(?:order|notification|office order|g\.o\.|go|memo|cabinet decision|minutes)\s*(?:no\.?|number)?\s*[:\-]?\s*([A-Z0-9/._\-]+)", re.I)
DATE_PATTERNS = [
    r"(?:dated|date|on)\s*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
    r"(?:dated|date|on)\s*(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})",
    r"w\.e\.f\.\s*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
    r"with effect from\s*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
]

MOVEMENT_KEYWORDS: dict[MovementType, list[str]] = {
    MovementType.appointment: ["appointed", "appointment", "assigned", "takes charge", "assumes charge", "given charge"],
    MovementType.transfer: ["transferred", "transfer", "reshuffle"],
    MovementType.posting: ["posted", "posting", "posted as", "posted to"],
    MovementType.portfolio_change: ["portfolio", "portfolio changed", "allocated portfolio", "assigned portfolio", "holds excise portfolio"],
    MovementType.cabinet_reshuffle: ["cabinet reshuffle", "council of ministers", "reshuffle"],
    MovementType.sworn_in: ["sworn in", "took oath", "oath taking"],
    MovementType.additional_charge: ["additional charge", "additional responsibility", "look after charge"],
    MovementType.relieved: ["relieved", "handed over charge"],
    MovementType.retirement: ["retired", "retirement", "superannuation"],
    MovementType.suspension: ["suspended", "suspension"],
    MovementType.promotion: ["promoted", "promotion"],
    MovementType.official_meeting: ["meeting", "chaired a meeting", "review meeting", "held a meeting"],
    MovementType.policy_review: ["reviewed policy", "policy review", "reviewed excise", "reviewed liquor policy"],
    MovementType.press_statement: ["said", "announced", "press release", "press statement"],
    MovementType.assembly_statement: ["assembly", "vidhan sabha", "legislative assembly", "question hour", "laid on the table"],
}

WORK_KEYWORDS: dict[WorkSignalType, list[str]] = {
    WorkSignalType.cm_review: ["chief minister", "cm reviewed", "cm chaired", "cmo", "reviewed excise revenue"],
    WorkSignalType.minister_review: ["excise minister", "minister for excise", "minister reviewed", "minister chaired"],
    WorkSignalType.cabinet_decision: ["cabinet decision", "cabinet approved", "council of ministers", "cabinet note"],
    WorkSignalType.cabinet_minutes: ["minutes", "meeting minutes", "mom", "proceedings", "agenda item"],
    WorkSignalType.assembly_question: ["assembly question", "legislative assembly", "vidhan sabha", "question hour", "starred question", "unstarred question"],
    WorkSignalType.press_statement: ["press release", "press note", "press statement", "announced", "said"],
    WorkSignalType.budget_tax: ["budget", "finance bill", "tax", "duty", "cess", "excise revenue"],
    WorkSignalType.policy: ["excise policy", "new policy", "policy review", "licensing year", "abkari policy", "liquor policy"],
    WorkSignalType.licensing: ["licence", "license", "renewal", "l-1", "fl", "shop", "bar licence", "retail vend"],
    WorkSignalType.pricing_mrp: ["mrp", "price", "pricing", "duty", "fee", "levy", "rate", "margin"],
    WorkSignalType.permit_transport: ["permit", "transport", "import", "export", "movement", "challan", "pass"],
    WorkSignalType.enforcement_review: ["enforcement review", "reviewed enforcement", "enforcement drive"],
    WorkSignalType.enforcement: ["raid", "seizure", "inspection", "crackdown", "enforcement", "illicit", "penalty", "suspension"],
    WorkSignalType.digital_transformation: ["track and trace", "qr", "barcode", "e-governance", "portal", "online", "digital", "escims", "e-abkari"],
    WorkSignalType.tender_procurement: ["tender", "rfp", "eoi", "bid", "vendor", "procurement"],
    WorkSignalType.meeting_review: ["meeting", "review", "chaired", "conference", "briefing", "minutes"],
    WorkSignalType.court_legal: ["court", "high court", "supreme court", "writ", "judgment", "order"],
    WorkSignalType.revenue_collection: ["revenue", "collection", "target", "auction", "excise revenue"],
    WorkSignalType.transfer_admin: ["transfer", "posting", "appointment", "charge", "portfolio"],
}

DESIGNATION_PHRASES = [
    "chief minister",
    "deputy chief minister",
    "excise minister",
    "minister for excise",
    "minister of excise",
    "minister of state for excise",
    "finance minister",
    "chief secretary",
    "principal secretary",
    "additional chief secretary",
    "secretary",
    "commissioner of excise",
    "excise commissioner",
    "commissioner excise",
    "managing director",
    "chairman and managing director",
    "chairman",
    "director",
    "district excise officer",
    "deputy commissioner",
    "assistant excise commissioner",
    "collector excise",
    "superintendent excise",
    "inspector excise",
]

PUBLIC_OFFICE_WORDS = [
    "chief minister", "cm", "cmo", "minister", "cabinet", "council of ministers", "assembly", "vidhan sabha",
    "principal secretary", "secretary", "commissioner", "md", "managing director", "chairman", "district excise officer",
]

EXCISE_WORDS = [
    "excise", "prohibition", "abkari", "liquor", "alcohol", "tasmac", "beverage corporation",
    "beverages corporation", "spirits", "wine shop", "retail vend", "l-1", "fl", "bar licence",
]


def normalize_name(name: str) -> str:
    cleaned = re.sub(r"\b(shri|smt|ms|mrs|mr|dr|sir|sri|hon'?ble|honble)\b\.?", "", name, flags=re.I)
    cleaned = re.sub(r"\b(IAS|IPS|IRS|DANICS|PCS|HCS|KAS|RAS|WBCS|MCS|GCS|SCS)\b", "", cleaned, flags=re.I)
    cleaned = re.sub(r"[^A-Za-z .'-]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,-")
    return cleaned.lower()


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def read_raw_text(raw: RawItem) -> str:
    parts = [raw.title or "", raw.snippet or ""]
    if raw.full_text_path and Path(raw.full_text_path).exists():
        try:
            parts.append(Path(raw.full_text_path).read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            pass
    return "\n".join(parts)


def infer_role_type(text: str) -> OfficialRoleType:
    hay = f" {text.lower()} "
    for role, patterns in ROLE_PATTERNS:
        if any(p in hay for p in patterns):
            return role
    return OfficialRoleType.other


def infer_office_level(role: OfficialRoleType) -> str:
    if role in {
        OfficialRoleType.chief_minister,
        OfficialRoleType.deputy_chief_minister,
        OfficialRoleType.excise_minister,
        OfficialRoleType.minister_of_state_excise,
        OfficialRoleType.finance_minister,
        OfficialRoleType.cabinet_minister,
        OfficialRoleType.cm_office,
        OfficialRoleType.minister_office,
    }:
        return "political_executive"
    if role == OfficialRoleType.chief_secretary:
        return "state_apex_bureaucracy"
    if role in {OfficialRoleType.principal_secretary, OfficialRoleType.additional_chief_secretary, OfficialRoleType.secretary}:
        return "state_secretariat"
    if role in {OfficialRoleType.commissioner_excise, OfficialRoleType.managing_director, OfficialRoleType.corporation_chairman, OfficialRoleType.director}:
        return "state_headquarters"
    if role in {OfficialRoleType.collector_excise, OfficialRoleType.deputy_commissioner, OfficialRoleType.district_excise_officer, OfficialRoleType.assistant_excise_commissioner}:
        return "district_or_regional"
    return "unknown"


def infer_movement_type(text: str, source_type: SourceType) -> MovementType:
    hay = text.lower()
    for movement, words in MOVEMENT_KEYWORDS.items():
        if any(w in hay for w in words):
            return movement
    if source_type == SourceType.social:
        return MovementType.chatter
    if any(w in hay for w in ["meeting", "review", "chaired", "inspection"]):
        return MovementType.official_activity
    return MovementType.unknown


def infer_work_signal_type(text: str, source_type: SourceType) -> WorkSignalType:
    hay = text.lower()
    best = WorkSignalType.unknown
    best_score = 0
    for signal_type, words in WORK_KEYWORDS.items():
        score = sum(1 for w in words if w in hay)
        if score > best_score:
            best, best_score = signal_type, score
    if best == WorkSignalType.unknown and source_type == SourceType.social:
        return WorkSignalType.chatter
    return best


def extract_cadre(text: str) -> str | None:
    match = CADRE_PATTERN.search(text)
    return match.group(1).upper() if match else None


def extract_order_no(text: str) -> str | None:
    match = ORDER_PATTERN.search(text)
    if not match:
        return None
    value = match.group(1).strip(" .,-")
    if len(value) < 3:
        return None
    return value[:80]


def extract_date(text: str):
    for pat in DATE_PATTERNS:
        m = re.search(pat, text, flags=re.I)
        if m:
            try:
                return dateparser.parse(m.group(1), dayfirst=True, fuzzy=True).date()
            except Exception:
                continue
    return None


def extract_person_names(text: str) -> list[str]:
    names: list[str] = []
    # Role-first patterns: Chief Minister A B, Excise Minister A B, etc.
    role_prefix = r"(?:Chief Minister|Deputy Chief Minister|Excise Minister|Minister for Excise|Minister of Excise|Finance Minister|Principal Secretary|Additional Chief Secretary|Chief Secretary|Excise Commissioner|Commissioner of Excise)"
    for m in re.finditer(role_prefix + r"\s+(?:Shri|Sri|Smt|Ms|Mrs|Mr|Dr)?\.?\s*([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){1,4})", text):
        names.append(m.group(1).strip())
    # Honorific/cadre-heavy government order patterns.
    for m in re.finditer(r"\b(?:Shri|Sri|Smt|Ms|Mrs|Mr|Dr)\.?\s+([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){1,4})(?:\s*,?\s*(?:IAS|IPS|IRS|DANICS|PCS|HCS|KAS|RAS|WBCS|MCS|GCS|SCS))?", text):
        names.append(m.group(1).strip())
    # Name before service cadre.
    for m in re.finditer(r"\b([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){1,4})\s*,?\s*(?:IAS|IPS|IRS|DANICS|PCS|HCS|KAS|RAS|WBCS|MCS|GCS|SCS)\b", text):
        names.append(m.group(1).strip())
    # Name before transfer/portfolio verbs.
    for m in re.finditer(r"\b([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){1,4})\s+(?:has been|was|is|be)\s+(?:transferred|posted|appointed|assigned|promoted|relieved|suspended|allocated|given)", text):
        names.append(m.group(1).strip())

    clean: list[str] = []
    seen = set()
    blacklist = {
        "Government of", "Department of", "Office of", "Excise Department", "State Excise",
        "Prohibition Excise", "Chief Minister", "Excise Minister", "Finance Minister", "Cabinet Minister",
    }
    for name in names:
        name = re.sub(r"\s+", " ", name).strip(" .,-")
        if not name or name in blacklist or len(name.split()) < 2:
            continue
        if any(b.lower() in name.lower() for b in ["office", "department", "government", "excise policy", "cabinet decision"]):
            continue
        norm = normalize_name(name)
        if len(norm) < 5 or norm in seen:
            continue
        seen.add(norm)
        clean.append(name)
    return clean[:10]


def extract_designation(text: str) -> str | None:
    patterns = [
        r"(?:posted|appointed|assigned)\s+as\s+([^.;\n]{5,180})",
        r"(?:to\s+the\s+post\s+of)\s+([^.;\n]{5,180})",
        r"(?:given\s+additional\s+charge\s+of)\s+([^.;\n]{5,180})",
        r"(?:allocated|assigned)\s+the\s+portfolio\s+of\s+([^.;\n]{5,180})",
        r"(?:holds|retains)\s+the\s+([^.;\n]{5,180})\s+portfolio",
        r"(?:takes|assumes)\s+charge\s+as\s+([^.;\n]{5,180})",
        r"(?:designated\s+as)\s+([^.;\n]{5,180})",
    ]
    for pat in patterns:
        m = re.search(pat, text, flags=re.I)
        if m:
            return clean_designation(m.group(1))
    hay = text.lower()
    for phrase in DESIGNATION_PHRASES:
        if phrase in hay:
            idx = hay.find(phrase)
            return clean_designation(text[idx: idx + 160])
    return None


def extract_from_designation(text: str) -> str | None:
    m = re.search(r"from\s+([^.;\n]{5,140})\s+to\s+([^.;\n]{5,140})", text, flags=re.I)
    if m:
        return clean_designation(m.group(1))
    return None


def clean_designation(value: str | None) -> str | None:
    if not value:
        return None
    value = re.sub(r"\s+", " ", value).strip(" .,-")
    value = re.split(
        r"\b(?:with|vide|under|against|until|in place of|and posted|and is reviewing|and will review|and he|and she|, who| who | after | during )\b",
        value,
        flags=re.I,
    )[0]
    value = value.strip(" .,-")
    return value[:180] if value else None


def is_official_people_relevant(text: str) -> bool:
    hay = text.lower()
    public_office_hit = any(word in hay for word in PUBLIC_OFFICE_WORDS)
    excise_hit = any(word in hay for word in EXCISE_WORDS)
    movement_hit = any(word in hay for words in MOVEMENT_KEYWORDS.values() for word in words)
    work_hit = any(word in hay for words in WORK_KEYWORDS.values() for word in words)
    # Public-office intelligence is in-scope only if it touches excise/prohibition/liquor administration.
    return excise_hit and (public_office_hit or movement_hit or work_hit)


def workstream_label(signal_type: WorkSignalType) -> str:
    return {
        WorkSignalType.cm_review: "Chief Minister / CMO-level review of excise or revenue matters",
        WorkSignalType.minister_review: "Excise Minister-level review or directive",
        WorkSignalType.cabinet_decision: "Cabinet decision / council-of-ministers decision",
        WorkSignalType.cabinet_minutes: "Cabinet / departmental minutes, agenda, or proceedings",
        WorkSignalType.assembly_question: "Legislative Assembly question, answer, or statement",
        WorkSignalType.press_statement: "Press release / public statement",
        WorkSignalType.budget_tax: "Budget, duty, tax, or revenue measure",
        WorkSignalType.policy: "Excise policy / annual policy structure",
        WorkSignalType.licensing: "Licence renewal / grant / retail-wholesale conditions",
        WorkSignalType.pricing_mrp: "Duties, fees, MRP, pricing, margin control",
        WorkSignalType.permit_transport: "Import/export/transport permits and challans",
        WorkSignalType.enforcement_review: "Ministerial/departmental enforcement review",
        WorkSignalType.enforcement: "Enforcement, raids, compliance inspections",
        WorkSignalType.digital_transformation: "Digital portals, track-and-trace, QR/barcode systems",
        WorkSignalType.tender_procurement: "Tenders, RFPs, technology/procurement",
        WorkSignalType.meeting_review: "Official review meeting or departmental coordination",
        WorkSignalType.court_legal: "Court/legal response and litigation tracking",
        WorkSignalType.revenue_collection: "Revenue collection, auctions, fee realization",
        WorkSignalType.transfer_admin: "Administrative transfers, postings, portfolios",
        WorkSignalType.chatter: "Unverified market signal",
        WorkSignalType.unknown: "Unknown workstream; human review required",
    }.get(signal_type, "Unknown workstream")


def action_required_for(signal_type: WorkSignalType, tier: EvidenceTier) -> str:
    if tier == EvidenceTier.official_confirmed:
        prefix = "Official-confirmed:"
    elif tier == EvidenceTier.chatter_unverified:
        prefix = "Chatter only:"
    else:
        prefix = "Verify:"
    detail = {
        WorkSignalType.cm_review: "watch for cabinet note, excise circular, finance approval, or policy order.",
        WorkSignalType.minister_review: "track departmental follow-up, circulars, and field instructions.",
        WorkSignalType.cabinet_decision: "update policy tracker and wait for department order/gazette before ERP change.",
        WorkSignalType.cabinet_minutes: "extract action points, responsible department, deadlines, and pending approvals.",
        WorkSignalType.assembly_question: "check whether reply indicates coming policy, duty, enforcement, or revenue target.",
        WorkSignalType.press_statement: "verify against notification/circular before treating as binding.",
        WorkSignalType.budget_tax: "check duty, fee, pricing, and MRP master impact.",
        WorkSignalType.policy: "review possible ERP/compliance-rule impact.",
        WorkSignalType.licensing: "check licence renewal calendar, fee payments, and outlet eligibility.",
        WorkSignalType.pricing_mrp: "check MRP/price masters before billing.",
        WorkSignalType.permit_transport: "check permit workflows before dispatch.",
        WorkSignalType.enforcement_review: "review depot/field controls and risk hot spots.",
        WorkSignalType.enforcement: "review risk areas, depot controls, and field conduct.",
        WorkSignalType.digital_transformation: "monitor new portal/track-and-trace integration requirements.",
        WorkSignalType.tender_procurement: "monitor technology/procurement opportunity or compliance-system change.",
        WorkSignalType.meeting_review: "monitor for follow-up circulars/orders.",
        WorkSignalType.court_legal: "send to legal/compliance for interpretation.",
        WorkSignalType.revenue_collection: "monitor fee/duty/auction impact.",
        WorkSignalType.transfer_admin: "update relationship map only after official confirmation.",
        WorkSignalType.chatter: "do not act; seek official order/circular.",
        WorkSignalType.unknown: "triage manually.",
    }.get(signal_type, "triage manually.")
    return f"{prefix} {detail}"


def upsert_profile_from_movement(session: Session, movement: OfficialMovement) -> OfficialProfile:
    stmt = select(OfficialProfile).where(
        OfficialProfile.state_code == movement.state_code,
        OfficialProfile.normalized_name == movement.normalized_name,
        OfficialProfile.is_current == True,  # noqa: E712
    )
    profile = session.exec(stmt).first()
    if not profile:
        profile = OfficialProfile(
            state_code=movement.state_code,
            state_name=movement.state_name,
            person_name=movement.person_name,
            normalized_name=movement.normalized_name,
        )
    profile.service_cadre = movement.service_cadre or profile.service_cadre
    profile.department = movement.department or profile.department or "Excise / Prohibition / Beverages administration"
    profile.current_designation = movement.to_designation or movement.from_designation or profile.current_designation
    profile.role_type = infer_role_type(profile.current_designation or movement.summary or movement.person_name)
    profile.office_level = infer_office_level(profile.role_type)
    profile.effective_from = movement.effective_date or movement.order_date or profile.effective_from
    profile.last_seen_at = datetime.utcnow()
    profile.evidence_tier = movement.evidence_tier
    profile.confidence_score = movement.confidence_score
    profile.source_name = movement.source_name
    profile.source_type = movement.source_type
    profile.source_url = movement.source_url
    profile.raw_item_id = movement.raw_item_id
    profile.needs_human_review = movement.needs_human_review
    if profile.role_type in {
        OfficialRoleType.chief_minister,
        OfficialRoleType.deputy_chief_minister,
        OfficialRoleType.excise_minister,
        OfficialRoleType.minister_of_state_excise,
        OfficialRoleType.finance_minister,
        OfficialRoleType.cabinet_minister,
    }:
        profile.notes = "Public-office profile. Tracks portfolio/official work only; no personal movement tracking."
    else:
        profile.notes = "Auto-updated from movement signal. Confirm from official order before relying on current designation." if movement.needs_human_review else "Auto-updated from official-confirmed source."
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile


def process_raw_for_officials(session: Session, raw: RawItem) -> tuple[list[OfficialMovement], list[WorkSignal]]:
    text = read_raw_text(raw)
    if not is_official_people_relevant(text):
        return [], []

    tier, score, needs_review = evidence_tier(raw.source_type, raw.url, raw.title, raw.snippet or text)
    movement_type = infer_movement_type(text, raw.source_type)
    signal_type = infer_work_signal_type(text, raw.source_type)
    names = extract_person_names(text)
    cadre = extract_cadre(text)
    to_designation = extract_designation(text)
    role_type = infer_role_type(text + " " + (to_designation or ""))
    if not names and role_type != OfficialRoleType.other:
        names = [role_type.value.replace("_", " ").title()]
    from_designation = extract_from_designation(text)
    order_no = extract_order_no(text)
    order_date = extract_date(text)
    summary = compact_snippet(text, max_chars=800)

    movements: list[OfficialMovement] = []
    if not names and to_designation and movement_type != MovementType.unknown:
        names = ["Unknown public officer"]

    for idx, name in enumerate(names[:5]):
        digest = sha256(f"official-movement|{raw.content_hash}|{idx}|{normalize_name(name)}|{movement_type}|{to_designation}|{order_no}")
        exists = session.exec(select(OfficialMovement).where(OfficialMovement.content_hash == digest)).first()
        if exists:
            continue
        movement = OfficialMovement(
            state_code=raw.state_code,
            state_name=raw.state_name,
            person_name=name,
            normalized_name=normalize_name(name),
            service_cadre=cadre,
            movement_type=movement_type,
            from_designation=from_designation,
            to_designation=to_designation or role_type.value.replace("_", " ").title(),
            department="Excise / Prohibition / Beverages administration",
            order_no=order_no,
            order_date=order_date,
            effective_date=order_date,
            summary=summary,
            evidence_tier=tier,
            confidence_score=score,
            source_name=raw.source_name,
            source_type=raw.source_type,
            source_url=raw.url,
            raw_item_id=raw.id,
            content_hash=digest,
            needs_human_review=needs_review,
        )
        session.add(movement)
        session.commit()
        session.refresh(movement)
        movements.append(movement)
        upsert_profile_from_movement(session, movement)

    work_signals: list[WorkSignal] = []
    if signal_type != WorkSignalType.unknown or names:
        digest = sha256(f"work-signal|{raw.content_hash}|{signal_type}|{to_designation}|{role_type}")
        exists = session.exec(select(WorkSignal).where(WorkSignal.content_hash == digest)).first()
        if not exists:
            signal = WorkSignal(
                state_code=raw.state_code,
                state_name=raw.state_name,
                signal_type=signal_type,
                person_name=names[0] if names else None,
                designation=to_designation or role_type.value.replace("_", " ").title(),
                title=raw.title[:250],
                summary=summary,
                likely_workstream=workstream_label(signal_type),
                action_required=action_required_for(signal_type, tier),
                evidence_tier=tier,
                confidence_score=score,
                source_name=raw.source_name,
                source_type=raw.source_type,
                source_url=raw.url,
                raw_item_id=raw.id,
                content_hash=digest,
                needs_human_review=needs_review,
            )
            session.add(signal)
            session.commit()
            session.refresh(signal)
            work_signals.append(signal)
    return movements, work_signals


def process_new_official_raw_items(session: Session, limit: int = 1000) -> dict:
    raw_items = list(session.exec(select(RawItem).order_by(RawItem.fetched_at.desc()).limit(limit)).all())
    movements: list[OfficialMovement] = []
    work_signals: list[WorkSignal] = []
    for raw in raw_items:
        m, w = process_raw_for_officials(session, raw)
        movements.extend(m)
        work_signals.extend(w)
    return {"movements_created": len(movements), "work_signals_created": len(work_signals), "movements": movements, "work_signals": work_signals}


def ingest_forward_data(
    session: Session,
    state_code: str,
    state_name: str,
    title: str,
    text: str,
    source_reference: str = "manual://forward-data",
    source_name: str = "Manual forward data",
    source_type: SourceType = SourceType.social,
) -> RawItem | None:
    settings = get_settings()
    Path(settings.doc_dir).mkdir(parents=True, exist_ok=True)
    digest = sha256(f"official-forward|{state_code}|{title}|{text}|{source_reference}|{source_type}")
    if session.exec(select(RawItem).where(RawItem.content_hash == digest)).first():
        return None
    path = Path(settings.doc_dir) / f"official-forward-{state_code.lower()}-{digest[:16]}.txt"
    path.write_text(f"{title}\n{source_reference}\n{text}", encoding="utf-8")
    item = RawItem(
        state_code=state_code,
        state_name=state_name,
        source_name=source_name,
        source_type=source_type,
        title=title[:250],
        url=source_reference,
        published_at=None,
        fetched_at=datetime.utcnow(),
        content_hash=digest,
        snippet=compact_snippet(text),
        full_text_path=str(path),
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def latest_official_movements(session: Session, state_code: str | None = None, person: str | None = None, limit: int = 100, days: int | None = None) -> list[OfficialMovement]:
    stmt = select(OfficialMovement)
    if days:
        stmt = stmt.where(OfficialMovement.detected_at >= datetime.utcnow() - timedelta(days=days))
    if state_code:
        stmt = stmt.where(OfficialMovement.state_code == state_code.upper())
    stmt = stmt.order_by(OfficialMovement.detected_at.desc()).limit(limit)
    rows = list(session.exec(stmt).all())
    if person:
        q = normalize_name(person)
        rows = [r for r in rows if q in r.normalized_name or r.normalized_name in q]
    return rows


def latest_work_signals(session: Session, state_code: str | None = None, limit: int = 100, days: int | None = None) -> list[WorkSignal]:
    stmt = select(WorkSignal)
    if days:
        stmt = stmt.where(WorkSignal.detected_at >= datetime.utcnow() - timedelta(days=days))
    if state_code:
        stmt = stmt.where(WorkSignal.state_code == state_code.upper())
    stmt = stmt.order_by(WorkSignal.detected_at.desc()).limit(limit)
    return list(session.exec(stmt).all())


def officials_directory(session: Session, state_code: str | None = None, role_type: OfficialRoleType | None = None, limit: int = 100) -> list[OfficialProfile]:
    stmt = select(OfficialProfile).where(OfficialProfile.is_current == True)  # noqa: E712
    if state_code:
        stmt = stmt.where(OfficialProfile.state_code == state_code.upper())
    if role_type:
        stmt = stmt.where(OfficialProfile.role_type == role_type)
    stmt = stmt.order_by(OfficialProfile.last_seen_at.desc()).limit(limit)
    return list(session.exec(stmt).all())


def _tier_rank(tier: EvidenceTier) -> int:
    return {
        EvidenceTier.official_confirmed: 5,
        EvidenceTier.govt_probable: 4,
        EvidenceTier.reported_not_confirmed: 3,
        EvidenceTier.chatter_unverified: 1,
        EvidenceTier.insufficient: 0,
    }.get(tier, 0)


def _source_bucket(source_type: SourceType | None) -> str:
    if source_type in {SourceType.official, SourceType.gazette, SourceType.court, SourceType.regulator}:
        return "official"
    if source_type == SourceType.news:
        return "news"
    if source_type in {SourceType.social, SourceType.industry, SourceType.manual}:
        return "chatter"
    return "other"


def _tokenize(question: str) -> list[str]:
    return [t for t in re.split(r"\W+", question.lower()) if len(t) > 2]


def _score_text(tokens: list[str], text: str, tier: EvidenceTier) -> int:
    hay = text.lower()
    return sum(1 for t in tokens if t in hay) + _tier_rank(tier)


def _detect_conflicts(profiles: list[OfficialProfile], movements: list[OfficialMovement]) -> list[str]:
    conflicts: list[str] = []
    by_role: dict[OfficialRoleType, set[str]] = defaultdict(set)
    political_roles = {
        OfficialRoleType.chief_minister,
        OfficialRoleType.excise_minister,
        OfficialRoleType.minister_of_state_excise,
        OfficialRoleType.finance_minister,
        OfficialRoleType.chief_secretary,
        OfficialRoleType.commissioner_excise,
        OfficialRoleType.managing_director,
    }
    for p in profiles:
        if p.role_type in political_roles and p.evidence_tier == EvidenceTier.official_confirmed:
            by_role[p.role_type].add(p.normalized_name)
    for role, names in by_role.items():
        if len(names) > 1:
            conflicts.append(f"Multiple official-confirmed current names for {role.value}: {', '.join(sorted(names))}")
    # Chatter contradicting official profile is not a conflict; it is a verification task.
    for m in movements:
        if m.evidence_tier == EvidenceTier.chatter_unverified and m.to_designation:
            role = infer_role_type(m.to_designation)
            official_names = by_role.get(role, set())
            if official_names and m.normalized_name not in official_names:
                conflicts.append(f"Chatter names {m.person_name} for {role.value}, but official profile differs.")
    return conflicts[:10]


def _build_source_rows(items: list[object]) -> list[dict]:
    rows: list[dict] = []
    seen = set()
    for item in items:
        url = getattr(item, "source_url", None) or getattr(item, "url", None)
        title = getattr(item, "title", None) or getattr(item, "person_name", None) or getattr(item, "current_designation", None)
        if not url or url in seen:
            continue
        seen.add(url)
        rows.append({
            "title": title,
            "source_url": url,
            "source_name": getattr(item, "source_name", None),
            "source_type": getattr(item, "source_type", None),
            "evidence_tier": getattr(item, "evidence_tier", None),
            "confidence_score": getattr(item, "confidence_score", None),
            "detected_at": getattr(item, "detected_at", None) or getattr(item, "last_seen_at", None),
        })
    return rows[:20]


def answer_officials_question(session: Session, question: str, state_code: str | None = None, days: int = 365) -> dict:
    # Backward-compatible wrapper, now using the conclusive answer engine.
    return answer_conclusive_question(session, question, state_code=state_code, days=days)


def answer_conclusive_question(session: Session, question: str, state_code: str | None = None, days: int = 365) -> dict:
    tokens = _tokenize(question)
    movements = latest_official_movements(session, state_code=state_code, limit=250, days=days)
    works = latest_work_signals(session, state_code=state_code, limit=250, days=days)
    profiles = officials_directory(session, state_code=state_code, limit=250)

    # Include legal changes because a conclusive public-office answer often needs the order/circular itself.
    since = datetime.utcnow() - timedelta(days=days)
    stmt = select(LegalChange).where(LegalChange.detected_at >= since)
    if state_code:
        stmt = stmt.where(LegalChange.state_code == state_code.upper())
    changes = list(session.exec(stmt.order_by(LegalChange.detected_at.desc()).limit(250)).all())

    scored_movements = []
    for m in movements:
        hay = f"{m.person_name} {m.to_designation} {m.from_designation} {m.summary} {m.movement_type} {m.department}"
        rel = relevance_score(question, hay, category_hint="admin")
        if rel.passed:
            score = rel.score * 10 + _tier_rank(m.evidence_tier)
            scored_movements.append((score, m))
    scored_works = []
    for w in works:
        hay = f"{w.person_name} {w.designation} {w.title} {w.summary} {w.likely_workstream} {w.signal_type}"
        rel = relevance_score(question, hay, category_hint="admin")
        if rel.passed:
            score = rel.score * 10 + _tier_rank(w.evidence_tier)
            scored_works.append((score, w))
    scored_profiles = []
    for p in profiles:
        hay = f"{p.person_name} {p.current_designation} {p.role_type} {p.department} {p.notes}"
        rel = relevance_score(question, hay, category_hint="admin")
        if rel.passed:
            score = rel.score * 10 + _tier_rank(p.evidence_tier)
            scored_profiles.append((score, p))
    scored_changes = []
    for c in changes:
        hay = f"{c.title} {c.summary} {c.legal_effect} {c.change_type}"
        rel = relevance_score(question, hay, category_hint=normalize_category_hint(c.change_type))
        if rel.passed:
            score = rel.score * 10 + _tier_rank(c.evidence_tier)
            scored_changes.append((score, c))

    top_movements = [m for _, m in sorted(scored_movements, key=lambda x: x[0], reverse=True)[:12]]
    top_works = [w for _, w in sorted(scored_works, key=lambda x: x[0], reverse=True)[:12]]
    top_profiles = [p for _, p in sorted(scored_profiles, key=lambda x: x[0], reverse=True)[:12]]
    top_changes = [c for _, c in sorted(scored_changes, key=lambda x: x[0], reverse=True)[:12]]
    ranked_items: list[tuple[float, object]] = [*sorted(scored_profiles, key=lambda x: x[0], reverse=True)[:12], *sorted(scored_movements, key=lambda x: x[0], reverse=True)[:12], *sorted(scored_works, key=lambda x: x[0], reverse=True)[:12], *sorted(scored_changes, key=lambda x: x[0], reverse=True)[:12]]
    ranked_items.sort(key=lambda x: (x[0], _tier_rank(getattr(x[1], "evidence_tier", EvidenceTier.insufficient))), reverse=True)
    all_items: list[object] = [item for _, item in ranked_items]

    if not all_items:
        conclusion = "No matching public-office, ministerial, officer, legal-change, or workstream signal is currently in the local database. Ingest official URLs/orders or forward data, then run processing."
        status = AnswerStatus.insufficient
        strongest = EvidenceTier.insufficient
        definitive = False
        conflicts: list[str] = []
    else:
        strongest = max((getattr(x, "evidence_tier", EvidenceTier.insufficient) for x in all_items), key=_tier_rank)
        conflicts = _detect_conflicts(top_profiles, top_movements)
        official_count = sum(1 for x in all_items if _source_bucket(getattr(x, "source_type", None)) == "official" or getattr(x, "evidence_tier", None) == EvidenceTier.official_confirmed)
        news_count = sum(1 for x in all_items if _source_bucket(getattr(x, "source_type", None)) == "news")
        chatter_count = sum(1 for x in all_items if _source_bucket(getattr(x, "source_type", None)) == "chatter" or getattr(x, "evidence_tier", None) == EvidenceTier.chatter_unverified)
        if conflicts and official_count:
            status = AnswerStatus.conflicting
            definitive = False
            conclusion = "Not definitive because matching signals contain conflicts. Use the evidence ledger and resolve against the official order/gazette before action."
        elif strongest == EvidenceTier.official_confirmed and official_count:
            status = AnswerStatus.confirmed
            definitive = True
            best_title = getattr(all_items[0], "title", None) or getattr(all_items[0], "current_designation", None) or getattr(all_items[0], "person_name", "matched item")
            conclusion = f"Definite from official-confirmed evidence. Strongest matched item: {best_title}."
        elif strongest == EvidenceTier.govt_probable:
            status = AnswerStatus.official_but_incomplete
            definitive = False
            conclusion = "Official/probable but not final enough. Treat as strong signal and verify the original order, gazette, or department circular."
        elif news_count and not official_count:
            status = AnswerStatus.reported_only
            definitive = False
            conclusion = "Reported by non-official sources only. Useful intelligence, not a conclusive compliance answer."
        elif chatter_count and not official_count and not news_count:
            status = AnswerStatus.chatter_only
            definitive = False
            conclusion = "Chatter only. Do not change compliance, dispatch, relationship map, or policy assumptions until official confirmation arrives."
        else:
            status = AnswerStatus.insufficient
            definitive = False
            conclusion = f"Not definitive yet. Strongest evidence is {strongest}. {certainty_sentence(strongest)}"

    source_rows = _build_source_rows(all_items) if all_items else []
    official_count = sum(1 for x in all_items if _source_bucket(getattr(x, "source_type", None)) == "official" or getattr(x, "evidence_tier", None) == EvidenceTier.official_confirmed)
    news_count = sum(1 for x in all_items if _source_bucket(getattr(x, "source_type", None)) == "news")
    chatter_count = sum(1 for x in all_items if _source_bucket(getattr(x, "source_type", None)) == "chatter" or getattr(x, "evidence_tier", None) == EvidenceTier.chatter_unverified)

    roles = sorted({str(getattr(p, "role_type", "")) for p in top_profiles if getattr(p, "role_type", None)})
    streams = sorted({str(getattr(w, "signal_type", "")) for w in top_works if getattr(w, "signal_type", None)})
    brief = IntelligenceBrief(
        state_code=state_code.upper() if state_code else None,
        state_name=(all_items[0].state_name if all_items and hasattr(all_items[0], "state_name") else None),
        question=question[:500],
        conclusion=conclusion[:2000],
        answer_status=status,
        definitive=definitive,
        strongest_evidence_tier=strongest,
        official_source_count=official_count,
        news_source_count=news_count,
        chatter_source_count=chatter_count,
        conflict_count=len(conflicts),
        source_urls="\n".join(r["source_url"] for r in source_rows if r.get("source_url"))[:4000],
        affected_roles=", ".join(roles)[:1000],
        affected_workstreams=", ".join(streams)[:1000],
        days_lookback=days,
    )
    session.add(brief)
    session.commit()
    session.refresh(brief)

    return {
        "answer": conclusion,
        "definitive": definitive,
        "answer_status": status,
        "evidence_tier": strongest,
        "counts": {
            "official_sources": official_count,
            "news_sources": news_count,
            "chatter_sources": chatter_count,
            "conflicts": len(conflicts),
            "profiles": len(top_profiles),
            "movements": len(top_movements),
            "work_signals": len(top_works),
            "legal_changes": len(top_changes),
        },
        "conflicts": conflicts,
        "profiles": [p.model_dump() for p in top_profiles],
        "movements": [m.model_dump() for m in top_movements],
        "work_signals": [w.model_dump() for w in top_works],
        "legal_changes": [c.model_dump() for c in top_changes],
        "sources": source_rows,
        "brief_id": brief.id,
    }


def latest_intelligence_briefs(session: Session, state_code: str | None = None, limit: int = 50) -> list[IntelligenceBrief]:
    stmt = select(IntelligenceBrief)
    if state_code:
        stmt = stmt.where(IntelligenceBrief.state_code == state_code.upper())
    stmt = stmt.order_by(IntelligenceBrief.created_at.desc()).limit(limit)
    return list(session.exec(stmt).all())
