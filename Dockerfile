# WriteAI 2.0 — single-container deployment: the API also serves the built
# web UI, so one service is the whole app (Render, Hugging Face Spaces,
# Fly.io, Railway, or `docker run -p 8000:8000`).
# docker-compose.yml keeps the two-container nginx setup for self-hosting.

FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    WRITEAI_ENV=production \
    WRITEAI_DATA_DIR=/data \
    WRITEAI_STATIC_DIR=/app/static \
    WRITEAI_EMBEDDING_BACKEND=hashing \
    MALLOC_ARENA_MAX=2 \
    WRITEAI_CV_THREADS=1 \
    PORT=8000

RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt \
 && python -m spacy download en_core_web_sm

COPY backend ./backend
COPY ml_models ./ml_models
COPY --from=web /web/dist ./static

RUN useradd --create-home --uid 10001 writeai \
 && mkdir -p /data && chown -R writeai:writeai /data
USER writeai
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
  CMD curl -fsS "http://127.0.0.1:${PORT}/api/health" || exit 1

# Hosts set $PORT; one worker because jobs run in-process with SQLite.
CMD ["sh", "-c", "exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
