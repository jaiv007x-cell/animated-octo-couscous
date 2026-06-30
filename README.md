# ExciseWatch v6 — Production Compliance Engine

ExciseWatch v6 is the production-hardened version of the All-India Excise AI Suite. It keeps the v5 AI modules and adds the governance layers required before a liquor distributor or alco-bev business can rely on the system for real compliance operations.

## Core principle

**AI can monitor, classify, summarize and recommend. Human approval is required before an item becomes official internal compliance guidance.**

The bot separates:

| Evidence tier | Meaning | Action rule |
|---|---|---|
| `OFFICIAL_CONFIRMED` | Government/gazette/court/regulator source | Create review task; publish only after approval |
| `GOVT_PROBABLE` | Government-adjacent but incomplete | Review required |
| `REPORTED_NOT_CONFIRMED` | News / industry report | Send only as reported intelligence |
| `CHATTER_UNVERIFIED` | WhatsApp / Telegram / market gossip | Never publish as legal guidance |
| `INSUFFICIENT_EVIDENCE` | Weak or unclear | Review required |

## What v6 adds over v5

| Production layer | New capability |
|---|---|
| Live source validation | Checks configured source URLs, creates snapshots, hashes page content, archives source text |
| Auth + RBAC | Admin/user login, local HMAC token, API keys, roles and permissions |
| Database hardening | PostgreSQL-ready schema, Alembic migration skeleton, document/source/audit tables |
| Scheduler jobs | Run source validation, watcher, review generation and Telegram digest jobs |
| Human-review workflow | Review queue, approve/reject/escalate/supersede actions |
| Publication control | Approved guidance records and Telegram-safe publication |
| Audit log | Tracks sensitive actions and approvals |
| Readiness endpoint | `/api/v6/readiness` shows production layer status |

## Install locally

```bash
cd excisewatch_bot_v6_production
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Open API docs:

```text
http://127.0.0.1:8000/docs
```

Run dashboard:

```bash
streamlit run streamlit_app.py
```

## Run with PostgreSQL using Docker

```bash
docker compose up --build
```

API:

```text
http://localhost:8000/docs
```

Dashboard:

```text
http://localhost:8501
```

## Optional Alembic migration

```bash
alembic upgrade head
```

The app also still calls `SQLModel.metadata.create_all()` on startup for local/MVP convenience.

## First setup

Seed all Indian states/UT source registry:

```bash
curl -X POST "http://127.0.0.1:8000/api/admin/seed-sources"
```

Bootstrap first admin:

```bash
curl -X POST "http://127.0.0.1:8000/api/auth/bootstrap-admin" \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"StrongPass123","email":"admin@example.com"}'
```

Login:

```bash
curl -X POST "http://127.0.0.1:8000/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"StrongPass123"}'
```

## Live source validation

Dry run:

```bash
curl -X POST "http://127.0.0.1:8000/api/sources/validate-live" \
  -H "Content-Type: application/json" \
  -d '{"state_code":"DL","live_fetch":false}'
```

Actual live fetch:

```bash
curl -X POST "http://127.0.0.1:8000/api/sources/validate-live" \
  -H "Content-Type: application/json" \
  -d '{"state_code":"DL","live_fetch":true,"archive_documents":true}'
```

View snapshots and archived documents:

```bash
curl "http://127.0.0.1:8000/api/sources/snapshots?state_code=DL"
curl "http://127.0.0.1:8000/api/documents?state_code=DL"
```

## Review workflow

Generate review tasks:

```bash
curl -X POST "http://127.0.0.1:8000/api/review/generate" \
  -H "Content-Type: application/json" \
  -d '{"state_code":"DL"}'
```

List tasks:

```bash
curl "http://127.0.0.1:8000/api/review/tasks?state_code=DL"
```

Approve a task:

```bash
curl -X POST "http://127.0.0.1:8000/api/review/tasks/1/approve" \
  -H "Content-Type: application/json" \
  -d '{"note":"Approved after verifying official source PDF."}'
