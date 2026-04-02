import time
import logging
import requests as _requests
from flask import Blueprint, session, request, jsonify
from core.qb_client import is_logged_in, qb_request
import core.config as _cfg

bp  = Blueprint("system", __name__)
log = logging.getLogger(__name__)


@bp.route("/api/version/check")
def api_version_check():
    now = time.monotonic()
    if _cfg._version_cache["latest"] and now - _cfg._version_cache["ts"] < _cfg.VERSION_CACHE_TTL:
        latest = _cfg._version_cache["latest"]
    else:
        try:
            r = _requests.get(
                f"https://api.github.com/repos/{_cfg.GITHUB_REPO}/releases/latest",
                headers={"Accept": "application/vnd.github+json"},
                timeout=5,
            )
            latest = r.json().get("tag_name", "").lstrip("v")
            _cfg._version_cache["latest"] = latest
            _cfg._version_cache["ts"]     = now
        except Exception:
            return jsonify({"error": "unavailable"}), 503

    up_to_date = _cfg._version_tuple(_cfg.APP_VERSION) >= _cfg._version_tuple(latest) if latest else True
    return jsonify({"current": _cfg.APP_VERSION, "latest": latest, "up_to_date": up_to_date})


@bp.route("/api/debug/status")
def api_debug_status():
    return jsonify({"debug": _cfg._debug_mode})


@bp.route("/api/debug/toggle", methods=["POST"])
def api_debug_toggle():
    if not is_logged_in():
        return jsonify({"error": "Not authenticated"}), 401
    _cfg._set_debug(not _cfg._debug_mode)
    log.info("Mode debug %s", "activé" if _cfg._debug_mode else "désactivé")
    return jsonify({"debug": _cfg._debug_mode})


@bp.route("/api/qb/logs")
def api_qb_logs():
    if not is_logged_in():
        return jsonify({"error": "Not authenticated"}), 401
    last_id = request.args.get("last_id", "-1")
    try:
        resp = qb_request(session, "GET",
                          f"/api/v2/log/main?last_known_id={last_id}&normal=true&info=true&warning=true&critical=true")
        return jsonify(resp.json())
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502
