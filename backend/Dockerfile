# APIx backend — FastAPI + uvicorn
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# ENABLE_OTA=1 installs a headless Chromium for the OTA browser scrapers
# (ota_cleartrip / ota_easemytrip). Off by default so the demo image stays lean:
#   docker compose build --build-arg ENABLE_OTA=1
ARG ENABLE_OTA=0

WORKDIR /app

# Install dependencies first (cached layer).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && if [ "$ENABLE_OTA" = "1" ]; then playwright install --with-deps chromium; fi

COPY app ./app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
