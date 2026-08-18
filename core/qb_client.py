import logging
import time

import requests
from flask import session as flask_session

log = logging.getLogger(__name__)

# Sessions requests persistées par SID qBittorrent
_qb_sessions: dict[str, requests.Session] = {}


def qb_request(session_data, method, endpoint, **kwargs):
    sid = session_data["qb_sid"]
    sid_cookie = session_data.get("qb_sid_cookie", "SID")
    base_url = session_data["qb_url"].rstrip("/")
    url = f"{base_url}{endpoint}"

    if sid not in _qb_sessions:
        s = requests.Session()
        s.cookies.set(sid_cookie, sid)
        _qb_sessions[sid] = s
    else:
        _qb_sessions[sid].cookies.set(sid_cookie, sid)

    try:
        t0 = time.monotonic()
        resp = _qb_sessions[sid].request(method, url, timeout=30, **kwargs)
        log.debug(
            "qb %s %s → %s (%.2fs)", method, endpoint, resp.status_code, time.monotonic() - t0
        )
        resp.raise_for_status()
        return resp
    except requests.exceptions.ConnectionError as exc:
        _qb_sessions.pop(sid, None)
        raise RuntimeError(f"Cannot connect to qBittorrent: {exc}") from exc
    except requests.exceptions.Timeout as exc:
        raise RuntimeError(f"qBittorrent request timed out: {exc}") from exc
    except requests.exceptions.HTTPError as exc:
        raise RuntimeError(f"qBittorrent returned an error: {exc}") from exc


def is_logged_in() -> bool:
    return "qb_sid" in flask_session and "qb_url" in flask_session


def session_snapshot() -> dict:
    """Build a qb session dict from the current Flask session."""
    snap = {"qb_url": flask_session["qb_url"], "qb_sid": flask_session["qb_sid"]}
    if "qb_sid_cookie" in flask_session:
        snap["qb_sid_cookie"] = flask_session["qb_sid_cookie"]
    return snap
