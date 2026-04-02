import logging
from flask import Blueprint, session, request, jsonify
from core.qb_client import is_logged_in, qb_request
from core.cache import _cache

bp  = Blueprint("categories", __name__)
log = logging.getLogger(__name__)


@bp.route("/api/categories")
def api_categories():
    if not is_logged_in():
        return jsonify({"error": "Not authenticated"}), 401
    try:
        cats = qb_request(session, "GET", "/api/v2/torrents/categories").json()
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502

    try:
        torrents_list = qb_request(session, "GET", "/api/v2/torrents/info",
                                   params={"fields": "hash,category,size"}).json()
    except RuntimeError:
        torrents_list = _cache.get()

    stats: dict[str, dict] = {
        name: {"name": name, "savePath": info.get("savePath", ""), "torrents": 0, "size": 0}
        for name, info in cats.items()
    }
    for t in torrents_list:
        cat = t.get("category", "")
        if cat in stats:
            stats[cat]["torrents"] += 1
            stats[cat]["size"]     += t.get("size", 0)

    return jsonify(stats)


@bp.route("/api/category/torrents")
def api_category_torrents():
    if not is_logged_in():
        return jsonify({"error": "Not authenticated"}), 401
    cat = request.args.get("name", "")
    try:
        resp = qb_request(session, "GET", "/api/v2/torrents/info", params={"category": cat})
        return jsonify(resp.json())
    except RuntimeError:
        return jsonify([t for t in _cache.get() if t.get("category", "") == cat])


@bp.route("/api/category/create", methods=["POST"])
def api_category_create():
    if not is_logged_in():
        return jsonify({"error": "Not authenticated"}), 401
    body      = request.get_json(force=True, silent=True) or {}
    name      = (body.get("name") or "").strip()
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


@bp.route("/api/category/edit", methods=["POST"])
def api_category_edit():
    if not is_logged_in():
        return jsonify({"error": "Not authenticated"}), 401
    body      = request.get_json(force=True, silent=True) or {}
    old_name  = (body.get("name") or "").strip()
    new_name  = (body.get("new_name") or "").strip()
    save_path = (body.get("save_path") or "").strip()
    if not old_name:
        return jsonify({"error": "name is required"}), 400
    try:
        if new_name and new_name != old_name:
            qb_request(session, "POST", "/api/v2/torrents/createCategory",
                       data={"category": new_name, "savePath": save_path})
            for t in qb_request(session, "GET", "/api/v2/torrents/info",
                                params={"category": old_name}).json():
                qb_request(session, "POST", "/api/v2/torrents/setCategory",
                           data={"hashes": t["hash"], "category": new_name})
            qb_request(session, "POST", "/api/v2/torrents/removeCategories",
                       data={"categories": old_name})
        else:
            qb_request(session, "POST", "/api/v2/torrents/editCategory",
                       data={"category": old_name, "savePath": save_path})
        log.info("Catégorie modifiée : %s → %s", old_name, new_name or old_name)
        _cache.invalidate()
        return jsonify({"ok": True})
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502


@bp.route("/api/category/delete", methods=["POST"])
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


@bp.route("/api/category/move-torrents", methods=["POST"])
def api_category_move_torrents():
    if not is_logged_in():
        return jsonify({"error": "Not authenticated"}), 401
    body = request.get_json(force=True, silent=True) or {}
    src  = (body.get("src") or "").strip()
    dst  = (body.get("dst") or "").strip()
    if not src:
        return jsonify({"error": "src is required"}), 400
    try:
        torrents = qb_request(session, "GET", "/api/v2/torrents/info",
                              params={"category": src}).json()
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502

    success = 0
    failed  = 0
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
