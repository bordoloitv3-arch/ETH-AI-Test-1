from __future__ import annotations

import os
from typing import Any, Dict, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Any, Dict, List, Optional

from optimizer.logger import get_logger
from webhook.coordinator import WebhookTradingCoordinator
from webhook.models import TradingViewAlertPayload


def get_env(name: str, default: Optional[str] = None) -> Optional[str]:
    return os.environ.get(name, default)


def validate_token(x_webhook_token: Optional[str] = Header(None)) -> Optional[str]:
    return x_webhook_token


def create_app() -> FastAPI:
    logger = get_logger(
        level=os.environ.get("WEBHOOK_LOG_LEVEL", "INFO"),
        path=os.environ.get("WEBHOOK_LOG_PATH", "logs/webhook/webhook.log"),
        structured=True,
    )
    # Configuration: support both legacy WEBHOOK_* vars and standardized names
    db_path = os.environ.get("DATABASE_PATH") or os.environ.get("WEBHOOK_DB_PATH") or "memory/webhook/webhook.db"
    default_state_dir = os.path.join(os.path.dirname(db_path), "webhook_state") if os.path.dirname(db_path) else "memory/webhook_state"
    state_dir = os.environ.get("STATE_DIR") or os.environ.get("WEBHOOK_STATE_DIR") or default_state_dir
    report_dir = os.environ.get("WEBHOOK_REPORT_DIR") or os.environ.get("REPORT_DIR") or "reports/webhook"
    log_dir = os.environ.get("WEBHOOK_LOG_DIR") or os.environ.get("LOG_DIR") or "logs/webhook"
    secret = os.environ.get("WEBHOOK_SECRET") or os.environ.get("WEBHOOK_SECRET_TOKEN")
    max_age = int(os.environ.get("MAX_AGE_SECONDS") or os.environ.get("WEBHOOK_MAX_AGE_SECONDS") or "300")
    log_level = os.environ.get("LOG_LEVEL") or os.environ.get("WEBHOOK_LOG_LEVEL") or "INFO"
    environment = os.environ.get("ENVIRONMENT") or os.environ.get("APP_ENV") or "production"
    prometheus_enabled = (os.environ.get("PROMETHEUS_ENABLED") or "true").lower() in ("1", "true", "yes")

    coordinator = WebhookTradingCoordinator(
        db_path=db_path,
        report_dir=report_dir,
        log_dir=log_dir,
        state_dir=state_dir,
        max_age_seconds=max_age,
        secret_token=secret,
        logger=logger,
    )

    # PAPER_MODE: force paper trading mode when true
    if (os.environ.get("PAPER_MODE") or "true").lower() in ("1", "true", "yes"):
        try:
            coordinator.engine.paper_mode = True
        except Exception:
            pass
    app = FastAPI(
        title="ETH Futures TradingView Webhook",
        description="Webhook server for TradingView alert forward testing with paper trading and metrics.",
        version="0.1.0",
    )

    @app.on_event("startup")
    async def startup_event() -> None:
        logger.info("Webhook server startup complete.")

    @app.get("/health")
    async def health() -> Dict[str, Any]:
        return {
            "status": "ok",
            "service": "TradingView Webhook",
            "webhook_secret_configured": coordinator.secret_token is not None,
            "last_alert_time": coordinator.last_alert_time.isoformat() if coordinator.last_alert_time else None,
        }

    @app.get("/metrics")
    async def metrics() -> Dict[str, Any]:
        return {
            "status": "ok",
            "metrics": coordinator.get_metrics(),
            "health": coordinator.get_health(),
        }

    @app.post("/webhook")
    async def webhook(
        payload: TradingViewAlertPayload,
        request: Request,
        x_webhook_token: Optional[str] = Depends(validate_token),
    ) -> JSONResponse:
        if coordinator.secret_token and x_webhook_token != coordinator.secret_token:
            logger.warning("Webhook authentication failed for request from %s", request.client.host if request.client else "unknown")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook token")

        try:
            result = coordinator.process_alert(payload)
            return JSONResponse(status_code=status.HTTP_200_OK, content={"success": True, "result": result})
        except ValueError as exc:
            logger.warning("Webhook validation failed: %s", exc)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
        except Exception as exc:
            logger.exception("Unhandled webhook processing error.")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal webhook failure")

    @app.post("/replay")
    async def replay_alerts(request: Request) -> Dict[str, Any]:
        from webhook.replay import ReplayModeRunner

        body = await request.json()
        payloads = body.get("payloads", [])
        speed = float(body.get("speed_multiplier", 10.0))
        mode = body.get("mode", "standard")
        bursts = int(body.get("stress_test_bursts", 1))

        runner = ReplayModeRunner(coordinator, speed_multiplier=speed)
        if mode == "stress":
            return runner.stress_test(payloads, bursts=max(1, bursts))
        return runner.run_from_historical(payloads)

    return app


app = create_app()
