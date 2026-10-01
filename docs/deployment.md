# Deployment

## Publish online (one container, Render free plan)

The root `Dockerfile` builds the web UI and serves it from the API, so one
service is the whole app. `render.yaml` describes it for Render:

1. Sign in at render.com with GitHub and allow access to this repository.
2. **New → Blueprint**, pick the repository and the branch named in
   `render.yaml`.
3. When asked, set **WRITEAI_API_TOKEN** to a password (anyone without it
   sees only a login page). `ANTHROPIC_API_KEY` is optional.
4. **Apply**. The first build takes about 10 minutes; the site is then at
   `https://writeai-….onrender.com`.

Free-plan limits:

* The service sleeps after 15 minutes without visitors; the next visit
  takes about a minute to wake it.
* No persistent disk: uploaded documents are lost when it restarts or
  redeploys. Download your PDFs. (Paid plans can add a disk at `/data`.)
* 512 MB of memory. Measured in a 512 MB container: three 20-page
  photo-look renders plus two normal documents in a row, peak anonymous
  memory ~410 MB, no restarts. What keeps it there: renders run one at a
  time, OpenCV runs single-threaded (`WRITEAI_CV_THREADS=1`), memory is
  handed back to the OS after each job, MuPDF's cache is cleared per page,
  and spaCy loads only its sentence splitter.

### Site password

With `WRITEAI_API_TOKEN` set, every `/api` call needs it. The web UI shows a
login page; `POST /api/auth/login` checks the password (rate-limited) and
sets an HttpOnly, SameSite=Strict cookie holding an HMAC of the password
(never the password itself), scoped to `/api`. The cookie also covers
preview images and PDF downloads. Scripts can still send `X-API-Token`.

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
