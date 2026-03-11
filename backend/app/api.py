from __future__ import annotations

import os

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.core import DatabaseLockedError, InventoryError, InventoryService, NotFoundError
from backend.app.schemas import (
    AllocActionRequest,
    AllocActionResponse,
    BomBatchRequest,
    GenericResult,
    HealthResponse,
    ImportResponse,
    LcscImportRequest,
    LcscImportResponse,
    LedgerResponse,
    LocationListResponse,
    PartListResponse,
    ProjectAllocResponse,
    ProjectListResponse,
    ProjectResponse,
    ProjectStatusResponse,
    ProjectUpsertRequest,
    ReserveRequest,
    ReserveResponse,
    ResourceCheckResponse,
    ResourceDeleteRequest,
    ResourceListResponse,
    ResourceUpsertRequest,
    StockAdjustRequest,
    StockInRequest,
    StockListResponse,
    StockMoveRequest,
    StockOutRequest,
)

DB_PATH = os.getenv("LABINV_DB", "./lab_inventory.db")
service = InventoryService(DB_PATH)

app = FastAPI(title="LabInventory API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(InventoryError)
async def inventory_error_handler(_request: Request, exc: InventoryError) -> JSONResponse:
    if isinstance(exc, NotFoundError):
        return JSONResponse(status_code=404, content={"detail": str(exc)})
    if isinstance(exc, DatabaseLockedError):
        return JSONResponse(status_code=409, content={"detail": str(exc)})
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(RuntimeError)
async def runtime_error_handler(_request: Request, exc: RuntimeError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})



# --- Health ---

@app.get("/api/health", response_model=HealthResponse)
def health():
    return service.health()


# --- Parts ---

@app.get("/api/parts", response_model=PartListResponse)
def search_parts(query: str = Query(default="")):
    return {"items": service.search_parts(query)}


# --- Stock ---

@app.get("/api/stock", response_model=StockListResponse)
def list_stock(query: str = Query(default=""), location: str = Query(default="")):
    return {"items": service.list_stock(query, location)}


@app.post("/api/lcsc/import", response_model=LcscImportResponse)
def lcsc_import(req: LcscImportRequest):
    return service.lcsc_import(req.url)


@app.post("/api/stock/in", response_model=GenericResult)
def api_stock_in(req: StockInRequest):
    service.stock_in(req.mpn, req.location, req.qty, req.condition, req.note)
    return {"ok": True, "detail": f"入库成功：{req.mpn} @ {req.location} +{req.qty}"}


@app.post("/api/stock/out", response_model=GenericResult)
def api_stock_out(req: StockOutRequest):
    service.stock_out(req.mpn, req.location, req.qty, req.project_code, req.ref, req.note, req.operator)
    return {"ok": True, "detail": f"出库成功：{req.mpn} @ {req.location} -{req.qty}"}


@app.post("/api/stock/move", response_model=GenericResult)
def api_stock_move(req: StockMoveRequest):
    service.stock_move(req.mpn, req.from_location, req.to_location, req.qty, req.note, req.operator)
    return {"ok": True, "detail": f"移库成功：{req.mpn} {req.from_location} → {req.to_location} qty={req.qty}"}


@app.post("/api/stock/adjust", response_model=GenericResult)
def api_stock_adjust(req: StockAdjustRequest):
    service.stock_adjust(req.mpn, req.location, add_qty=req.add_qty, sub_qty=req.sub_qty, note=req.note, ref=req.ref, operator=req.operator)
    mode = "add" if req.add_qty > 0 else "sub"
    v = req.add_qty if req.add_qty > 0 else req.sub_qty
    return {"ok": True, "detail": f"调整成功：{req.mpn} @ {req.location} {mode} {v}"}


# --- Locations ---

@app.get("/api/locations", response_model=LocationListResponse)
def list_locations():
    return {"items": service.list_locations()}


# --- Ledger ---

@app.get("/api/ledger", response_model=LedgerResponse)
def query_ledger(
    project: str = Query(default=""),
    mpn: str = Query(default=""),
    since: str = Query(default=""),
):
    return {"items": service.query_ledger(project, mpn, since)}


# --- Projects ---

@app.post("/api/projects", response_model=ProjectResponse)
def upsert_project(req: ProjectUpsertRequest):
    return service.upsert_project(req.code, req.name, req.owner, req.note)


@app.get("/api/projects", response_model=ProjectListResponse)
def list_projects(query: str = Query(default="")):
    return {"items": service.list_projects(query)}


@app.get("/api/projects/{code}", response_model=ProjectResponse)
def project_detail(code: str):
    return service.get_project(code)


@app.get("/api/projects/{code}/status", response_model=ProjectStatusResponse)
def project_status(code: str):
    return {"items": service.get_project_status(code)}


@app.get("/api/projects/{code}/allocs", response_model=ProjectAllocResponse)
def project_allocs(code: str):
    return {"items": service.get_project_allocs(code)}


@app.post("/api/projects/{code}/bom", response_model=GenericResult)
def set_project_bom(code: str, req: BomBatchRequest):
    result = service.set_project_bom(code, [item.model_dump() for item in req.items])
    return {"ok": True, "detail": f"BOM 已更新 {result['updated']} 行"}


@app.post("/api/projects/{code}/reserve", response_model=ReserveResponse)
def reserve(code: str, req: ReserveRequest):
    return service.reserve(code, req.mpn, req.location, req.qty, req.note)


@app.post("/api/allocs/{alloc_id}/release", response_model=AllocActionResponse)
def release(alloc_id: int, req: AllocActionRequest):
    return service.release_alloc(alloc_id, req.note)


@app.post("/api/allocs/{alloc_id}/consume", response_model=AllocActionResponse)
def consume(alloc_id: int, req: AllocActionRequest):
    return service.consume_alloc(alloc_id, req.note)


@app.post("/api/projects/{code}/resources", response_model=GenericResult)
def add_resource(code: str, req: ResourceUpsertRequest):
    service.upsert_resource(code, req.type, req.name, req.uri, req.is_dir, req.tags, req.note, req.no_check)
    return {"ok": True, "detail": "资源已保存"}


@app.get("/api/projects/{code}/resources", response_model=ResourceListResponse)
def get_resources(code: str):
    return {"items": service.list_resources(code)}


@app.delete("/api/projects/{code}/resources", response_model=GenericResult)
def delete_resource(code: str, req: ResourceDeleteRequest):
    result = service.delete_resource(code, req.type, req.uri)
    return {"ok": True, "detail": f"删除 {result['deleted']} 条资源"}


@app.post("/api/projects/{code}/resources/check", response_model=ResourceCheckResponse)
def check_resource(code: str):
    return {"items": service.check_resource(code)}


@app.post("/api/projects/resources/import-xlsx", response_model=ImportResponse)
async def import_resources_xlsx(
    file: UploadFile = File(...),
    sheet: str = Form("Resources"),
    header_row: int = Form(1),
    no_check: bool = Form(False),
    auto_create_project: bool = Form(False),
):
    data = await file.read()
    return service.import_resource_xlsx(data, sheet=sheet, header_row=header_row, no_check=no_check, auto_create_project=auto_create_project)


@app.post("/api/txns/import-xlsx", response_model=ImportResponse)
async def import_txns_xlsx(
    file: UploadFile = File(...),
    partial: bool = Form(False),
    mode: str = Form("auto"),
):
    data = await file.read()
    return service.import_txn_xlsx(data, partial=partial, mode=mode)


def main() -> None:
    import uvicorn

    uvicorn.run("app.api:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    main()
