# ExciseWatch Cloud: Free Render Deployment

Render gives a fixed free subdomain after the service is created. The URL is not live until this repository is pushed to GitHub and connected to Render.

The target service name in `render.yaml` is `excisewatch-cloud`, so the intended URL is:

`https://excisewatch-cloud.onrender.com`

If that name is already taken, choose another service name such as `excisewatch-india`, and Render will assign:

`https://excisewatch-india.onrender.com`

## What This Deployment Runs

- Public SaaS website: Streamlit on Render's public port.
- Private backend API: FastAPI on `127.0.0.1:8000` inside the same service.
- Optional Telegram poller: disabled by default for SaaS hosting.

## Deploy Steps

1. Push this folder to a private GitHub repository.
2. Open Render and choose **New > Blueprint**.
3. Select the repository.
4. Render will read `render.yaml`.
5. Set secret environment variables:
   - `OPENAI_API_KEY`, if AI calls are needed.
   - `TELEGRAM_BOT_TOKEN`, only if Telegram alerts are needed.
   - `TELEGRAM_CHAT_ID`, only if Telegram alerts are needed.
6. Deploy.

## Important Free-Tier Limits

- Free services may sleep when idle.
- SQLite storage on the free web service is not production-persistent across rebuilds.
- Use this free deployment for demo, sales, and pilot validation.
- For paying customers, move to PostgreSQL and add real authentication, tenant isolation, billing, and backups.

## Telegram Positioning

Telegram should be an alert channel, not the product surface.

Use the website for:

- Company onboarding
- Subscription plans
- Evidence ledger
- Review and approval
- Conclusive AI answers
- Audit and export

Use Telegram for:

- Urgent alerts
- Daily digests
- Field team notifications
- Quick `/feednews` and `/conclusive` checks
