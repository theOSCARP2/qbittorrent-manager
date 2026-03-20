import os
import time
import threading
import logging
import requests
from flask import (
    Flask, session, redirect, url_for, request,
    render_template, jsonify, flash
)

# ---------------------------------------------------------------------------
# Persistent requests sessions keyed by SID
# ---------------------------------------------------------------------------
_qb_sessions: dict[str, requests.Session] = {}

# ---------------------------------------------------------------------------
# Torrent cache
# ---------------------------------------------------------------------------
CACHE_TTL = 30  # seconds

class _TorrentCache:
    def __init__(self):
        self._lock = threading.Lock()
        self._data: list = []
        self._ts: float = 0.0
        self._refreshing: bool = False

    def get(self) -> list:
        return self._data

    def age(self) -> float:
        return time.monotonic() - self._ts

    def is_ready(self) -> bool:
        return bool(self._data)

    def set(self, data: list):
        with self._lock:
            self._data = data
            self._ts = time.monotonic()
            self._refreshing = False

    def invalidate(self):
        self._ts = 0.0

    def start_refresh(self) -> bool:
        with self._lock:
            if self._refreshing:
                return False
            self._refreshing = True
            return True

    def cancel_refresh(self):
        with self._lock:
            self._refreshing = False

_cache = _TorrentCache()

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.DEBUG, format="[%(asctime)s] %(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-production-please")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_TORRENT_FIELDS = {"hash", "name", "size", "progress", "state",
                   "num_seeds", "num_leechs", "dlspeed", "upspeed"}

# Columns sortable server-side: DataTables column index → torrent field
_SORT_COLS = {
    1: "name",
    2: "size",
    4: "state",
    5: "num_seeds",
    6: "num_leechs",
    7: "dlspeed",
    8: "upspeed",
}


def qb_request(session_data, method, endpoint, **kwargs):
    sid = session_data["qb_sid"]
    base_url = session_data["qb_url"].rstrip("/")
    url = f"{base_url}{endpoint}"

    if sid not in _qb_sessions:
        s = requests.Session()
        s.cookies.set("SID", sid)
        _qb_sessions[sid] = s
    else:
        _qb_sessions[sid].cookies.set("SID", sid)

    try:
        t0 = time.monotonic()
        resp = _qb_sessions[sid].request(method, url, timeout=30, **kwargs)
        log.debug("qb_request %s %s → %s in %.2fs", method, endpoint, resp.status_code, time.monotonic()-t0)
        resp.raise_for_status()
        return resp
    except requests.exceptions.ConnectionError as exc:
        _qb_sessions.pop(sid, None)
        raise RuntimeError(f"Cannot connect to qBittorrent: {exc}") from exc
    except requests.exceptions.Timeout as exc:
        raise RuntimeError(f"qBittorrent request timed out: {exc}") from exc
    except requests.exceptions.HTTPError as exc:
        raise RuntimeError(f"qBittorrent returned an error: {exc}") from exc


def is_logged_in():
    return "qb_sid" in session and "qb_url" in session


def _fetch_and_cache(session_snapshot: dict):
    """Fetch all torrents from qBittorrent and store in cache."""
    log.debug("→ _fetch_and_cache: start (url=%s)", session_snapshot.get("qb_url"))
    t0 = time.monotonic()
    try:
        resp = qb_request(session_snapshot, "GET", "/api/v2/torrents/info")
        log.debug("   HTTP %s in %.2fs, content-length=%s",
                  resp.status_code, time.monotonic() - t0,
                  resp.headers.get("content-length", "?"))
        raw = resp.json()
        log.debug("   Parsed %d torrents", len(raw))
        slim = [{k: t[k] for k in _TORRENT_FIELDS if k in t} for t in raw]
        _cache.set(slim)
        log.debug("← _fetch_and_cache: done in %.2fs, %d torrents cached",
                  time.monotonic() - t0, len(slim))
    except Exception as exc:
        log.error("   _fetch_and_cache ERROR: %s", exc, exc_info=True)
        _cache.cancel_refresh()


