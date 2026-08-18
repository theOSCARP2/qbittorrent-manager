import logging
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core.cache import _cache
from core.extensions import auth_required
from core.qb_client import qb_request
from services import categories as category_service

router = APIRouter(dependencies=[Depends(auth_required)])
log = logging.getLogger(__name__)


class CreateBody(BaseModel):
    name: str
    save_path: Optional[str] = ""


class EditBody(BaseModel):
    name: str
    new_name: Optional[str] = ""
    save_path: Optional[str] = ""


class DeleteBody(BaseModel):
    name: str


class MoveBody(BaseModel):
    src: str
    dst: Optional[str] = ""


@router.get("/api/categories")
def api_categories(request: Request):
    try:
        return category_service.get_stats(request.session)
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)


@router.get("/api/category/torrents")
def api_category_torrents(request: Request, name: str = ""):
    try:
        resp = qb_request(request.session, "GET", "/api/v2/torrents/info", params={"category": name})
        return resp.json()
    except RuntimeError:
        return [t for t in _cache.get() if t.get("category", "") == name]


@router.post("/api/category/create")
def api_category_create(request: Request, body: CreateBody):
    if not body.name.strip():
        return JSONResponse({"error": "name is required"}, status_code=400)
    try:
        category_service.create(request.session, body.name.strip(), (body.save_path or "").strip())
        return {"ok": True}
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)


@router.post("/api/category/edit")
def api_category_edit(request: Request, body: EditBody):
    old_name = (body.name or "").strip()
    if not old_name:
        return JSONResponse({"error": "name is required"}, status_code=400)
    try:
        category_service.edit(
            request.session,
            old_name,
            (body.new_name or "").strip(),
            (body.save_path or "").strip(),
        )
        _cache.invalidate()
        return {"ok": True}
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)


@router.post("/api/category/delete")
def api_category_delete(request: Request, body: DeleteBody):
    name = (body.name or "").strip()
    if not name:
        return JSONResponse({"error": "name is required"}, status_code=400)
    try:
        category_service.delete(request.session, name)
        _cache.invalidate()
        return {"ok": True}
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)


@router.post("/api/category/move-torrents")
def api_category_move_torrents(request: Request, body: MoveBody):
    src = (body.src or "").strip()
    if not src:
        return JSONResponse({"error": "src is required"}, status_code=400)
    try:
        result = category_service.move_torrents(request.session, src, (body.dst or "").strip())
        _cache.invalidate()
        return result
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)
