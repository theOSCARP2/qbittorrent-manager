import io
import logging
import os
import shutil
import tempfile
import threading
import time
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from core.cache import _cache, _start_bg_fetch
from core.config import CACHE_TTL
from core.extensions import auth_required
from core.qb_client import qb_request, session_snapshot
from core.validators import safe_path, valid_hash, valid_hashes
from schemas import ActionResult, OkResponse, StatusResponse, TorrentsResponse
from services import torrents as torrent_service

router = APIRouter(dependencies=[Depends(auth_required)])
log = logging.getLogger(__name__)


class SetCategoryBody(BaseModel):
    hash: str
    category: Optional[str] = ""


class ActionBody(BaseModel):
    action: str
    hashes: List[str] = []
    deleteFiles: Optional[bool] = False


class FilePriorityBody(BaseModel):
    hash: str
    id: int
    priority: int


class SetLocationBody(BaseModel):
    hash: str
    location: str


class SetSpeedLimitBody(BaseModel):
    hash: str
    dl_limit: Optional[int] = None
    up_limit: Optional[int] = None


@router.get("/api/torrents/status", response_model=StatusResponse)
def api_torrents_status():
    return {"ready": _cache.is_ready(), "total": len(_cache.get())}


@router.get("/api/torrents", response_model=TorrentsResponse)
def api_torrents(
    request: Request,
    draw: int = 1,
    start: int = 0,
    length: int = 20,
    category: str = "",
    state: str = "",
):
    search = request.query_params.get("search[value]", "").strip().lower()
    order_col = int(request.query_params.get("order[0][column]", 1))
    order_dir = request.query_params.get("order[0][dir]", "asc")

    snap = session_snapshot(request.session)

    if not _cache.is_ready():
        log.debug("Cache vide, démarrage de la récupération")
        _start_bg_fetch(snap)
        return {
            "draw": draw,
            "recordsTotal": 0,
            "recordsFiltered": 0,
            "data": [],
            "loading": True,
        }

    if _cache.age() > CACHE_TTL:
        log.debug("Cache expiré (%.0fs), rafraîchissement en arrière-plan", _cache.age())
        _start_bg_fetch(snap)

    data = _cache.get()
    filtered = torrent_service.filter_and_sort(
        data,
        search=search,
        category=category.strip(),
        state=state.strip(),
        order_col=order_col,
        order_dir=order_dir,
    )

    return {
        "draw": draw,
        "recordsTotal": len(data),
        "recordsFiltered": len(filtered),
        "data": filtered[start : start + length],
    }


@router.get("/api/torrents/states")
def api_torrents_states():
    states = sorted({t.get("state", "") for t in _cache.get() if t.get("state")})
    return states


@router.get("/api/torrents/categories")
def api_torrents_categories():
    cats = sorted({t.get("category", "") for t in _cache.get() if t.get("category")})
    return cats


@router.get("/api/qb/categories")
def api_qb_categories(request: Request):
    try:
        resp = qb_request(request.session, "GET", "/api/v2/torrents/categories")
        return sorted(resp.json().keys())
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)


@router.post("/api/torrent/set-category")
def api_torrent_set_category(request: Request, body: SetCategoryBody):
    hash_ = body.hash.strip()
    cat = (body.category or "").strip()
    if not valid_hash(hash_):
        return JSONResponse({"error": "Invalid hash"}, status_code=400)
    try:
        qb_request(
            request.session,
            "POST",
            "/api/v2/torrents/setCategory",
            data={"hashes": hash_, "category": cat},
        )
        _cache.update_torrent(hash_, category=cat)
        return {"ok": True}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)


