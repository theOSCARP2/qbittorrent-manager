import secrets

from jinja2 import pass_context
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="templates")


@pass_context
def _csrf_token(ctx) -> str:
    """Jinja2 global — generates or returns the CSRF token stored in the session."""
    request = ctx.get("request")
    if request is None:
        return ""
    if "_csrf_token" not in request.session:
        request.session["_csrf_token"] = secrets.token_hex(32)
    return request.session["_csrf_token"]


templates.env.globals["csrf_token"] = _csrf_token
