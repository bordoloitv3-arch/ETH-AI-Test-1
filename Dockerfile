FROM python:3.14-slim

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY . .

ENV WEBHOOK_LOG_PATH=logs/webhook/webhook.log
ENV WEBHOOK_STATE_DIR=memory/webhook_state
ENV WEBHOOK_DB_PATH=memory/webhook/webhook.db
ENV WEBHOOK_REPORT_DIR=reports/webhook
ENV WEBHOOK_LOG_DIR=logs/webhook
ENV WEBHOOK_MAX_AGE_SECONDS=300

EXPOSE 8000
CMD ["uvicorn", "webhook.server:app", "--host", "0.0.0.0", "--port", "8000"]
