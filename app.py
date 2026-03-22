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
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Debug mode (togglable at runtime via the web UI)
# ---------------------------------------------------------------------------
_debug_mode = False

def _set_debug(enabled: bool):
    global _debug_mode
    _debug_mode = enabled
    level = logging.DEBUG if enabled else logging.INFO
    logging.getLogger().setLevel(level)
    log.setLevel(level)

app = Flask(__name__)

APP_VERSION   = "1.15.0"
GITHUB_REPO   = "theOSCARP2/qbittorrent-manager"
_version_cache: dict = {"latest": None, "ts": 0.0}
VERSION_CACHE_TTL = 3600  # 1 heure


def _version_tuple(v: str) -> tuple:
    return tuple(int(x) for x in v.lstrip("v").split("."))


@app.context_processor
def inject_version():
    return {"app_version": APP_VERSION, "github_repo": GITHUB_REPO}


@app.route("/api/version/check")
def api_version_check():
    now = time.monotonic()
    if _version_cache["latest"] and now - _version_cache["ts"] < VERSION_CACHE_TTL:
        latest = _version_cache["latest"]
    else:
        try:
            r = requests.get(
                f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
                headers={"Accept": "application/vnd.github+json"},
                timeout=5,
            )
            latest = r.json().get("tag_name", "").lstrip("v")
            _version_cache["latest"] = latest
            _version_cache["ts"]     = now
        except Exception:
            return jsonify({"error": "unavailable"}), 503

    up_to_date = _version_tuple(APP_VERSION) >= _version_tuple(latest) if latest else True
    return jsonify({
        "current": APP_VERSION,
        "latest":  latest,
        "up_to_date": up_to_date,
    })


def _get_secret_key() -> str:
    # Priorité 1 : variable d'environnement (usage serveur / avancé)
    if key := os.environ.get("SECRET_KEY"):
        return key
    # Priorité 2 : clé persistée dans le dossier utilisateur
    from pathlib import Path
    key_file = Path.home() / ".qbittorrent-manager" / "secret.key"
    key_file.parent.mkdir(exist_ok=True)
    if key_file.exists():
        return key_file.read_text().strip()
    # Premier lancement : génération et sauvegarde
    import secrets
    key = secrets.token_hex(32)
    key_file.write_text(key)
    log.info("Nouvelle clé secrète générée : %s", key_file)
    return key


app.secret_key = _get_secret_key()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_TORRENT_FIELDS = {"hash", "name", "category", "size", "progress", "state",
                   "num_seeds", "num_leechs", "dlspeed", "upspeed",
                   "added_on", "completion_on", "save_path", "ratio", "eta"}

