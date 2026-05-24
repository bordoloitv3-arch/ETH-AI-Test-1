# After GitHub: Railway & TradingView Setup

Congratulations! Your repository is on GitHub. Now let's deploy it to Railway and connect it to TradingView.

**Estimated time:** 20–30 minutes total (Railway 15 min, TradingView 10–15 min).

---

## Phase 1: Railway Deployment (15 minutes)

Railway is a cloud platform that automatically deploys your code from GitHub and runs it 24/7.

### Step 1: Create Railway account

1. Go to https://railway.app
2. Click **"Start Project"** (or **"Sign Up"**)
3. Log in with GitHub (easiest option)
4. Authorize Railway to access your GitHub account

### Step 2: Create a new project in Railway

1. Click **"+ New Project"** (top-right)
2. Select **"Deploy from GitHub repo"**
3. Select your repository (e.g., `eth-futures-ai`)
4. Click **"Connect"**

Railway will:
- Detect your `Dockerfile` and `railway.json`
- Start building your app
- Show a build log

**Wait for the build to complete.** You'll see ✓ when done.

### Step 3: Configure environment variables

1. Click on your service (left sidebar shows your app name)
2. Go to **"Variables"** tab
3. Add these environment variables (see `.env.example` for reference):

```
WEBHOOK_SECRET = your-secret-key
PAPER_MODE = true
LOG_LEVEL = INFO
ENVIRONMENT = production
PROMETHEUS_ENABLED = true
DATABASE_PATH = /data/trading.sqlite
STATE_DIR = /data/state
MAX_AGE_SECONDS = 3600
```

**Explanations:**
- `WEBHOOK_SECRET` — Random string to protect your webhook (e.g., `super-secret-key-12345`)
- `PAPER_MODE = true` — Use paper trading (no real money yet)
- `LOG_LEVEL = INFO` — Show informational logs
- `ENVIRONMENT = production` — Railway environment
- `PROMETHEUS_ENABLED = true` — Enable metrics
- `DATABASE_PATH` — Where to store database
- `STATE_DIR` — Where to store state snapshots
- `MAX_AGE_SECONDS` — How old alerts can be before rejecting

**For now, use defaults.** You can change them later.

### Step 4: Enable persistent storage

**Why:** Your database and state files need to survive app restarts.

1. Go to **"Volumes"** tab
2. Click **"+ Add Volume"**
3. Set:
   - **Mount path:** `/data`
   - **Size:** 1 GB (enough for data)
4. Click **"Create"**

This ensures your trading data isn't lost on redeploy.

### Step 5: Get your webhook URL

1. Go to **"Deployments"** tab
2. Click the latest deployment
3. Look for **"View Logs"** or **"Public URL"**
4. The URL will be something like: `https://eth-futures-ai-production-abc123.railway.app`

**Copy this URL.** You'll need it for TradingView.

### Step 6: Verify deployment

In your browser, visit:

```
https://your-railway-url/health
```

You should see:

```json
{"status": "ok"}
```

**✓ Great! Your webhook is running.**

Also visit (no auth needed for health check):

```
https://your-railway-url/metrics
```

