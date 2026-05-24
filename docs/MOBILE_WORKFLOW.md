# Mobile Workflow (Android + TradingView)

1. Configure TradingView Alert
   - Open the TradingView chart on your Android phone.
   - Create an alert and choose "Webhook URL".
   - Paste your Railway webhook URL: `https://<project>.railway.app/webhook`
   - Use a JSON payload as in `docs/TRADINGVIEW_ALERTS.md`.
   - Add `x-webhook-token` header with your `WEBHOOK_SECRET` value.

2. Monitor the System
   - Use Railway dashboard to view deployment status and logs.
   - Open the Streamlit dashboard (if deployed) to view alerts, executions, latency.
   - Use the `/metrics` endpoint for Prometheus scraping.

3. Restarting Deployments
   - From Railway dashboard click "Restart".
   - For graceful restarts, ensure snapshots are stored in `STATE_DIR`.

4. Viewing Logs
   - Use Railway's Logs panel to view stdout/stderr and structured logs.
   - For local debugging, tail `logs/webhook/webhook.log`.

5. Monitoring Paper Trades
   - Use Streamlit dashboard to inspect open positions and PnL.
   - Check `reports/webhook` for JSON/CSV reports and execution history.

6. Checking Latency & Drift
   - `/metrics` exposes `webhook_processing_seconds` and other metrics.
   - Use Prometheus/Grafana to alert on p95 latency, drift scores, reconnects.
