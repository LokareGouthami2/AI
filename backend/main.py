"""FastAPI application factory.

    uvicorn backend.main:app --reload
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from backend.api.routes import auth_router, router
from backend.config import get_settings
from backend.database.session import init_engine
from backend.services.errors import AppError

log = logging.getLogger("writeai")

# The web UI needs scripts, styles and Google Fonts; the API needs nothing.
WEB_CSP = (
    "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; script-src 'self'; connect-src 'self'; frame-ancestors 'none'"
)
API_CSP = "default-src 'none'; img-src 'self'; frame-ancestors 'none'"


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    init_engine()
    app = FastAPI(
        title="WriteAI 2.0 API",
        version="2.0.0",
        description="Document intelligence, editable study notes and handwriting-style rendering.",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "Authorization", "X-API-Token"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        path = request.url.path
        if not path.startswith("/api/docs"):
            response.headers.setdefault("Content-Security-Policy", API_CSP if path.startswith("/api/") else WEB_CSP)
        return response

    @app.exception_handler(AppError)
    async def app_error(_: Request, exc: AppError):
        return JSONResponse(status_code=exc.status, content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}})

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        errs = [{"loc": ".".join(str(p) for p in e["loc"]), "msg": e["msg"]} for e in exc.errors()[:20]]
        return JSONResponse(status_code=422, content={"error": {"code": "VALIDATION_ERROR", "message": "The request is invalid.", "details": {"errors": errs}}})

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception):
        log.exception("unhandled error: %s", exc)
        return JSONResponse(status_code=500, content={"error": {"code": "INTERNAL_ERROR", "message": "Something went wrong.", "details": {}}})

    @app.get("/api/health")
    def health():
        from backend.llm.provider import get_provider
        from backend.ml.predict import get_classifier
        from backend.rag.embedder import get_embedder

        return {
            "ok": True,
            "version": "2.0.0",
            "llm_provider": get_provider().name,
            "classifier": get_classifier().version,
            "embedder": get_embedder().name,
        }

    app.include_router(auth_router)
    app.include_router(router)
    if settings.static_dir is not None:
        _serve_web_ui(app, settings.static_dir.resolve())
    return app


def _serve_web_ui(app: FastAPI, root) -> None:
    """Serve the built single-page app: real files as-is, every other
    non-API path gets index.html (client-side routing)."""
    index = root / "index.html"
    if not index.is_file():
        raise RuntimeError(f"WRITEAI_STATIC_DIR has no index.html: {root}")

    @app.get("/{path:path}", include_in_schema=False)
    def web_ui(path: str):
        if path.startswith("api/"):
            return JSONResponse(status_code=404, content={"error": {"code": "NOT_FOUND", "message": "Not found.", "details": {}}})
        f = (root / path).resolve()
        if path and f.is_file() and f.is_relative_to(root):  # never outside the build folder
            cache = "public, max-age=31536000, immutable" if path.startswith("assets/") else "no-cache"
            return FileResponse(f, headers={"Cache-Control": cache})
        return FileResponse(index, headers={"Cache-Control": "no-cache"})


app = create_app()
