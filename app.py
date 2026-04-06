import logging
from flask import Flask
from core.config import _get_secret_key, APP_VERSION, GITHUB_REPO
from core.extensions import csrf, limiter
from routes import auth, pages, dashboard, torrents, trackers, categories, system

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
app = Flask(__name__)
app.secret_key = _get_secret_key()

# ── Cookies de session sécurisés ────────────────────────────────────────────
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["WTF_CSRF_TIME_LIMIT"]     = 3600  # token CSRF valide 1h

# ---------------------------------------------------------------------------
# Extensions
# ---------------------------------------------------------------------------
csrf.init_app(app)
limiter.init_app(app)

# ---------------------------------------------------------------------------
# Content Security Policy
# ---------------------------------------------------------------------------
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


@app.after_request
def set_security_headers(response):
    response.headers["Content-Security-Policy"] = _CSP
    response.headers["X-Content-Type-Options"]  = "nosniff"
    response.headers["X-Frame-Options"]          = "DENY"
    response.headers["Referrer-Policy"]          = "strict-origin-when-cross-origin"
    return response


# ---------------------------------------------------------------------------
# Context processors
# ---------------------------------------------------------------------------
@app.context_processor
def inject_version():
    return {"app_version": APP_VERSION, "github_repo": GITHUB_REPO}


# ---------------------------------------------------------------------------
# Blueprints
# ---------------------------------------------------------------------------
app.register_blueprint(auth.bp)
app.register_blueprint(pages.bp)
app.register_blueprint(dashboard.bp)
app.register_blueprint(torrents.bp)
app.register_blueprint(trackers.bp)
app.register_blueprint(categories.bp)
app.register_blueprint(system.bp)

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from waitress import serve
    log.info("━" * 42)
    log.info("  qBittorrent Manager v%s", APP_VERSION)
    log.info("  http://localhost:5000")
    log.info("  Mode debug : désactivé (bouton 🐛 dans l'interface)")
    log.info("━" * 42)
    serve(app, host="0.0.0.0", port=5000, threads=4)
