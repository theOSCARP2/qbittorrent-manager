import logging

from flask import Blueprint, jsonify, request, session

from core.cache import _cache
from core.extensions import require_auth
from core.qb_client import qb_request
from services import categories as category_service

bp = Blueprint("categories", __name__)
log = logging.getLogger(__name__)


@bp.route("/api/categories")
@require_auth
def api_categories():
    try:
        return jsonify(category_service.get_stats(session))
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502


@bp.route("/api/category/torrents")
@require_auth
def api_category_torrents():
    cat = request.args.get("name", "")
    try:
        resp = qb_request(session, "GET", "/api/v2/torrents/info", params={"category": cat})
        return jsonify(resp.json())
    except RuntimeError:
        return jsonify([t for t in _cache.get() if t.get("category", "") == cat])


@bp.route("/api/category/create", methods=["POST"])
@require_auth
def api_category_create():
    body = request.get_json(force=True, silent=True) or {}
    name = (body.get("name") or "").strip()
    save_path = (body.get("save_path") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    try:
        category_service.create(session, name, save_path)
        return jsonify({"ok": True})
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502


@bp.route("/api/category/edit", methods=["POST"])
@require_auth
def api_category_edit():
    body = request.get_json(force=True, silent=True) or {}
    old_name = (body.get("name") or "").strip()
    new_name = (body.get("new_name") or "").strip()
    save_path = (body.get("save_path") or "").strip()
    if not old_name:
        return jsonify({"error": "name is required"}), 400
    try:
        category_service.edit(session, old_name, new_name, save_path)
        _cache.invalidate()
        return jsonify({"ok": True})
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502


@bp.route("/api/category/delete", methods=["POST"])
@require_auth
def api_category_delete():
    body = request.get_json(force=True, silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    try:
        category_service.delete(session, name)
        _cache.invalidate()
        return jsonify({"ok": True})
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502


@bp.route("/api/category/move-torrents", methods=["POST"])
@require_auth
def api_category_move_torrents():
    body = request.get_json(force=True, silent=True) or {}
    src = (body.get("src") or "").strip()
    dst = (body.get("dst") or "").strip()
    if not src:
        return jsonify({"error": "src is required"}), 400
    try:
        result = category_service.move_torrents(session, src, dst)
        _cache.invalidate()
        return jsonify(result)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502
