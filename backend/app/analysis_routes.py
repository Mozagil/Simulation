"""Veri seti API: listeleme, filtreleme, detay, export, parametre taramasi."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from .analysis_store import (
    AnalysisFilters,
    delete_analysis,
    export_dataset_csv,
    get_analysis_detail,
    get_analysis_result,
    get_filter_options,
    list_analyses,
    list_geometries,
    save_analysis_run,
)
from .models import ModelSetup
from .solver import solve_static

_ALLOWED_EXTENSIONS = {".step", ".stp"}
_MAX_BYTES = 100 * 1024 * 1024


def _solve(path: str, setup: ModelSetup, element_size: float | None):
    result = solve_static(
        path,
        setup.material,
        setup.constraints,
        setup.loads,
        element_size,
    )
    return result.to_dict()

router = APIRouter(prefix="/api/dataset", tags=["dataset"])


class SweepRequest(BaseModel):
    setup: ModelSetup
    element_sizes: list[float] = Field(..., min_length=1, max_length=50)
    notes: str | None = None


def _parse_filters(
    geometry_id: int | None = None,
    filename: str | None = None,
    analysis_type: str | None = None,
    material_name: str | None = None,
    mesh_es_min: float | None = None,
    mesh_es_max: float | None = None,
    youngs_min: float | None = None,
    youngs_max: float | None = None,
    max_disp_min: float | None = None,
    max_disp_max: float | None = None,
    max_vm_min: float | None = None,
    max_vm_max: float | None = None,
    fixed_face_id: int | None = None,
    load_type: str | None = None,
    status: str | None = None,
    created_after: str | None = None,
    created_before: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> AnalysisFilters:
    def _dt(s: str | None) -> datetime | None:
        if not s:
            return None
        return datetime.fromisoformat(s.replace("Z", "+00:00"))

    return AnalysisFilters(
        geometry_id=geometry_id,
        filename_contains=filename,
        analysis_type=analysis_type,
        material_name=material_name,
        mesh_element_size_min=mesh_es_min,
        mesh_element_size_max=mesh_es_max,
        youngs_min=youngs_min,
        youngs_max=youngs_max,
        max_disp_min=max_disp_min,
        max_disp_max=max_disp_max,
        max_vm_min=max_vm_min,
        max_vm_max=max_vm_max,
        fixed_face_id=fixed_face_id,
        load_type=load_type,
        status=status,
        created_after=_dt(created_after),
        created_before=_dt(created_before),
        limit=min(limit, 500),
        offset=offset,
    )


@router.get("/options")
def dataset_options() -> dict:
    return get_filter_options()


@router.get("/geometries")
def dataset_geometries() -> dict:
    return {"items": list_geometries()}


@router.get("/analyses")
def dataset_analyses(
    geometry_id: Annotated[int | None, Query()] = None,
    filename: Annotated[str | None, Query()] = None,
    analysis_type: Annotated[str | None, Query()] = None,
    material_name: Annotated[str | None, Query()] = None,
    mesh_es_min: Annotated[float | None, Query()] = None,
    mesh_es_max: Annotated[float | None, Query()] = None,
    youngs_min: Annotated[float | None, Query()] = None,
    youngs_max: Annotated[float | None, Query()] = None,
    max_disp_min: Annotated[float | None, Query()] = None,
    max_disp_max: Annotated[float | None, Query()] = None,
    max_vm_min: Annotated[float | None, Query()] = None,
    max_vm_max: Annotated[float | None, Query()] = None,
    fixed_face_id: Annotated[int | None, Query()] = None,
    load_type: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    created_after: Annotated[str | None, Query()] = None,
    created_before: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    f = _parse_filters(
        geometry_id=geometry_id,
        filename=filename,
        analysis_type=analysis_type,
        material_name=material_name,
        mesh_es_min=mesh_es_min,
        mesh_es_max=mesh_es_max,
        youngs_min=youngs_min,
        youngs_max=youngs_max,
        max_disp_min=max_disp_min,
        max_disp_max=max_disp_max,
        max_vm_min=max_vm_min,
        max_vm_max=max_vm_max,
        fixed_face_id=fixed_face_id,
        load_type=load_type,
        status=status,
        created_after=created_after,
        created_before=created_before,
        limit=limit,
        offset=offset,
    )
    items, total = list_analyses(f)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/analyses/export")
def dataset_export_csv(
    geometry_id: Annotated[int | None, Query()] = None,
    filename: Annotated[str | None, Query()] = None,
    analysis_type: Annotated[str | None, Query()] = None,
    material_name: Annotated[str | None, Query()] = None,
) -> PlainTextResponse:
    f = _parse_filters(
        geometry_id=geometry_id,
        filename=filename,
        analysis_type=analysis_type,
        material_name=material_name,
    )
    csv_text = export_dataset_csv(f)
    return PlainTextResponse(
        csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=crash_dataset.csv"},
    )


@router.get("/analyses/{analysis_id}")
def dataset_analysis_detail(analysis_id: int) -> dict:
    detail = get_analysis_detail(analysis_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Analiz bulunamadi.")
    return detail


@router.get("/analyses/{analysis_id}/result")
def dataset_analysis_result(analysis_id: int) -> dict:
    result = get_analysis_result(analysis_id)
    if not result:
        raise HTTPException(status_code=404, detail="Sonuc bulunamadi.")
    return result


@router.delete("/analyses/{analysis_id}")
def dataset_delete_analysis(analysis_id: int) -> dict:
    if not delete_analysis(analysis_id):
        raise HTTPException(status_code=404, detail="Analiz bulunamadi.")
    return {"ok": True, "id": analysis_id}


@router.post("/sweep")
async def dataset_sweep(
    file: UploadFile = File(...),
    setup: str = Form(...),
    element_sizes: str = Form(...),  # JSON list: [2.0, 4.0, 8.0]
    notes: str = Form(""),
) -> dict:
    """Ayni model + BC ile birden fazla eleman boyutunda cozum uretir (surrogate veri)."""
    filename = file.filename or "model.step"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Gecersiz dosya uzantisi.")

    try:
        model_setup = ModelSetup.model_validate_json(setup)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"Gecersiz kurulum: {exc}")

    import json as _json

    try:
        sizes = _json.loads(element_sizes)
        if not isinstance(sizes, list) or not sizes:
            raise ValueError("element_sizes bos liste olamaz")
        sizes = [float(s) for s in sizes]
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"element_sizes JSON list olmali: {exc}")

    if not model_setup.constraints:
        raise HTTPException(status_code=422, detail="En az bir mesnet gerekli.")

    data = await file.read()
    if len(data) == 0 or len(data) > _MAX_BYTES:
        raise HTTPException(status_code=400, detail="Dosya boyutu gecersiz.")

    tmp_path = None
    created: list[dict] = []
    errors: list[dict] = []
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(data)
            tmp_path = tmp.name

        for es in sizes:
            size = es if es > 0 else None
            try:
                payload = await run_in_threadpool(_solve, tmp_path, model_setup, size)
                aid = save_analysis_run(
                    data,
                    filename,
                    model_setup,
                    "static_linear",
                    payload,
                    mesh_element_size=es,
                    notes=notes or f"sweep h={es}",
                )
                created.append(
                    {"analysisId": aid, "elementSize": es, "maxDisp": payload["maxDisp"], "maxVonMises": payload["maxVonMises"]}
                )
            except Exception as exc:  # noqa: BLE001
                errors.append({"elementSize": es, "error": str(exc)})
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    return {"created": created, "errors": errors, "count": len(created)}
