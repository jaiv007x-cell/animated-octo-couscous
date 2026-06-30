from __future__ import annotations

from dataclasses import dataclass
from sqlmodel import Session, select
from .models import SourceItem


@dataclass(frozen=True)
class Jurisdiction:
    code: str
    name: str
    kind: str  # state or union_territory


# Current India administrative coverage: 28 states + 8 union territories.
# Use this registry to validate that every monitoring run and source file covers all jurisdictions.
ALL_JURISDICTIONS: tuple[Jurisdiction, ...] = (
    Jurisdiction("AP", "Andhra Pradesh", "state"),
    Jurisdiction("AR", "Arunachal Pradesh", "state"),
    Jurisdiction("AS", "Assam", "state"),
    Jurisdiction("BR", "Bihar", "state"),
    Jurisdiction("CG", "Chhattisgarh", "state"),
    Jurisdiction("GA", "Goa", "state"),
    Jurisdiction("GJ", "Gujarat", "state"),
    Jurisdiction("HR", "Haryana", "state"),
    Jurisdiction("HP", "Himachal Pradesh", "state"),
    Jurisdiction("JH", "Jharkhand", "state"),
    Jurisdiction("KA", "Karnataka", "state"),
    Jurisdiction("KL", "Kerala", "state"),
    Jurisdiction("MP", "Madhya Pradesh", "state"),
    Jurisdiction("MH", "Maharashtra", "state"),
    Jurisdiction("MN", "Manipur", "state"),
    Jurisdiction("ML", "Meghalaya", "state"),
    Jurisdiction("MZ", "Mizoram", "state"),
    Jurisdiction("NL", "Nagaland", "state"),
    Jurisdiction("OD", "Odisha", "state"),
    Jurisdiction("PB", "Punjab", "state"),
    Jurisdiction("RJ", "Rajasthan", "state"),
    Jurisdiction("SK", "Sikkim", "state"),
    Jurisdiction("TN", "Tamil Nadu", "state"),
    Jurisdiction("TS", "Telangana", "state"),
    Jurisdiction("TR", "Tripura", "state"),
    Jurisdiction("UP", "Uttar Pradesh", "state"),
    Jurisdiction("UK", "Uttarakhand", "state"),
    Jurisdiction("WB", "West Bengal", "state"),
    Jurisdiction("AN", "Andaman and Nicobar Islands", "union_territory"),
    Jurisdiction("CH", "Chandigarh", "union_territory"),
    Jurisdiction("DN", "Dadra and Nagar Haveli and Daman and Diu", "union_territory"),
    Jurisdiction("DL", "Delhi", "union_territory"),
    Jurisdiction("JK", "Jammu and Kashmir", "union_territory"),
    Jurisdiction("LA", "Ladakh", "union_territory"),
    Jurisdiction("LD", "Lakshadweep", "union_territory"),
    Jurisdiction("PY", "Puducherry", "union_territory"),
)

JURISDICTION_BY_CODE = {j.code: j for j in ALL_JURISDICTIONS}
STATE_CODES = [j.code for j in ALL_JURISDICTIONS if j.kind == "state"]
UNION_TERRITORY_CODES = [j.code for j in ALL_JURISDICTIONS if j.kind == "union_territory"]
ALL_CODES = [j.code for j in ALL_JURISDICTIONS]


def validate_all_india_coverage(codes: set[str]) -> dict:
    expected = set(ALL_CODES)
    return {
        "expected_total": len(expected),
        "state_count": len(STATE_CODES),
        "union_territory_count": len(UNION_TERRITORY_CODES),
        "present_total": len(codes & expected),
        "missing_codes": sorted(expected - codes),
        "extra_codes": sorted(codes - expected),
        "complete": expected.issubset(codes),
    }


def source_coverage(session: Session) -> dict:
    rows = list(session.exec(select(SourceItem)).all())
    by_code: dict[str, dict] = {}
    for j in ALL_JURISDICTIONS:
        by_code[j.code] = {
            "code": j.code,
            "name": j.name,
            "kind": j.kind,
            "source_count": 0,
            "active_source_count": 0,
            "official_like_source_count": 0,
            "sources": [],
        }
    extras: dict[str, dict] = {}
    for src in rows:
        target = by_code.get(src.state_code)
        if not target:
            target = extras.setdefault(src.state_code, {
                "code": src.state_code,
                "name": src.state_name,
                "kind": "unknown",
                "source_count": 0,
                "active_source_count": 0,
                "official_like_source_count": 0,
                "sources": [],
            })
        target["source_count"] += 1
        if src.is_active:
            target["active_source_count"] += 1
        if src.source_type.value in {"official", "gazette", "court", "regulator"}:
            target["official_like_source_count"] += 1
        target["sources"].append({
            "source_name": src.source_name,
            "url": src.url,
            "source_type": src.source_type.value,
            "priority": src.priority,
            "active": src.is_active,
            "notes": src.notes,
        })
    coverage = validate_all_india_coverage(set(by_code) | set(extras))
    coverage["jurisdictions"] = list(by_code.values()) + list(extras.values())
    coverage["needs_source_work"] = [
        row for row in coverage["jurisdictions"]
        if row["kind"] != "unknown" and (row["active_source_count"] == 0 or row["official_like_source_count"] == 0)
    ]
    return coverage
