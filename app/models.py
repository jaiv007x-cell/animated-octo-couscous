from datetime import datetime, date
from enum import Enum
from typing import Optional
from sqlmodel import SQLModel, Field


class SourceType(str, Enum):
    official = "official"
    gazette = "gazette"
    court = "court"
    regulator = "regulator"
    news = "news"
    industry = "industry"
    social = "social"
    manual = "manual"


class EvidenceTier(str, Enum):
    official_confirmed = "OFFICIAL_CONFIRMED"
    govt_probable = "GOVT_PROBABLE"
    reported_not_confirmed = "REPORTED_NOT_CONFIRMED"
    chatter_unverified = "CHATTER_UNVERIFIED"
    insufficient = "INSUFFICIENT_EVIDENCE"


class ChangeType(str, Enum):
    policy = "policy"
    rule = "rule"
    license = "license"
    fee = "fee"
    mrp_price = "mrp_price"
    dry_day = "dry_day"
    permit_transport = "permit_transport"
    enforcement = "enforcement"
    court = "court"
    tender = "tender"
    admin = "admin"
    officer_movement = "officer_movement"
    official_workstream = "official_workstream"
    chatter = "chatter"
    unknown = "unknown"


class OfficialRoleType(str, Enum):
    chief_minister = "chief_minister"
    deputy_chief_minister = "deputy_chief_minister"
    excise_minister = "excise_minister"
    minister_of_state_excise = "minister_of_state_excise"
    finance_minister = "finance_minister"
    cabinet_minister = "cabinet_minister"
    cm_office = "cm_office"
    minister_office = "minister_office"
    chief_secretary = "chief_secretary"
    principal_secretary = "principal_secretary"
    additional_chief_secretary = "additional_chief_secretary"
    secretary = "secretary"
    commissioner_excise = "commissioner_excise"
    managing_director = "managing_director"
    corporation_chairman = "corporation_chairman"
    director = "director"
    collector_excise = "collector_excise"
    deputy_commissioner = "deputy_commissioner"
    district_excise_officer = "district_excise_officer"
    assistant_excise_commissioner = "assistant_excise_commissioner"
    enforcement_officer = "enforcement_officer"
    other = "other"


class MovementType(str, Enum):
    appointment = "appointment"
    transfer = "transfer"
    posting = "posting"
    portfolio_change = "portfolio_change"
    cabinet_reshuffle = "cabinet_reshuffle"
    sworn_in = "sworn_in"
    additional_charge = "additional_charge"
    relieved = "relieved"
    retirement = "retirement"
    suspension = "suspension"
    promotion = "promotion"
    official_activity = "official_activity"
    official_meeting = "official_meeting"
    policy_review = "policy_review"
    press_statement = "press_statement"
    assembly_statement = "assembly_statement"
    chatter = "chatter"
    unknown = "unknown"


class WorkSignalType(str, Enum):
    policy = "policy"
    cm_review = "cm_review"
    minister_review = "minister_review"
    cabinet_decision = "cabinet_decision"
    cabinet_minutes = "cabinet_minutes"
    assembly_question = "assembly_question"
    press_statement = "press_statement"
    budget_tax = "budget_tax"
    licensing = "licensing"
    pricing_mrp = "pricing_mrp"
    permit_transport = "permit_transport"
    enforcement = "enforcement"
    enforcement_review = "enforcement_review"
    digital_transformation = "digital_transformation"
    tender_procurement = "tender_procurement"
    meeting_review = "meeting_review"
    court_legal = "court_legal"
    revenue_collection = "revenue_collection"
    transfer_admin = "transfer_admin"
    chatter = "chatter"
    unknown = "unknown"


