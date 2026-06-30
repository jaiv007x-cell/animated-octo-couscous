# ExciseWatch Cloud

ExciseWatch Cloud is a regulatory intelligence SaaS and Telegram alert bot for Indian excise, liquor, public-office, and compliance monitoring.

It monitors official government sources, gazettes, regulator/court sources, news, and manually ingested chatter. It classifies evidence, separates confirmed law from reported news and unverified market talk, generates conclusive AI answers, and routes important items through human review before they become operational guidance.

Current GitHub repo:

```text
https://github.com/jaiv007x-cell/animated-octo-couscous
```

Current local app:

```text
SaaS website: http://127.0.0.1:8501
API docs:     http://127.0.0.1:8000/docs
API health:   http://127.0.0.1:8000/health
```

Current temporary public links, while this machine stays running:

```text
Cloudflare quick tunnel:
https://meals-mitsubishi-firmware-indexes.trycloudflare.com

Fixed LocalTunnel name:
https://excisewatch-cloud.loca.lt
```

If LocalTunnel asks for an IP, enter the IP shown on the tunnel page. The previously shown host IP was:

```text
95.173.220.240
```

Do not treat temporary tunnel links as production hosting. They are demos only.

## Product Strategy

For a subscription business, the website is the product. Telegram is an alert channel.

Use the SaaS website for:

- Customer onboarding
- Subscription packaging
- Source registry
- Intelligence feed
- Evidence ledger
- Conclusive AI answers
- Review and approval workflow
- Publication controls
- Admin operations
- Audit trail

Use Telegram for:

- Urgent alerts
- Daily digests
- Field-team updates
- Quick status checks
- Fast `/feednews`, `/news`, `/conclusive`, and `/hunt` commands

## Evidence Model

ExciseWatch never treats all information equally.

| Evidence tier | Meaning | Action rule |
|---|---|---|
| `OFFICIAL_CONFIRMED` | Government, gazette, court, or regulator source | Strongest tier, but still review before publishing guidance |
| `GOVT_PROBABLE` | Government-adjacent or official-looking but incomplete | Treat as strong signal, verify original order |
| `REPORTED_NOT_CONFIRMED` | News or industry report | Share only as reported intelligence |
| `CHATTER_UNVERIFIED` | WhatsApp, Telegram, forward, market talk | Never act as law |
| `INSUFFICIENT_EVIDENCE` | Weak or unclear evidence | Manual triage |

Important rule:

Official evidence is conclusive only when it is relevant to the question. An official dry-day order must not confirm an unrelated licence-fee increase question.

## What The System Does

Core workflows:

- Seed all-India source registry.
- Fetch official and news sources.
- Ingest latest news from Google News RSS.
- Ingest manual chatter or forwarded officer/ministry information.
- Classify legal changes.
- Extract public-office movements, portfolio changes, officer transfers, and workstream signals.
- Rank evidence.
- Generate conclusive answers.
- Detect conflicts.
- Create review tasks.
- Publish approved guidance to Telegram.
- Show a SaaS console for customers and internal operators.

## Repository Layout

```text
app/
  main.py                         FastAPI application and API routes
  telegram_bot.py                 Interactive Telegram polling bot
  telegram_updates.py             Telegram digest formatting and sending
  watch.py                        Official/news watch runner
  processor.py                    Raw item to legal-change processing
  officials.py                    Ministry, portfolio, officer, and workstream intelligence
  ai_modules.py                   AI/RAG/conclusive/checklist modules
  evidence.py                     Evidence-tier rules
  relevance.py                    Relevance gate for conclusive answers
  source_registry.py              Source seeding and validation
  collectors/
    news.py                       Google News RSS collector
    chatter.py                    Manual chatter ingest
    official.py                   Official source collection helpers
  services/
    news_feed_service.py          Latest news feed job and digest
    review_service.py             Review-task generation and approvals
    live_source_validator.py      Source health/snapshot validator
    publication_service.py        Publish approved guidance
    decision_engine.py            Action gating by evidence tier
    audit.py                      Audit log helpers

scripts/
  run_telegram_bot.py             Starts the Telegram poller
  start_render.py                 Render single-service runner
  send_telegram_digest.py         CLI digest sender
  run_once.py                     One-shot local watcher
  run_all_india_and_alert.py      All-India run helper
  backtest_v5.py                  Backtest suite
  backtest_v6_conclusive.py       Conclusive/evidence backtest

data/
  sources.yaml                    Verified official source registry
  source_verification_manifest.csv
  source_verification_summary.json

streamlit_app.py                  SaaS website
render.yaml                       Render deployment blueprint
DEPLOY_STREAMLIT_CLOUD.md         No-card Streamlit deployment notes
DEPLOY_RENDER.md                  Render deployment notes
SAAS_COMMERCIAL_READINESS.md      Commercial packaging checklist
```

