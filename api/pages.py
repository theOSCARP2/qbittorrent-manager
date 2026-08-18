import logging

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from core.cache import _cache, _start_bg_fetch
from core.flash import pop_flashes
from core.qb_client import is_logged_in, session_snapshot
from core.templates import templates

router = APIRouter()
log = logging.getLogger(__name__)


def _check_auth(request: Request):
    if not is_logged_in(request.session):
        return RedirectResponse("/login", status_code=302)
    return None


@router.get("/dashboard")
def dashboard(request: Request):
    if redir := _check_auth(request):
        return redir
    if not _cache.is_ready():
        _start_bg_fetch(session_snapshot(request.session))
    return templates.TemplateResponse(
        "dashboard.html", {"request": request, "flashes": pop_flashes(request)}
    )


@router.get("/torrents")
def torrents(request: Request):
    if redir := _check_auth(request):
        return redir
    if not _cache.is_ready():
        log.debug("Cache vide, démarrage du préchauffage")
        _start_bg_fetch(session_snapshot(request.session))
    return templates.TemplateResponse(
        "torrents.html", {"request": request, "flashes": pop_flashes(request)}
    )


@router.get("/trackers")
def trackers(request: Request):
    if redir := _check_auth(request):
        return redir
    return templates.TemplateResponse(
        "trackers.html", {"request": request, "flashes": pop_flashes(request)}
    )


@router.get("/categories")
def categories(request: Request):
    if redir := _check_auth(request):
        return redir
    return templates.TemplateResponse(
        "categories.html", {"request": request, "flashes": pop_flashes(request)}
    )


@router.get("/logs")
def logs(request: Request):
    if redir := _check_auth(request):
        return redir
    return templates.TemplateResponse(
        "logs.html", {"request": request, "flashes": pop_flashes(request)}
    )
