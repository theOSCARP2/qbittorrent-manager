import logging
import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request

from api import auth, categories, dashboard, pages, system, torrents, trackers
from core.config import APP_VERSION, GITHUB_REPO, _get_secret_key
from core.extensions import limiter
from core.templates import templates

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="qBittorrent Manager", version=APP_VERSION, docs_url=None, redoc_url=None)

# ── Session (signed cookie via Starlette SessionMiddleware) ─────────────────
app.add_middleware(
    SessionMiddleware,
    secret_key=_get_secret_key(),
    same_site="lax",
    https_only=False,
    max_age=86400,
)

# ── Rate limiter ─────────────────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── Static files ─────────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory="static"), name="static")

# ── Security headers ─────────────────────────────────────────────────────────
_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' "
    "cdn.jsdelivr.net code.jquery.com cdn.datatables.net; "
    "style-src 'self' 'unsafe-inline' "
    "cdn.jsdelivr.net cdn.datatables.net; "
    "font-src 'self' cdn.jsdelivr.net data:; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "worker-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self';"
)


class _SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = _CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


app.add_middleware(_SecurityHeadersMiddleware)

# ── Template globals ─────────────────────────────────────────────────────────
templates.env.globals["app_version"] = APP_VERSION
templates.env.globals["github_repo"] = GITHUB_REPO

# ── Routers ──────────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(pages.router)
app.include_router(dashboard.router)
app.include_router(torrents.router)
app.include_router(trackers.router)
app.include_router(categories.router)
app.include_router(system.router)

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    log.info("━" * 42)
    log.info("  qBittorrent Manager v%s", APP_VERSION)
    port = int(os.environ.get("PORT", 5000))
    log.info("  http://localhost:%s", port)
    log.info("  Framework : FastAPI + Uvicorn")
    log.info("━" * 42)
    uvicorn.run("app:app", host="0.0.0.0", port=port, workers=1, log_level="info")