## Security Rules

Never commit real secrets.

Secrets belong in `.env`, Streamlit Cloud secrets, Render environment variables, or another managed secret store.

Do not commit:

- Telegram bot token
- Telegram chat ID if private
- OpenAI API key
- SMTP password
- JWT secret
- Customer data
- SQLite production database
- `storage/` contents

The repo already ignores `.env`, `.venv`, cache files, and `storage/`.

If a Telegram token was ever pasted into chat or logs, rotate it in BotFather before real production use.

## Local Setup On Windows

Run these commands in PowerShell from the project root:

```powershell
cd C:\Users\HP\Desktop\excisewatch_bot_v6_2_verified_sources
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` and set only the secrets you need:

```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
OPENAI_API_KEY=
JWT_SECRET_KEY=replace-with-long-random-secret
```

The app works without OpenAI for many extractive/classification flows, but AI features are better with `OPENAI_API_KEY`.

## Start The API

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000/docs
```

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Readiness:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v6/readiness | ConvertTo-Json -Depth 5
```

## Start The SaaS Website

In another PowerShell:

```powershell
cd C:\Users\HP\Desktop\excisewatch_bot_v6_2_verified_sources
.\.venv\Scripts\python.exe -m streamlit run streamlit_app.py --server.address 127.0.0.1 --server.port 8501
```

Open:

```text
http://127.0.0.1:8501
```

The SaaS console includes:

- Command Center
- Intelligence Feed
- Conclusive AI
- Review & Publish
- Plans
- Onboarding
- Admin

## Start The Telegram Bot

Make sure `.env` contains:

```env
TELEGRAM_BOT_TOKEN=your-token
TELEGRAM_CHAT_ID=your-chat-id
```

Then run:

```powershell
.\.venv\Scripts\python.exe scripts\run_telegram_bot.py
```

Telegram commands:

| Command | Purpose |
|---|---|
| `/help` | Show bot commands |
| `/id` | Show current chat ID |
| `/health` | Initialize/check database and source seed |
| `/status` | Show database counts |
| `/latest [STATE]` | Latest fetched/processed items |
| `/news [STATE] [DAYS]` | Latest reported news intelligence |
| `/feednews [STATE\|ALL] [MAX] [DAYS]` | Ingest latest news and send digest |
| `/digest [STATE] [DAYS]` | Build digest from local database |
| `/ask [STATE] question` | Ask local compliance database |
| `/conclusive STATE question` | Evidence-ranked final answer |
| `/hunt STATE question` | Fetch/process one state, then answer |
| `/process` | Classify raw items into legal changes |
| `/watch STATE` | Fetch one state |

Examples:

```text
/status
/feednews ALL 8 30
/news TN 30
/watch KA
/conclusive TN has privilege fee for bars increased?
/hunt KA licence fee increase
```

Notes:

- `/watch ALL` is intentionally disabled inside Telegram because it can block replies.
- Use `/feednews ALL 8 30` for broad current news ingestion.
- Chatter is not treated as law. It is only an early-warning signal.

## Start Everything Locally

If services are already running and you want a clean local restart:

