from __future__ import annotations
import json, hashlib, os, subprocess, sys, tempfile, time
from pathlib import Path
from datetime import datetime
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from sqlmodel import SQLModel, Session, create_engine, select
from fastapi.testclient import TestClient

from app.models import (
    SourceItem, SourceType, LegalChange, ChangeType, EvidenceTier, SourceSnapshot,
    DocumentRecord, ReviewTask, PublishedGuidance, ApprovalDecision, UserAccount,
    WorkSignal, WorkSignalType, UserRole, AuditLog, GuidanceStatus
)
from app.source_registry import validate_source_config, seed_sources
from app.india_states import source_coverage
from app.services.live_source_validator import validate_sources
import app.services.live_source_validator as lsv
from app.services.document_archiver import archive_text_document
from app.services.decision_engine import decide_action
from app.services.review_service import generate_review_tasks, list_review_tasks, decide_review
from app.services.publication_service import publish_guidance_to_telegram
from app.jobs.scheduler import run_named_job
from app.auth.security import hash_password, verify_password, create_access_token, decode_access_token, has_permission
from app.ai_modules import (
    module_catalog, run_all_ai_suite, conclusive_synthesis, score_chatter,
    retailer_dispatch_risk, fraud_anomaly, demand_forecast
)
from app.main import app
from app.db import get_session

OUT_DIR = ROOT / "storage" / "backtests"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_JSON = OUT_DIR / "excisewatch_v6_conclusive_backtest_results.json"
OUT_MD = OUT_DIR / "excisewatch_v6_conclusive_backtest_report.md"
ZIP = ROOT.parent / "excisewatch_bot_v6_production.zip"

results: dict[str, Any] = {
    'generated_at_ist_context': '2026-06-27',
    'package': str(ZIP),
    'checks': [],
    'metrics': {},
    'findings': [],
    'recommendations': [],
}

def add_check(name: str, passed: bool, details: Any = None, severity: str = 'gate'):
    results['checks'].append({'name': name, 'passed': bool(passed), 'severity': severity, 'details': details})

# 1. Package integrity
if ZIP.exists():
    digest = hashlib.sha256(ZIP.read_bytes()).hexdigest()
    results['metrics']['zip_size_bytes'] = ZIP.stat().st_size
    results['metrics']['zip_sha256'] = digest
    add_check('ZIP exists and SHA256 generated', ZIP.stat().st_size > 0, {'size_bytes': ZIP.stat().st_size, 'sha256': digest})
else:
    add_check('ZIP package integrity skipped for source checkout', True, {'zip_path': str(ZIP), 'note': 'ZIP not found; running backtest against source checkout.'}, severity='info')

# 2. Unit tests
start = time.time()
proc = subprocess.run([sys.executable, '-m', 'pytest', '-q'], cwd=ROOT, text=True, capture_output=True, timeout=120)
results['metrics']['pytest_seconds'] = round(time.time() - start, 2)
results['metrics']['pytest_stdout'] = proc.stdout[-2000:]
results['metrics']['pytest_stderr'] = proc.stderr[-2000:]
unit_pass = proc.returncode == 0 and 'failed' not in proc.stdout.lower()
add_check('Unit test suite', unit_pass, {'returncode': proc.returncode, 'stdout_tail': proc.stdout[-500:]})

# 3. Test DB setup
work = Path(tempfile.mkdtemp(prefix='ew_v6_backtest_'))
engine = create_engine(f"sqlite:///{work/'backtest.db'}", connect_args={'check_same_thread': False})
SQLModel.metadata.create_all(engine)

def session_factory():
    return Session(engine)

