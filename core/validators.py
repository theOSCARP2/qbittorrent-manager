import re

_HASH_RE = re.compile(r'^[a-fA-F0-9]{40}$')


def valid_hash(h: str) -> bool:
    """Vérifie qu'un hash de torrent est bien un hexadécimal de 40 caractères."""
    return bool(h and _HASH_RE.match(h))


def valid_hashes(hashes: list) -> bool:
    """Vérifie que tous les hashes d'une liste sont valides."""
    return bool(hashes) and all(valid_hash(h) for h in hashes)


def safe_path(p: str) -> bool:
    """Vérifie qu'un chemin ne contient pas de traversée de répertoire."""
    parts = p.replace("\\", "/").split("/")
    return ".." not in parts