# Columns sortable server-side: DataTables column index → torrent field
_SORT_COLS = {
    1: "name",
    2: "category",
    3: "size",
    5: "state",
    6: "num_seeds",
    7: "num_leechs",
    8: "dlspeed",
    9: "upspeed",
    10: "ratio",
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
        log.debug("qb %s %s → %s (%.2fs)", method, endpoint, resp.status_code, time.monotonic()-t0)
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
    log.debug("Récupération du cache (url=%s)", session_snapshot.get("qb_url"))
    t0 = time.monotonic()
    try:
        resp = qb_request(session_snapshot, "GET", "/api/v2/torrents/info")
        log.debug("Réponse HTTP %s en %.2fs", resp.status_code, time.monotonic() - t0)
        raw = resp.json()
        slim = [{k: t[k] for k in _TORRENT_FIELDS if k in t} for t in raw]
        _cache.set(slim)
        log.info("Cache actualisé — %d torrents (%.1fs)", len(slim), time.monotonic() - t0)
    except Exception as exc:
        log.error("Erreur lors du rafraîchissement du cache : %s", exc)
        _cache.cancel_refresh()


def _start_bg_fetch(session_snapshot: dict):
    """Start a background fetch only if not already running."""
    if _cache.start_refresh():
        log.debug("Démarrage du thread de mise à jour du cache")
        threading.Thread(target=_fetch_and_cache, args=(session_snapshot,), daemon=True).start()
    else:
        log.debug("Mise à jour du cache déjà en cours")


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
                log.info("Connexion : %s @ %s", username or "(anonyme)", qb_url)
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


@app.route("/dashboard")
def dashboard():
    if not is_logged_in():
        return redirect(url_for("login"))
    if not _cache.is_ready():
        _start_bg_fetch({"qb_url": session["qb_url"], "qb_sid": session["qb_sid"]})
    return render_template("dashboard.html")


@app.route("/api/dashboard")
def api_dashboard():
    if not is_logged_in():
        return jsonify({"error": "Not authenticated"}), 401
    session_snapshot = {"qb_url": session["qb_url"], "qb_sid": session["qb_sid"]}
    if _cache.age() > CACHE_TTL:
        _start_bg_fetch(session_snapshot)
    data = _cache.get()
    by_state    = {}
    by_category = {}
    size_by_category = {}
    total_dl = total_up = total_size = 0
    for t in data:
        state = t.get("state", "unknown")
        by_state[state] = by_state.get(state, 0) + 1
        cat = t.get("category") or ""
        by_category[cat]      = by_category.get(cat, 0) + 1
        size_by_category[cat] = size_by_category.get(cat, 0) + t.get("size", 0)
        total_dl   += t.get("dlspeed", 0)
        total_up   += t.get("upspeed", 0)
        total_size += t.get("size", 0)

    # Espace disque libre via qBittorrent
    free_space = None
    try:
        resp = qb_request(session_snapshot, "GET", "/api/v2/sync/maindata")
        main = resp.json()
        free_space = main.get("server_state", {}).get("free_space_on_disk")
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


@app.route("/torrents")
def torrents():
    if not is_logged_in():
        return redirect(url_for("login"))
    # Pre-warm cache if empty (e.g. user arrives directly without fresh login)
    if not _cache.is_ready():
        log.debug("Cache vide, démarrage du préchauffage")
        _start_bg_fetch({"qb_url": session["qb_url"], "qb_sid": session["qb_sid"]})
    return render_template("torrents.html")


@app.route("/trackers")
def trackers():
    if not is_logged_in():
        return redirect(url_for("login"))
    return render_template("trackers.html")


@app.route("/categories")
def categories():
    if not is_logged_in():
        return redirect(url_for("login"))
    return render_template("categories.html")


@app.route("/logs")
def logs():
    if not is_logged_in():
        return redirect(url_for("login"))
    return render_template("logs.html")


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
        log.debug("Cache vide, démarrage de la récupération")
        _start_bg_fetch(session_snapshot)
        draw = int(request.args.get("draw", 1))
        return jsonify({"draw": draw, "recordsTotal": 0, "recordsFiltered": 0,
                        "data": [], "loading": True})

    # Trigger background refresh if stale
    if _cache.age() > CACHE_TTL:
        log.debug("Cache expiré (%.0fs), rafraîchissement en arrière-plan", _cache.age())
        _start_bg_fetch(session_snapshot)

    data = _cache.get()

    # -- DataTables params
    draw   = int(request.args.get("draw", 1))
    start  = int(request.args.get("start", 0))
    length = int(request.args.get("length", 20))
    search = request.args.get("search[value]", "").strip().lower()
    order_col = int(request.args.get("order[0][column]", 1))
    order_dir = request.args.get("order[0][dir]", "asc")

    category_filter = request.args.get("category", "").strip()
    state_filter    = request.args.get("state", "").strip()

    # -- Filter
    filtered = data
    if search:
        filtered = [t for t in filtered if search in t.get("name", "").lower()]
    if category_filter:
        filtered = [t for t in filtered if t.get("category", "") == category_filter]
    if state_filter:
        filtered = [t for t in filtered if t.get("state", "") == state_filter]

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


@app.route("/api/torrents/states")
def api_torrents_states():
    if not is_logged_in():
        return jsonify({"error": "Not authenticated"}), 401
    states = sorted({t.get("state", "") for t in _cache.get() if t.get("state")})
    return jsonify(states)


@app.route("/api/torrents/categories")
def api_torrents_categories():
    if not is_logged_in():
        return jsonify({"error": "Not authenticated"}), 401
    cats = sorted({t.get("category", "") for t in _cache.get() if t.get("category")})
    return jsonify(cats)


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


@app.route("/api/qb/categories")
def api_qb_categories():
    if not is_logged_in():
        return jsonify({"error": "Not authenticated"}), 401
    try:
        resp = qb_request(session, "GET", "/api/v2/torrents/categories")
        return jsonify(sorted(resp.json().keys()))
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502


@app.route("/api/torrent/set-category", methods=["POST"])
def api_torrent_set_category():
    if not is_logged_in():
        return jsonify({"error": "Not authenticated"}), 401
    body  = request.get_json(force=True, silent=True) or {}
    hash_ = body.get("hash", "").strip()
    cat   = body.get("category", "").strip()
    if not hash_:
        return jsonify({"error": "Missing hash"}), 400
    try:
        qb_request(session, "POST", "/api/v2/torrents/setCategory",
                   data={"hashes": hash_, "category": cat})
        with _cache._lock:
            for t in _cache._data:
                if t.get("hash") == hash_:
                    t["category"] = cat
                    break
        return jsonify({"ok": True})
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502


@app.route("/api/torrent/add", methods=["POST"])
def api_torrent_add():
    if not is_logged_in():
        return jsonify({"error": "Not authenticated"}), 401

    savepath = request.form.get("savepath", "").strip()
    category = request.form.get("category", "").strip()
    paused   = request.form.get("paused", "false")

    form_data = {"paused": paused}
    if savepath: form_data["savepath"] = savepath
    if category: form_data["category"] = category

    try:
        if "torrents" in request.files:
            f = request.files["torrents"]
            resp = qb_request(
                session, "POST", "/api/v2/torrents/add",
                files={"torrents": (f.filename, f.read(), "application/x-bittorrent")},
                data=form_data,
            )
        else:
            urls = request.form.get("urls", "").strip()
            if not urls:
                return jsonify({"error": "No URL or file provided"}), 400
            form_data["urls"] = urls
            resp = qb_request(session, "POST", "/api/v2/torrents/add", data=form_data)

        if resp.text.strip() == "Ok.":
            session_snapshot = {"qb_url": session["qb_url"], "qb_sid": session["qb_sid"]}
            _cache.invalidate()
            _start_bg_fetch(session_snapshot)
            return jsonify({"ok": True})
        return jsonify({"error": resp.text.strip()}), 400
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502


@app.route("/api/torrent/trackers")
def api_torrent_trackers():
    if not is_logged_in():
        return jsonify({"error": "Not authenticated"}), 401
    hash_ = request.args.get("hash", "").strip()
    if not hash_:
        return jsonify({"error": "Missing hash"}), 400
    try:
        resp = qb_request(session, "GET", f"/api/v2/torrents/trackers?hash={hash_}")
        trackers = [t for t in resp.json() if not t.get("url", "").startswith("** ")]
        return jsonify(trackers)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502


@app.route("/api/torrent/files")
def api_torrent_files():
    if not is_logged_in():
        return jsonify({"error": "Not authenticated"}), 401
    hash_ = request.args.get("hash", "").strip()
    if not hash_:
        return jsonify({"error": "Missing hash"}), 400
    try:
        resp = qb_request(session, "GET", f"/api/v2/torrents/files?hash={hash_}")
        return jsonify(resp.json())
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502


@app.route("/api/torrent/properties")
def api_torrent_properties():
    if not is_logged_in():
        return jsonify({"error": "Not authenticated"}), 401
    hash_ = request.args.get("hash", "").strip()
    if not hash_:
        return jsonify({"error": "Missing hash"}), 400
    try:
        resp = qb_request(session, "GET", f"/api/v2/torrents/properties?hash={hash_}")
        return jsonify(resp.json())
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502


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


@app.route("/api/debug/status")
def api_debug_status():
    return jsonify({"debug": _debug_mode})


@app.route("/api/debug/toggle", methods=["POST"])
def api_debug_toggle():
    if not is_logged_in():
        return jsonify({"error": "Not authenticated"}), 401
    _set_debug(not _debug_mode)
    log.info("Mode debug %s", "activé" if _debug_mode else "désactivé")
    return jsonify({"debug": _debug_mode})


@app.route("/api/torrent/set-file-priority", methods=["POST"])
def api_torrent_set_file_priority():
    if not is_logged_in():
        return jsonify({"error": "Not authenticated"}), 401
    body     = request.get_json(force=True, silent=True) or {}
    hash_    = body.get("hash", "").strip()
    file_id  = body.get("id")
    priority = body.get("priority")
    if not hash_ or file_id is None or priority is None:
        return jsonify({"error": "Missing parameters"}), 400
    try:
        qb_request(session, "POST", "/api/v2/torrents/filePrio",
                   data={"hash": hash_, "id": str(file_id), "priority": str(priority)})
        log.debug("Priorité fichier %s[%s] → %s", hash_[:8], file_id, priority)
        return jsonify({"ok": True})
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502


@app.route("/api/qb/logs")
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


@app.route("/api/tracker/bulk", methods=["POST"])
def api_tracker_bulk():
    if not is_logged_in():
        return jsonify({"error": "Not authenticated"}), 401

    body = request.get_json(force=True, silent=True) or {}
    operation = body.get("operation")
    old_url = (body.get("old_url") or "").strip()
    new_url = (body.get("new_url") or "").strip()

    if operation not in ("replace", "add", "remove", "copy"):
        return jsonify({"error": "Invalid operation"}), 400
    if operation in ("replace", "remove", "copy") and not old_url:
        return jsonify({"error": "old_url is required"}), 400
    if operation in ("replace", "add", "copy") and not new_url:
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

    elif operation == "copy":
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
# Categories API
# ---------------------------------------------------------------------------

@app.route("/api/categories")
def api_categories():
    """
    Returns all categories with torrent count and total size.
    {
      "CategoryName": { "name": str, "savePath": str, "torrents": int, "size": int }
    }
    """
    if not is_logged_in():
        return jsonify({"error": "Not authenticated"}), 401
    try:
        cats_resp = qb_request(session, "GET", "/api/v2/torrents/categories")
        cats = cats_resp.json()  # { name: { name, savePath } }
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502

    # Fetch live torrent list to get accurate counts (don't rely on cache)
    try:
        torrents_resp = qb_request(session, "GET", "/api/v2/torrents/info",
                                   params={"fields": "hash,category,size"})
        torrents_list = torrents_resp.json()
    except RuntimeError:
        torrents_list = _cache.get()  # fallback to cache if live fetch fails

    stats: dict[str, dict] = {
        name: {"name": name, "savePath": info.get("savePath", ""), "torrents": 0, "size": 0}
        for name, info in cats.items()
    }
    for t in torrents_list:
        cat = t.get("category", "")
        if cat in stats:
            stats[cat]["torrents"] += 1
            stats[cat]["size"] += t.get("size", 0)

    return jsonify(stats)


@app.route("/api/category/torrents")
def api_category_torrents():
    """Returns the live list of torrents for a given category."""
    if not is_logged_in():
        return jsonify({"error": "Not authenticated"}), 401
    cat = request.args.get("name", "")
    try:
        resp = qb_request(session, "GET", "/api/v2/torrents/info",
                          params={"category": cat})
        return jsonify(resp.json())
    except RuntimeError:
        # Fallback to cache
        return jsonify([t for t in _cache.get() if t.get("category", "") == cat])


@app.route("/api/category/create", methods=["POST"])
def api_category_create():
    if not is_logged_in():
        return jsonify({"error": "Not authenticated"}), 401
    body = request.get_json(force=True, silent=True) or {}
    name = (body.get("name") or "").strip()
    save_path = (body.get("save_path") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    try:
        qb_request(session, "POST", "/api/v2/torrents/createCategory",
                   data={"category": name, "savePath": save_path})
        log.info("Catégorie créée : %s", name)
        return jsonify({"ok": True})
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502


@app.route("/api/category/edit", methods=["POST"])
def api_category_edit():
    if not is_logged_in():
        return jsonify({"error": "Not authenticated"}), 401
    body = request.get_json(force=True, silent=True) or {}
    old_name = (body.get("name") or "").strip()
    new_name = (body.get("new_name") or "").strip()
    save_path = (body.get("save_path") or "").strip()
    if not old_name:
        return jsonify({"error": "name is required"}), 400

    try:
        # If renaming: create new, move torrents, delete old
        if new_name and new_name != old_name:
            qb_request(session, "POST", "/api/v2/torrents/createCategory",
                       data={"category": new_name, "savePath": save_path})
            # Move all torrents from old category to new
            torrents_resp = qb_request(session, "GET", "/api/v2/torrents/info",
                                       params={"category": old_name})
            for t in torrents_resp.json():
                qb_request(session, "POST", "/api/v2/torrents/setCategory",
                           data={"hashes": t["hash"], "category": new_name})
            qb_request(session, "POST", "/api/v2/torrents/removeCategories",
                       data={"categories": old_name})
        else:
            # Just update save path
            qb_request(session, "POST", "/api/v2/torrents/editCategory",
                       data={"category": old_name, "savePath": save_path})
        log.info("Catégorie modifiée : %s → %s", old_name, new_name or old_name)
        _cache.invalidate()
        return jsonify({"ok": True})
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502


@app.route("/api/category/delete", methods=["POST"])
def api_category_delete():
    if not is_logged_in():
        return jsonify({"error": "Not authenticated"}), 401
    body = request.get_json(force=True, silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    try:
        qb_request(session, "POST", "/api/v2/torrents/removeCategories",
                   data={"categories": name})
        log.info("Catégorie supprimée : %s", name)
        _cache.invalidate()
        return jsonify({"ok": True})
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502


@app.route("/api/category/move-torrents", methods=["POST"])
def api_category_move_torrents():
    """Move all torrents from src category to dst category (empty = uncategorized)."""
    if not is_logged_in():
        return jsonify({"error": "Not authenticated"}), 401
    body = request.get_json(force=True, silent=True) or {}
    src = (body.get("src") or "").strip()
    dst = (body.get("dst") or "").strip()
    if not src:
        return jsonify({"error": "src is required"}), 400
    try:
        torrents_resp = qb_request(session, "GET", "/api/v2/torrents/info",
                                   params={"category": src})
        torrents = torrents_resp.json()
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502

    success = 0
    failed = 0
    details = []
    for t in torrents:
        try:
            qb_request(session, "POST", "/api/v2/torrents/setCategory",
                       data={"hashes": t["hash"], "category": dst})
            success += 1
            details.append({"name": t.get("name", t["hash"]), "status": "ok"})
        except RuntimeError as exc:
            failed += 1
            details.append({"name": t.get("name", t["hash"]), "status": "error", "message": str(exc)})

    _cache.invalidate()
    log.info("Torrents déplacés de '%s' vers '%s' : %d OK, %d erreurs", src, dst or "(aucune)", success, failed)
    return jsonify({"ok": True, "success": success, "failed": failed, "details": details})


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
