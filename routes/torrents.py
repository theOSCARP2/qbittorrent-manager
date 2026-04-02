import os
import io
import time
import shutil
import logging
import tempfile
import threading
from flask import Blueprint, session, request, jsonify, send_file
from core.qb_client import is_logged_in, qb_request
from core.cache import _cache, _start_bg_fetch, CACHE_TTL
from core.config import _SORT_COLS

bp  = Blueprint("torrents", __name__)
log = logging.getLogger(__name__)


@bp.route("/api/torrents/status")
def api_torrents_status():
    if not is_logged_in():
        return jsonify({"error": "Not authenticated"}), 401
    return jsonify({"ready": _cache.is_ready(), "total": len(_cache.get())})


@bp.route("/api/torrents")
def api_torrents():
    if not is_logged_in():
        return jsonify({"error": "Not authenticated"}), 401

    session_snapshot = {"qb_url": session["qb_url"], "qb_sid": session["qb_sid"]}

    if not _cache.is_ready():
        log.debug("Cache vide, démarrage de la récupération")
        _start_bg_fetch(session_snapshot)
        draw = int(request.args.get("draw", 1))
        return jsonify({"draw": draw, "recordsTotal": 0, "recordsFiltered": 0,
                        "data": [], "loading": True})

    if _cache.age() > CACHE_TTL:
        log.debug("Cache expiré (%.0fs), rafraîchissement en arrière-plan", _cache.age())
        _start_bg_fetch(session_snapshot)

    data = _cache.get()

    draw            = int(request.args.get("draw", 1))
    start           = int(request.args.get("start", 0))
    length          = int(request.args.get("length", 20))
    search          = request.args.get("search[value]", "").strip().lower()
    order_col       = int(request.args.get("order[0][column]", 1))
    order_dir       = request.args.get("order[0][dir]", "asc")
    category_filter = request.args.get("category", "").strip()
    state_filter    = request.args.get("state", "").strip()

    filtered = data
    if search:
        filtered = [t for t in filtered if search in t.get("name", "").lower()]
    if category_filter:
        filtered = [t for t in filtered if t.get("category", "") == category_filter]
    if state_filter:
        filtered = [t for t in filtered if t.get("state", "") == state_filter]

    sort_key = _SORT_COLS.get(order_col, "name")
    reverse  = order_dir == "desc"
    if sort_key == "name":
        filtered = sorted(filtered, key=lambda t: t.get("name", "").lower(), reverse=reverse)
    else:
        filtered = sorted(filtered, key=lambda t: t.get(sort_key) or 0, reverse=reverse)

    page = filtered[start: start + length]
    return jsonify({
        "draw":            draw,
        "recordsTotal":    len(data),
        "recordsFiltered": len(filtered),
        "data":            page,
    })


@bp.route("/api/torrents/states")
def api_torrents_states():
    if not is_logged_in():
        return jsonify({"error": "Not authenticated"}), 401
    states = sorted({t.get("state", "") for t in _cache.get() if t.get("state")})
    return jsonify(states)


@bp.route("/api/torrents/categories")
def api_torrents_categories():
    if not is_logged_in():
        return jsonify({"error": "Not authenticated"}), 401
    cats = sorted({t.get("category", "") for t in _cache.get() if t.get("category")})
    return jsonify(cats)


@bp.route("/api/qb/categories")
def api_qb_categories():
    if not is_logged_in():
        return jsonify({"error": "Not authenticated"}), 401
    try:
        resp = qb_request(session, "GET", "/api/v2/torrents/categories")
        return jsonify(sorted(resp.json().keys()))
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502


@bp.route("/api/torrent/set-category", methods=["POST"])
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


@bp.route("/api/torrent/add", methods=["POST"])
def api_torrent_add():
    if not is_logged_in():
        return jsonify({"error": "Not authenticated"}), 401

    savepath  = request.form.get("savepath", "").strip()
    category  = request.form.get("category", "").strip()
    paused    = request.form.get("paused", "false")
    form_data = {"paused": paused}
    if savepath: form_data["savepath"] = savepath
    if category: form_data["category"] = category

    try:
        if "torrents" in request.files:
            f    = request.files["torrents"]
            resp = qb_request(session, "POST", "/api/v2/torrents/add",
                              files={"torrents": (f.filename, f.read(), "application/x-bittorrent")},
                              data=form_data)
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


