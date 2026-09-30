# Deployment

## Docker Compose (single host)

```bash
cp .env.example .env          # optionally add ANTHROPIC_API_KEY
docker compose up --build -d
open http://localhost:8080
```

* `backend` (FastAPI, Tesseract, spaCy model, fonts, trained classifier) runs
  as a non-root user with data on the `writeai-data` volume.
* `frontend` is nginx serving the built SPA. It proxies `/api` to the backend,
  so the UI and API share one origin and CORS isn't needed.

### Verified

Both images were built and run together in the development sandbox. There,
the sandbox's network policy blocked `deb.debian.org`, so the Tesseract apt
layer couldn't be installed. The images were verified with that one step
removed. Through the nginx proxy:

* health returned 200;
* the SPA route fallback worked and the security headers were present;
* upload → extract → analyze → generate → final render (quality checks and
  PDF audit passed) → download worked;
* Ask Your Document answered.

On a normal network the Dockerfile builds as written.

## Scaling beyond one host

| Concern | v1 | Swap to |
|---|---|---|
| Database | SQLite in `/data` | PostgreSQL via `WRITEAI_DATABASE_URL` (SQLAlchemy; JSON columns portable) |
| Jobs | In-process thread pool + `jobs` table | RQ or Celery workers behind `services/jobs.submit` |
| Files | Local volume | S3-compatible storage behind `documents/storage.py` |
| Vectors | Embedded ChromaDB | Chroma server or pgvector behind `rag/store.py` |
| Rate limits | In-process | Redis |

Keep **one Uvicorn worker per container** while jobs are in-process.

## Platforms

Any container host works: Fly.io, Render, Railway, a VM with Docker, or
Kubernetes. Mount a persistent volume at `/data`, set the environment
variables from `.env.example`, and expose the `frontend` service.

## CI

`.github/workflows/ci.yml` runs:

* backend lint and tests, with Tesseract installed;
* frontend lint, unit tests and build;
* the Playwright suite, including the critical acceptance test (traces
  uploaded on failure).
