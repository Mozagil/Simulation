"""FastAPI uygulamasi - Crash/Yapisal Simulasyon platformu backend.

Faz 1: STEP import + ucgenlestirme (per-face id) endpoint'i.
"""

from __future__ import annotations

import os
import tempfile
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

from .analysis_routes import router as dataset_router
from .analysis_store import save_analysis_run
from .database import init_db
from .step_loader import load_step_tessellation
from .mesher import generate_mesh, init_gmsh, shutdown_gmsh
from .midsurface import extract_midsurface, write_step
from .models import ModelSetup, ValidationResult, validate_setup
from .solver import solve_static


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    init_gmsh()
    yield
    shutdown_gmsh()


app = FastAPI(title="Crash Sim Platform API", version="0.2.0", lifespan=lifespan)
app.include_router(dataset_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

_ALLOWED_EXTENSIONS = {".step", ".stp"}
_MAX_BYTES = 100 * 1024 * 1024  # 100 MB


@app.get("/api/health")
def health() -> dict[str, str]:
    from .database import DB_PATH

    return {"status": "ok", "database": str(DB_PATH)}


@app.post("/api/model/validate", response_model=ValidationResult)
def model_validate(setup: ModelSetup) -> ValidationResult:
    return validate_setup(setup)


@app.post("/api/step/tessellate")
async def tessellate_step(file: UploadFile = File(...)) -> dict:
    filename = file.filename or "model.step"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Desteklenmeyen dosya turu: '{ext}'. .step veya .stp bekleniyor.",
        )

    data = await file.read()
    if len(data) == 0:
        raise HTTPException(status_code=400, detail="Bos dosya yuklendi.")
    if len(data) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="Dosya cok buyuk (max 100 MB).")

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(data)
            tmp_path = tmp.name

        result = load_step_tessellation(tmp_path)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Isleme hatasi: {exc}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    payload = result.to_dict()
    payload["filename"] = filename
    return payload


def _midsurface_shell(path: str, element_size: float | None, recombine: bool):
    """Orta yuzey cikar -> temp STEP -> Gmsh 2D shell mesh. (sync, worker thread)"""
    ms = extract_midsurface(path)
    thicknesses = [p.thickness for p in ms.pairs]
    avg_thickness = ms.avg_thickness

    ms_path = None
    try:
        ms_path = tempfile.NamedTemporaryFile(delete=False, suffix=".step").name
        write_step(ms.shape, ms_path)
        mesh = generate_mesh(ms_path, element_size, dim=2, recombine=recombine)
    finally:
        if ms_path and os.path.exists(ms_path):
            try:
                os.remove(ms_path)
            except OSError:
                pass

    payload = mesh.to_dict()
    payload["isShell"] = True
    payload["surfaceCount"] = ms.surface_count
    payload["avgThickness"] = avg_thickness
    payload["thicknesses"] = thicknesses
    return payload


@app.post("/api/midsurface/shell")
async def midsurface_shell(
    file: UploadFile = File(...),
    element_size: float = Form(0.0),
    recombine: bool = Form(False),
) -> dict:
    filename = file.filename or "model.step"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Desteklenmeyen dosya turu: '{ext}'. .step veya .stp bekleniyor.",
        )

    data = await file.read()
    if len(data) == 0:
        raise HTTPException(status_code=400, detail="Bos dosya yuklendi.")
    if len(data) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="Dosya cok buyuk (max 100 MB).")

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(data)
            tmp_path = tmp.name

        size = element_size if element_size and element_size > 0 else None
        payload = await run_in_threadpool(_midsurface_shell, tmp_path, size, recombine)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Midsurface hatasi: {exc}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    payload["filename"] = filename
    return payload


def _solve(path: str, setup: ModelSetup, element_size: float | None):
    result = solve_static(
        path,
        setup.material,
        setup.constraints,
        setup.loads,
        element_size,
    )
    return result.to_dict()


@app.post("/api/solve")
async def solve(
    file: UploadFile = File(...),
    setup: str = Form(...),
    element_size: float = Form(0.0),
) -> dict:
    filename = file.filename or "model.step"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Desteklenmeyen dosya turu: '{ext}'. .step veya .stp bekleniyor.",
        )

    try:
        model_setup = ModelSetup.model_validate_json(setup)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"Gecersiz model kurulumu: {exc}")

    if not model_setup.constraints:
        raise HTTPException(
            status_code=422,
            detail="En az bir sinir kosulu (mesnet) gerekli - aksi halde sistem tekil olur.",
        )

    data = await file.read()
    if len(data) == 0:
        raise HTTPException(status_code=400, detail="Bos dosya yuklendi.")
    if len(data) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="Dosya cok buyuk (max 100 MB).")

    tmp_path = None
    analysis_id: int | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(data)
            tmp_path = tmp.name

        size = element_size if element_size and element_size > 0 else None
        payload = await run_in_threadpool(_solve, tmp_path, model_setup, size)
        analysis_id = await run_in_threadpool(
            save_analysis_run,
            data,
            filename,
            model_setup,
            "static_linear",
            payload,
            mesh_element_size=element_size,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Cozum hatasi: {exc}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    payload["filename"] = filename
    payload["analysisId"] = analysis_id
    return payload


@app.post("/api/mesh/generate")
async def mesh_generate(
    file: UploadFile = File(...),
    element_size: float = Form(0.0),
    dim: int = Form(3),
    recombine: bool = Form(False),
) -> dict:
    filename = file.filename or "model.step"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Desteklenmeyen dosya turu: '{ext}'. .step veya .stp bekleniyor.",
        )
    if dim not in (2, 3):
        raise HTTPException(status_code=400, detail="dim 2 veya 3 olmali.")

    data = await file.read()
    if len(data) == 0:
        raise HTTPException(status_code=400, detail="Bos dosya yuklendi.")
    if len(data) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="Dosya cok buyuk (max 100 MB).")

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(data)
            tmp_path = tmp.name

        size = element_size if element_size and element_size > 0 else None
        result = await run_in_threadpool(generate_mesh, tmp_path, size, dim, recombine)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Mesh hatasi: {exc}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    payload = result.to_dict()
    payload["filename"] = filename
    return payload
