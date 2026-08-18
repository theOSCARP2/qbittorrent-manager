import io
import logging
import os
import shutil
import tempfile
import threading
import time

from flask import Blueprint, jsonify, request, send_file, session

from core.cache import _cache, _start_bg_fetch
from core.config import CACHE_TTL
from core.extensions import require_auth
from core.qb_client import qb_request
from core.qb_client import session_snapshot as _session_snapshot
from core.validators import safe_path, valid_hash, valid_hashes
from services import torrents as torrent_service

bp = Blueprint("torrents", __name__)
log = logging.getLogger(__name__)


@bp.route("/api/torrents/status")
@require_auth
def api_torrents_status():
    return jsonify({"ready": _cache.is_ready(), "total": len(_cache.get())})


@bp.route("/api/torrents")
@require_auth
def api_torrents():
    session_snapshot = _session_snapshot()

    if not _cache.is_ready():
        log.debug("Cache vide, démarrage de la récupération")
        _start_bg_fetch(session_snapshot)
        draw = int(request.args.get("draw", 1))
        return jsonify(
            {"draw": draw, "recordsTotal": 0, "recordsFiltered": 0, "data": [], "loading": True}
        )

    if _cache.age() > CACHE_TTL:
        log.debug("Cache expiré (%.0fs), rafraîchissement en arrière-plan", _cache.age())
        _start_bg_fetch(session_snapshot)

    data = _cache.get()
    draw = int(request.args.get("draw", 1))
    start = int(request.args.get("start", 0))
    length = int(request.args.get("length", 20))

    filtered = torrent_service.filter_and_sort(
        data,
        search=request.args.get("search[value]", "").strip().lower(),
        category=request.args.get("category", "").strip(),
        state=request.args.get("state", "").strip(),
        order_col=int(request.args.get("order[0][column]", 1)),
        order_dir=request.args.get("order[0][dir]", "asc"),
    )

    return jsonify(
        {
            "draw": draw,
            "recordsTotal": len(data),
            "recordsFiltered": len(filtered),
            "data": filtered[start : start + length],
        }
    )


@bp.route("/api/torrents/states")
@require_auth
def api_torrents_states():
    states = sorted({t.get("state", "") for t in _cache.get() if t.get("state")})
    return jsonify(states)


@bp.route("/api/torrents/categories")
@require_auth
def api_torrents_categories():
    cats = sorted({t.get("category", "") for t in _cache.get() if t.get("category")})
    return jsonify(cats)


@bp.route("/api/qb/categories")
@require_auth
def api_qb_categories():
    try:
        resp = qb_request(session, "GET", "/api/v2/torrents/categories")
        return jsonify(sorted(resp.json().keys()))
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502


@bp.route("/api/torrent/set-category", methods=["POST"])
@require_auth
def api_torrent_set_category():
    body = request.get_json(force=True, silent=True) or {}
    hash_ = body.get("hash", "").strip()
    cat = body.get("category", "").strip()
    if not valid_hash(hash_):
        return jsonify({"error": "Invalid hash"}), 400
    try:
        qb_request(
            session, "POST", "/api/v2/torrents/setCategory", data={"hashes": hash_, "category": cat}
        )
        _cache.update_torrent(hash_, category=cat)
        return jsonify({"ok": True})
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502


@bp.route("/api/torrent/add", methods=["POST"])
@require_auth
def api_torrent_add():
    savepath = request.form.get("savepath", "").strip()
    category = request.form.get("category", "").strip()
    paused = request.form.get("paused", "false")
    form_data = {"paused": paused}
    if savepath:
        form_data["savepath"] = savepath
    if category:
        form_data["category"] = category

    try:
        if "torrents" in request.files:
            f = request.files["torrents"]
            resp = qb_request(
                session,
                "POST",
                "/api/v2/torrents/add",
                files={"torrents": (f.filename, f.read(), "application/x-bittorrent")},
                data=form_data,
            )
        else:
            urls = request.form.get("urls", "").strip()
            if not urls:
                return jsonify({"error": "No URL or file provided"}), 400
            form_data["urls"] = urls
            resp = qb_request(session, "POST", "/api/v2/torrents/add", data=form_data)

        body = resp.text.strip()
        try:
            data = resp.json()
            failures = data.get("failures", [])
            if data.get("added_torrent_ids") or not failures:
                _cache.invalidate()
                _start_bg_fetch(_session_snapshot())
                return jsonify({"ok": True})
            return jsonify({"error": "; ".join(str(f) for f in failures)}), 400
        except Exception:
            if body in ("Ok.", "Ok"):
                _cache.invalidate()
                _start_bg_fetch(_session_snapshot())
                return jsonify({"ok": True})
            return jsonify({"error": body}), 400
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502