with session_factory() as session:
    # 4. Source config and coverage
    cfg_cov = validate_source_config(str(ROOT/'data/sources.yaml'))
    add_check('Source config covers 28 states + 8 UTs', cfg_cov['complete'] and cfg_cov['present_total'] == 36, cfg_cov)
    seeded = seed_sources(session, force=True)
    cov = source_coverage(session)
    results['metrics']['seeded_sources'] = seeded
    results['metrics']['jurisdictions_configured'] = cov['present_total']
    results['metrics']['jurisdictions_needing_source_work'] = len([j for j in cov['jurisdictions'] if j.get('kind') != 'unknown' and j.get('source_count', 0) < 2])
    add_check('All jurisdictions seeded with at least one active source', cov['complete'] and all(j['active_source_count'] >= 1 for j in cov['jurisdictions'] if j['kind'] != 'unknown'), {'seeded': seeded, 'needs_source_work_count': len(cov['needs_source_work'])})
    add_check('Source-depth target: at least two sources per jurisdiction', all(j['source_count'] >= 2 for j in cov['jurisdictions'] if j['kind'] != 'unknown'), {'states_with_one_source': [j['code'] for j in cov['jurisdictions'] if j['kind'] != 'unknown' and j['source_count'] < 2]}, severity='production_gap')

    # 5. Dry-run validation across all India
    dry = validate_sources(session, live_fetch=False, max_sources=200)
    snap_count = len(session.exec(select(SourceSnapshot)).all())
    add_check('Dry-run live-source validator creates snapshots for all configured sources', dry['sources_checked'] == seeded and snap_count >= seeded, {'sources_checked': dry['sources_checked'], 'snapshots': snap_count})

    # 6. Fake live HTTP validation path, no external internet needed
    class FakeResp:
        status_code = 200
        headers = {'content-type': 'text/html'}
        text = '<html><body><h1>Official Excise Notification No. EX/DL/2026/01 dated 27/06/2026</h1><p>Dry day order and permit transport workflow reviewed by Excise Commissioner.</p></body></html>'
        def raise_for_status(self): return None
    old_get = lsv.requests.get
    lsv.requests.get = lambda *a, **kw: FakeResp()
    try:
        live = validate_sources(session, state_code='DL', live_fetch=True, max_sources=1, archive_documents=True)
    finally:
        lsv.requests.get = old_get
    docs = session.exec(select(DocumentRecord).where(DocumentRecord.state_code == 'DL')).all()
    add_check('Live fetch code path archives hashed official document', live['live_sources_working'] == 1 and live['documents_archived'] >= 1 and len(docs) >= 1, {'live_result': live, 'document_count_dl': len(docs), 'doc_sha256': docs[-1].sha256 if docs else None})

    # 7. Document archival direct extraction test
    doc = archive_text_document(
        session,
        state_code='MH', state_name='Maharashtra', title='Excise Circular No. MH/EX/2026/77 dated 27/06/2026',
        source_url='https://stateexcise.maharashtra.gov.in/official/circular', source_name='Maharashtra State Excise',
        source_type=SourceType.official,
        content='Circular No. MH/EX/2026/77 dated 27/06/2026: licence renewal and MRP price master update.'
    )
    add_check('Document archiver detects order/date and assigns official tier', bool(doc.sha256) and doc.evidence_tier == EvidenceTier.official_confirmed and (doc.detected_order_no is not None or doc.detected_date is not None), {'sha256': doc.sha256, 'order_no': doc.detected_order_no, 'date': str(doc.detected_date), 'tier': doc.evidence_tier.value})

    # 8. Auth/RBAC local security functions
    hp = hash_password('StrongPass123')
    tok = create_access_token('admin', 'super_admin', minutes=5)
    payload = decode_access_token(tok)
    auth_ok = verify_password('StrongPass123', hp) and payload['sub'] == 'admin' and has_permission(UserRole.super_admin, '*') and not has_permission(UserRole.viewer, 'approve')
    add_check('Auth hashing, token verification and RBAC permissions', auth_ok, {'token_subject': payload.get('sub'), 'super_admin_all': has_permission(UserRole.super_admin, '*'), 'viewer_approve': has_permission(UserRole.viewer, 'approve')})

    # 9. TestClient API auth endpoints with dependency override
    def override_get_session():
        with Session(engine) as s:
            yield s
    app.dependency_overrides[get_session] = override_get_session
    client = TestClient(app)
    boot = client.post('/api/auth/bootstrap-admin', json={'username': 'admin', 'password': 'StrongPass123', 'email': 'admin@example.com'})
    login = client.post('/api/auth/login', json={'username': 'admin', 'password': 'StrongPass123'})
    bearer = login.json().get('access_token') if login.status_code == 200 else None
    who = client.get('/api/auth/whoami', headers={'Authorization': f'Bearer {bearer}'}) if bearer else None
    add_check('API auth bootstrap/login/whoami', boot.status_code == 200 and login.status_code == 200 and who and who.status_code == 200 and who.json().get('role') == 'super_admin', {'bootstrap': boot.json() if boot.status_code == 200 else boot.text, 'login_status': login.status_code, 'whoami': who.json() if who else None})

    # 10. Decision engine hard stops
    d_chatter = decide_action(evidence_tier=EvidenceTier.chatter_unverified)
    d_official_unapproved = decide_action(evidence_tier=EvidenceTier.official_confirmed, document_archived=True, human_approved=False)
    d_approved = decide_action(evidence_tier=EvidenceTier.official_confirmed, document_archived=True, human_approved=True)
    add_check('Decision engine blocks chatter and requires approval for official evidence', d_chatter['outcome'] == 'BLOCK_ACTION' and d_official_unapproved['outcome'] == 'REVIEW_REQUIRED' and d_approved['outcome'] == 'ALLOW_PUBLICATION', {'chatter': d_chatter, 'official_unapproved': d_official_unapproved, 'approved': d_approved})

    # 11. Insert official legal change, generate review, approve, guidance
    official_change = LegalChange(
        state_code='DL', state_name='Delhi', change_type=ChangeType.dry_day,
        title='Official dry day order notification increased restrictions',
        summary='Official Excise Department notification imposes dry day restrictions for a specified date.',
        legal_effect='Block affected dispatch and retail sale on restricted date.',
        published_at=datetime.utcnow(), evidence_tier=EvidenceTier.official_confirmed, confidence_score=0.95,
        source_name='Delhi Excise', source_type=SourceType.official, source_url='https://excise.delhi.gov.in/notifications',
        content_hash='official-dry-day-hash', needs_human_review=True
    )
    session.add(official_change)
    session.commit()
    gen = generate_review_tasks(session, state_code='DL')
    tasks = list_review_tasks(session, state_code='DL')
    task = next((t for t in tasks if t.entity_type.value == 'legal_change' and t.entity_id == official_change.id), None)
    appr = decide_review(session, task.id, ApprovalDecision.approve, actor='legal_head', actor_role='compliance_head', note='Backtest approval after official source review') if task else {'status':'missing'}
    guidance = session.get(PublishedGuidance, appr.get('guidance_id')) if appr.get('guidance_id') else None
    add_check('Human review approval creates approved guidance', bool(task) and appr.get('status') == 'APPROVED' and guidance is not None and guidance.status == GuidanceStatus.approved, {'review_generate': gen, 'approval': appr, 'guidance_id': guidance.id if guidance else None})

    # 12. Telegram publication dry-run and chatter block
    pub = publish_guidance_to_telegram(session, guidance.id, dry_run=True) if guidance else {'status':'missing'}
    chatter_guidance = PublishedGuidance(review_task_id=None, state_code='DL', title='Chatter guidance should be blocked', body='Rumour only', evidence_tier=EvidenceTier.chatter_unverified, status=GuidanceStatus.approved, approved_by='tester')
    session.add(chatter_guidance); session.commit(); session.refresh(chatter_guidance)
    blocked = publish_guidance_to_telegram(session, chatter_guidance.id, dry_run=True)
    add_check('Telegram publication dry-run works and blocks chatter guidance', pub.get('status') == 'dry_run' and blocked.get('status') == 'blocked', {'official_dry_run': pub, 'chatter_block': blocked})

    # 13. Scheduler jobs
    job1 = run_named_job(session, 'validate_sources', state_code='DL', dry_run=True)
    job2 = run_named_job(session, 'generate_review_tasks', state_code='DL', dry_run=True)
    add_check('Scheduler run-now jobs execute successfully', job1['status'] == 'success' and job2['status'] == 'success', {'validate_sources': job1, 'generate_review_tasks': job2})

    # 14. AI module catalog and module functions
    catalog = module_catalog()
    add_check('AI module catalog exposes all 14 modules', catalog['count'] == 14, {'count': catalog['count']})
    high_risk = retailer_dispatch_risk({'retailer_license_active': False, 'permit_valid': False, 'dry_day': True, 'quantity_cases': 100, 'permit_balance_cases': 50, 'declared_mrp': 5200, 'registered_mrp': 5000}, session=session, state_code='DL')
    low_risk = retailer_dispatch_risk({'retailer_license_active': True, 'permit_valid': True, 'dry_day': False, 'quantity_cases': 10, 'permit_balance_cases': 50, 'declared_mrp': 5000, 'registered_mrp': 5000}, session=session, state_code='DL')
    fraud = fraud_anomaly([
        {'invoice_no':'INV1','quantity_cases':10,'permit_id':'TP1'},
        {'invoice_no':'INV1','quantity_cases':11,'permit_id':'TP1'},
        {'invoice_no':'INV2','quantity_cases':100,'permit_id':'','route_mismatch':True,'breakage_cases':5},
    ], session=session, state_code='DL')
    forecast = demand_forecast([{'period':'W1','value':100},{'period':'W2','value':120},{'period':'W3','value':140},{'period':'W4','value':160}], horizon=2, session=session, state_code='DL')
    ai_ops_ok = high_risk['block_dispatch'] and low_risk['risk_tier'] == 'low' and fraud['investigation_required'] and forecast['trend'] == 'rising'
    add_check('Operational AI modules: dispatch risk, fraud, demand forecast', ai_ops_ok, {'high_risk': high_risk, 'low_risk': low_risk, 'fraud': fraud, 'forecast': forecast})

    # 15. Conclusive AI suite positive test
    suite = run_all_ai_suite(session, question='What is the latest confirmed dry day order in Delhi?', state_code='DL', days=365, include_chatter=False)
    add_check('Conclusive AI suite confirms official dry-day evidence', suite['conclusive']['definitive'] is True and suite['conclusive']['answer_status'] == 'CONFIRMED', {'status': suite['conclusive']['answer_status'], 'definitive': suite['conclusive']['definitive'], 'final_decision': suite['final_decision']})

    # 16. Negative semantic isolation test: unrelated official evidence should not confirm chatter-only query
    chatter_change = LegalChange(
        state_code='DL', state_name='Delhi', change_type=ChangeType.fee,
        title='WhatsApp forward says licence fee may increase',
        summary='Forwarded market chatter says licence fee may increase. Not verified.',
        legal_effect='No action until official circular.',
        published_at=datetime.utcnow(), evidence_tier=EvidenceTier.chatter_unverified, confidence_score=0.2,
        source_name='Trade WhatsApp forward', source_type=SourceType.social, source_url='manual://whatsapp-forward',
        content_hash='chatter-fee-hash', needs_human_review=True
    )
    session.add(chatter_change); session.commit()
    conclusive_bad = conclusive_synthesis(session, question='Is there a confirmed licence fee increase in Delhi?', state_code='DL', days=365, include_chatter=True)
    # Desired behavior: should NOT be confirmed merely because an unrelated official dry-day item exists.
    semantic_isolation_ok = not (conclusive_bad['answer_status'] == 'CONFIRMED' and conclusive_bad['definitive'] is True)
    add_check('Semantic isolation: unrelated official update must not confirm a different query', semantic_isolation_ok, conclusive_bad, severity='critical_quality_gate')
    if not semantic_isolation_ok:
        results['findings'].append('Critical: conclusive_synthesis can return CONFIRMED for a query when any official-confirmed item exists in the state/date window, even if the official item is unrelated to the user question. Needs relevance threshold/filter before production legal use.')

    # 17. Chatter credibility scoring keeps forwards non-definitive
    chatter_score = score_chatter('Forwarded WhatsApp message: market says licence fee may increase, not verified, expected soon.', title='Trade forward', source_name='WhatsApp', source_url='manual://whatsapp-forward', session=session, state_code='DL')
    add_check('Chatter credibility scoring is non-definitive', chatter_score['definitive'] is False and chatter_score['evidence_tier'] == EvidenceTier.chatter_unverified.value, chatter_score)

    # 18. Readiness via API
    ready = client.get('/api/v6/readiness')
    add_check('v6 readiness endpoint responds', ready.status_code == 200 and ready.json().get('version') == '0.6.0', ready.json() if ready.status_code == 200 else ready.text)

    # 19. Audit log exists for approval
    audit_rows = session.exec(select(AuditLog)).all()
    add_check('Audit log captures review approval', any(a.action == 'review.approve' for a in audit_rows), {'audit_count': len(audit_rows), 'actions': [a.action for a in audit_rows[-5:]]})

    # Counts
    results['metrics']['review_tasks'] = len(session.exec(select(ReviewTask)).all())
    results['metrics']['guidance_records'] = len(session.exec(select(PublishedGuidance)).all())
    results['metrics']['snapshots'] = len(session.exec(select(SourceSnapshot)).all())
    results['metrics']['documents'] = len(session.exec(select(DocumentRecord)).all())
    results['metrics']['ai_module_runs'] = 0
    try:
        from app.models import AIModuleRun
        results['metrics']['ai_module_runs'] = len(session.exec(select(AIModuleRun)).all())
    except Exception:
        pass

