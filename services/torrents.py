from core.config import _SORT_COLS

_STR_COLS = {"name", "category", "state"}


def filter_and_sort(
    data: list[dict],
    search: str = "",
    category: str = "",
    state: str = "",
    order_col: int = 1,
    order_dir: str = "asc",
) -> list[dict]:
    result = data
    if search:
        needle = search.lower()
        result = [t for t in result if needle in t.get("name", "").lower()]
    if category:
        result = [t for t in result if t.get("category", "") == category]
    if state:
        result = [t for t in result if t.get("state", "") == state]

    sort_key = _SORT_COLS.get(order_col, "name")
    reverse = order_dir == "desc"
    if sort_key in _STR_COLS:
        result = sorted(
            result, key=lambda t: str(t.get(sort_key) or "").lower(), reverse=reverse
        )
    else:
        result = sorted(
            result,
            key=lambda t: t.get(sort_key) if isinstance(t.get(sort_key), (int, float)) else 0,
            reverse=reverse,
        )
    return result
