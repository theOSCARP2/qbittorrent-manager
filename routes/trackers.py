import logging
from flask import Blueprint, session, request, jsonify
from core.qb_client import is_logged_in, qb_request
from core.extensions import limiter

bp  = Blueprint("trackers", __name__)
log = logging.getLogger(__name__)


@bp.route("/api/trackers")
def api_trackers():
    if not is_logged_in():
        return jsonify({"error": "Not authenticated"}), 401
    try:
        torrents_list = qb_request(session, "GET", "/api/v2/torrents/info").json()
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502

    tracker_map = {}
    for torrent in torrents_list:
        t_hash = torrent.get("hash", "")
        t_info = {
            "hash":     t_hash,
            "name":     torrent.get("name", t_hash),
            "state":    torrent.get("state", "unknown"),
            "progress": torrent.get("progress", 0),
            "dlspeed":  torrent.get("dlspeed", 0),
            "upspeed":  torrent.get("upspeed", 0),
            "size":     torrent.get("size", 0),
        }
        try:
            for tracker in qb_request(session, "GET", f"/api/v2/torrents/trackers?hash={t_hash}").json():
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


@bp.route("/api/tracker/bulk", methods=["POST"])
@limiter.limit("30 per minute")
def api_tracker_bulk():
    if not is_logged_in():
        return jsonify({"error": "Not authenticated"}), 401

    body      = request.get_json(force=True, silent=True) or {}
    operation = body.get("operation")
    old_url   = (body.get("old_url") or "").strip()
    new_url   = (body.get("new_url") or "").strip()

    if operation not in ("replace", "add", "remove", "copy"):
        return jsonify({"error": "Invalid operation"}), 400
    if operation in ("replace", "remove", "copy") and not old_url:
        return jsonify({"error": "old_url is required"}), 400
    if operation in ("replace", "add", "copy") and not new_url:
        return jsonify({"error": "new_url is required"}), 400

    try:
        torrents_list = qb_request(session, "GET", "/api/v2/torrents/info").json()
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502

    success = 0
    failed  = 0
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
                tr_urls = [t.get("url", "") for t in qb_request(session, "GET", f"/api/v2/torrents/trackers?hash={t_hash}").json()]
                if old_url in tr_urls:
                    target_torrents.append({"hash": t_hash, "name": t_name})
            except RuntimeError:
                continue
        for torrent in target_torrents:
            try:
                qb_request(session, "POST", "/api/v2/torrents/addTrackers",
                           data={"hash": torrent["hash"], "urls": new_url})
                success += 1
                details.append({"name": torrent["name"], "status": "ok"})
            except RuntimeError as exc:
                failed += 1
                details.append({"name": torrent["name"], "status": "error", "message": str(exc)})

    elif operation in ("replace", "remove"):
        target_torrents = []
        for torrent in torrents_list:
            t_hash = torrent.get("hash", "")
            t_name = torrent.get("name", t_hash)
            try:
                tr_urls = [t.get("url", "") for t in qb_request(session, "GET", f"/api/v2/torrents/trackers?hash={t_hash}").json()]
                if old_url in tr_urls:
                    target_torrents.append({"hash": t_hash, "name": t_name})
            except RuntimeError:
                continue
        for torrent in target_torrents:
            try:
                if operation == "replace":
                    qb_request(session, "POST", "/api/v2/torrents/addTrackers",
                               data={"hash": torrent["hash"], "urls": new_url})
                qb_request(session, "POST", "/api/v2/torrents/removeTrackers",
                           data={"hash": torrent["hash"], "urls": old_url})
                success += 1
                details.append({"name": torrent["name"], "status": "ok"})
            except RuntimeError as exc:
                failed += 1
                details.append({"name": torrent["name"], "status": "error", "message": str(exc)})

    return jsonify({"ok": True, "operation": operation,
                    "success": success, "failed": failed, "details": details})


@bp.route("/api/tracker/delete-many", methods=["POST"])
def api_tracker_delete_many():
    if not is_logged_in():
        return jsonify({"error": "Not authenticated"}), 401

    body           = request.get_json(force=True, silent=True) or {}
    urls_to_remove = [u.strip() for u in (body.get("urls") or []) if u.strip()]
    if not urls_to_remove:
        return jsonify({"error": "No tracker URLs provided"}), 400

    try:
        torrents_list = qb_request(session, "GET", "/api/v2/torrents/info").json()
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502

    url_set = set(urls_to_remove)
    targets: dict[str, list] = {u: [] for u in url_set}

    for torrent in torrents_list:
        t_hash = torrent.get("hash", "")
        t_name = torrent.get("name", t_hash)
        try:
            torrent_tracker_urls = {t.get("url", "") for t in qb_request(session, "GET", f"/api/v2/torrents/trackers?hash={t_hash}").json()}
            for u in url_set:
                if u in torrent_tracker_urls:
                    targets[u].append({"hash": t_hash, "name": t_name})
        except RuntimeError:
            continue

    total_removed = 0
    failed        = 0
    details       = []

    for tracker_url, torrents in targets.items():
        ok_count   = 0
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
