import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from core.cache import _cache, _start_bg_fetch
from core.config import CACHE_TTL
from core.extensions import auth_required
from core.qb_client import qb_request, session_snapshot
from schemas import DashboardResponse

router = APIRouter(dependencies=[Depends(auth_required)])
log = logging.getLogger(__name__)


@router.get("/api/dashboard", response_model=DashboardResponse)
def api_dashboard(request: Request):
    snap = session_snapshot(request.session)
    if _cache.age() > CACHE_TTL:
        _start_bg_fetch(snap)

    data = _cache.get()
    by_state: dict = {}
    by_category: dict = {}
    size_by_category: dict = {}
    total_dl = total_up = total_size = 0

    for t in data:
        state = t.get("state", "unknown")
        by_state[state] = by_state.get(state, 0) + 1
        cat = t.get("category") or ""
        by_category[cat] = by_category.get(cat, 0) + 1
        size_by_category[cat] = size_by_category.get(cat, 0) + t.get("size", 0)
        total_dl += t.get("dlspeed", 0)
        total_up += t.get("upspeed", 0)
        total_size += t.get("size", 0)

    free_space = None
    try:
        resp = qb_request(snap, "GET", "/api/v2/sync/maindata")
        free_space = resp.json().get("server_state", {}).get("free_space_on_disk")
    except Exception:
        pass

    return {
        "total": len(data),
        "dl_speed": total_dl,
        "up_speed": total_up,
        "total_size": total_size,
        "free_space": free_space,
        "by_state": by_state,
        "by_category": by_category,
        "size_by_category": size_by_category,
        "ready": _cache.is_ready(),
    }