@bp.route("/api/torrent/create", methods=["POST"])
def api_torrent_create():
    if not is_logged_in():
        return jsonify({"error": "Not authenticated"}), 401
    try:
        import torf
    except ImportError:
        return jsonify({"error": "La librairie 'torf' n'est pas installée (pip install torf)."}), 500

    is_upload = "multipart/form-data" in (request.content_type or "")
    tmpdir    = None

    try:
        if is_upload:
            files      = request.files.getlist("files[]")
            rel_paths  = request.form.getlist("rel_paths[]")
            name       = (request.form.get("name") or "").strip()
            trackers   = [t.strip() for t in (request.form.get("trackers") or "").splitlines() if t.strip()]
            piece_size = int(request.form.get("piece_size") or 0)
            private    = request.form.get("private") == "true"
            comment    = (request.form.get("comment") or "").strip()
            source     = (request.form.get("source") or "").strip()
            add_to_qb  = request.form.get("add_to_qb") == "true"

            if not files:
                return jsonify({"error": "Aucun fichier reçu."}), 400

            tmpdir = tempfile.mkdtemp(prefix="qbm-create-")
            for f, rel in zip(files, rel_paths or [f.filename for f in files]):
                dest = os.path.join(tmpdir, rel.replace("/", os.sep).replace("\\", os.sep))
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                f.save(dest)

            top           = os.listdir(tmpdir)
            torrent_input = os.path.join(tmpdir, top[0]) if len(top) == 1 else tmpdir

        else:
            body       = request.get_json(force=True) or {}
            path_str   = (body.get("path") or "").strip()
            name       = (body.get("name") or "").strip()
            trackers   = [t.strip() for t in (body.get("trackers") or "").splitlines() if t.strip()]
            piece_size = int(body.get("piece_size") or 0)
            private    = bool(body.get("private", False))
            comment    = (body.get("comment") or "").strip()
            source     = (body.get("source") or "").strip()
            add_to_qb  = bool(body.get("add_to_qb", True))

            if not path_str:
                return jsonify({"error": "Veuillez saisir un chemin."}), 400
            if not os.path.exists(path_str):
                return jsonify({"error": f"Chemin introuvable : {path_str}"}), 400
            torrent_input = path_str

        t = torf.Torrent(path=torrent_input)
        if name:       t.name       = name
        if trackers:   t.trackers   = [[tr] for tr in trackers]
        if piece_size: t.piece_size = piece_size
        t.private = private
        if comment:    t.comment    = comment
        if source:     t.source     = source

        t.generate(threads=2)

        torrent_name = t.name or "torrent"
        tmp_f        = tempfile.NamedTemporaryFile(suffix=".torrent", delete=False)
        tmp_f.close()
        t.write(tmp_f.name, overwrite=True)

        with open(tmp_f.name, "rb") as fh:
            torrent_bytes = fh.read()
        os.unlink(tmp_f.name)

        if add_to_qb:
            qb_request(session, "POST", "/api/v2/torrents/add",
                       files={"torrents": (f"{torrent_name}.torrent",
                                           torrent_bytes,
                                           "application/x-bittorrent")})
            _cache.invalidate()
            _start_bg_fetch({"qb_url": session["qb_url"], "qb_sid": session["qb_sid"]})
            log.info("Torrent créé et ajouté à qBittorrent : %s", torrent_name)

        return send_file(
            io.BytesIO(torrent_bytes),
            as_attachment=True,
            download_name=f"{torrent_name}.torrent",
            mimetype="application/x-bittorrent",
        )
    except Exception as exc:
        log.error("Erreur création torrent : %s", exc)
        return jsonify({"error": str(exc)}), 500
    finally:
        if tmpdir:
            shutil.rmtree(tmpdir, ignore_errors=True)


@bp.route("/api/torrent/trackers")
def api_torrent_trackers():
    if not is_logged_in():
        return jsonify({"error": "Not authenticated"}), 401
    hash_ = request.args.get("hash", "").strip()
    if not hash_:
        return jsonify({"error": "Missing hash"}), 400
    try:
        resp     = qb_request(session, "GET", f"/api/v2/torrents/trackers?hash={hash_}")
        trackers = [t for t in resp.json() if not t.get("url", "").startswith("** ")]
        return jsonify(trackers)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502


@bp.route("/api/torrent/files")
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


@bp.route("/api/torrent/properties")
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


@bp.route("/api/torrent/action", methods=["POST"])
def api_torrent_action():
    if not is_logged_in():
        return jsonify({"error": "Not authenticated"}), 401

    body   = request.get_json(force=True, silent=True) or {}
    action = body.get("action")
    hashes = body.get("hashes", [])

    if not action:
        return jsonify({"error": "Missing action"}), 400
    if not hashes:
        return jsonify({"error": "No torrents selected"}), 400

    hashes_str = "|".join(hashes)
    action_map = {
        "pause":   "/api/v2/torrents/stop",
        "resume":  "/api/v2/torrents/start",
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
        hash_set = set(hashes)
        with _cache._lock:
            if action == "delete":
                _cache._data = [t for t in _cache._data if t.get("hash") not in hash_set]
            elif action == "pause":
                for t in _cache._data:
                    if t.get("hash") in hash_set:
                        t["state"] = "pausedDL" if t.get("state", "").endswith("DL") or t.get("state") in ("downloading", "metaDL", "forcedDL") else "pausedUP"
            elif action == "resume":
                for t in _cache._data:
                    if t.get("hash") in hash_set:
                        t["state"] = "downloading" if t.get("state") == "pausedDL" else "uploading"
            elif action == "recheck":
                for t in _cache._data:
                    if t.get("hash") in hash_set:
                        t["state"] = "checkingResumeData"

        session_snapshot = {"qb_url": session["qb_url"], "qb_sid": session["qb_sid"]}

        def _delayed_refresh():
            time.sleep(3)
            _cache.invalidate()
            _start_bg_fetch(session_snapshot)

        threading.Thread(target=_delayed_refresh, daemon=True).start()
        return jsonify({"ok": True, "action": action, "count": len(hashes)})
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502


@bp.route("/api/torrent/set-file-priority", methods=["POST"])
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
