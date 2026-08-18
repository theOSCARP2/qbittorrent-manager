import contextlib
import logging

import requests
from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from core.cache import _cache, _start_bg_fetch
from core.extensions import limiter
from core.qb_client import _qb_sessions, is_logged_in, qb_request

bp = Blueprint("auth", __name__)
log = logging.getLogger(__name__)


@bp.route("/")
def index():
    if is_logged_in():
        return redirect(url_for("pages.torrents"))
    return redirect(url_for("auth.login"))


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def login():
    if request.method == "POST":
        qb_url = request.form.get("qb_url", "").strip().rstrip("/")
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not qb_url:
            flash("Server URL is required.", "danger")
            return render_template("login.html")

        try:
            resp = requests.post(
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
                session["qb_url"] = qb_url
                session["qb_sid"] = sid
                session["qb_sid_cookie"] = sid_key
                session["qb_username"] = username

                log.info("Connexion : %s @ %s", username or "(anonyme)", qb_url)
                _cache.invalidate()
                _start_bg_fetch({"qb_url": qb_url, "qb_sid": sid, "qb_sid_cookie": sid_key})
                return redirect(url_for("pages.torrents"))
            elif body in ("Fails.", "fails"):
                flash("Invalid username or password.", "danger")
            elif resp.status_code == 403:
                flash(
                    "qBittorrent refused the connection (403). Check your IP ban settings.",
                    "danger",
                )
            else:
                log.warning("qBittorrent login: status=%s body=%r", resp.status_code, body)
                flash("Invalid username or password.", "danger")
        except requests.exceptions.ConnectionError:
            flash(f"Cannot connect to {qb_url}. Check the URL and try again.", "danger")
        except requests.exceptions.Timeout:
            flash("Connection timed out.", "danger")

        return render_template("login.html")

    if is_logged_in():
        return redirect(url_for("pages.torrents"))
    return render_template("login.html")


@bp.route("/logout")
def logout():
    if is_logged_in():
        sid = session.get("qb_sid")
        with contextlib.suppress(Exception):
            qb_request(session, "POST", "/api/v2/auth/logout")
        _qb_sessions.pop(sid, None)
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