@bp.route("/api/torrent/create", methods=["POST"])
@require_auth
def api_torrent_create():
    try:
        import torf
    except ImportError:
        return (
            jsonify({"error": "La librairie 'torf' n'est pas installée (pip install torf)."}),
            500,
        )

    is_upload = "multipart/form-data" in (request.content_type or "")
    tmpdir = None

    try:
        if is_upload:
            files = request.files.getlist("files[]")
            rel_paths = request.form.getlist("rel_paths[]")
            name = (request.form.get("name") or "").strip()
            trackers = [
                t.strip() for t in (request.form.get("trackers") or "").splitlines() if t.strip()
            ]
            piece_size = int(request.form.get("piece_size") or 0)
            private = request.form.get("private") == "true"
            comment = (request.form.get("comment") or "").strip()
            source = (request.form.get("source") or "").strip()
            add_to_qb = request.form.get("add_to_qb") == "true"

            if not files:
                return jsonify({"error": "Aucun fichier reçu."}), 400

            tmpdir = tempfile.mkdtemp(prefix="qbm-create-")
            for f, rel in zip(files, rel_paths or [f.filename for f in files], strict=False):
                dest = os.path.join(tmpdir, rel.replace("/", os.sep).replace("\\", os.sep))
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                f.save(dest)

            top = os.listdir(tmpdir)
            torrent_input = os.path.join(tmpdir, top[0]) if len(top) == 1 else tmpdir

        else:
            body = request.get_json(force=True) or {}
            path_str = (body.get("path") or "").strip()
            name = (body.get("name") or "").strip()
            trackers = [t.strip() for t in (body.get("trackers") or "").splitlines() if t.strip()]
            piece_size = int(body.get("piece_size") or 0)
            private = bool(body.get("private", False))
            comment = (body.get("comment") or "").strip()
            source = (body.get("source") or "").strip()
            add_to_qb = bool(body.get("add_to_qb", True))

            if not path_str:
                return jsonify({"error": "Veuillez saisir un chemin."}), 400
            if not safe_path(path_str):
                return jsonify({"error": "Chemin invalide."}), 400
            if not os.path.exists(path_str):
                return jsonify({"error": f"Chemin introuvable : {path_str}"}), 400
            torrent_input = path_str

        t = torf.Torrent(path=torrent_input)
        if name:
            t.name = name
        if trackers:
            t.trackers = [[tr] for tr in trackers]
        if piece_size:
            t.piece_size = piece_size
        t.private = private
        if comment:
            t.comment = comment
        if source:
            t.source = source

        t.generate(threads=2)

        torrent_name = t.name or "torrent"
        with tempfile.NamedTemporaryFile(suffix=".torrent", delete=False) as tmp_f:
            tmp_path = tmp_f.name
        t.write(tmp_path, overwrite=True)

        with open(tmp_path, "rb") as fh:
            torrent_bytes = fh.read()
        os.unlink(tmp_path)

        if add_to_qb:
            qb_request(
                session,
                "POST",
                "/api/v2/torrents/add",
                files={
                    "torrents": (
                        f"{torrent_name}.torrent",
                        torrent_bytes,
                        "application/x-bittorrent",
                    )
                },
            )
            _cache.invalidate()
            _start_bg_fetch(_session_snapshot())
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
@require_auth
def api_torrent_trackers():
    hash_ = request.args.get("hash", "").strip()
    if not valid_hash(hash_):
        return jsonify({"error": "Invalid hash"}), 400
    try:
        resp = qb_request(session, "GET", f"/api/v2/torrents/trackers?hash={hash_}")
        trackers = [t for t in resp.json() if not t.get("url", "").startswith("** ")]
        return jsonify(trackers)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502


@bp.route("/api/torrent/files")
@require_auth
def api_torrent_files():
    hash_ = request.args.get("hash", "").strip()
    if not valid_hash(hash_):
        return jsonify({"error": "Invalid hash"}), 400
    try:
        resp = qb_request(session, "GET", f"/api/v2/torrents/files?hash={hash_}")
        return jsonify(resp.json())
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502


