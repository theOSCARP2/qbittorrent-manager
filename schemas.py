"""Pydantic response models partagés entre les routes API."""

from typing import Any, Optional

from pydantic import BaseModel


class OkResponse(BaseModel):
    ok: bool = True


class StatusResponse(BaseModel):
    ready: bool
    total: int


class DashboardResponse(BaseModel):
    total: int
    dl_speed: int
    up_speed: int
    total_size: int
    free_space: Optional[int]
    by_state: dict[str, int]
    by_category: dict[str, int]
    size_by_category: dict[str, int]
    ready: bool


class TorrentSummary(BaseModel):
    model_config = {"extra": "allow"}

    hash: str = ""
    name: str = ""
    category: str = ""
    size: int = 0
    progress: float = 0.0
    state: str = ""
    num_seeds: int = 0
    num_leechs: int = 0
    dlspeed: int = 0
    upspeed: int = 0
    added_on: int = 0
    save_path: str = ""
    ratio: float = 0.0
    eta: int = 0


class TorrentsResponse(BaseModel):
    draw: int
    recordsTotal: int
    recordsFiltered: int
    data: list[TorrentSummary]
    loading: bool = False


class ActionResult(BaseModel):
    ok: bool = True
    action: str
    count: int


class BulkResult(BaseModel):
    ok: bool = True
    operation: str
    success: int
    failed: int
    details: list[dict[str, Any]]


class DeleteManyResult(BaseModel):
    ok: bool = True
    total_removed: int
    failed: int
    details: list[dict[str, Any]]


class MoveTorrentsResult(BaseModel):
    ok: bool = True
    success: int
    failed: int
    details: list[dict[str, Any]]


class VersionResponse(BaseModel):
    current: str
    latest: str
    up_to_date: bool


class DebugResponse(BaseModel):
    debug: bool
