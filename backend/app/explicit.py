"""Faz 6: OpenRadioss explicit dynamics entegrasyonu."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from .database import _DATA_DIR
from .models import Constraint, ExplicitParams, Load, Material, ModelSetup
from .models import KeywordBlock
from .radioss_deck import write_starter_deck
from .radioss_keywords import compose_deck
from .radioss_result import ExplicitResult, parse_explicit_results
from .radioss_runner import find_openradioss, run_openradioss
from .volume_mesh import mesh_volume_from_step

_RUNS_DIR = _DATA_DIR / "runs"


def run_explicit(
    step_path: str,
    material: Material,
    constraints: list[Constraint],
    loads: list[Load],
    params: ExplicitParams,
    element_size: float | None = None,
    keyword_blocks: list[KeywordBlock] | None = None,
) -> ExplicitResult:
    if not find_openradioss():
        raise RuntimeError(
            "OpenRadioss kurulu degil. OPENRADIOSS_PATH ortam degiskenini ayarlayin "
            "(ornek: C:\\OpenRadioss). Indirme: https://github.com/OpenRadioss/OpenRadioss/releases"
        )

    mesh = mesh_volume_from_step(step_path, element_size)
    if mesh.coords.shape[0] > 80_000:
        raise ValueError(
            f"Cok fazla dugum ({mesh.coords.shape[0]}). Explicit icin eleman boyutunu buyutun (max ~80k dugum MVP)."
        )

    run_id = uuid.uuid4().hex[:12]
    run_name = "crash"
    work_dir = _RUNS_DIR / run_id
    work_dir.mkdir(parents=True, exist_ok=True)

    extra_lines: list[str] | None = None
    if keyword_blocks:
        extra_text = compose_deck(
            [b for b in keyword_blocks if b.enabled and b.category not in ("header", "mesh")]
        )
        extra_lines = [
            ln
            for ln in extra_text.splitlines()
            if ln.strip() and not ln.strip().startswith("/END")
        ]

    write_starter_deck(
        mesh,
        material,
        constraints,
        loads,
        params,
        work_dir / f"{run_name}_0000.rad",
        run_name=run_name,
        extra_lines_before_end=extra_lines,
    )

    # STEP kopyasi (tekrar calistirma / arsiv)
    try:
        shutil.copy2(step_path, work_dir / "model.step")
    except OSError:
        pass

    _, logs = run_openradioss(work_dir, run_name, threads=params.threads)

    cfg = find_openradioss()
    result = parse_explicit_results(
        work_dir,
        run_name,
        mesh.coords,
        mesh.surf_tris,
        element_size=mesh.element_size,
        bbox_min=mesh.bbox_min,
        bbox_max=mesh.bbox_max,
        tet_count=int(mesh.tets.shape[0]),
        run_logs=logs,
        anim_to_vtk=cfg.anim_to_vtk if cfg else None,
    )
    result.run_logs.append(f"work_dir={work_dir}")
    return result