# Compute verdict
critical_failures = [c for c in results['checks'] if not c['passed'] and c['severity'] in {'gate', 'critical_quality_gate'}]
prod_gaps = [c for c in results['checks'] if not c['passed'] and c['severity'] == 'production_gap']
passed = sum(1 for c in results['checks'] if c['passed'])
total = len(results['checks'])
results['summary'] = {
    'total_checks': total,
    'passed_checks': passed,
    'failed_checks': total - passed,
    'critical_failures': len(critical_failures),
    'production_gaps': len(prod_gaps),
    'final_verdict': 'PASS_WITH_FIX_REQUIRED' if critical_failures else ('PASS_WITH_PRODUCTION_GAPS' if prod_gaps else 'PASS'),
}

if critical_failures:
    results['recommendations'].append('Fix query relevance in conclusive_synthesis / rag_answer before treating state-level official evidence as a definitive answer for a specific question.')
if prod_gaps:
    results['recommendations'].append('Expand source registry depth: each state/UT should have at least excise department, gazette, CMO/cabinet, corporation/department, and news/legal source where available.')
results['recommendations'].extend([
    'Keep human approval mandatory before guidance publication.',
    'Replace default JWT secret before deployment.',
    'Use PostgreSQL in production and run Alembic migration.',
    'Run a real live-source validation pass after official URLs are verified and outbound network access is enabled.',
])

