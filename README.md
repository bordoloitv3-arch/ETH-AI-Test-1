# ETH Futures AI — Optimizer & Live Testing Framework

A modular framework for optimizing and forward-testing ETH perpetual futures strategies. Designed for research, paper trading, and production-ready webhook-based forward testing with Railway deployment support.

**Key features**
- Backtester with fees, slippage, position sizing, and drawdown analysis
- Multiple optimization engines: Optuna, genetic, and RL scaffolds
- Pine Script parsing for parameter extraction and automated strategy generation
- SQLite-backed memory store with snapshotting for recoverable runs
- FastAPI webhook server for TradingView alerts, deduplication and replay
- Streamlit dashboard for monitoring and replay visualization

## Repository layout

Top-level folders you'll use most:

- `backtester/` — Backtesting engine and utilities
- `optimizer/` — Optimization engines and workflow orchestration
- `webhook/`, `webhook_server/` — FastAPI webhook server + local helpers
- `memory/` — SQLite memory backends and state stores
- `reports/` — Generated reports and examples
- `examples/` — Example scripts and data loaders
- `tests/` — Pytest test suite

## Quick start (development)

1. Create a Python virtual environment and activate it:

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
```

2. Install dependencies:

```bash
python -m pip install -r requirements.txt
```

3. Run tests:

```bash

py -3.14 -m pytest -q
```

4. Run an example optimization:

```bash
python examples/run_eth_optimization.py
```

## GitHub & deployment preparation (beginner-friendly)

**New to Git? Start here!**

### Quick links:
1. **Workflow overview:** [WORKFLOW_OVERVIEW.md](WORKFLOW_OVERVIEW.md) — see the complete journey from GitHub to mobile trading
2. **Quick commands:** [QUICK_REFERENCE.md](QUICK_REFERENCE.md) — keep open while uploading
3. **Full step-by-step:** [docs/GITHUB_UPLOAD_INTERACTIVE.md](docs/GITHUB_UPLOAD_INTERACTIVE.md) — detailed walkthrough with troubleshooting
4. **After GitHub:** [docs/RAILWAY_AND_TRADINGVIEW_NEXT_STEPS.md](docs/RAILWAY_AND_TRADINGVIEW_NEXT_STEPS.md) — Railway & TradingView setup

### Quick start:

Run this in PowerShell from the project folder:

```powershell
powershell -ExecutionPolicy Bypass -File .\init_repo.ps1
```

Then follow `QUICK_REFERENCE.md` for the next steps (GitHub repo creation, `git push`, verification).

### What these guides cover:
- Installing Git on Windows (5 min)
- Running the initialization script with explanations for every prompt
- Creating a GitHub repository correctly
- Pushing your code safely (`git push -u origin main`)
- Verifying the upload in GitHub browser
- Railway deployment (15 min)
- TradingView webhook integration (10–15 min)
- Forward testing on Android with paper trading
- Troubleshooting common errors

**Also see:** 
- [docs/GIT_GUIDE.md](docs/GIT_GUIDE.md) — Git commands reference
- [docs/PRE_PUSH_CHECKLIST.md](docs/PRE_PUSH_CHECKLIST.md) — pre-push verification

## TradingView webhook forward testing

This project includes a FastAPI webhook server that accepts TradingView alert POSTs at `/webhook`. Features:

- Optional token authentication (`WEBHOOK_SECRET`)
- Deduplication via canonical payload hashing
- Persistence to SQLite and optional JSON/CSV snapshots
- Replay mode and accelerated stress testing runner

To run the webhook server locally:

```bash
uvicorn webhook.server:app --reload --port 8000
```

Set `WEBHOOK_SECRET` in your environment or in a `.env` (do NOT commit `.env`).

## Paper trading & live mode

- `live/paper_engine.py` provides a paper trading engine that consumes normalized signals and simulates fills.
- Use `PAPER_MODE=true` to avoid real execution and to validate logic before any live deployment.

## Dashboard

There is a lightweight Streamlit dashboard in `webhook_server/dashboard_streamlit.py` for replay visualizations and monitoring.

Run:

```bash
streamlit run webhook_server/dashboard_streamlit.py
```

## Railway deployment notes

- `Dockerfile`, `railway.json`, and `Procfile` are included for containerized deployments.
- Recommended start command (Railway `start`):

```bash
uvicorn webhook.server:app --host 0.0.0.0 --port $PORT
```

- Configure Railway environment variables (see `.env.example`) and mount persistent storage for `DATABASE_PATH` and `STATE_DIR`.

## Testing

- Unit tests are in `tests/` and run with `pytest`.
- Integration tests for webhook and replay are provided — run `py -3.14 -m pytest tests/test_webhook.py -q` for webhook-specific tests.

## Security and secrets

- Never commit `.env` or credentials. Add keys to Railway secrets when deploying.
- The repository `.gitignore` includes common secret and runtime files.

## Contributing & workflows

- Follow branch naming: `feature/<short-desc>`, `fix/<short-desc>`, `hotfix/<short-desc>`, `chore/<short-desc>`
- Use descriptive commit messages: `type(scope): short description` (e.g. `fix(engine): handle numpy datetime64`) — see `docs/GIT_GUIDE.md`.

## Resources

- **First time with Git?** Start here: [QUICK_REFERENCE.md](QUICK_REFERENCE.md) — keep open while uploading.
- **Full GitHub walkthrough:** [docs/GITHUB_UPLOAD_INTERACTIVE.md](docs/GITHUB_UPLOAD_INTERACTIVE.md) — beginner-friendly step-by-step.
- **After GitHub upload:** [docs/RAILWAY_AND_TRADINGVIEW_NEXT_STEPS.md](docs/RAILWAY_AND_TRADINGVIEW_NEXT_STEPS.md) — Railway & TradingView setup (20–30 min).
- **Verify upload worked:** Run `.\verify_github_upload.ps1` after pushing to GitHub.
- Railway deployment: `docs/RAILWAY_DEPLOY.md`
- Git workflow: `docs/GIT_GUIDE.md`
- Pre-push safety: `docs/PRE_PUSH_CHECKLIST.md`

---
**For beginners:** See [QUICK_REFERENCE.md](QUICK_REFERENCE.md) and [docs/GITHUB_UPLOAD_INTERACTIVE.md](docs/GITHUB_UPLOAD_INTERACTIVE.md) for a complete walkthrough of GitHub and Railway deployment.
