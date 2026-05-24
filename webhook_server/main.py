import os
import json
import hashlib
import time
from typing import Dict

from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import ValidationError
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

from .models import TradingViewAlert
from .db import init_db, insert_alert, record_execution, record_error, write_metric
from live.paper_engine import PaperTradingEngine


WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
DB_PATH = os.getenv("WEBHOOK_DB", "webhook_state.db")

app = FastAPI(title="TradingView Webhook Receiver")

# metrics
alerts_received = Counter("webhook_alerts_total", "Total TradingView alerts received")
alerts_accepted = Counter("webhook_alerts_accepted_total", "Accepted alerts")
alerts_rejected = Counter("webhook_alerts_rejected_total", "Rejected alerts")
processing_latency = Histogram("webhook_processing_seconds", "Processing latency seconds")

# initialize DB and engine
init_db(DB_PATH)
engine = PaperTradingEngine()

# simple in-memory recent hashes for replay protection
RECENT_HASHES: Dict[str, float] = {}
REPLAY_WINDOW = int(os.getenv("REPLAY_WINDOW_SEC", "300"))


def compute_alert_hash(payload: Dict) -> str:
    raw = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@app.get("/health")
async def health() -> Dict:
    return {"status": "ok"}


@app.get("/metrics")
async def metrics() -> PlainTextResponse:
    data = generate_latest()
    return PlainTextResponse(content=data, media_type=CONTENT_TYPE_LATEST)


@app.post("/webhook")
async def webhook(request: Request, x_webhook_token: str = Header(None)):
    start = time.time()
    alerts_received.inc()
    try:
        body = await request.json()
    except Exception as exc:
        alerts_rejected.inc()
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # optional token validation
    if WEBHOOK_SECRET:
        if not x_webhook_token or x_webhook_token != WEBHOOK_SECRET:
            alerts_rejected.inc()
            raise HTTPException(status_code=401, detail="Invalid webhook token")

    try:
        alert = TradingViewAlert(**body)
    except ValidationError as exc:
        alerts_rejected.inc()
        record_error(None, f"validation_error: {exc}")
        raise HTTPException(status_code=422, detail=str(exc))

    payload = alert.dict()
    h = compute_alert_hash(payload)

    # replay/duplicate protection: check recent in-memory and DB
    now = time.time()
    # purge old
    keys_to_delete = [k for k, t in RECENT_HASHES.items() if now - t > REPLAY_WINDOW]
    for k in keys_to_delete:
        RECENT_HASHES.pop(k, None)

    if h in RECENT_HASHES:
        alerts_rejected.inc()
        return JSONResponse({"status": "duplicate", "hash": h}, status_code=409)

    persisted = insert_alert(h, payload, path=DB_PATH)
    if not persisted:
        alerts_rejected.inc()
        return JSONResponse({"status": "duplicate_db", "hash": h}, status_code=409)

    RECENT_HASHES[h] = now

    # map signals
    sig_map = {"LONG": 1, "SHORT": -1, "CLOSE": 0, "STOP": 0}
    normalized_signal = {"signal": payload.get("signal"), "side": sig_map.get(payload.get("signal"))}

    try:
        order = engine.process_signal(normalized_signal, timestamp=payload.get("timestamp"))
        if order is not None:
            record_execution(h, order.id, "created", price=order.requested_size)
            alerts_accepted.inc()
            processing_latency.observe(time.time() - start)
            write_metric("last_alert_latency", time.time() - start, tags=str({"symbol": payload.get("symbol")}), path=DB_PATH)
            return JSONResponse({"status": "ok", "order_id": order.id, "hash": h})
        else:
            alerts_accepted.inc()
            processing_latency.observe(time.time() - start)
            write_metric("last_alert_latency", time.time() - start, tags=str({"symbol": payload.get("symbol")}), path=DB_PATH)
            return JSONResponse({"status": "no_action", "hash": h})
    except Exception as exc:
        alerts_rejected.inc()
        record_error(h, str(exc), path=DB_PATH)
        raise HTTPException(status_code=500, detail="internal processing error")
