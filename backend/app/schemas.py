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


# --- Health ---

class HealthResponse(BaseModel):
    status: str
    version: str
    db_path: str
    parts_count: int
    stock_rows: int
    projects_count: int


# --- Parts ---

class PartRow(BaseModel):
    id: int
    mpn: str
    name: str
    category: str
    package: str | None = None
    params: str | None = None
    unit: str = "pcs"
    url: str | None = None
    datasheet: str | None = None
    note: str | None = None
    created_at: str


class PartListResponse(BaseModel):
    items: list[PartRow]


# --- Stock ---

class StockRow(BaseModel):
    stock_id: int
    part_id: int
    mpn: str
    part_name: str
    location: str
    qty: int
    condition: str | None = None
    updated_at: str


class StockListResponse(BaseModel):
    items: list[StockRow]


class StockInRequest(BaseModel):
    mpn: str
    location: str
    qty: int = Field(gt=0)
    condition: str = "new"
    note: str = ""


class StockOutRequest(BaseModel):
    mpn: str
    location: str
    qty: int = Field(gt=0)
    project_code: str = ""
    ref: str = ""
    note: str = ""
    operator: str = ""


class StockMoveRequest(BaseModel):
    mpn: str
    from_location: str
    to_location: str
    qty: int = Field(gt=0)
    note: str = ""
    operator: str = ""


class StockAdjustRequest(BaseModel):
    mpn: str
    location: str
    add_qty: int = 0
    sub_qty: int = 0
    note: str = ""
    ref: str = ""
    operator: str = ""


# --- Locations ---

class LocationRow(BaseModel):
    location: str
    note: str | None = None


class LocationListResponse(BaseModel):
    items: list[LocationRow]


# --- Ledger ---

class LedgerRow(BaseModel):
    created_at: str
    doc_type: str
    project_code: str | None = None
    mpn: str
    from_location: str | None = None
    to_location: str | None = None
    qty: int
    ref: str | None = None
    operator: str | None = None
    note: str | None = None


class LedgerResponse(BaseModel):
    items: list[LedgerRow]


# --- LLM Chat ---

class LLMChatMessage(BaseModel):
    role: str = Field(pattern=r"^(system|user|assistant)$")
    content: str


class LLMChatRequest(BaseModel):
    messages: list[LLMChatMessage]


class LLMChatResponse(BaseModel):
    reply: str


class LLMIntentRequest(BaseModel):
    text: str


class LLMIntentResponse(BaseModel):
    intent: str
    params: dict = {}
    missing_fields: list[str] = []
    is_complete: bool = False
    is_query: bool = False
    confidence: str = "mock"


class LLMConfigResponse(BaseModel):
    provider: str
    model: str
    api_base: str
    api_key: str
    api_type: str
    timeout: int
    max_tokens: int