```

Reject / escalate / supersede:

```bash
curl -X POST "http://127.0.0.1:8000/api/review/tasks/1/reject" -H "Content-Type: application/json" -d '{"note":"Not official."}'
curl -X POST "http://127.0.0.1:8000/api/review/tasks/1/escalate" -H "Content-Type: application/json" -d '{"note":"Needs legal head."}'
curl -X POST "http://127.0.0.1:8000/api/review/tasks/1/mark-superseded" -H "Content-Type: application/json" -d '{"note":"Superseded by later circular."}'
```

## Publish approved guidance to Telegram

Dry run:

```bash
curl -X POST "http://127.0.0.1:8000/api/publish/guidance/1/telegram" \
  -H "Content-Type: application/json" \
  -d '{"dry_run":true}'
```

Actual send after setting `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`:

```bash
curl -X POST "http://127.0.0.1:8000/api/publish/guidance/1/telegram" \
  -H "Content-Type: application/json" \
  -d '{"dry_run":false}'
```

## Scheduled jobs / run-now jobs

```bash
curl -X POST "http://127.0.0.1:8000/api/jobs/run-now" \
  -H "Content-Type: application/json" \
  -d '{"job_name":"validate_sources","state_code":"DL","dry_run":true}'

curl -X POST "http://127.0.0.1:8000/api/jobs/run-now" \
  -H "Content-Type: application/json" \
  -d '{"job_name":"generate_review_tasks","state_code":"DL","dry_run":true}'

curl -X POST "http://127.0.0.1:8000/api/jobs/run-now" \
  -H "Content-Type: application/json" \
  -d '{"job_name":"telegram_digest","state_code":"DL","dry_run":true}'
```

View job runs:

```bash
curl "http://127.0.0.1:8000/api/jobs/status"
```

## v5 AI suite still included

All earlier endpoints still exist:

- `/api/ai/modules`
- `/api/ai/suite`
- `/api/ai/conclusive`
- `/api/ai/rag/ask`
- `/api/ai/chatter-score`
- `/api/ai/impact`
- `/api/ai/checklist`
- `/api/ai/dispatch-risk`
- `/api/ai/fraud-anomaly`
- `/api/telegram/digest`
- `/api/conclusive/ask`
- `/api/officials/*`

## Production deployment checklist

Before using it for actual compliance decisions:

1. Replace starter source URLs with verified official sources for every state/UT.
2. Set `DATABASE_URL` to PostgreSQL.
3. Set a strong `JWT_SECRET_KEY`.
4. Create admin and reviewer accounts.
5. Configure Telegram channel and keep chatter in a private group only.
6. Use `live_fetch=true` only after source registry is validated.
7. Require human approval for all official compliance guidance.
8. Keep document snapshots and hashes backed up.
9. Run daily source validation and review-task generation.
10. Treat every output as internal compliance intelligence until reviewed by legal/compliance.

## Test result

The v6 package includes v5 tests plus v6 production-layer tests.

```text
22 tests passed
```

---

# v6.1 Relevance-Fixed Patch

This patch fixes the critical v6 backtest failure where an unrelated official update could make a specific question look `CONFIRMED`.

## What changed

- Added `app/relevance.py` with a semantic relevance gate.
- Updated `app/ai_modules.py` so RAG and conclusive synthesis only count official evidence after it matches the user question.
- Updated `app/officials.py` so CM/minister/officer conclusive questions also respect relevance/category/intent matching.
- Added regression tests proving that an official dry-day order cannot confirm an unrelated licence-fee increase query.

## New safety rule

Official evidence is conclusive only when it is:

1. Official-confirmed,
2. Relevant to the question,
3. Category-matched,
4. Directionally matched for terms like increase/decrease/suspension/renewal,
5. Not contradicted by stronger or same-tier evidence.

## Test result

```text
26 tests passed
```


## v6.2 verified-source patch

This package includes a fully replaced `data/sources.yaml` registry with only official/government/gazette/regulator URLs. The previous starter/unverified entries were removed. See:

- `data/sources.yaml`
- `data/source_verification_manifest.csv`
- `data/source_verification_summary.json`
- `SOURCE_VERIFICATION_REPORT.md`

Operational rule: a source URL being verified means the URL is an official/government/gazette/regulator source. It does **not** mean every future item found on that source is automatically conclusive. Every downloaded document still goes through snapshot hashing, evidence ranking, relevance gating, conflict detection and human review before becoming approved compliance guidance.