class OfficialProfile(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    state_code: str = Field(index=True)
    state_name: str = Field(index=True)
    person_name: str = Field(index=True)
    normalized_name: str = Field(index=True)
    service_cadre: str | None = Field(default=None, index=True)
    department: str | None = Field(default=None, index=True)
    current_designation: str | None = Field(default=None, index=True)
    role_type: OfficialRoleType = Field(default=OfficialRoleType.other, index=True)
    office_level: str | None = Field(default=None, index=True)
    is_current: bool = Field(default=True, index=True)
    effective_from: date | None = Field(default=None, index=True)
    last_seen_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    evidence_tier: EvidenceTier = Field(default=EvidenceTier.insufficient, index=True)
    confidence_score: float = Field(default=0.0, index=True)
    source_name: str | None = None
    source_type: SourceType | None = Field(default=None, index=True)
    source_url: str | None = None
    raw_item_id: int | None = Field(default=None, foreign_key="rawitem.id")
    notes: str | None = None
    needs_human_review: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)


class OfficialMovement(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    state_code: str = Field(index=True)
    state_name: str = Field(index=True)
    person_name: str = Field(index=True)
    normalized_name: str = Field(index=True)
    service_cadre: str | None = Field(default=None, index=True)
    movement_type: MovementType = Field(default=MovementType.unknown, index=True)
    from_designation: str | None = Field(default=None, index=True)
    to_designation: str | None = Field(default=None, index=True)
    department: str | None = Field(default=None, index=True)
    order_no: str | None = Field(default=None, index=True)
    order_date: date | None = Field(default=None, index=True)
    effective_date: date | None = Field(default=None, index=True)
    summary: str
    evidence_tier: EvidenceTier = Field(index=True)
    confidence_score: float = Field(default=0.0, index=True)
    source_name: str | None = None
    source_type: SourceType | None = Field(default=None, index=True)
    source_url: str | None = None
    raw_item_id: int | None = Field(default=None, foreign_key="rawitem.id")
    content_hash: str = Field(index=True)
    needs_human_review: bool = True
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    review_note: str | None = None
    detected_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class WorkSignal(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    state_code: str = Field(index=True)
    state_name: str = Field(index=True)
    signal_type: WorkSignalType = Field(default=WorkSignalType.unknown, index=True)
    person_name: str | None = Field(default=None, index=True)
    designation: str | None = Field(default=None, index=True)
    title: str = Field(index=True)
    summary: str
    likely_workstream: str | None = Field(default=None, index=True)
    action_required: str | None = None
    evidence_tier: EvidenceTier = Field(index=True)
    confidence_score: float = Field(default=0.0, index=True)
    source_name: str | None = None
    source_type: SourceType | None = Field(default=None, index=True)
    source_url: str | None = None
    raw_item_id: int | None = Field(default=None, foreign_key="rawitem.id")
    content_hash: str = Field(index=True)
    needs_human_review: bool = True
    detected_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class AnswerStatus(str, Enum):
    confirmed = "CONFIRMED"
    official_but_incomplete = "OFFICIAL_BUT_INCOMPLETE"
    conflicting = "CONFLICTING_EVIDENCE"
    reported_only = "REPORTED_ONLY"
    chatter_only = "CHATTER_ONLY"
    insufficient = "INSUFFICIENT"


class IntelligenceBrief(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    state_code: str | None = Field(default=None, index=True)
    state_name: str | None = Field(default=None, index=True)
    question: str = Field(index=True)
    conclusion: str
    answer_status: AnswerStatus = Field(index=True)
    definitive: bool = Field(default=False, index=True)
    strongest_evidence_tier: EvidenceTier = Field(default=EvidenceTier.insufficient, index=True)
    official_source_count: int = 0
    news_source_count: int = 0
    chatter_source_count: int = 0
    conflict_count: int = 0
    source_urls: str | None = None
    affected_roles: str | None = None
    affected_workstreams: str | None = None
    days_lookback: int = 365
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class SourceItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    state_code: str = Field(index=True)
    state_name: str = Field(index=True)
    source_name: str
    url: str = Field(index=True)
    source_type: SourceType = Field(index=True)
    priority: int = 50
    is_active: bool = True
    notes: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class RawItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    state_code: str = Field(index=True)
    state_name: str = Field(index=True)
    source_name: str
    source_type: SourceType = Field(index=True)
    title: str = Field(index=True)
    url: str = Field(index=True)
    published_at: datetime | None = Field(default=None, index=True)
    fetched_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    content_hash: str = Field(index=True)
    snippet: str | None = None
    full_text_path: str | None = None
    raw_payload_path: str | None = None


class LegalChange(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    state_code: str = Field(index=True)
    state_name: str = Field(index=True)
    change_type: ChangeType = Field(index=True)
    title: str = Field(index=True)
    summary: str
    legal_effect: str | None = None
    effective_date: date | None = Field(default=None, index=True)
    published_at: datetime | None = Field(default=None, index=True)
    detected_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    evidence_tier: EvidenceTier = Field(index=True)
    confidence_score: float = Field(default=0.0, index=True)
    source_name: str
    source_type: SourceType = Field(index=True)
    source_url: str
    raw_item_id: int | None = Field(default=None, foreign_key="rawitem.id")
    content_hash: str = Field(index=True)
    needs_human_review: bool = True
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    review_note: str | None = None


class WatchRun(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    started_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    finished_at: datetime | None = None
    status: str = "running"
    states_requested: str = "ALL"
    official_items: int = 0
    news_items: int = 0
    social_items: int = 0
    changes_created: int = 0
    errors: str | None = None


class AIModuleRun(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    module_name: str = Field(index=True)
    state_code: str | None = Field(default=None, index=True)
    question: str | None = Field(default=None, index=True)
    input_hash: str = Field(index=True)
    result_json: str
    summary: str | None = None
    evidence_tier: EvidenceTier = Field(default=EvidenceTier.insufficient, index=True)
    confidence_score: float = Field(default=0.0, index=True)
    definitive: bool = Field(default=False, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


# ---------------------------
# v6 production-hardening models
# ---------------------------

class UserRole(str, Enum):
    super_admin = "super_admin"
    compliance_head = "compliance_head"
    legal_reviewer = "legal_reviewer"
    state_manager = "state_manager"
    analyst = "analyst"
    ops_user = "ops_user"
    viewer = "viewer"


class UserAccount(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    display_name: str | None = None
    email: str | None = Field(default=None, index=True)
    password_hash: str
    role: UserRole = Field(default=UserRole.viewer, index=True)
    state_scope: str | None = Field(default=None, index=True, description="Comma-separated state codes or ALL")
    is_active: bool = Field(default=True, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    last_login_at: datetime | None = Field(default=None, index=True)


class APIKey(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    key_hash: str = Field(index=True)
    role: UserRole = Field(default=UserRole.analyst, index=True)
    state_scope: str | None = Field(default=None, index=True)
    is_active: bool = Field(default=True, index=True)
    created_by: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    last_used_at: datetime | None = Field(default=None, index=True)


class AuditLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    actor: str = Field(index=True)
    actor_role: str | None = Field(default=None, index=True)
    action: str = Field(index=True)
    entity_type: str = Field(index=True)
    entity_id: int | None = Field(default=None, index=True)
    state_code: str | None = Field(default=None, index=True)
    request_id: str | None = Field(default=None, index=True)
    details_json: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class SourceHealthStatus(str, Enum):
    live = "LIVE"
    changed = "CHANGED"
    unchanged = "UNCHANGED"
    failed = "FAILED"
    dry_run = "DRY_RUN"


class SourceSnapshot(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    source_item_id: int | None = Field(default=None, foreign_key="sourceitem.id", index=True)
    state_code: str = Field(index=True)
    state_name: str = Field(index=True)
    source_name: str = Field(index=True)
    url: str = Field(index=True)
    source_type: SourceType = Field(index=True)
    status: SourceHealthStatus = Field(index=True)
    http_status: int | None = Field(default=None, index=True)
    content_hash: str | None = Field(default=None, index=True)
    previous_hash: str | None = Field(default=None, index=True)
    changed: bool = Field(default=False, index=True)
    content_path: str | None = None
    error: str | None = None
    checked_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class DocumentRecord(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    state_code: str = Field(index=True)
    state_name: str = Field(index=True)
    title: str = Field(index=True)
    source_url: str = Field(index=True)
    source_name: str | None = Field(default=None, index=True)
    source_type: SourceType = Field(index=True)
    file_path: str | None = None
    text_path: str | None = None
    sha256: str = Field(index=True)
    detected_order_no: str | None = Field(default=None, index=True)
    detected_date: date | None = Field(default=None, index=True)
    evidence_tier: EvidenceTier = Field(default=EvidenceTier.insufficient, index=True)
    archived_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class ReviewStatus(str, Enum):
    new = "NEW"
    ai_processed = "AI_PROCESSED"
    needs_review = "NEEDS_REVIEW"
    approved = "APPROVED"
    rejected = "REJECTED"
    escalated = "ESCALATED"
    superseded = "SUPERSEDED"
    archived = "ARCHIVED"


class ReviewEntityType(str, Enum):
    legal_change = "legal_change"
    official_movement = "official_movement"
    work_signal = "work_signal"
    intelligence_brief = "intelligence_brief"
    raw_item = "raw_item"


class ReviewTask(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    entity_type: ReviewEntityType = Field(index=True)
    entity_id: int = Field(index=True)
    state_code: str | None = Field(default=None, index=True)
    title: str = Field(index=True)
    summary: str | None = None
    evidence_tier: EvidenceTier = Field(default=EvidenceTier.insufficient, index=True)
    confidence_score: float = Field(default=0.0, index=True)
    decision_recommendation: str = Field(default="REVIEW_REQUIRED", index=True)
    status: ReviewStatus = Field(default=ReviewStatus.needs_review, index=True)
    assigned_to_role: UserRole = Field(default=UserRole.compliance_head, index=True)
    assigned_to_user: str | None = Field(default=None, index=True)
    due_at: datetime | None = Field(default=None, index=True)
    source_url: str | None = None
    conflict_count: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    reviewed_by: str | None = Field(default=None, index=True)
    reviewed_at: datetime | None = Field(default=None, index=True)
    review_note: str | None = None


class ApprovalDecision(str, Enum):
    approve = "APPROVE"
    reject = "REJECT"
    escalate = "ESCALATE"
    supersede = "SUPERSEDE"


class Approval(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    review_task_id: int = Field(foreign_key="reviewtask.id", index=True)
    decision: ApprovalDecision = Field(index=True)
    decided_by: str = Field(index=True)
    decided_role: str | None = Field(default=None, index=True)
    note: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class GuidanceStatus(str, Enum):
    draft = "DRAFT"
    approved = "APPROVED"
    sent = "SENT"
    failed = "FAILED"


class PublishedGuidance(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    review_task_id: int | None = Field(default=None, foreign_key="reviewtask.id", index=True)
    state_code: str | None = Field(default=None, index=True)
    title: str = Field(index=True)
    body: str
    evidence_tier: EvidenceTier = Field(default=EvidenceTier.insufficient, index=True)
    status: GuidanceStatus = Field(default=GuidanceStatus.draft, index=True)
    telegram_sent: bool = Field(default=False, index=True)
    approved_by: str | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    sent_at: datetime | None = Field(default=None, index=True)


class JobRun(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    job_name: str = Field(index=True)
    status: str = Field(default="running", index=True)
    state_code: str | None = Field(default=None, index=True)
    started_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    finished_at: datetime | None = Field(default=None, index=True)
    result_json: str | None = None
    error: str | None = None
