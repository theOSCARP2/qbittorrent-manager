import logging

from flask import Blueprint, jsonify, request, session

from core.extensions import limiter, require_auth
from services import trackers as tracker_service

bp = Blueprint("trackers", __name__)
log = logging.getLogger(__name__)


@bp.route("/api/trackers")
@require_auth
def api_trackers():
    try:
        return jsonify(tracker_service.build_tracker_map(session))
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502


@bp.route("/api/tracker/bulk", methods=["POST"])
@require_auth
@limiter.limit("30 per minute")
def api_tracker_bulk():
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
        return jsonify(tracker_service.bulk_operation(session, operation, old_url, new_url))
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502


@bp.route("/api/tracker/delete-many", methods=["POST"])
@require_auth
def api_tracker_delete_many():
    body = request.get_json(force=True, silent=True) or {}
    urls = [u.strip() for u in (body.get("urls") or []) if u.strip()]
    if not urls:
        return jsonify({"error": "No tracker URLs provided"}), 400
    try:
        return jsonify(tracker_service.delete_many(session, urls))
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502
