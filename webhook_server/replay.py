"""Replay utility to send historical alerts to the webhook server for stress testing."""
import json
import time
from typing import Iterable

import httpx


def send_alerts(url: str, alerts: Iterable[dict], delay: float = 0.0, token: str | None = None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["x-webhook-token"] = token
    with httpx.Client(timeout=30) as client:
        for a in alerts:
            r = client.post(url + "/webhook", json=a, headers=headers)
            print(r.status_code, r.text)
            if delay:
                time.sleep(delay)


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "sample_alerts.json"
    url = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8000"
    token = sys.argv[3] if len(sys.argv) > 3 else None
    with open(path, "r") as f:
        alerts = json.load(f)
    send_alerts(url, alerts, delay=0.0, token=token)
