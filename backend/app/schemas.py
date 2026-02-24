from __future__ import annotations

from pydantic import BaseModel, Field


class MessageResponse(BaseModel):
    message: str


class ProjectUpsertRequest(BaseModel):
    code: str
    name: str
    owner: str = ""
    note: str = ""


class ProjectResponse(BaseModel):
    id: int
    code: str
    name: str
    owner: str | None = None
    status: str
    note: str | None = None
    created_at: str


class ProjectListResponse(BaseModel):
    items: list[ProjectResponse]


class ProjectStatusRow(BaseModel):
    project_code: str
    project_name: str
    category: str
    mpn: str
    part_desc: str
    package: str | None = None
    params: str | None = None
    req_qty: int
    total_stock: int
    reserved_qty_all_projects: int
    available_stock: int
    reserved_for_project: int
    remaining_to_reserve: int
    shortage_if_reserve_now: int


class ProjectStatusResponse(BaseModel):
    items: list[ProjectStatusRow]


class ProjectAllocRow(BaseModel):
    alloc_id: int
    project_code: str
    mpn: str
    part_desc: str
    location: str | None = None
    alloc_qty: int
    status: str
    note: str | None = None
    updated_at: str


class ProjectAllocResponse(BaseModel):
    items: list[ProjectAllocRow]


class BomItem(BaseModel):
    mpn: str
    req_qty: int = Field(gt=0)
    priority: int = 2
    note: str = ""


class BomBatchRequest(BaseModel):
    items: list[BomItem]


class GenericResult(BaseModel):
    ok: bool = True
    detail: str = ""


class ReserveRequest(BaseModel):
    mpn: str
    location: str
    qty: int = Field(gt=0)
    note: str = ""


class ReserveResponse(BaseModel):
    alloc_id: int
    project_code: str


class AllocActionRequest(BaseModel):
    note: str = ""


class AllocActionResponse(BaseModel):
    alloc_id: int
    status: str


class ResourceUpsertRequest(BaseModel):
    type: str
    name: str
    uri: str
    is_dir: int = 1
    tags: str = ""
    note: str = ""
    no_check: bool = False


class ResourceDeleteRequest(BaseModel):
    type: str
    uri: str


class ResourceRow(BaseModel):
    id: int
    type: str
    name: str
    uri: str
    is_dir: int
    tags: str | None = None
    note: str | None = None
    created_at: str
    updated_at: str


class ResourceListResponse(BaseModel):
    items: list[ResourceRow]


class ResourceCheckRow(BaseModel):
    id: int
    type: str
    name: str
    uri: str
    ok: bool
    detail: str


class ResourceCheckResponse(BaseModel):
    items: list[ResourceCheckRow]


class ImportResponse(BaseModel):
    ok: int
    err: int
