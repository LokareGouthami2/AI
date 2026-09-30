# WriteAI 2.0 — API image (FastAPI + OCR + ML + handwriting renderer)
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    WRITEAI_ENV=production \
    WRITEAI_DATA_DIR=/data

RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt \
 && python -m spacy download en_core_web_sm

# Application code, bundled fonts (backend/assets) and the trained classifier.
COPY backend ./backend
COPY ml_models ./ml_models

RUN useradd --create-home --uid 10001 writeai \
 && mkdir -p /data && chown -R writeai:writeai /data
USER writeai
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s \
  CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

# One worker: jobs run in-process and SQLite is the default database.
# Scale out with PostgreSQL + a job queue (see docs/deployment.md).
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
