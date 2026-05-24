# Railway Deployment Guide

This guide explains how to deploy the ETH Futures webhook + paper trading system to Railway.

1. Connect GitHub repo
   - In Railway, create a new project and connect your GitHub repository.
   - Choose the branch you want to deploy (e.g., `main`).

2. Environment variables (set in Railway project settings)
   - `WEBHOOK_SECRET`: secret token for TradingView webhooks
   - `PAPER_MODE`: `true` (default)
   - `LOG_LEVEL`: `INFO` or `DEBUG`
   - `ENVIRONMENT`: `production`
   - `PROMETHEUS_ENABLED`: `true` or `false`
   - `DATABASE_PATH`: path inside container (e.g., `memory/webhook/webhook.db`)
   - `STATE_DIR`: path for snapshots (e.g., `memory/webhook_state`)

3. Build and start
   - Railway will build using the provided `Dockerfile`.
   - The start command is in `railway.json` / `Procfile`:

```bash
uvicorn webhook.server:app --host 0.0.0.0 --port $PORT
```

4. Webhook URL
   - After deployment, Railway provides a project URL. Use:

```
https://<your-project>.railway.app/webhook
```

5. Monitoring
   - Enable Prometheus scraping if `PROMETHEUS_ENABLED=true`.
   - Use the `/metrics` endpoint to expose metrics.

6. Logs & restarts
   - Use Railway dashboard to view logs and restart the service.
   - For safe restarts, ensure `STATE_DIR` and `DATABASE_PATH` are persistent (Railway volumes).

7. Security
   - Keep `WEBHOOK_SECRET` private and do not commit it to Git.
   - Optionally restrict Traffic via IP allow lists.

8. Notes
   - Use `PAPER_MODE=true` until you are satisfied with forward-testing results.
