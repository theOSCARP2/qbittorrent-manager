import logging
import requests
from flask import (
    Blueprint, session, redirect, url_for,
    request, render_template, flash,
)
from core.qb_client import is_logged_in, qb_request, _qb_sessions
from core.cache import _cache, _start_bg_fetch

bp  = Blueprint("auth", __name__)
log = logging.getLogger(__name__)


@bp.route("/")
def index():
    if is_logged_in():
        return redirect(url_for("pages.torrents"))
    return redirect(url_for("auth.login"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        qb_url   = request.form.get("qb_url", "").strip().rstrip("/")
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not qb_url:
            flash("Server URL is required.", "danger")
            return render_template("login.html")

        try:
            resp = requests.post(
                f"{qb_url}/api/v2/auth/login",
                data={"username": username, "password": password},
                timeout=15,
            )
            body = resp.text.strip()
            if body == "Ok.":
                sid = resp.cookies.get("SID")
                if not sid:
                    flash("Login succeeded but no SID cookie was returned.", "danger")
                    return render_template("login.html")
                session["qb_url"]      = qb_url
                session["qb_sid"]      = sid
                session["qb_username"] = username

                log.info("Connexion : %s @ %s", username or "(anonyme)", qb_url)
                _cache.invalidate()
                _start_bg_fetch({"qb_url": qb_url, "qb_sid": sid})
                return redirect(url_for("pages.torrents"))
            elif body == "Fails.":
                flash("Invalid username or password.", "danger")
            else:
                flash(f"Unexpected response from qBittorrent: {body}", "warning")
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
        try:
            qb_request(session, "POST", "/api/v2/auth/logout")
        except Exception:
            pass
        _qb_sessions.pop(sid, None)
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
