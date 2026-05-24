# TradingView Alert JSON Examples

Use these example payloads when configuring TradingView webhook alerts. Replace placeholders with actual TradingView template variables.

Example LONG alert

```json
{
  "symbol": "ETHUSDT",
  "timeframe": "1m",
  "signal": "LONG",
  "strategy_name": "Example Strategy",
  "strategy_parameters": {"size_override": 0.01, "risk_pct": 0.01},
  "timestamp": "{{timenow}}",
  "price": {{close}},
  "risk_settings": {"stop_loss_pct": 0.01, "take_profit_pct": 0.02}
}
```

Example SHORT alert

```json
{
  "symbol": "ETHUSDT",
  "timeframe": "1m",
  "signal": "SHORT",
  "strategy_name": "Example Strategy",
  "strategy_parameters": {"size_override": 0.01, "risk_pct": 0.01},
  "timestamp": "{{timenow}}",
  "price": {{close}},
  "risk_settings": {"stop_loss_pct": 0.01, "take_profit_pct": 0.02}
}
```

Example CLOSE alert

```json
{
  "symbol": "ETHUSDT",
  "timeframe": "1m",
  "signal": "CLOSE",
  "strategy_name": "Example Strategy",
  "timestamp": "{{timenow}}",
  "price": {{close}}
}
```

Example STOP alert

```json
{
  "symbol": "ETHUSDT",
  "timeframe": "1m",
  "signal": "STOP",
  "strategy_name": "Example Strategy",
  "timestamp": "{{timenow}}",
  "price": {{close}},
  "direction": "LONG",
  "risk_settings": {"stop_loss_pct": 0.02}
}
```

Notes:
- Use `{{close}}` and `{{timenow}}` placeholders in TradingView's webhook message template.
- Ensure the webhook JSON is valid and contains `signal` and `timestamp` fields.
