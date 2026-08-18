from fastapi import Depends, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)


def auth_required(request: Request) -> None:
    from core.qb_client import is_logged_in

    if not is_logged_in(request.session):
        raise HTTPException(status_code=401, detail="Not authenticated")
