from starlette.requests import Request


def flash(request: Request, message: str, category: str = "info") -> None:
    msgs = list(request.session.get("_flashes", []))
    msgs.append([category, message])
    request.session["_flashes"] = msgs


def pop_flashes(request: Request) -> list:
    msgs = list(request.session.get("_flashes", []))
    request.session["_flashes"] = []
    return msgs