```powershell
$workspace = "C:\Users\HP\Desktop\excisewatch_bot_v6_2_verified_sources"
cd $workspace

Get-CimInstance Win32_Process | Where-Object {
    $_.Name -like 'python*' -and $_.CommandLine -like "*$workspace*" -and (
        $_.CommandLine -like '*run_telegram_bot.py*' -or
        $_.CommandLine -like '*uvicorn app.main:app*' -or
        $_.CommandLine -like '*streamlit_app.py*'
    )
} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

$py = Join-Path $workspace ".venv\Scripts\python.exe"
Start-Process -FilePath $py -ArgumentList @("-m","uvicorn","app.main:app","--host","127.0.0.1","--port","8000") -WorkingDirectory $workspace -WindowStyle Hidden -RedirectStandardOutput "storage\api.out.log" -RedirectStandardError "storage\api.err.log"
Start-Process -FilePath $py -ArgumentList @("scripts\run_telegram_bot.py") -WorkingDirectory $workspace -WindowStyle Hidden -RedirectStandardOutput "storage\telegram_bot.out.log" -RedirectStandardError "storage\telegram_bot.err.log"
Start-Process -FilePath $py -ArgumentList @("-m","streamlit","run","streamlit_app.py","--server.address","127.0.0.1","--server.port","8501") -WorkingDirectory $workspace -WindowStyle Hidden -RedirectStandardOutput "storage\streamlit.out.log" -RedirectStandardError "storage\streamlit.err.log"
```

Check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
(Invoke-WebRequest http://127.0.0.1:8501 -UseBasicParsing).StatusCode
```

## Public Demo Tunnels

### Cloudflare Quick Tunnel

Cloudflare quick tunnels do not require a card or account, but the URL is random.

```powershell
cloudflared tunnel --url http://127.0.0.1:8501
```

Copy the generated `trycloudflare.com` URL.

### LocalTunnel Fixed Name

LocalTunnel can request a fixed name, but it may show a safety gate.

```powershell
npx --yes localtunnel --port 8501 --subdomain excisewatch-cloud
```

Expected URL:

```text
https://excisewatch-cloud.loca.lt
```

### Important Tunnel Limits

Temporary tunnels are fine for demos, but not for production:

- They depend on your laptop staying awake.
- URLs can change or become unavailable.
- LocalTunnel may show a warning/interstitial page.
- They do not replace proper SaaS hosting.

## No-Card Hosted Deployment

Render asked for a card, so the current no-card path is Streamlit Community Cloud.

See:

```text
DEPLOY_STREAMLIT_CLOUD.md
```

Settings:

```text
Repository: jaiv007x-cell/animated-octo-couscous
Branch: main
Main file path: streamlit_app.py
App URL/name: excisewatch-cloud, if available
```

The Streamlit app can start its own internal FastAPI backend on `127.0.0.1:8000`, so the demo can run as one Streamlit app.

Streamlit GitHub OAuth may require your GitHub account to authorize Streamlit. If GitHub disables the authorize button, enable/finish GitHub 2FA or use another deployment provider.

## Render Deployment

Render is prepared but may require a card depending on account state.

Files:

```text
render.yaml
scripts/start_render.py
DEPLOY_RENDER.md
```

Render service behavior:

- Public port: Streamlit SaaS website
- Internal backend: FastAPI on `127.0.0.1:8000`
- Telegram polling: disabled by default unless `TELEGRAM_ENABLE_POLLING=true`

## API Quick Commands

Seed sources:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/admin/seed-sources
```

Run one-state watch:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/watch/run `
  -ContentType "application/json" `
  -Body '{"state_code":"DL","include_news":true,"include_alerts":false}'
```

Run latest news feed job:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/jobs/run-now `
  -ContentType "application/json" `
  -Body '{"job_name":"latest_news_feed","state_code":null,"dry_run":false}'
```

Preview Telegram digest:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/telegram/digest `
  -ContentType "application/json" `
  -Body '{"state_code":"DL","days":7,"limit":10,"dry_run":true,"include_chatter":false}'
```

Send Telegram test:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/telegram/test `
  -ContentType "application/json" `
  -Body '{"message":"ExciseWatch test","dry_run":false}'
```

Ask conclusive AI:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/ai/conclusive `
  -ContentType "application/json" `
  -Body '{"question":"Has Tamil Nadu increased privilege fee for bars?","state_code":"TN","days":30,"include_chatter":false}'
```

Ingest manual chatter:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/chatter/ingest `
  -ContentType "application/json" `
  -Body '{"state_code":"KA","state_name":"Karnataka","title":"Forward: possible excise portfolio change","text":"Market chatter says excise portfolio may change. Not verified.","source_url":"manual://forward"}'
```

Process raw items:

```powershell
Invoke-RestMethod -Method Post "http://127.0.0.1:8000/api/process/raw?include_officials=true"
```

## Chatter And Ministry Portfolio Changes

The bot can handle chatter, but by design it does not treat chatter as conclusive.

Portfolio/ministry signals can enter through:

- Manual chatter ingest: `/api/chatter/ingest`
- Official forward ingest: `/api/officials/forward-ingest`
- News ingestion when reported publicly
- Official source watch when a government order/cabinet page publishes it

Relevant models:

- `OfficialMovement`
- `OfficialProfile`
- `WorkSignal`
- `IntelligenceBrief`

Relevant evidence behavior:

- Social/manual forward data becomes `CHATTER_UNVERIFIED`.
- News reports become `REPORTED_NOT_CONFIRMED`.
- Government orders/gazettes become `OFFICIAL_CONFIRMED`.
- Conclusive answer can mention chatter only when `include_chatter=true`.
- Telegram digest excludes chatter by default.

API example for a ministry/portfolio forward:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/officials/forward-ingest `
  -ContentType "application/json" `
  -Body '{
    "state_code":"KA",
    "state_name":"Karnataka",
    "title":"Forward: possible excise portfolio change",
    "text":"Forward says the Excise Minister portfolio may be reassigned in a cabinet reshuffle. Not verified.",
    "source_reference":"manual://portfolio-chatter",
    "source_name":"Manual forward data",
    "source_type":"social",
    "process_now":true
  }'
