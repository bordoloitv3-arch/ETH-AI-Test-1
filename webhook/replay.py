from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional

from webhook.coordinator import WebhookTradingCoordinator
from webhook.models import TradingViewAlertPayload


class ReplayModeRunner:
    def __init__(self, coordinator: WebhookTradingCoordinator, speed_multiplier: float = 10.0) -> None:
        self.coordinator = coordinator
        self.speed_multiplier = max(float(speed_multiplier), 0.01)

    def run_from_alerts(self, alerts: Iterable[TradingViewAlertPayload]) -> Dict[str, Any]:
        results: List[Dict[str, Any]] = []
        previous_time: Optional[datetime] = None
        for alert in alerts:
            if previous_time is not None:
                delay = (alert.timestamp - previous_time).total_seconds() / self.speed_multiplier
                if delay > 0:
                    time.sleep(min(delay, 0.1))
            result = self.coordinator.process_alert(alert)
            results.append(result)
            previous_time = alert.timestamp
        return {
            "run_at": datetime.utcnow().isoformat() + "Z",
            "count": len(results),
            "results": results,
        }

    def run_from_historical(self, payloads: List[Dict[str, Any]]) -> Dict[str, Any]:
        alerts = [TradingViewAlertPayload(**payload) for payload in payloads]
        return self.run_from_alerts(alerts)

    def stress_test(self, payloads: List[Dict[str, Any]], bursts: int = 3) -> Dict[str, Any]:
        results = []
        for _ in range(bursts):
            results.extend(self.run_from_historical(payloads)["results"])
        return {
            "status": "stress_complete",
            "count": len(results),
            "results": results,
        }
