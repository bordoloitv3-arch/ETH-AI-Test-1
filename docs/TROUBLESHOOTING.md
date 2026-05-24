# Troubleshooting Guide

Common issues and resolutions

Webhook failures
- Symptom: 4xx responses from webhook endpoint.
- Check: `WEBHOOK_SECRET` header correctness and JSON payload validity.
- Fix: Validate TradingView JSON template and timestamp format.

TradingView alert issues
- Symptom: Alerts not arriving.
- Check: Correct webhook URL, header, and that TradingView supports the message size.

Railway deployment failures
- Symptom: Build or container start failure.
- Check: Railway build logs for pip install errors; ensure `requirements.txt` is complete.
- Fix: Rebuild with updated dependencies and confirm `Dockerfile` works locally.

Websocket disconnects
- Symptom: Frequent disconnects, missing market data.
- Check: Network, rate-limits, and Binance API status.
- Fix: Increase reconnect backoff, verify API keys, monitor reconnect metrics.

Replay failures
- Symptom: Replay runs different PnL vs live.
- Check: Ensure replay uses identical slippage/fill models and timestamps.
- Fix: Calibrate replay parameters; run stress tests.

SQLite locking issues
- Symptom: SQLite 'database is locked' exceptions.
- Check: Ensure concurrent access uses `check_same_thread=False` and use short transactions.
- Fix: Move to a managed DB for production or use a connection pool and WAL mode.
