import logging
from flask import Blueprint, session, redirect, url_for, render_template
from core.qb_client import is_logged_in
from core.cache import _cache, _start_bg_fetch

bp  = Blueprint("pages", __name__)
log = logging.getLogger(__name__)


@bp.route("/dashboard")
def dashboard():
    if not is_logged_in():
        return redirect(url_for("auth.login"))
    if not _cache.is_ready():
        _start_bg_fetch({"qb_url": session["qb_url"], "qb_sid": session["qb_sid"]})
    return render_template("dashboard.html")


@bp.route("/torrents")
def torrents():
    if not is_logged_in():
        return redirect(url_for("auth.login"))
    if not _cache.is_ready():
        log.debug("Cache vide, démarrage du préchauffage")
        _start_bg_fetch({"qb_url": session["qb_url"], "qb_sid": session["qb_sid"]})
    return render_template("torrents.html")


@bp.route("/trackers")
def trackers():
    if not is_logged_in():
        return redirect(url_for("auth.login"))
    return render_template("trackers.html")


@bp.route("/categories")
def categories():
    if not is_logged_in():
        return redirect(url_for("auth.login"))
    return render_template("categories.html")


@bp.route("/logs")
def logs():
    if not is_logged_in():
        return redirect(url_for("auth.login"))
    return render_template("logs.html")
