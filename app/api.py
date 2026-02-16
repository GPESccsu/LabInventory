from __future__ import annotations

import os

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.core import DatabaseLockedError, InventoryService, NotFoundError
from app.schemas import (
    AllocActionRequest,
    AllocActionResponse,
    BomBatchRequest,
    GenericResult,
    ImportResponse,
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


def _http_error(exc: Exception):
    if isinstance(exc, NotFoundError):
        raise HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, DatabaseLockedError):
        raise HTTPException(status_code=409, detail=str(exc))
    raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/projects", response_model=ProjectResponse)
def upsert_project(req: ProjectUpsertRequest):
    try:
        return service.upsert_project(req.code, req.name, req.owner, req.note)
    except Exception as exc:
        _http_error(exc)


@app.get("/api/projects", response_model=ProjectListResponse)
def list_projects(query: str = Query(default="")):
    try:
        return {"items": service.list_projects(query)}
    except Exception as exc:
        _http_error(exc)


@app.get("/api/projects/{code}", response_model=ProjectResponse)
def project_detail(code: str):
    try:
        return service.get_project(code)
    except Exception as exc:
        _http_error(exc)


@app.get("/api/projects/{code}/status", response_model=ProjectStatusResponse)
def project_status(code: str):
    try:
        return {"items": service.get_project_status(code)}
    except Exception as exc:
        _http_error(exc)


@app.get("/api/projects/{code}/allocs", response_model=ProjectAllocResponse)
def project_allocs(code: str):
    try:
        return {"items": service.get_project_allocs(code)}
    except Exception as exc:
        _http_error(exc)


@app.post("/api/projects/{code}/bom", response_model=GenericResult)
def set_project_bom(code: str, req: BomBatchRequest):
    try:
        result = service.set_project_bom(code, [item.model_dump() for item in req.items])
        return {"ok": True, "detail": f"BOM 已更新 {result['updated']} 行"}
    except Exception as exc:
        _http_error(exc)


@app.post("/api/projects/{code}/reserve", response_model=ReserveResponse)
def reserve(code: str, req: ReserveRequest):
    try:
        return service.reserve(code, req.mpn, req.location, req.qty, req.note)
    except Exception as exc:
        _http_error(exc)


@app.post("/api/allocs/{alloc_id}/release", response_model=AllocActionResponse)
def release(alloc_id: int, req: AllocActionRequest):
    try:
        return service.release_alloc(alloc_id, req.note)
    except Exception as exc:
        _http_error(exc)


@app.post("/api/allocs/{alloc_id}/consume", response_model=AllocActionResponse)
def consume(alloc_id: int, req: AllocActionRequest):
    try:
        return service.consume_alloc(alloc_id, req.note)
    except Exception as exc:
        _http_error(exc)


@app.post("/api/projects/{code}/resources", response_model=GenericResult)
def add_resource(code: str, req: ResourceUpsertRequest):
    try:
        service.upsert_resource(code, req.type, req.name, req.uri, req.is_dir, req.tags, req.note, req.no_check)
        return {"ok": True, "detail": "资源已保存"}
    except Exception as exc:
        _http_error(exc)


@app.get("/api/projects/{code}/resources", response_model=ResourceListResponse)
def get_resources(code: str):
    try:
        return {"items": service.list_resources(code)}
    except Exception as exc:
        _http_error(exc)


@app.delete("/api/projects/{code}/resources", response_model=GenericResult)
def delete_resource(code: str, req: ResourceDeleteRequest):
    try:
        result = service.delete_resource(code, req.type, req.uri)
        return {"ok": True, "detail": f"删除 {result['deleted']} 条资源"}
    except Exception as exc:
        _http_error(exc)


@app.post("/api/projects/{code}/resources/check", response_model=ResourceCheckResponse)
def check_resource(code: str):
    try:
        return {"items": service.check_resource(code)}
    except Exception as exc:
        _http_error(exc)


@app.post("/api/projects/resources/import-xlsx", response_model=ImportResponse)
async def import_resources_xlsx(
    file: UploadFile = File(...),
    sheet: str = Form("Resources"),
    header_row: int = Form(1),
    no_check: bool = Form(False),
    auto_create_project: bool = Form(False),
):
    try:
        data = await file.read()
        return service.import_resource_xlsx(data, sheet=sheet, header_row=header_row, no_check=no_check, auto_create_project=auto_create_project)
    except Exception as exc:
        _http_error(exc)


@app.post("/api/txns/import-xlsx", response_model=ImportResponse)
async def import_txns_xlsx(
    file: UploadFile = File(...),
    partial: bool = Form(False),
    mode: str = Form("auto"),
):
    try:
        data = await file.read()
        return service.import_txn_xlsx(data, partial=partial, mode=mode)
    except Exception as exc:
        _http_error(exc)


def main() -> None:
    import uvicorn

    uvicorn.run("app.api:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    main()