OUT_JSON.write_text(json.dumps(results, indent=2, default=str), encoding='utf-8')

# Markdown report
lines = []
lines.append('# ExciseWatch v6 — Conclusive Backtest Report')
lines.append('')
lines.append(f"Generated: 2026-06-27")
lines.append('')
lines.append('## Final verdict')
lines.append('')
lines.append(f"**{results['summary']['final_verdict']}**")
lines.append('')
lines.append('| Metric | Result |')
lines.append('|---|---:|')
for k,v in results['summary'].items():
    lines.append(f"| {k.replace('_',' ').title()} | {v} |")
lines.append(f"| Pytest | {'passed' if unit_pass else 'failed'} |")
lines.append(f"| Jurisdictions seeded | {results['metrics'].get('jurisdictions_configured')} / 36 |")
lines.append(f"| Source records | {results['metrics'].get('seeded_sources')} |")
lines.append(f"| Snapshots | {results['metrics'].get('snapshots')} |")
lines.append(f"| Documents | {results['metrics'].get('documents')} |")
lines.append(f"| Review tasks | {results['metrics'].get('review_tasks')} |")
lines.append(f"| Guidance records | {results['metrics'].get('guidance_records')} |")
lines.append(f"| AI module runs | {results['metrics'].get('ai_module_runs')} |")
lines.append('')
lines.append('## Checks')
lines.append('')
lines.append('| # | Check | Verdict | Severity |')
lines.append('|---:|---|---:|---|')
for i,c in enumerate(results['checks'],1):
    lines.append(f"| {i} | {c['name']} | {'PASS' if c['passed'] else 'FAIL'} | {c['severity']} |")
lines.append('')
if results['findings']:
    lines.append('## Critical findings')
    lines.append('')
    for f in results['findings']:
        lines.append(f'- {f}')
    lines.append('')
lines.append('## Recommendations')
lines.append('')
for r in results['recommendations']:
    lines.append(f'- {r}')
lines.append('')
lines.append('## Scope limitation')
lines.append('')
lines.append('This backtest validates the package locally, including a mocked live-fetch code path. It does not prove that every state/UT official URL is correct or reachable in real time from a production network. A separate live URL verification pass is still required before deployment.')
OUT_MD.write_text('\n'.join(lines), encoding='utf-8')
print(json.dumps(results['summary'], indent=2))
print(f'Wrote {OUT_JSON}')
print(f'Wrote {OUT_MD}')
