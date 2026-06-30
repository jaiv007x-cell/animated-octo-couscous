# ExciseWatch Cloud SaaS Readiness

ExciseWatch Cloud packages the Telegram intelligence bot and compliance API as a subscription product for liquor distributors, alco-bev companies, legal/advisory teams, state corporations, and government departments.

## Product Positioning

ExciseWatch is not a generic chatbot. It is a regulatory intelligence and evidence-governance platform for excise compliance.

Core promise:

- Monitor official excise, gazette, court, regulator and news sources.
- Separate official-confirmed evidence from reported news and unverified chatter.
- Produce conclusive answers only when the source evidence is relevant and official.
- Require human approval before guidance is published to operational teams.
- Send Telegram digests and alerts with evidence labels.

## Subscription Packaging

| Plan | Buyer | Suggested Packaging |
|---|---|---|
| Pilot | Single-state compliance team | 1 state/UT, Telegram alerts, conclusive answer desk |
| Professional | Multi-state distributor | Up to 8 states, review queue, evidence exports |
| Enterprise | National alco-bev company | All-India coverage, RBAC, private deployment, SLA |
| Government | Excise department / corporation | On-prem or sovereign cloud, audit logs, official publication workflows |

## Production Requirements Before Selling

1. Rotate all Telegram/API secrets and move them to a managed secret store.
2. Replace SQLite with PostgreSQL and run Alembic migrations.
3. Enforce tenant isolation across users, sources, documents, review tasks and guidance.
4. Add billing integration for subscriptions and invoices.
5. Add SSO/SAML/OIDC for enterprise and government accounts.
6. Complete official source verification for each subscribed jurisdiction.
7. Add uptime monitoring, job queues and retry policies for slow government sites.
8. Publish legal disclaimers: AI intelligence is not legal advice until reviewed.
9. Add exportable audit reports for approvals and Telegram publications.
10. Run security review before handling customer data.

## Current Local SaaS Console

Run:

```powershell
.\.venv\Scripts\python.exe -m streamlit run streamlit_app.py --server.address 127.0.0.1 --server.port 8501
```

Open:

```text
http://127.0.0.1:8501
```

The console includes:

- Command Center
- Intelligence Feed
- Conclusive AI
- Review & Publish
- Subscription Plans
- Enterprise Onboarding
- Admin / Source Registry

