from functools import wraps

from flask import jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect

csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address, default_limits=[])


def require_auth(f):
    @wraps(f)
    def _decorated(*args, **kwargs):
        from core.qb_client import is_logged_in

        if not is_logged_in():
            return jsonify({"error": "Not authenticated"}), 401
        return f(*args, **kwargs)

    return _decorated
