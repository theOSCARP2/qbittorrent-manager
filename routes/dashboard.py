import logging
from flask import Blueprint, session, jsonify
from core.qb_client import is_logged_in, qb_request
from core.cache import _cache, _start_bg_fetch, CACHE_TTL

bp  = Blueprint("dashboard", __name__)
log = logging.getLogger(__name__)


@bp.route("/api/dashboard")
def api_dashboard():
    if not is_logged_in():
        return jsonify({"error": "Not authenticated"}), 401

    session_snapshot = {"qb_url": session["qb_url"], "qb_sid": session["qb_sid"]}
    if _cache.age() > CACHE_TTL:
        _start_bg_fetch(session_snapshot)

    data             = _cache.get()
    by_state         = {}
    by_category      = {}
    size_by_category = {}
    total_dl = total_up = total_size = 0

    for t in data:
        state             = t.get("state", "unknown")
        by_state[state]   = by_state.get(state, 0) + 1
        cat               = t.get("category") or ""
        by_category[cat]      = by_category.get(cat, 0) + 1
        size_by_category[cat] = size_by_category.get(cat, 0) + t.get("size", 0)
        total_dl   += t.get("dlspeed", 0)
        total_up   += t.get("upspeed", 0)
        total_size += t.get("size", 0)

    free_space = None
    try:
        resp       = qb_request(session_snapshot, "GET", "/api/v2/sync/maindata")
        free_space = resp.json().get("server_state", {}).get("free_space_on_disk")
    except Exception:
        pass

    return jsonify({
        "total":            len(data),
        "dl_speed":         total_dl,
        "up_speed":         total_up,
        "total_size":       total_size,
        "free_space":       free_space,
        "by_state":         by_state,
        "by_category":      by_category,
        "size_by_category": size_by_category,
        "ready":            _cache.is_ready(),
    })
