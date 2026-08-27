import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core.extensions import auth_required, limiter
from services import trackers as tracker_service

router = APIRouter(dependencies=[Depends(auth_required)])
log = logging.getLogger(__name__)


class BulkBody(BaseModel):
    operation: str
    old_url: str | None = ""
    new_url: str | None = ""


class DeleteManyBody(BaseModel):
    urls: list[str] = []


@router.get("/api/trackers")
def api_trackers(request: Request):
    try:
        return tracker_service.build_tracker_map(request.session)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)


@router.post("/api/tracker/bulk")
@limiter.limit("30/minute")
def api_tracker_bulk(request: Request, body: BulkBody):
    operation = body.operation
    old_url = (body.old_url or "").strip()
    new_url = (body.new_url or "").strip()

    if operation not in ("replace", "add", "remove", "copy"):
        return JSONResponse({"error": "Invalid operation"}, status_code=400)
    if operation in ("replace", "remove", "copy") and not old_url:
        return JSONResponse({"error": "old_url is required"}, status_code=400)
    if operation in ("replace", "add", "copy") and not new_url:
        return JSONResponse({"error": "new_url is required"}, status_code=400)

    try:
        return tracker_service.bulk_operation(request.session, operation, old_url, new_url)
    except Exception as exc:
        log.exception("bulk_operation error")
        return JSONResponse({"error": str(exc)}, status_code=502)


@router.post("/api/tracker/delete-many")
def api_tracker_delete_many(request: Request, body: DeleteManyBody):
    urls = [u.strip() for u in body.urls if u.strip()]
    if not urls:
        return JSONResponse({"error": "No tracker URLs provided"}, status_code=400)
    try:
        return tracker_service.delete_many(request.session, urls)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)
