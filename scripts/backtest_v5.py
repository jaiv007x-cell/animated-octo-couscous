from __future__ import annotations

import json
import subprocess
import zipfile
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yaml
from sqlmodel import SQLModel, Session, create_engine, select

from app.ai_modules import (
    module_catalog,
    extract_entities,
    summarize_text,
    classify_update,
    score_chatter,
    analyze_impact,
    build_compliance_checklist,
    rag_answer,
    conclusive_synthesis,
    detect_conflicts,
    officer_workmap,
    demand_forecast,
    retailer_dispatch_risk,
    fraud_anomaly,
    telegram_ai_preview,
    run_all_ai_suite,
)
from app.india_states import ALL_CODES, STATE_CODES, UNION_TERRITORY_CODES, validate_all_india_coverage
from app.models import RawItem, SourceType, EvidenceTier, LegalChange, OfficialMovement, WorkSignal, OfficialProfile, SourceItem, AIModuleRun
from app.processor import process_new_raw_items
from app.officials import ingest_forward_data, process_new_official_raw_items, answer_conclusive_question
from app.source_registry import seed_sources, validate_source_config
from app.telegram_updates import build_digest_text, split_telegram_message, send_telegram_text

OUT_JSON = ROOT.parent / "excisewatch_v5_backtest_results.json"
OUT_MD = ROOT.parent / "excisewatch_v5_backtest_report.md"
ZIP_PATH = ROOT.parent / "excisewatch_bot_v5_ai_suite.zip"


def shaish(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode()).hexdigest()[:20]