@router.post("/api/torrent/add")
async def api_torrent_add(
    request: Request,
    savepath: str = Form(""),
    category: str = Form(""),
    paused: str = Form("false"),
    urls: str = Form(""),
    torrents: Optional[UploadFile] = File(None),
):
    form_data: dict = {"paused": paused}
    if savepath:
        form_data["savepath"] = savepath
    if category:
        form_data["category"] = category

    try:
        if torrents and torrents.filename:
            file_bytes = await torrents.read()
            resp = qb_request(
                request.session,
                "POST",
                "/api/v2/torrents/add",
                files={"torrents": (torrents.filename, file_bytes, "application/x-bittorrent")},
                data=form_data,
            )
        else:
            if not urls.strip():
                return JSONResponse({"error": "No URL or file provided"}, status_code=400)
            form_data["urls"] = urls.strip()
            resp = qb_request(request.session, "POST", "/api/v2/torrents/add", data=form_data)

        body_text = resp.text.strip()
        try:
            data = resp.json()
            failures = data.get("failures", [])
            if data.get("added_torrent_ids") or not failures:
                _cache.invalidate()
                _start_bg_fetch(session_snapshot(request.session))
                return {"ok": True}
            error_msg = "; ".join(str(f) for f in failures)
            if "already" in error_msg.lower():
                return JSONResponse({"error": "duplicate"}, status_code=400)
            return JSONResponse({"error": error_msg}, status_code=400)
        except Exception:
            if body_text in ("Ok.", "Ok"):
                _cache.invalidate()
                _start_bg_fetch(session_snapshot(request.session))
                return {"ok": True}
            if "already" in body_text.lower():
                return JSONResponse({"error": "duplicate"}, status_code=400)
            return JSONResponse({"error": body_text}, status_code=400)
    except Exception as exc:
        msg = str(exc).lower()
        if "409" in msg or "conflict" in msg or "already" in msg:
            return JSONResponse({"error": "duplicate"}, status_code=409)
        log.warning("torrent add error: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=502)


@router.post("/api/torrent/create")
async def api_torrent_create(request: Request):
    try:
        import torf
    except ImportError:
        return JSONResponse(
            {"error": "La librairie 'torf' n'est pas installée (pip install torf)."}, status_code=500
        )

    content_type = request.headers.get("content-type", "")
    is_upload = "multipart/form-data" in content_type
    tmpdir = None

    try:
        if is_upload:
            form = await request.form()
            files = form.getlist("files[]")
            rel_paths = form.getlist("rel_paths[]")
            name = (form.get("name") or "").strip()
            trackers = [
                t.strip() for t in (form.get("trackers") or "").splitlines() if t.strip()
            ]
            piece_size = int(form.get("piece_size") or 0)
            private = form.get("private") == "true"
            comment = (form.get("comment") or "").strip()
            source = (form.get("source") or "").strip()
            add_to_qb = form.get("add_to_qb") == "true"

            if not files:
                return JSONResponse({"error": "Aucun fichier reçu."}, status_code=400)

            tmpdir = tempfile.mkdtemp(prefix="qbm-create-")
            for f, rel in zip(files, rel_paths or [f.filename for f in files], strict=False):
                dest = os.path.join(
                    tmpdir, rel.replace("/", os.sep).replace("\\", os.sep)
                )
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                content = await f.read()
                with open(dest, "wb") as fh:
                    fh.write(content)

            top = os.listdir(tmpdir)
            torrent_input = os.path.join(tmpdir, top[0]) if len(top) == 1 else tmpdir

        else:
            body = await request.json()
            path_str = (body.get("path") or "").strip()
            name = (body.get("name") or "").strip()
            trackers = [t.strip() for t in (body.get("trackers") or "").splitlines() if t.strip()]
            piece_size = int(body.get("piece_size") or 0)
            private = bool(body.get("private", False))
            comment = (body.get("comment") or "").strip()
            source = (body.get("source") or "").strip()
            add_to_qb = bool(body.get("add_to_qb", True))

            if not path_str:
                return JSONResponse({"error": "Veuillez saisir un chemin."}, status_code=400)
            if not safe_path(path_str):
                return JSONResponse({"error": "Chemin invalide."}, status_code=400)
            if not os.path.exists(path_str):
                return JSONResponse({"error": f"Chemin introuvable : {path_str}"}, status_code=400)
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
                request.session,
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
            _start_bg_fetch(session_snapshot(request.session))
            log.info("Torrent créé et ajouté à qBittorrent : %s", torrent_name)

        return Response(
            content=torrent_bytes,
            media_type="application/x-bittorrent",
            headers={"Content-Disposition": f'attachment; filename="{torrent_name}.torrent"'},
        )
    except Exception as exc:
        log.error("Erreur création torrent : %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=500)
    finally:
        if tmpdir:
            shutil.rmtree(tmpdir, ignore_errors=True)


@router.get("/api/torrent/trackers")
def api_torrent_trackers(request: Request, hash: str = ""):
    hash_ = hash.strip()
    if not valid_hash(hash_):
        return JSONResponse({"error": "Invalid hash"}, status_code=400)
    try:
        resp = qb_request(request.session, "GET", f"/api/v2/torrents/trackers?hash={hash_}")
        return [t for t in resp.json() if not t.get("url", "").startswith("** ")]
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)


@router.get("/api/torrent/files")
def api_torrent_files(request: Request, hash: str = ""):
    hash_ = hash.strip()
    if not valid_hash(hash_):
        return JSONResponse({"error": "Invalid hash"}, status_code=400)
    try:
        resp = qb_request(request.session, "GET", f"/api/v2/torrents/files?hash={hash_}")
        return resp.json()
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)