You should see Prometheus metrics (may look like gibberish — that's normal).

---

## Phase 2: Connect TradingView (10–15 minutes)

### What will happen:
1. You'll create an alert in TradingView
2. When the alert triggers, TradingView sends a webhook POST to Railway
3. Railway receives it and processes a paper trade
4. Your mobile app shows the fill

### Step 1: Create a TradingView strategy alert

1. Go to https://www.tradingview.com
2. Open a chart (e.g., **ETHUSDT** on 5m timeframe)
3. Click on a strategy or create one (use an existing one for testing)
4. Right-click chart → **"Add Alert"** or use the **Alert** button (bell icon)

### Step 2: Configure the alert

**Alert Settings:**
- **Condition:** Set your trigger condition (e.g., "when close crosses above 50-period MA")
- **Frequency:** Webhook events (not email)
- **Show popups:** Yes (so you see alerts)

### Step 3: Add webhook action

1. Scroll down to **"Notifications"**
2. Enable **"Webhook URL"**
3. Paste your Railway webhook URL:

```
https://your-railway-url/webhook
```

**In the webhook payload**, use this template (see `docs/TRADINGVIEW_ALERTS.md` for examples):

```json
{
  "symbol": "ETHUSDT",
  "action": "{{strategy.order.action}}",
  "price": "{{close}}",
  "time": "{{timenow}}"
}
```

### Step 4: Test the webhook

1. After creating the alert, click **"Test"**
2. You should see a POST to your webhook URL
3. Check Railway logs to see if it was received

**In Railway:**
- Go to **Deployments** → **View Logs**
- You should see a POST request logged
- Look for `200 OK` response

### Step 5: Verify the webhook is working

In PowerShell, test locally:

```powershell
$url = "https://your-railway-url/webhook"
$payload = @{
    symbol = "ETHUSDT"
    action = "BUY"
    price = "2500"
    time = "2026-05-24T10:30:00Z"
} | ConvertTo-Json

$headers = @{
    "x-webhook-token" = "your-webhook-secret"
}

Invoke-WebRequest -Uri $url -Method POST -Body $payload -Headers $headers -ContentType "application/json"
```

**Expected response:**
```
StatusCode : 200
```

---

## Phase 3: Paper Trading Forward Test

### Enable paper trading on your phone

1. Open TradingView on your Android phone
2. Go to **Alerts** (bell icon)
3. Create a simple alert (e.g., "close crosses above 50MA on ETHUSDT 5m")
4. Enable webhook to your Railway URL

### Start a forward test

1. Create a TradingView alert that triggers during market hours
2. Wait for the alert to fire
3. Check your Railway logs to see the POST
4. (Optional) Check your database to see the recorded trade

### Monitor the dashboard

Your Streamlit dashboard can show paper trading results:

```powershell
streamlit run webhook_server/dashboard_streamlit.py
```

Open: `http://localhost:8501`

---

## Troubleshooting

### Railway app won't build

**Cause:** Missing dependencies or wrong Python version.

**Fix:**
1. Check Railway build logs for errors
2. Ensure `requirements.txt` is up to date
3. Redeploy manually: Click **"Redeploy"** in Railway

### Webhook returns 401 (Unauthorized)

**Cause:** `WEBHOOK_SECRET` doesn't match header.

**Fix:**
1. In Railway Variables, set `WEBHOOK_SECRET`
2. In TradingView webhook payload, add header:
   ```
   x-webhook-token: your-secret
   ```

### Webhook times out (504 error)

**Cause:** Request is taking too long.

**Fix:**
1. Check Railway logs for processing errors
2. Simplify webhook payload (remove unnecessary fields)
3. Increase timeout in Railway settings

### Database file not persisting

**Cause:** Volume not mounted correctly.

**Fix:**
1. Verify volume is mounted at `/data` in Railway UI
2. Restart the deployment
3. Check logs: `tail -f /data/trading.sqlite`

---

## Next: Mobile Paper Trading Forward Tests

Once Railway and TradingView are connected:

1. **Test phase (1–2 weeks):** Run paper trading alerts from TradingView
   - Verify fills are recorded
   - Check for duplicate alerts (dedup working?)
   - Monitor latency (webhook → fill)

2. **Validation phase:** Run 30+ days of forward tests
   - Verify P&L calculation
   - Check slippage assumptions
   - Ensure no crashes or data loss

3. **Production phase (after validation):** Consider real trading
   - Use Railway production settings
   - Enable rate limiting and HMAC signatures
   - Set up monitoring and alerts

---

## Quick Command Reference

### Check Railway deployment status

```powershell
# Test webhook
curl https://your-railway-url/health

# View metrics
curl https://your-railway-url/metrics

# Check if running
Invoke-WebRequest -Uri https://your-railway-url/health
```

### Check local database

```powershell
# See recorded trades (if SQLite)
sqlite3 trading.sqlite "SELECT * FROM trades LIMIT 5;"
```

### Restart Railway deployment

1. Go to Railway UI
2. Click **"Deployments"**
3. Click **"Redeploy"** on latest deployment

---

## Summary

You now have:

✓ GitHub repository (code safe and version-controlled)
✓ Railway deployment (app running 24/7 on the internet)
✓ TradingView webhook integration (alerts trigger trades)
✓ Paper trading engine (test strategies risk-free)

**Next:** Forward test on ETHUSDT for 30+ days, monitor metrics, then consider production deployment!

