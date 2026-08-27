import logging
import time

import requests as _requests
from fastapi import APIRouter, Depends, Request

import core.config as _cfg
from core.extensions import auth_required
from schemas import DebugResponse, VersionResponse

router = APIRouter()
log = logging.getLogger(__name__)


@router.get("/api/version/check", response_model=VersionResponse)
def api_version_check():
    now = time.monotonic()
    if _cfg._version_cache["latest"] and now - _cfg._version_cache["ts"] < _cfg.VERSION_CACHE_TTL:
        latest = _cfg._version_cache["latest"]
    else:
        try:
            r = _requests.get(
                f"https://api.github.com/repos/{_cfg.GITHUB_REPO}/releases/latest",
                headers={"Accept": "application/vnd.github+json"},
                timeout=5,
            )
            latest = r.json().get("tag_name", "").lstrip("v")
            _cfg._version_cache["latest"] = latest
            _cfg._version_cache["ts"] = now
        except Exception:
            from fastapi.responses import JSONResponse

            return JSONResponse({"error": "unavailable"}, status_code=503)

    up_to_date = (
        _cfg._version_tuple(_cfg.APP_VERSION) >= _cfg._version_tuple(latest) if latest else True
    )
    return {"current": _cfg.APP_VERSION, "latest": latest, "up_to_date": up_to_date}


@router.get("/api/debug/status", response_model=DebugResponse)
def api_debug_status():
    return {"debug": _cfg._debug_mode}


@router.post("/api/debug/toggle", dependencies=[Depends(auth_required)], response_model=DebugResponse)
def api_debug_toggle():
    _cfg._set_debug(not _cfg._debug_mode)
    log.info("Mode debug %s", "activé" if _cfg._debug_mode else "désactivé")
    return {"debug": _cfg._debug_mode}


@router.get("/api/qb/logs", dependencies=[Depends(auth_required)])
def api_qb_logs(request: Request, last_id: str = "-1"):
    from core.qb_client import qb_request
    from fastapi.responses import JSONResponse

    try:
        resp = qb_request(
            request.session,
            "GET",
            f"/api/v2/log/main?last_known_id={last_id}&normal=true&info=true&warning=true&critical=true",
        )
        return resp.json()
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)