@router.get("/api/torrent/properties")
def api_torrent_properties(request: Request, hash: str = ""):
    hash_ = hash.strip()
    if not valid_hash(hash_):
        return JSONResponse({"error": "Invalid hash"}, status_code=400)
    try:
        resp = qb_request(request.session, "GET", f"/api/v2/torrents/properties?hash={hash_}")
        return resp.json()
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)


@router.post("/api/torrent/action", response_model=ActionResult)
def api_torrent_action(request: Request, body: ActionBody):
    action = body.action
    hashes = body.hashes

    if not action:
        return JSONResponse({"error": "Missing action"}, status_code=400)
    if not valid_hashes(hashes):
        return JSONResponse({"error": "Invalid or missing hashes"}, status_code=400)

    action_map = {
        "pause": "/api/v2/torrents/stop",
        "resume": "/api/v2/torrents/start",
        "recheck": "/api/v2/torrents/recheck",
        "delete": "/api/v2/torrents/delete",
    }
    if action not in action_map:
        return JSONResponse({"error": f"Unknown action: {action}"}, status_code=400)

    data = {"hashes": "|".join(hashes)}
    if action == "delete":
        data["deleteFiles"] = "true" if body.deleteFiles else "false"

    try:
        qb_request(request.session, "POST", action_map[action], data=data)
        hash_set = set(hashes)
        if action == "delete":
            _cache.remove_torrents(hash_set)
        else:
            _cache.apply_state_change(hash_set, action)

        snap = session_snapshot(request.session)

        def _delayed_refresh():
            time.sleep(3)
            _cache.invalidate()
            _start_bg_fetch(snap)

        threading.Thread(target=_delayed_refresh, daemon=True).start()
        return {"ok": True, "action": action, "count": len(hashes)}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)


@router.post("/api/torrent/set-file-priority")
def api_torrent_set_file_priority(request: Request, body: FilePriorityBody):
    hash_ = body.hash.strip()
    if not hash_:
        return JSONResponse({"error": "Missing parameters"}, status_code=400)
    try:
        qb_request(
            request.session,
            "POST",
            "/api/v2/torrents/filePrio",
            data={"hash": hash_, "id": str(body.id), "priority": str(body.priority)},
        )
        log.debug("Priorité fichier %s[%s] → %s", hash_[:8], body.id, body.priority)
        return {"ok": True}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)


@router.post("/api/torrent/set-location")
def api_torrent_set_location(request: Request, body: SetLocationBody):
    hash_ = body.hash.strip()
    location = body.location.strip()
    if not valid_hash(hash_):
        return JSONResponse({"error": "Invalid hash"}, status_code=400)
    if not location or not safe_path(location):
        return JSONResponse({"error": "Invalid location"}, status_code=400)
    try:
        qb_request(
            request.session,
            "POST",
            "/api/v2/torrents/setLocation",
            data={"hashes": hash_, "location": location},
        )
        _cache.update_torrent(hash_, save_path=location)
        log.info("Répertoire torrent %s → %s", hash_[:8], location)
        return {"ok": True}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)


@router.post("/api/torrent/set-speed-limit")
def api_torrent_set_speed_limit(request: Request, body: SetSpeedLimitBody):
    hash_ = body.hash.strip()
    if not valid_hash(hash_):
        return JSONResponse({"error": "Invalid hash"}, status_code=400)
    if body.dl_limit is None and body.up_limit is None:
        return JSONResponse({"error": "Missing dl_limit or up_limit"}, status_code=400)
    try:
        if body.dl_limit is not None:
            qb_request(
                request.session,
                "POST",
                "/api/v2/torrents/setDownloadLimit",
                data={"hashes": hash_, "limit": str(body.dl_limit)},
            )
        if body.up_limit is not None:
            qb_request(
                request.session,
                "POST",
                "/api/v2/torrents/setUploadLimit",
                data={"hashes": hash_, "limit": str(body.up_limit)},
            )
        log.info("Limites vitesse %s → DL=%s UP=%s", hash_[:8], body.dl_limit, body.up_limit)
        return {"ok": True}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)
