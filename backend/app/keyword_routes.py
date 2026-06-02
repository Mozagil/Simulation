"""Radioss Starter keyword sablonlari ve deck onizleme API."""

from __future__ import annotations

import os
import tempfile

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import PlainTextResponse

from .models import ExplicitParams, KeywordComposeRequest, ModelSetup
from .radioss_keywords import compose_deck, generate_deck_from_model, list_templates

router = APIRouter(prefix="/api/keywords", tags=["keywords"])

_ALLOWED = {".step", ".stp"}
_MAX_BYTES = 100 * 1024 * 1024


@router.get("/templates")
def keyword_templates() -> dict:
    return {"items": list_templates()}


@router.post("/compose")
def keyword_compose(body: KeywordComposeRequest) -> dict:
    deck = compose_deck(body.blocks)
    return {"deck": deck, "blocks": [b.model_dump() for b in body.blocks]}


@router.post("/generate")
async def keyword_generate(
    file: UploadFile = File(...),
    setup: str = Form(...),
    element_size: float = Form(0.0),
    run_name: str = Form("crash"),
) -> dict:
    """STEP + model kurulumundan keyword bloklari ve tam deck uretir."""
    filename = file.filename or "model.step"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in _ALLOWED:
        raise HTTPException(status_code=400, detail="Gecersiz dosya uzantisi.")

    try:
        model_setup = ModelSetup.model_validate_json(setup)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"Gecersiz kurulum: {exc}")

    params = model_setup.explicit or ExplicitParams()
    data = await file.read()
    if not data or len(data) > _MAX_BYTES:
        raise HTTPException(status_code=400, detail="Dosya boyutu gecersiz.")

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(data)
            tmp_path = tmp.name

        size = element_size if element_size and element_size > 0 else None

        def _gen():
            return generate_deck_from_model(
                tmp_path,
                model_setup.material,
                model_setup.constraints,
                model_setup.loads,
                params,
                run_name=run_name,
                element_size=size,
                extra_blocks=model_setup.keyword_blocks or None,
            )

        return await run_in_threadpool(_gen)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Keyword uretim hatasi: {exc}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


@router.post("/export")
def keyword_export(body: KeywordComposeRequest) -> PlainTextResponse:
    deck = compose_deck(body.blocks)
    return PlainTextResponse(
        deck,
        media_type="text/plain",
        headers={"Content-Disposition": "attachment; filename=crash_0000.rad"},
    )
