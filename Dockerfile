FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    RADAR_DATABASE=/data/radar.sqlite \
    RADAR_CACHE_DIR=/data/source-cache \
    HOST=0.0.0.0 \
    PORT=8000 \
    RADAR_SYNC_ON_START=true \
    RADAR_SYNC_INTERVAL_HOURS=24

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN python -m pip install --no-cache-dir . \
    && mkdir -p /data/source-cache

EXPOSE 8000

CMD ["michiana-radar-production"]
