import os
import logging

APP_VERSION       = "1.23.0"
GITHUB_REPO       = "theOSCARP2/qbittorrent-manager"
VERSION_CACHE_TTL = 3600  # 1 heure
CACHE_TTL         = 30    # secondes

_version_cache: dict = {"latest": None, "ts": 0.0}

_TORRENT_FIELDS = {
    "hash", "name", "category", "size", "progress", "state",
    "num_seeds", "num_leechs", "dlspeed", "upspeed",
    "added_on", "completion_on", "save_path", "ratio", "eta",
}

# Colonnes triables côté serveur : index DataTables → champ torrent
_SORT_COLS = {
    1: "name",
    2: "category",
    3: "size",
    5: "state",
    6: "num_seeds",
    7: "num_leechs",
    8: "dlspeed",
    9: "upspeed",
    10: "ratio",
}

# ---------------------------------------------------------------------------
# Debug mode (togglable at runtime via the web UI)
# ---------------------------------------------------------------------------
_debug_mode = False


def _set_debug(enabled: bool):
    global _debug_mode
    _debug_mode = enabled
    level = logging.DEBUG if enabled else logging.INFO
    logging.getLogger().setLevel(level)
    logging.getLogger("core").setLevel(level)


# ---------------------------------------------------------------------------
# Version helpers
# ---------------------------------------------------------------------------

def _version_tuple(v: str) -> tuple:
    return tuple(int(x) for x in v.lstrip("v").split("."))


# ---------------------------------------------------------------------------
# Secret key
# ---------------------------------------------------------------------------

def _get_secret_key() -> str:
    # Priorité 1 : variable d'environnement (usage serveur / avancé)
    if key := os.environ.get("SECRET_KEY"):
        return key
    # Priorité 2 : clé persistée dans le dossier utilisateur
    from pathlib import Path
    import secrets
    key_file = Path.home() / ".qbittorrent-manager" / "secret.key"
    key_file.parent.mkdir(exist_ok=True)
    if key_file.exists():
        return key_file.read_text().strip()
    # Premier lancement : génération et sauvegarde
    key = secrets.token_hex(32)
    key_file.write_text(key)
    logging.getLogger(__name__).info("Nouvelle clé secrète générée : %s", key_file)
    return key
