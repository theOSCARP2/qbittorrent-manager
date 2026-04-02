import time
import threading
import logging

from .config import CACHE_TTL, _TORRENT_FIELDS
from .qb_client import qb_request

log = logging.getLogger(__name__)


class _TorrentCache:
    def __init__(self):
        self._lock       = threading.Lock()
        self._data: list = []
        self._ts: float  = 0.0
        self._refreshing = False

    def get(self) -> list:
        return self._data

    def age(self) -> float:
        return time.monotonic() - self._ts

    def is_ready(self) -> bool:
        return bool(self._data)

    def set(self, data: list):
        with self._lock:
            self._data       = data
            self._ts         = time.monotonic()
            self._refreshing = False

    def invalidate(self):
        self._ts = 0.0

    def start_refresh(self) -> bool:
        with self._lock:
            if self._refreshing:
                return False
            self._refreshing = True
            return True

    def cancel_refresh(self):
        with self._lock:
            self._refreshing = False


_cache = _TorrentCache()


def _fetch_and_cache(session_snapshot: dict):
    """Fetch all torrents from qBittorrent and store in cache."""
    log.debug("Récupération du cache (url=%s)", session_snapshot.get("qb_url"))
    t0 = time.monotonic()
    try:
        resp = qb_request(session_snapshot, "GET", "/api/v2/torrents/info")
        log.debug("Réponse HTTP %s en %.2fs", resp.status_code, time.monotonic() - t0)
        raw  = resp.json()
        slim = [{k: t[k] for k in _TORRENT_FIELDS if k in t} for t in raw]
        _cache.set(slim)
        log.info("Cache actualisé — %d torrents (%.1fs)", len(slim), time.monotonic() - t0)
    except Exception as exc:
        log.error("Erreur lors du rafraîchissement du cache : %s", exc)
        _cache.cancel_refresh()


def _start_bg_fetch(session_snapshot: dict):
    """Start a background fetch only if not already running."""
    if _cache.start_refresh():
        log.debug("Démarrage du thread de mise à jour du cache")
        threading.Thread(target=_fetch_and_cache, args=(session_snapshot,), daemon=True).start()
    else:
        log.debug("Mise à jour du cache déjà en cours")