def _start_bg_fetch(session_snapshot: dict):
    """Start a background fetch only if not already running."""
    if _cache.start_refresh():
        log.debug("Starting background fetch thread")
        threading.Thread(target=_fetch_and_cache, args=(session_snapshot,), daemon=True).start()
    else:
        log.debug("Background fetch already in progress, skipping")


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    if is_logged_in():
        return redirect(url_for("torrents"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        qb_url = request.form.get("qb_url", "").strip().rstrip("/")
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not qb_url:
            flash("Server URL is required.", "danger")
            return render_template("login.html")

        try:
            resp = requests.post(
                f"{qb_url}/api/v2/auth/login",
                data={"username": username, "password": password},
                timeout=15,
            )
            body = resp.text.strip()
            if body == "Ok.":
                sid = resp.cookies.get("SID")
                if not sid:
                    flash("Login succeeded but no SID cookie was returned.", "danger")
                    return render_template("login.html")
                session["qb_url"] = qb_url
                session["qb_sid"] = sid
                session["qb_username"] = username

                # ── Start fetching torrents in background immediately at login
                log.debug("Login OK for %s @ %s — starting bg fetch", username, qb_url)
                _cache.invalidate()
                _start_bg_fetch({"qb_url": qb_url, "qb_sid": sid})

                return redirect(url_for("torrents"))
            elif body == "Fails.":
                flash("Invalid username or password.", "danger")
            else:
                flash(f"Unexpected response from qBittorrent: {body}", "warning")
        except requests.exceptions.ConnectionError:
            flash(f"Cannot connect to {qb_url}. Check the URL and try again.", "danger")
        except requests.exceptions.Timeout:
            flash("Connection timed out.", "danger")

        return render_template("login.html")

    if is_logged_in():
        return redirect(url_for("torrents"))
    return render_template("login.html")


@app.route("/logout")
def logout():
    if is_logged_in():
        sid = session.get("qb_sid")
        try:
            qb_request(session, "POST", "/api/v2/auth/logout")
        except Exception:
            pass
        _qb_sessions.pop(sid, None)
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


@app.route("/torrents")
def torrents():
    if not is_logged_in():
        return redirect(url_for("login"))
    # Pre-warm cache if empty (e.g. user arrives directly without fresh login)
    if not _cache.is_ready():
        log.debug("/torrents: cache empty, pre-warming")
        _start_bg_fetch({"qb_url": session["qb_url"], "qb_sid": session["qb_sid"]})
    return render_template("torrents.html")


@app.route("/trackers")
def trackers():
    if not is_logged_in():
        return redirect(url_for("login"))
    return render_template("trackers.html")


# ---------------------------------------------------------------------------
# API proxy routes
# ---------------------------------------------------------------------------

@app.route("/api/torrents/status")
def api_torrents_status():
    """Let the frontend know whether the cache is populated yet."""
    if not is_logged_in():
        return jsonify({"error": "Not authenticated"}), 401
    return jsonify({"ready": _cache.is_ready(), "total": len(_cache.get())})


@app.route("/api/torrents")
def api_torrents():
    """
    DataTables server-side endpoint.
    Params: draw, start, length, search[value], order[0][column], order[0][dir]
    Returns: { draw, recordsTotal, recordsFiltered, data }
    If cache not ready yet, returns { loading: true }.
    """
    if not is_logged_in():
        return jsonify({"error": "Not authenticated"}), 401

    session_snapshot = {"qb_url": session["qb_url"], "qb_sid": session["qb_sid"]}

    # If cache is empty, start background fetch (if not already running)
    if not _cache.is_ready():
        log.debug("/api/torrents: cache empty, starting bg fetch")
        _start_bg_fetch(session_snapshot)
        draw = int(request.args.get("draw", 1))
        return jsonify({"draw": draw, "recordsTotal": 0, "recordsFiltered": 0,
                        "data": [], "loading": True})

    # Trigger background refresh if stale
    if _cache.age() > CACHE_TTL:
        log.debug("/api/torrents: cache stale (%.0fs), refreshing in bg", _cache.age())
        _start_bg_fetch(session_snapshot)

    data = _cache.get()

    # -- DataTables params
    draw   = int(request.args.get("draw", 1))
    start  = int(request.args.get("start", 0))
    length = int(request.args.get("length", 20))
    search = request.args.get("search[value]", "").strip().lower()
    order_col = int(request.args.get("order[0][column]", 1))
    order_dir = request.args.get("order[0][dir]", "asc")

    # -- Filter
    filtered = [t for t in data if search in t.get("name", "").lower()] if search else data

    # -- Sort
    sort_key = _SORT_COLS.get(order_col, "name")
    reverse  = order_dir == "desc"
    if sort_key == "name":
        filtered = sorted(filtered, key=lambda t: t.get("name", "").lower(), reverse=reverse)
    else:
        filtered = sorted(filtered, key=lambda t: t.get(sort_key) or 0, reverse=reverse)

    # -- Paginate
    page = filtered[start: start + length]

    return jsonify({
        "draw": draw,
        "recordsTotal": len(data),
        "recordsFiltered": len(filtered),
        "data": page,
    })


@app.route("/api/trackers")
def api_trackers():
    """
    Fetch trackers for ALL torrents.
    Returns a dict: {
        tracker_url: {
            torrents: [{ hash, name }, ...],
            ok:       <count of status=2 (working)>,
            error:    <count of status=4 (not working)>,
            pending:  <count of status 0/1/3>,
        }
    }
    qBittorrent tracker status codes:
        0 = disabled, 1 = not contacted, 2 = working, 3 = updating, 4 = not working
    """
    if not is_logged_in():
        return jsonify({"error": "Not authenticated"}), 401
    try:
        torrents_resp = qb_request(session, "GET", "/api/v2/torrents/info")
        torrents_list = torrents_resp.json()
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502

    tracker_map = {}

    for torrent in torrents_list:
        t_hash  = torrent.get("hash", "")
        t_info  = {
            "hash":     t_hash,
            "name":     torrent.get("name", t_hash),
            "state":    torrent.get("state", "unknown"),
            "progress": torrent.get("progress", 0),
            "dlspeed":  torrent.get("dlspeed", 0),
            "upspeed":  torrent.get("upspeed", 0),
            "size":     torrent.get("size", 0),
        }
        try:
            tr_resp = qb_request(session, "GET", f"/api/v2/torrents/trackers?hash={t_hash}")
            for tracker in tr_resp.json():
                url = tracker.get("url", "").strip()
                if not url or url.startswith("** "):
                    continue
                status = tracker.get("status", 1)
                if url not in tracker_map:
                    tracker_map[url] = {"torrents": [], "ok": 0, "error": 0, "pending": 0}
                tracker_map[url]["torrents"].append(t_info)
                if status == 2:
                    tracker_map[url]["ok"] += 1
                elif status == 4:
                    tracker_map[url]["error"] += 1
                else:
                    tracker_map[url]["pending"] += 1
        except RuntimeError:
            continue

    return jsonify(tracker_map)


@app.route("/api/torrent/action", methods=["POST"])
def api_torrent_action():
    if not is_logged_in():
        return jsonify({"error": "Not authenticated"}), 401

    body = request.get_json(force=True, silent=True) or {}
    action = body.get("action")
    hashes = body.get("hashes", [])

    if not action:
        return jsonify({"error": "Missing action"}), 400
    if not hashes:
        return jsonify({"error": "No torrents selected"}), 400

    hashes_str = "|".join(hashes)

    action_map = {
        "pause":   "/api/v2/torrents/stop",    # v5+: pause → stop
        "resume":  "/api/v2/torrents/start",   # v5+: resume → start
        "recheck": "/api/v2/torrents/recheck",
        "delete":  "/api/v2/torrents/delete",
    }

    if action not in action_map:
        return jsonify({"error": f"Unknown action: {action}"}), 400

    data = {"hashes": hashes_str}
    if action == "delete":
        data["deleteFiles"] = "true" if body.get("deleteFiles") else "false"

    try:
        qb_request(session, "POST", action_map[action], data=data)
        # Optimistic cache update — UI reload is instant, no need to wait for qBit
        hash_set = set(hashes)
        with _cache._lock:
            if action == "delete":
                _cache._data = [t for t in _cache._data if t.get("hash") not in hash_set]
            elif action == "pause":
                for t in _cache._data:
                    if t.get("hash") in hash_set:
                        t["state"] = "pausedDL" if t.get("state","").endswith("DL") or t.get("state") in ("downloading","metaDL","forcedDL") else "pausedUP"
            elif action == "resume":
                for t in _cache._data:
                    if t.get("hash") in hash_set:
                        t["state"] = "downloading" if t.get("state") == "pausedDL" else "uploading"
            elif action == "recheck":
                for t in _cache._data:
                    if t.get("hash") in hash_set:
                        t["state"] = "checkingResumeData"
        # Schedule a real refresh in background after a short delay
        session_snapshot = {"qb_url": session["qb_url"], "qb_sid": session["qb_sid"]}
        def _delayed_refresh():
            time.sleep(3)
            _cache.invalidate()
            _start_bg_fetch(session_snapshot)
        threading.Thread(target=_delayed_refresh, daemon=True).start()
        return jsonify({"ok": True, "action": action, "count": len(hashes)})
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502


@app.route("/api/tracker/bulk", methods=["POST"])
def api_tracker_bulk():
    if not is_logged_in():
        return jsonify({"error": "Not authenticated"}), 401

    body = request.get_json(force=True, silent=True) or {}
    operation = body.get("operation")
    old_url = (body.get("old_url") or "").strip()
    new_url = (body.get("new_url") or "").strip()

    if operation not in ("replace", "add", "remove"):
        return jsonify({"error": "Invalid operation"}), 400
    if operation in ("replace", "remove") and not old_url:
        return jsonify({"error": "old_url is required"}), 400
    if operation in ("replace", "add") and not new_url:
        return jsonify({"error": "new_url is required"}), 400

    try:
        torrents_resp = qb_request(session, "GET", "/api/v2/torrents/info")
        torrents_list = torrents_resp.json()
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502

    success = 0
    failed = 0
    details = []

    if operation == "add":
        for torrent in torrents_list:
            t_hash = torrent.get("hash", "")
            t_name = torrent.get("name", t_hash)
            try:
                qb_request(session, "POST", "/api/v2/torrents/addTrackers",
                            data={"hash": t_hash, "urls": new_url})
                success += 1
                details.append({"name": t_name, "status": "ok"})
            except RuntimeError as exc:
                failed += 1
                details.append({"name": t_name, "status": "error", "message": str(exc)})

    elif operation in ("replace", "remove"):
        target_torrents = []
        for torrent in torrents_list:
            t_hash = torrent.get("hash", "")
            t_name = torrent.get("name", t_hash)
            try:
                tr_resp = qb_request(session, "GET", f"/api/v2/torrents/trackers?hash={t_hash}")
                if old_url in [t.get("url", "") for t in tr_resp.json()]:
                    target_torrents.append({"hash": t_hash, "name": t_name})
            except RuntimeError:
                continue

        for torrent in target_torrents:
            t_hash = torrent["hash"]
            t_name = torrent["name"]
            try:
                if operation == "replace":
                    qb_request(session, "POST", "/api/v2/torrents/addTrackers",
                                data={"hash": t_hash, "urls": new_url})
                qb_request(session, "POST", "/api/v2/torrents/removeTrackers",
                            data={"hash": t_hash, "urls": old_url})
                success += 1
                details.append({"name": t_name, "status": "ok"})
            except RuntimeError as exc:
                failed += 1
                details.append({"name": t_name, "status": "error", "message": str(exc)})

    return jsonify({"ok": True, "operation": operation,
                    "success": success, "failed": failed, "details": details})


@app.route("/api/tracker/delete-many", methods=["POST"])
def api_tracker_delete_many():
    """
    Remove one or more tracker URLs from every torrent that has them.
    Body: { "urls": ["url1", "url2", ...] }
    Returns: { ok, total_removed, failed, details: [{tracker, torrents_ok, torrents_failed}] }
    """
    if not is_logged_in():
        return jsonify({"error": "Not authenticated"}), 401

    body = request.get_json(force=True, silent=True) or {}
    urls_to_remove = [u.strip() for u in (body.get("urls") or []) if u.strip()]
    if not urls_to_remove:
        return jsonify({"error": "No tracker URLs provided"}), 400

    try:
        torrents_resp = qb_request(session, "GET", "/api/v2/torrents/info")
        torrents_list = torrents_resp.json()
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502

    # Build map: tracker_url -> list of torrent hashes that have it
    url_set = set(urls_to_remove)
    targets: dict[str, list] = {u: [] for u in url_set}

    for torrent in torrents_list:
        t_hash = torrent.get("hash", "")
        t_name = torrent.get("name", t_hash)
        try:
            tr_resp = qb_request(session, "GET", f"/api/v2/torrents/trackers?hash={t_hash}")
            torrent_tracker_urls = {t.get("url", "") for t in tr_resp.json()}
            for u in url_set:
                if u in torrent_tracker_urls:
                    targets[u].append({"hash": t_hash, "name": t_name})
        except RuntimeError:
            continue

    total_removed = 0
    failed = 0
    details = []

    for tracker_url, torrents in targets.items():
        ok_count = 0
        fail_count = 0
        for t in torrents:
            try:
                qb_request(session, "POST", "/api/v2/torrents/removeTrackers",
                           data={"hash": t["hash"], "urls": tracker_url})
                ok_count += 1
                total_removed += 1
            except RuntimeError:
                fail_count += 1
                failed += 1
        details.append({"tracker": tracker_url, "torrents_ok": ok_count, "torrents_failed": fail_count})

    return jsonify({"ok": True, "total_removed": total_removed, "failed": failed, "details": details})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
