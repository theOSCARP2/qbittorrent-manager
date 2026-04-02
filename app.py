import logging
from flask import Flask
from core.config import _get_secret_key, APP_VERSION, GITHUB_REPO
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
