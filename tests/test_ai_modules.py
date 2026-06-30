from app.ai_modules import (
    module_catalog, extract_entities, score_chatter, demand_forecast,
    retailer_dispatch_risk, fraud_anomaly, build_compliance_checklist
)
from app.models import EvidenceTier


def test_module_catalog_has_all_modules():
    catalog = module_catalog()
    assert catalog["count"] >= 14
    ids = {m["id"] for m in catalog["modules"]}
    assert "conclusive_synthesis" in ids
    assert "fraud_anomaly" in ids


def test_entity_extraction_detects_order_and_role():
    text = "Notification No EX/123 dated 1 July 2026: Shri Ramesh Kumar, IAS, Excise Commissioner reviewed licence renewal and permit transport."
    result = extract_entities(text, state_code="DL", source_type="official", source_url="https://excise.delhi.gov.in/order")
    assert result["evidence_tier"] == EvidenceTier.official_confirmed.value
    assert result["order_numbers"]
    assert "license" in result["update_categories"] or "permit_transport" in result["update_categories"]


def test_chatter_score_not_definitive():
    result = score_chatter("WhatsApp forward says licence fee may change. Not verified.")
    assert result["definitive"] is False
    assert result["evidence_tier"] == EvidenceTier.chatter_unverified.value
    assert result["credibility_score"] < 50


def test_forecast_returns_signal():
    result = demand_forecast([
        {"period": "Jan", "value": 100},
        {"period": "Feb", "value": 120},
        {"period": "Mar", "value": 140},
    ], horizon=2)
    assert len(result["forecast"]) == 2
    assert result["trend"] == "rising"


def test_dispatch_risk_blocks_invalid_permit():
    result = retailer_dispatch_risk({"permit_valid": False, "retailer_license_active": False, "quantity_cases": 50, "permit_balance_cases": 10})
    assert result["block_dispatch"] is True
    assert result["risk_score"] >= 65


def test_fraud_anomaly_duplicate_invoice():
    result = fraud_anomaly([
        {"invoice_no": "A1", "quantity_cases": 10, "permit_id": "P1"},
        {"invoice_no": "A1", "quantity_cases": 12, "permit_id": "P2"},
    ])
    assert result["anomaly_count"] >= 1


def test_checklist_has_blockers():
    result = build_compliance_checklist("New MRP and excise duty notification with immediate effect", evidence_tier="OFFICIAL_CONFIRMED")
    assert result["blocker_count"] >= 1