```

Ask with chatter included:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/conclusive/ask `
  -ContentType "application/json" `
  -Body '{"question":"Is there chatter about change in excise ministry portfolio?","state_code":"KA","days":30}'
```

## Jobs

Supported scheduler job names:

```text
validate_sources
watch_sources
latest_news_feed
generate_review_tasks
telegram_digest
```

Run a job:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/jobs/run-now `
  -ContentType "application/json" `
  -Body '{"job_name":"validate_sources","state_code":"DL","dry_run":true}'
```

View recent jobs:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/jobs/status
```

## Review Workflow

Generate review tasks:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/review/generate `
  -ContentType "application/json" `
  -Body '{"state_code":"DL","limit":250}'
```

List tasks:

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/api/review/tasks?state_code=DL&limit=100"
```

Approve:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/review/tasks/1/approve `
  -ContentType "application/json" `
  -Body '{"note":"Approved after checking official source."}'
```

Publish approved guidance:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/publish/guidance/1/telegram `
  -ContentType "application/json" `
  -Body '{"dry_run":false}'
```

## Tests And Backtests

Run all tests:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Run focused Telegram tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_telegram_bot.py -q
```

Run v5 backtest:

```powershell
.\.venv\Scripts\python.exe scripts\backtest_v5.py
```

Run v6 conclusive backtest:

```powershell
.\.venv\Scripts\python.exe scripts\backtest_v6_conclusive.py
```

Recent status:

```text
33 tests passed
```

## Cursor Setup

Open the folder in Cursor:

```text
C:\Users\HP\Desktop\excisewatch_bot_v6_2_verified_sources
```

Recommended Cursor context files:

- `README.md`
- `app/main.py`
- `app/telegram_bot.py`
- `app/services/news_feed_service.py`
- `app/officials.py`
- `streamlit_app.py`
- `data/sources.yaml`
- `tests/test_telegram_bot.py`
- `tests/test_relevance_gate.py`

Suggested Cursor prompt:

```text
You are working on ExciseWatch Cloud. Read README.md first. Preserve the evidence-tier model: official evidence is conclusive only when relevant, news is reported-only, chatter is never law. Use existing patterns in app/main.py, app/telegram_bot.py, app/officials.py, and streamlit_app.py. Run pytest before finalizing changes.
```

Cursor run commands:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
.\.venv\Scripts\python.exe -m streamlit run streamlit_app.py --server.address 127.0.0.1 --server.port 8501
.\.venv\Scripts\python.exe scripts\run_telegram_bot.py
```

## Codex Setup

Codex should treat this as a shared local workspace.

Rules for Codex:

- Read the codebase before changing behavior.
- Do not reveal or commit `.env`.
- Prefer existing patterns over new abstractions.
- Use `rg` for search.
- Use `apply_patch` for manual edits.
- Run tests after code changes.
- Do not revert user changes.
- Keep Telegram token and chat ID out of final answers.

Suggested Codex prompt:

