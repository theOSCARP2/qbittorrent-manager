import logging

from core.qb_client import qb_request

log = logging.getLogger(__name__)


def build_tracker_map(session) -> dict:
    torrents_list = qb_request(session, "GET", "/api/v2/torrents/info").json()
    tracker_map: dict = {}
    for torrent in torrents_list:
        t_hash = torrent.get("hash", "")
        t_info = {
            "hash": t_hash,
            "name": torrent.get("name", t_hash),
            "state": torrent.get("state", "unknown"),
            "progress": torrent.get("progress", 0),
            "dlspeed": torrent.get("dlspeed", 0),
            "upspeed": torrent.get("upspeed", 0),
            "size": torrent.get("size", 0),
        }
        try:
            for tracker in qb_request(
                session, "GET", f"/api/v2/torrents/trackers?hash={t_hash}"
            ).json():
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
    return tracker_map


def bulk_operation(session, operation: str, old_url: str, new_url: str) -> dict:
    torrents_list = qb_request(session, "GET", "/api/v2/torrents/info").json()
    success = 0
    failed = 0
    details = []

    if operation == "add":
        for torrent in torrents_list:
            t_hash = torrent.get("hash", "")
            t_name = torrent.get("name", t_hash)
            try:
                qb_request(
                    session,
                    "POST",
                    "/api/v2/torrents/addTrackers",
                    data={"hash": t_hash, "urls": new_url},
                )
                success += 1
                details.append({"name": t_name, "status": "ok"})
            except RuntimeError as exc:
                failed += 1
                details.append({"name": t_name, "status": "error", "message": str(exc)})

    elif operation == "copy":
        target_torrents = _find_torrents_with_tracker(session, torrents_list, old_url)
        for torrent in target_torrents:
            try:
                qb_request(
                    session,
                    "POST",
                    "/api/v2/torrents/addTrackers",
                    data={"hash": torrent["hash"], "urls": new_url},
                )
                success += 1
                details.append({"name": torrent["name"], "status": "ok"})
            except RuntimeError as exc:
                failed += 1
                details.append({"name": torrent["name"], "status": "error", "message": str(exc)})

    elif operation in ("replace", "remove"):
        target_torrents = _find_torrents_with_tracker(session, torrents_list, old_url)
        for torrent in target_torrents:
            try:
                if operation == "replace":
                    qb_request(
                        session,
                        "POST",
                        "/api/v2/torrents/addTrackers",
                        data={"hash": torrent["hash"], "urls": new_url},
                    )
                qb_request(
                    session,
                    "POST",
                    "/api/v2/torrents/removeTrackers",
                    data={"hash": torrent["hash"], "urls": old_url},
                )
                success += 1
                details.append({"name": torrent["name"], "status": "ok"})
            except RuntimeError as exc:
                failed += 1
                details.append({"name": torrent["name"], "status": "error", "message": str(exc)})

    return {"ok": True, "operation": operation, "success": success, "failed": failed, "details": details}


def delete_many(session, urls: list[str]) -> dict:
    torrents_list = qb_request(session, "GET", "/api/v2/torrents/info").json()
    url_set = set(urls)
    targets: dict[str, list] = {u: [] for u in url_set}

    for torrent in torrents_list:
        t_hash = torrent.get("hash", "")
        t_name = torrent.get("name", t_hash)
        try:
            torrent_tracker_urls = {
                t.get("url", "")
                for t in qb_request(
                    session, "GET", f"/api/v2/torrents/trackers?hash={t_hash}"
                ).json()
            }
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
                qb_request(
                    session,
                    "POST",
                    "/api/v2/torrents/removeTrackers",
                    data={"hash": t["hash"], "urls": tracker_url},
                )
                ok_count += 1
                total_removed += 1
            except RuntimeError:
                fail_count += 1
                failed += 1
        details.append(
            {"tracker": tracker_url, "torrents_ok": ok_count, "torrents_failed": fail_count}
        )

    return {"ok": True, "total_removed": total_removed, "failed": failed, "details": details}


def _find_torrents_with_tracker(session, torrents_list: list, tracker_url: str) -> list:
    result = []
    for torrent in torrents_list:
        t_hash = torrent.get("hash", "")
        t_name = torrent.get("name", t_hash)
        try:
            tr_urls = [
                t.get("url", "")
                for t in qb_request(
                    session, "GET", f"/api/v2/torrents/trackers?hash={t_hash}"
                ).json()
            ]
            if tracker_url in tr_urls:
                result.append({"hash": t_hash, "name": t_name})
        except RuntimeError:
            continue
    return result
