# ExciseWatch Cloud: No-Card Streamlit Deployment

Use this path when Render asks for a card.

Streamlit Community Cloud deploys directly from GitHub and gives a stable URL like:

`https://excisewatch-cloud.streamlit.app`

If that name is taken, choose another app name such as:

`https://excisewatch-india.streamlit.app`

## Deploy Settings

- Repository: `jaiv007x-cell/animated-octo-couscous`
- Branch: `main`
- Main file path: `streamlit_app.py`
- App URL/name: `excisewatch-cloud` if available

## How It Works

The Streamlit app starts the FastAPI backend internally on `127.0.0.1:8000`, so a separate paid web service is not required for a demo/pilot.

## Limits

- This is for demos, pilots, and sales validation.
- Free Streamlit storage is not a production database.
- For paid subscribers, move to PostgreSQL, auth, tenant isolation, backups, and a separate backend worker.

## Secrets

Set secrets in Streamlit Cloud only if needed:

```toml
OPENAI_API_KEY = ""
TELEGRAM_BOT_TOKEN = ""
TELEGRAM_CHAT_ID = ""
JWT_SECRET_KEY = "replace-with-a-long-random-secret"
```

Do not commit real secrets to GitHub.
