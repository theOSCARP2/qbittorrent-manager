import logging
import secrets

import requests as _requests
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse

from core.cache import _cache, _start_bg_fetch
from core.extensions import limiter
from core.flash import flash, pop_flashes
from core.qb_client import _qb_sessions, is_logged_in, qb_request, session_snapshot
from core.templates import templates

router = APIRouter()
log = logging.getLogger(__name__)


@router.get("/")
def index(request: Request):
    if is_logged_in(request.session):
        return RedirectResponse("/torrents", status_code=302)
    return RedirectResponse("/login", status_code=302)


@router.get("/login")
def login_get(request: Request):
    if is_logged_in(request.session):
        return RedirectResponse("/torrents", status_code=302)
    return templates.TemplateResponse(request, "login.html", {"flashes": pop_flashes(request)})


@router.post("/login")
@limiter.limit("10/minute")
async def login_post(
    request: Request,
    qb_url: str = Form(""),
    username: str = Form(""),
    password: str = Form(""),
    csrf_token: str = Form(""),
):
    expected_csrf = request.session.get("_csrf_token", "")
    if not expected_csrf or not secrets.compare_digest(expected_csrf, csrf_token):
        flash(request, "Session expirée. Veuillez réessayer.", "danger")
        return RedirectResponse("/login", status_code=303)

    qb_url = qb_url.strip().rstrip("/")
    username = username.strip()

    if not qb_url:
        flash(request, "Server URL is required.", "danger")
        return templates.TemplateResponse(
            request, "login.html",
            {"flashes": pop_flashes(request), "form_qb_url": qb_url, "form_username": username},
            status_code=422,
        )

    try:
        resp = _requests.post(
            f"{qb_url}/api/v2/auth/login",
            data={"username": username, "password": password},
            headers={"Referer": qb_url, "Origin": qb_url},
            timeout=15,
        )
        body = resp.text.strip()
        raw_cookies = dict(resp.cookies)
        sid_key = (
            "SID"
            if "SID" in raw_cookies
            else next((k for k in raw_cookies if k.startswith("QBT_SID")), None)
        )
        sid = raw_cookies.get(sid_key) if sid_key else None

        if sid:
            request.session["qb_url"] = qb_url
            request.session["qb_sid"] = sid
            request.session["qb_sid_cookie"] = sid_key
            request.session["qb_username"] = username

            log.info("Connexion : %s @ %s", username or "(anonyme)", qb_url)
            _cache.invalidate()
            _start_bg_fetch({"qb_url": qb_url, "qb_sid": sid, "qb_sid_cookie": sid_key})
            return RedirectResponse("/torrents", status_code=303)
        elif body in ("Fails.", "fails"):
            flash(request, "Invalid username or password.", "danger")
        elif resp.status_code == 403:
            flash(
                request,
                "qBittorrent refused the connection (403). Check your IP ban settings.",
                "danger",
            )
        else:
            log.warning("qBittorrent login: status=%s body=%r", resp.status_code, body)
            flash(request, "Invalid username or password.", "danger")

    except _requests.exceptions.ConnectionError:
        flash(request, f"Cannot connect to {qb_url}. Check the URL and try again.", "danger")
    except _requests.exceptions.Timeout:
        flash(request, "Connection timed out.", "danger")

    return templates.TemplateResponse(
        request, "login.html",
        {"flashes": pop_flashes(request), "form_qb_url": qb_url, "form_username": username},
        status_code=422,
    )


@router.get("/logout")
def logout(request: Request):
    if is_logged_in(request.session):
        sid = request.session.get("qb_sid")
        try:
            qb_request(request.session, "POST", "/api/v2/auth/logout")
        except Exception:
            pass
        _qb_sessions.pop(sid, None)
    request.session.clear()
    flash(request, "You have been logged out.", "info")
    return RedirectResponse("/login", status_code=302)