@bp.route("/api/torrent/properties")
@require_auth
def api_torrent_properties():
    hash_ = request.args.get("hash", "").strip()
    if not valid_hash(hash_):
        return jsonify({"error": "Invalid hash"}), 400
    try:
        resp = qb_request(session, "GET", f"/api/v2/torrents/properties?hash={hash_}")
        return jsonify(resp.json())
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502


@bp.route("/api/torrent/action", methods=["POST"])
@require_auth
def api_torrent_action():
    body = request.get_json(force=True, silent=True) or {}
    action = body.get("action")
    hashes = body.get("hashes", [])

    if not action:
        return jsonify({"error": "Missing action"}), 400
    if not valid_hashes(hashes):
        return jsonify({"error": "Invalid or missing hashes"}), 400

    action_map = {
        "pause": "/api/v2/torrents/stop",
        "resume": "/api/v2/torrents/start",
        "recheck": "/api/v2/torrents/recheck",
        "delete": "/api/v2/torrents/delete",
    }
    if action not in action_map:
        return jsonify({"error": f"Unknown action: {action}"}), 400

    data = {"hashes": "|".join(hashes)}
    if action == "delete":
        data["deleteFiles"] = "true" if body.get("deleteFiles") else "false"

    try:
        qb_request(session, "POST", action_map[action], data=data)
        hash_set = set(hashes)
        if action == "delete":
            _cache.remove_torrents(hash_set)
        else:
            _cache.apply_state_change(hash_set, action)

        session_snapshot = _session_snapshot()

        def _delayed_refresh():
            time.sleep(3)
            _cache.invalidate()
            _start_bg_fetch(session_snapshot)

        threading.Thread(target=_delayed_refresh, daemon=True).start()
        return jsonify({"ok": True, "action": action, "count": len(hashes)})
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502


@bp.route("/api/torrent/set-file-priority", methods=["POST"])
@require_auth
def api_torrent_set_file_priority():
    body = request.get_json(force=True, silent=True) or {}
    hash_ = body.get("hash", "").strip()
    file_id = body.get("id")
    priority = body.get("priority")
    if not hash_ or file_id is None or priority is None:
        return jsonify({"error": "Missing parameters"}), 400
    try:
        qb_request(
            session,
            "POST",
            "/api/v2/torrents/filePrio",
            data={"hash": hash_, "id": str(file_id), "priority": str(priority)},
        )
        log.debug("Priorité fichier %s[%s] → %s", hash_[:8], file_id, priority)
        return jsonify({"ok": True})
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502


@bp.route("/api/torrent/set-location", methods=["POST"])
@require_auth
def api_torrent_set_location():
    body = request.get_json(force=True, silent=True) or {}
    hash_ = body.get("hash", "").strip()
    location = body.get("location", "").strip()
    if not valid_hash(hash_):
        return jsonify({"error": "Invalid hash"}), 400
    if not location or not safe_path(location):
        return jsonify({"error": "Invalid location"}), 400
    try:
        qb_request(
            session,
            "POST",
            "/api/v2/torrents/setLocation",
            data={"hashes": hash_, "location": location},
        )
        _cache.update_torrent(hash_, save_path=location)
        log.info("Répertoire torrent %s → %s", hash_[:8], location)
        return jsonify({"ok": True})
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502


@bp.route("/api/torrent/set-speed-limit", methods=["POST"])
@require_auth
def api_torrent_set_speed_limit():
    body = request.get_json(force=True, silent=True) or {}
    hash_ = body.get("hash", "").strip()
    dl = body.get("dl_limit")
    up = body.get("up_limit")
    if not valid_hash(hash_):
        return jsonify({"error": "Invalid hash"}), 400
    if dl is None and up is None:
        return jsonify({"error": "Missing dl_limit or up_limit"}), 400
    try:
        if dl is not None:
            qb_request(
                session,
                "POST",
                "/api/v2/torrents/setDownloadLimit",
                data={"hashes": hash_, "limit": str(int(dl))},
            )
        if up is not None:
            qb_request(
                session,
                "POST",
                "/api/v2/torrents/setUploadLimit",
                data={"hashes": hash_, "limit": str(int(up))},
            )
        log.info("Limites vitesse %s → DL=%s UP=%s", hash_[:8], dl, up)
        return jsonify({"ok": True})
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502