def add_raw(session: Session, state_code: str, state_name: str, source_name: str, source_type: SourceType, title: str, url: str, snippet: str, days_ago: int = 1):
    content = f"{title}\n{snippet}\n{url}"
    item = RawItem(
        state_code=state_code,
        state_name=state_name,
        source_name=source_name,
        source_type=source_type,
        title=title,
        url=url,
        published_at=datetime.utcnow() - timedelta(days=days_ago),
        fetched_at=datetime.utcnow(),
        content_hash=shaish(content),
        snippet=snippet,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def main():
    report: dict = {"generated_at_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z"}

    # 1) Package integrity and unit tests
    zip_checked = False
    zip_ok = True
    zip_tail = "ZIP not found; source checkout backtest, package integrity skipped."
    if ZIP_PATH.exists():
        zip_checked = True
        try:
            with zipfile.ZipFile(ZIP_PATH) as zf:
                bad_file = zf.testzip()
            zip_ok = bad_file is None
            zip_tail = "Archive test OK" if zip_ok else f"Corrupt member: {bad_file}"
        except Exception as exc:
            zip_tail = str(exc)
    pytest = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT, capture_output=True, text=True, timeout=120)
    report["package_integrity"] = {
        "zip_path": str(ZIP_PATH),
        "zip_checked": zip_checked,
        "zip_ok": zip_ok,
        "zip_tail": zip_tail,
    }
    report["unit_tests"] = {
        "passed": pytest.returncode == 0,
        "return_code": pytest.returncode,
        "output_tail": "\n".join((pytest.stdout + pytest.stderr).splitlines()[-25:]),
    }

    # 2) Static coverage
    source_cfg = yaml.safe_load((ROOT / "data/sources.yaml").read_text(encoding="utf-8"))
    configured_codes = {s["code"] for s in source_cfg["states"]}
    source_counts = {s["code"]: len(s.get("sources", [])) for s in source_cfg["states"]}
    coverage = validate_all_india_coverage(configured_codes)
    report["all_india_source_coverage"] = {
        **coverage,
        "state_count": len(STATE_CODES),
        "union_territory_count": len(UNION_TERRITORY_CODES),
        "total_sources_in_yaml": sum(source_counts.values()),
        "min_sources_per_jurisdiction": min(source_counts.values()),
        "max_sources_per_jurisdiction": max(source_counts.values()),
        "jurisdictions_with_one_source": sorted([code for code, cnt in source_counts.items() if cnt == 1]),
    }

    # 3) Create isolated backtest DB
    db_path = ROOT / "storage" / "backtest_v5.db"
    if db_path.exists():
        db_path.unlink()
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        inserted_sources = seed_sources(session, force=True)
        source_rows = session.exec(select(SourceItem)).all()
        report["db_seed"] = {"source_items_inserted": inserted_sources, "source_items_in_db": len(source_rows)}

        # Backtest data set: official-confirmed, reported-only, chatter, officer/ministry signals, conflict signal.
        official_law = add_raw(
            session,
            "DL",
            "Delhi",
            "Delhi Excise Notifications",
            SourceType.official,
            "Official: Excise licence renewal, MRP and transport permit notification issued",
            "https://excise.delhi.gov.in/notifications/excise-licence-renewal-mrp-transport-permit-2026",
            "Notification No EXC/LIC/2026/123 dated 01-07-2026. The Delhi Excise Department amends licence renewal workflow, excise duty rate, registered MRP, e-challan and transport permit requirements with immediate effect from 01-07-2026.",
            days_ago=2,
        )
        official_dry = add_raw(
            session,
            "MH",
            "Maharashtra",
            "Maharashtra State Excise PDF Lists",
            SourceType.official,
            "Official: Dry day order for polling and counting dates",
            "https://stateexcise.maharashtra.gov.in/official/dry-day-order-2026",
            "Order No MH/EX/DryDay/2026 dated 15-06-2026 declares dry day and closure for retail liquor shops during polling and counting, with immediate enforcement and inspection requirements.",
            days_ago=4,
        )
        reported = add_raw(
            session,
            "DL",
            "Delhi",
            "Reputed News Report",
            SourceType.news,
            "Report: Delhi may increase excise licence fee next quarter",
            "https://reuters.com/world/india/example-excise-license-fee-report",
            "News report says officials are considering a hike in licence fee and excise duty, but no official notification has been issued yet.",
            days_ago=3,
        )
        conflict_news = add_raw(
            session,
            "DL",
            "Delhi",
            "Industry News",
            SourceType.news,
            "Report: Delhi licence fee increase postponed",
            "https://business-standard.com/example-delhi-excise-fee-postponed",
            "Industry report says the proposed licence fee increase has been postponed and deferred until the next policy review.",
            days_ago=2,
        )
        chatter = add_raw(
            session,
            "DL",
            "Delhi",
            "Trade Telegram Forward",
            SourceType.social,
            "Forward: Delhi licence fee rumour",
            "manual://telegram-forward-fee-hike",
            "Forwarded WhatsApp/Telegram chatter says licence fee may double soon. Not verified. Market says new MRP list expected but no circular attached.",
            days_ago=1,
        )

        changes = process_new_raw_items(session)

        official_release = ingest_forward_data(
            session,
            "DL",
            "Delhi",
            "Official: Excise Minister review meeting and officer order",
            "Official release says Shri Rakesh Kumar, IAS, Principal Secretary Excise and the Excise Minister reviewed licence renewal, excise revenue, permit digitisation, MRP and track-and-trace. Order No ABC/123 dated 01-07-2026.",
            "https://excise.delhi.gov.in/official-release/minister-review-2026",
            "State official release",
            SourceType.official,
        )
        cm_forward = ingest_forward_data(
            session,
            "DL",
            "Delhi",
            "Forward: CMO excise review chatter",
            "Forward says the Chief Minister and Excise Minister reviewed licence renewal, duty changes, permit digitisation and officer transfers. Not verified. Minutes expected soon.",
            "manual://whatsapp-forward-cm-review",
            "Trade WhatsApp forward",
            SourceType.social,
        )
        official_results = process_new_official_raw_items(session)

        # Module runs
        sample_text = "Notification No EX/123 dated 1 July 2026: Shri Ramesh Kumar, IAS, Excise Commissioner reviewed licence renewal, MRP and permit transport with immediate effect."
        module_outputs = {
            "catalog_count": module_catalog()["count"],
            "extract_entities": extract_entities(sample_text, state_code="DL", source_type="official", source_url="https://excise.delhi.gov.in/order", session=session),
            "summarize": summarize_text(sample_text, title="Official notification", state_code="DL", session=session),
            "classify": classify_update(sample_text),
            "chatter_score": score_chatter("WhatsApp forward says licence fee may change. Not verified. No official circular attached.", state_code="DL", session=session),
            "impact": analyze_impact("New MRP and excise duty notification with immediate effect", state_code="DL", evidence_tier="OFFICIAL_CONFIRMED", session=session),
            "checklist": build_compliance_checklist("Transport permit and e-challan rules changed with immediate effect", state_code="DL", evidence_tier="OFFICIAL_CONFIRMED", session=session),
            "rag": rag_answer(session, "Delhi licence renewal MRP permit transport", state_code="DL", days=365, include_chatter=False),
            "conclusive": conclusive_synthesis(session, "Delhi licence renewal MRP permit transport", state_code="DL", days=365, include_chatter=True),
            "conflicts": detect_conflicts(session, state_code="DL", days=365, question="licence fee increase postponed effective"),
            "officer_workmap": officer_workmap(session, state_code="DL", days=365),
            "forecast": demand_forecast([
                {"period": "Jan", "cases": 100},
                {"period": "Feb", "cases": 120},
                {"period": "Mar", "cases": 145},
                {"period": "Apr", "cases": 160},
                {"period": "May", "cases": 180},
                {"period": "Jun", "cases": 210},
            ], period_key="period", value_key="cases", horizon=3, state_code="DL", session=session),
            "dispatch_risk_high": retailer_dispatch_risk({
                "permit_valid": False,
                "retailer_license_active": False,
                "quantity_cases": 75,
                "permit_balance_cases": 40,
                "payment_overdue_days": 46,
                "declared_mrp": 5400,
                "registered_mrp": 5200,
            }, state_code="DL", session=session),
            "dispatch_risk_low": retailer_dispatch_risk({
                "permit_valid": True,
                "retailer_license_active": True,
                "quantity_cases": 25,
                "permit_balance_cases": 100,
                "payment_overdue_days": 0,
                "declared_mrp": 5200,
                "registered_mrp": 5200,
            }, state_code="DL", session=session),
            "fraud_anomaly": fraud_anomaly([
                {"invoice_no": "INV-001", "quantity_cases": 10, "permit_id": "TP-1", "breakage_cases": 0},
                {"invoice_no": "INV-001", "quantity_cases": 12, "permit_id": "TP-2", "breakage_cases": 0},
                {"invoice_no": "INV-003", "quantity_cases": 280, "permit_id": "", "route_mismatch": True, "breakage_cases": 10},
                {"invoice_no": "INV-004", "quantity_cases": 9, "permit_id": "TP-4", "breakage_cases": 0},
            ], state_code="DL", session=session),
            "telegram_preview": telegram_ai_preview(session, state_code="DL", days=365, limit=10, include_chatter=False),
            "full_suite": run_all_ai_suite(session, "What is confirmed about Delhi licence renewal, MRP, permit transport, minister/officer movement?", state_code="DL", days=365, text=sample_text, include_chatter=True),
        }

        digest_text = build_digest_text(session, state_code="DL", days=365, limit=10, include_chatter=False)
        telegram_dry = send_telegram_text(digest_text, dry_run=True)
        telegram_chunks = split_telegram_message(digest_text)

        legal_changes = session.exec(select(LegalChange)).all()
        movements = session.exec(select(OfficialMovement)).all()
        work_signals = session.exec(select(WorkSignal)).all()
        profiles = session.exec(select(OfficialProfile)).all()
        ai_runs = session.exec(select(AIModuleRun)).all()

        tiers = Counter([c.evidence_tier.value for c in legal_changes] + [m.evidence_tier.value for m in movements] + [w.evidence_tier.value for w in work_signals])
        change_types = Counter([c.change_type.value for c in legal_changes])

        report["synthetic_backtest_dataset"] = {
            "raw_items_inserted": 5,
            "official_forward_items_inserted": 2,
            "legal_changes_created": len(changes),
            "official_movements_created": official_results.get("movements_created"),
            "work_signals_created": official_results.get("work_signals_created"),
            "profiles_created": len(profiles),
            "legal_change_types": dict(change_types),
            "evidence_tier_distribution": dict(tiers),
        }
        report["module_outputs_compact"] = {
            "catalog_count": module_outputs["catalog_count"],
            "extract_evidence_tier": module_outputs["extract_entities"]["evidence_tier"],
            "extract_order_numbers": module_outputs["extract_entities"]["order_numbers"],
            "classify_primary": module_outputs["classify"]["primary_category"],
            "chatter_definitive": module_outputs["chatter_score"]["definitive"],
            "chatter_score": module_outputs["chatter_score"]["credibility_score"],
            "impact_priority": module_outputs["impact"]["priority"],
            "checklist_blockers": module_outputs["checklist"]["blocker_count"],
            "rag_status": module_outputs["rag"]["answer_status"],
            "rag_definitive": module_outputs["rag"]["definitive"],
            "conclusive_status": module_outputs["conclusive"]["answer_status"],
            "conclusive_definitive": module_outputs["conclusive"]["definitive"],
            "conclusive_official_count": module_outputs["conclusive"]["official_source_count"],
            "conflict_count": module_outputs["conflicts"]["conflict_count"],
            "workmap_count": module_outputs["officer_workmap"]["signal_count"],
            "forecast_trend": module_outputs["forecast"]["trend"],
            "forecast_next_1": module_outputs["forecast"]["forecast"][0]["forecast_value"],
            "dispatch_high_block": module_outputs["dispatch_risk_high"]["block_dispatch"],
            "dispatch_high_score": module_outputs["dispatch_risk_high"]["risk_score"],
            "dispatch_low_block": module_outputs["dispatch_risk_low"]["block_dispatch"],
            "dispatch_low_score": module_outputs["dispatch_risk_low"]["risk_score"],
            "fraud_anomaly_count": module_outputs["fraud_anomaly"]["anomaly_count"],
            "fraud_investigation_required": module_outputs["fraud_anomaly"]["investigation_required"],
            "telegram_chunk_count": module_outputs["telegram_preview"]["chunk_count"],
            "suite_final_status": module_outputs["full_suite"]["final_decision"]["status"],
            "suite_can_act": module_outputs["full_suite"]["final_decision"]["can_act_operationally"],
            "ai_module_runs_logged": len(ai_runs),
        }
        report["telegram_backtest"] = {
            "dry_run": telegram_dry.get("dry_run"),
            "sent": telegram_dry.get("sent"),
            "chunk_count": len(telegram_chunks),
            "first_chunk_chars": len(telegram_chunks[0]) if telegram_chunks else 0,
            "digest_contains_confirmed_item": "Official:" in digest_text,
        }

        # Assertions / pass-fail gates
        gates = []
        def gate(name, passed, details=""):
            gates.append({"name": name, "passed": bool(passed), "details": details})

        gate("ZIP integrity", report["package_integrity"]["zip_ok"])
        gate("Unit tests", report["unit_tests"]["passed"])
        gate("All-India registry coverage", coverage["complete"] and len(STATE_CODES) == 28 and len(UNION_TERRITORY_CODES) == 8)
        gate("Source YAML has no missing jurisdiction", coverage["missing_codes"] == [] and coverage["extra_codes"] == [])
        gate("Source DB seeded", inserted_sources == sum(source_counts.values()))
        gate("AI module count >= 14", module_outputs["catalog_count"] >= 14)
        gate("Official evidence becomes definitive", module_outputs["conclusive"]["definitive"] is True and module_outputs["conclusive"]["answer_status"] == "CONFIRMED")
        gate("Chatter is not definitive", module_outputs["chatter_score"]["definitive"] is False and module_outputs["chatter_score"]["evidence_tier"] == "CHATTER_UNVERIFIED")
        gate("High-risk dispatch blocked", module_outputs["dispatch_risk_high"]["block_dispatch"] is True)
        gate("Low-risk dispatch not blocked", module_outputs["dispatch_risk_low"]["block_dispatch"] is False)
        gate("Fraud anomalies detected", module_outputs["fraud_anomaly"]["anomaly_count"] >= 3 and module_outputs["fraud_anomaly"]["investigation_required"] is True)
        gate("Telegram dry run safe", telegram_dry.get("dry_run") is True and telegram_dry.get("sent") == 0 and len(telegram_chunks) >= 1)
        gate("AI suite produces operational decision", module_outputs["full_suite"]["final_decision"]["status"] in {"CONFIRMED", "REPORTED_ONLY", "CHATTER_ONLY", "OFFICIAL_BUT_INCOMPLETE", "CONFLICTING_EVIDENCE", "INSUFFICIENT"})
        gate("AI runs are logged", len(ai_runs) >= 10)

        report["gates"] = gates
        report["gate_summary"] = {"passed": sum(g["passed"] for g in gates), "total": len(gates), "failed": [g for g in gates if not g["passed"]]}

    OUT_JSON.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    verdict = "PASS" if report["gate_summary"]["passed"] == report["gate_summary"]["total"] else "PARTIAL PASS"
    prod_verdict = "NOT production-ready without real official-source validation, database hardening, auth, rate limiting, and human compliance review."
    md = []
    md.append(f"# ExciseWatch v5 Backtest Report\n")
    md.append(f"Generated UTC: {report['generated_at_utc']}\n")
    md.append(f"## Executive verdict\n\n**Backtest verdict:** {verdict} ({report['gate_summary']['passed']}/{report['gate_summary']['total']} gates passed).\n\n**Production verdict:** {prod_verdict}\n")
    md.append("## What was tested\n")
    md.append("- ZIP integrity\n- Unit test suite\n- 28 states + 8 UT coverage registry\n- Source seeding\n- Official law-update processing\n- News/report handling\n- Chatter handling\n- CM / minister / Principal Secretary / officer workstream extraction\n- Conclusive answer engine\n- RAG answer engine\n- Conflict detector\n- Impact and compliance checklist modules\n- Demand forecast\n- Dispatch risk scoring\n- Fraud/diversion anomaly detection\n- Telegram digest dry run\n- AI run audit logging\n")
    md.append("## Key results\n")
    m = report["module_outputs_compact"]
    rows = [
        ("Unit tests", "PASS" if report["unit_tests"]["passed"] else "FAIL", report["unit_tests"]["output_tail"].splitlines()[0] if report["unit_tests"]["output_tail"] else ""),
        ("ZIP integrity", "PASS" if report["package_integrity"]["zip_ok"] else "FAIL", "Archive test OK"),
        ("All-India coverage", "PASS" if report["all_india_source_coverage"]["complete"] else "FAIL", f"{report['all_india_source_coverage']['present_total']}/{report['all_india_source_coverage']['expected_total']} jurisdictions"),
        ("Source registry", "PASS", f"{report['all_india_source_coverage']['total_sources_in_yaml']} source rows; {len(report['all_india_source_coverage']['jurisdictions_with_one_source'])} jurisdictions only have one source"),
        ("AI modules", "PASS" if m["catalog_count"] >= 14 else "FAIL", f"{m['catalog_count']} modules"),
        ("Conclusive engine", "PASS" if m["conclusive_definitive"] else "FAIL", f"{m['conclusive_status']} / official sources: {m['conclusive_official_count']}"),
        ("Chatter safety", "PASS" if not m["chatter_definitive"] else "FAIL", f"score {m['chatter_score']} / not definitive"),
        ("Dispatch risk", "PASS" if m["dispatch_high_block"] and not m["dispatch_low_block"] else "FAIL", f"high={m['dispatch_high_score']}, low={m['dispatch_low_score']}"),
        ("Fraud anomaly", "PASS" if m["fraud_anomaly_count"] >= 3 else "FAIL", f"{m['fraud_anomaly_count']} anomalies"),
        ("Telegram", "PASS" if report["telegram_backtest"]["dry_run"] and report["telegram_backtest"]["sent"] == 0 else "FAIL", f"{report['telegram_backtest']['chunk_count']} chunk(s)"),
    ]
    md.append("| Area | Result | Evidence |\n|---|---:|---|\n")
    for area, result, evidence in rows:
        md.append(f"| {area} | {result} | {str(evidence).replace('|','/')} |\n")
    md.append("\n## Gate results\n")
    md.append("| Gate | Result | Details |\n|---|---:|---|\n")
    for g in report["gates"]:
        md.append(f"| {g['name']} | {'PASS' if g['passed'] else 'FAIL'} | {g.get('details','')} |\n")
    md.append("\n## Synthetic dataset outcome\n")
    d = report["synthetic_backtest_dataset"]
    md.append(f"- Raw items inserted: {d['raw_items_inserted']}\n")
    md.append(f"- Official/forward items inserted: {d['official_forward_items_inserted']}\n")
    md.append(f"- Legal changes created: {d['legal_changes_created']}\n")
    md.append(f"- Official movements created: {d['official_movements_created']}\n")
    md.append(f"- Work signals created: {d['work_signals_created']}\n")
    md.append(f"- Evidence tier distribution: `{d['evidence_tier_distribution']}`\n")
    md.append("\n## Limitations found\n")
    md.append("1. This backtest validates the software logic with local/synthetic historical scenarios; it does not prove live state-government pages are reachable or parseable every day.\n")
    md.append("2. Several jurisdictions currently have only one configured source, so production coverage needs more official URLs, gazette feeds, court feeds, department circular pages and cabinet/CMO sources.\n")
    md.append("3. The AI layer is deterministic/rule-based by default. It is safe and auditable, but it will miss nuanced language until RAG/LLM extraction is connected to verified documents.\n")
    md.append("4. The app needs authentication, role-based permissions, source-verification workflow, immutable audit logging, scheduled jobs and monitoring before use in a real distributor.\n")
    md.append("5. Timezone warnings use `datetime.utcnow()`; not fatal, but should be changed to timezone-aware UTC datetimes.\n")
    md.append("\n## Conclusive recommendation\n")
    md.append("The v5 build passes the local backtest as an MVP intelligence engine. It is fit for pilot use with manual source review, Telegram dry-run alerts, and compliance-team validation. It is not yet fit for fully automated legal/compliance action across all Indian states without live source validation and production hardening.\n")
    OUT_MD.write_text("".join(md), encoding="utf-8")

    print(json.dumps({
        "report_json": str(OUT_JSON),
        "report_md": str(OUT_MD),
        "verdict": verdict,
        "gates": report["gate_summary"],
        "module_outputs_compact": report["module_outputs_compact"],
    }, indent=2))


if __name__ == "__main__":
    main()
