# Operational Validation Checklist (Before Live Deployment)

Minimum forward-testing requirements

- Minimum forward-testing duration: 30 days (configurable by strategy)
- Minimum number of trades: 100 (or strategy-specific thresholds)
- Minimum sample of market regimes: bull, bear, sideways

Acceptable thresholds

- Maximum daily drawdown during forward testing: 5%
- Maximum per-trade slippage increase: 2x historical
- Execution latency: median < 200 ms, p95 < 1s
- Execution quality: fill rate > 95%
- Rolling Sharpe: consistent with in-sample within 20%

Stability requirements

- No unexplained drift score > 0.2 over 7 days
- Reconnect rate < 1 per 24 hours
- No persistent error spikes in logs

Checklist before moving capital

- Run 30+ day forward testing with `PAPER_MODE=true`
- Verify replay stress tests under high-frequency bursts
- Verify reconnect and disconnect handling
- Verify monitoring dashboards and alerts
- Review execution logs and CSV reports