```text
Work in C:\Users\HP\Desktop\excisewatch_bot_v6_2_verified_sources. Read README.md and inspect the relevant files before editing. Keep evidence gating strict. Implement the requested change, run focused tests, then run pytest -q if practical. Do not expose secrets.
```

Useful Codex commands:

```powershell
rg -n "feednews|chatter|portfolio|conclusive" app tests streamlit_app.py
.\.venv\Scripts\python.exe -m pytest tests\test_telegram_bot.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

## VS Code Setup

Open folder:

```powershell
code C:\Users\HP\Desktop\excisewatch_bot_v6_2_verified_sources
```

Select interpreter:

```text
.\.venv\Scripts\python.exe
```

Recommended extensions:

- Python
- Pylance
- YAML
- GitHub Pull Requests
- Docker, optional

Suggested `.vscode/launch.json` if you want debugger configs:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "API: FastAPI",
      "type": "python",
      "request": "launch",
      "module": "uvicorn",
      "args": ["app.main:app", "--host", "127.0.0.1", "--port", "8000", "--reload"],
      "jinja": true
    },
    {
      "name": "Telegram Bot",
      "type": "python",
      "request": "launch",
      "program": "${workspaceFolder}/scripts/run_telegram_bot.py"
    },
    {
      "name": "Streamlit SaaS",
      "type": "python",
      "request": "launch",
      "module": "streamlit",
      "args": ["run", "streamlit_app.py", "--server.address", "127.0.0.1", "--server.port", "8501"]
    }
  ]
}
```

## Commercial Readiness

Current app is good for:

- Demo
- Pilot
- Internal prototype
- Sales validation
- Customer discovery

Before paid production:

1. Rotate all secrets.
2. Use PostgreSQL instead of SQLite.
3. Add tenant isolation.
4. Add production auth and RBAC enforcement in the SaaS UI.
5. Add billing/subscriptions.
6. Add background workers and scheduled jobs.
7. Add persistent document storage.
8. Add uptime monitoring.
9. Add legal disclaimers and customer terms.
10. Run a security review.

Suggested packaging:

| Plan | Buyer | Scope |
|---|---|---|
| Pilot | Single-state compliance team | 1 state, alerts, conclusive answer desk |
| Professional | Multi-state distributor | Up to 8 states, review queue, exports |
| Enterprise | National alco-bev company | All India, SLA, SSO, private deployment |
| Government | Department/corporation | On-prem/sovereign cloud, audit logs |

## Troubleshooting

### API says method not allowed

You probably opened a `POST` endpoint in the browser. Use Swagger docs or PowerShell:

```text
http://127.0.0.1:8000/docs
```

### Bot sends no data

Check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v6/readiness
```

Then run:

```text
/feednews ALL 8 30
/status
/news 30
```

### Latest news looks old

The news collector filters by `published_at` where available. Google News RSS can sometimes return older or cross-state articles. The service now applies:

- `when:7d` style query terms
- explicit publication-date filtering
- excise/liquor title keyword filtering
- title dedupe in digest

### Government source times out

Some state government websites are slow or unavailable. This is normal. The bot records fetch warnings and continues. Use news feed and retry official source watch later.

### Telegram is slow during watch

Use state-specific `/watch KA`, not all-India watch from Telegram. Use API jobs or SaaS controls for larger sweeps.

### Streamlit Cloud login blocks

If GitHub OAuth authorize is disabled, enable GitHub 2FA or use a tunnel/demo host. Streamlit deployment requires GitHub authorization.

### Render asks for card

Use Streamlit Community Cloud or tunnels for no-card demos. Render files are still included for accounts where free web services are available.

## Git Workflow

Check status:

```powershell
git status --short
```

Commit:

```powershell
git add .
git commit -m "Describe change"
git push
```

Current branch:

```text
main
```

Remote:

```text
origin https://github.com/jaiv007x-cell/animated-octo-couscous.git
```

## Operational Philosophy

ExciseWatch is not a random chatbot. It is an evidence-governed compliance intelligence system.

The right operating pattern is:

1. Ingest broadly.
2. Classify conservatively.
3. Label evidence visibly.
4. Answer conclusively only when official and relevant.
5. Treat news as intelligence.
6. Treat chatter as early warning.
7. Require human approval for guidance.
8. Keep an audit trail.

