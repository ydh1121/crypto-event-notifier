FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    B3_JOURNAL_DB=/tmp/b3_trader.sqlite3 \
    LIVE_TRADING_ENABLED=false \
    PRIVATE_WEBSOCKET_ENABLED=false

WORKDIR /app

COPY b3_trader/requirements.txt /app/b3_trader/requirements.txt
RUN pip install --no-cache-dir -r /app/b3_trader/requirements.txt

COPY b3_trader /app/b3_trader

EXPOSE 8080

CMD ["python", "-m", "b3_trader.service"]
