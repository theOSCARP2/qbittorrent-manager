import logging

from core.cache import _cache
from core.qb_client import qb_request

log = logging.getLogger(__name__)


def get_stats(session) -> dict:
    cats = qb_request(session, "GET", "/api/v2/torrents/categories").json()
    try:
        torrents_list = qb_request(
            session, "GET", "/api/v2/torrents/info", params={"fields": "hash,category,size"}
        ).json()
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
            stats[cat]["size"] += t.get("size", 0)
    return stats


def create(session, name: str, save_path: str = "") -> None:
    qb_request(
        session,
        "POST",
        "/api/v2/torrents/createCategory",
        data={"category": name, "savePath": save_path},
    )
    log.info("Catégorie créée : %s", name)


def edit(session, old_name: str, new_name: str = "", save_path: str = "") -> None:
    if new_name and new_name != old_name:
        qb_request(
            session,
            "POST",
            "/api/v2/torrents/createCategory",
            data={"category": new_name, "savePath": save_path},
        )
        for t in qb_request(
            session, "GET", "/api/v2/torrents/info", params={"category": old_name}
        ).json():
            qb_request(
                session,
                "POST",
                "/api/v2/torrents/setCategory",
                data={"hashes": t["hash"], "category": new_name},
            )
        qb_request(
            session, "POST", "/api/v2/torrents/removeCategories", data={"categories": old_name}
        )
    else:
        qb_request(
            session,
            "POST",
            "/api/v2/torrents/editCategory",
            data={"category": old_name, "savePath": save_path},
        )
    log.info("Catégorie modifiée : %s → %s", old_name, new_name or old_name)


def delete(session, name: str) -> None:
    qb_request(session, "POST", "/api/v2/torrents/removeCategories", data={"categories": name})
    log.info("Catégorie supprimée : %s", name)


def move_torrents(session, src: str, dst: str) -> dict:
    torrents = qb_request(
        session, "GET", "/api/v2/torrents/info", params={"category": src}
    ).json()

    success = 0
    failed = 0
    details = []
    for t in torrents:
        try:
            qb_request(
                session,
                "POST",
                "/api/v2/torrents/setCategory",
                data={"hashes": t["hash"], "category": dst},
            )
            success += 1
            details.append({"name": t.get("name", t["hash"]), "status": "ok"})
        except RuntimeError as exc:
            failed += 1
            details.append(
                {"name": t.get("name", t["hash"]), "status": "error", "message": str(exc)}
            )

    log.info(
        "Torrents déplacés de '%s' vers '%s' : %d OK, %d erreurs", src, dst or "(aucune)", success, failed
    )
    return {"ok": True, "success": success, "failed": failed, "details": details}
