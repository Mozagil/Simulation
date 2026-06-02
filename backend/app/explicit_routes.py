"""Faz 6 API: OpenRadioss explicit crash analizi."""

from __future__ import annotations

import os
import tempfile

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from .analysis_store import save_analysis_run
from .explicit import run_explicit
from .models import ExplicitParams, ModelSetup
from .radioss_runner import openradioss_status

router = APIRouter(prefix="/api/explicit", tags=["explicit"])

_ALLOWED = {".step", ".stp"}
_MAX_BYTES = 100 * 1024 * 1024


@router.get("/status")
def explicit_status() -> dict:
    return openradioss_status()


@router.post("/run")
async def explicit_run(
    file: UploadFile = File(...),
    setup: str = Form(...),
    element_size: float = Form(0.0),
) -> dict:
    filename = file.filename or "model.step"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in _ALLOWED:
        raise HTTPException(status_code=400, detail="Gecersiz dosya uzantisi.")

    try:
        model_setup = ModelSetup.model_validate_json(setup)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"Gecersiz kurulum: {exc}")

    if not model_setup.constraints:
        raise HTTPException(status_code=422, detail="En az bir sabit mesnet gerekli.")

    params = model_setup.explicit or ExplicitParams()
    model_setup.explicit = params

    data = await file.read()
    if not data or len(data) > _MAX_BYTES:
        raise HTTPException(status_code=400, detail="Dosya boyutu gecersiz.")

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(data)
            tmp_path = tmp.name

        size = element_size if element_size and element_size > 0 else None

        def _run():
            return run_explicit(
                tmp_path,
                model_setup.material,
                model_setup.constraints,
                model_setup.loads,
                params,
                size,
                model_setup.keyword_blocks or None,
            )

        result = await run_in_threadpool(_run)
        payload = result.to_dict()
        aid = save_analysis_run(
            data,
            filename,
            model_setup,
            "explicit_openradioss",
            payload,
            mesh_element_size=payload.get("elementSize", 0),
            notes=f"explicit t_end={params.end_time_ms}ms",
        )
        payload["filename"] = filename
        payload["analysisId"] = aid
        return payload
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Explicit hatasi: {exc}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
