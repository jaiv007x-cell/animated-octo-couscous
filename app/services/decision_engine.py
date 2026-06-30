from __future__ import annotations
from app.models import EvidenceTier


def decide_action(*, evidence_tier: EvidenceTier | str, has_conflict: bool = False, document_archived: bool = False, human_approved: bool = False, source_count: int = 1) -> dict:
    tier = evidence_tier.value if hasattr(evidence_tier, "value") else str(evidence_tier)
    if tier == EvidenceTier.chatter_unverified.value:
        return {"outcome": "BLOCK_ACTION", "review_required": True, "reason": "Chatter is not legal proof."}
    if has_conflict:
        return {"outcome": "REVIEW_REQUIRED", "review_required": True, "reason": "Conflicting evidence requires legal/compliance review."}
    if tier == EvidenceTier.official_confirmed.value:
        if human_approved:
            return {"outcome": "ALLOW_PUBLICATION", "review_required": False, "reason": "Official evidence approved by human reviewer."}
        if document_archived and source_count >= 1:
            return {"outcome": "REVIEW_REQUIRED", "review_required": True, "reason": "Official evidence found; approval required before internal guidance."}
        return {"outcome": "REVIEW_REQUIRED", "review_required": True, "reason": "Official source detected but proof archival or approval is incomplete."}
    if tier == EvidenceTier.govt_probable.value:
        return {"outcome": "REVIEW_REQUIRED", "review_required": True, "reason": "Government-adjacent signal but not conclusive."}
    if tier == EvidenceTier.reported_not_confirmed.value:
        return {"outcome": "SEND_AS_REPORTED", "review_required": False, "reason": "May be shared as reported intelligence, not compliance instruction."}
    return {"outcome": "REVIEW_REQUIRED", "review_required": True, "reason": "Insufficient proof."}
