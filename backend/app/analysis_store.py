"""Analiz veri seti: geometri kaydi, cozum saklama, filtreleme ve ML export."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, joinedload

from .database import SessionLocal, get_geom_dir, init_db
from .db_models import AnalysisRecord, AnalysisResultRecord, GeometryRecord
from .models import ModelSetup
from .step_loader import load_step_tessellation


def ensure_db() -> None:
    init_db()


@dataclass
class AnalysisFilters:
    geometry_id: int | None = None
    filename_contains: str | None = None
    analysis_type: str | None = None
    material_name: str | None = None
    mesh_element_size_min: float | None = None
    mesh_element_size_max: float | None = None
    youngs_min: float | None = None
    youngs_max: float | None = None
    max_disp_min: float | None = None
    max_disp_max: float | None = None
    max_vm_min: float | None = None
    max_vm_max: float | None = None
    fixed_face_id: int | None = None
    load_type: str | None = None
    status: str | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    limit: int = 200
    offset: int = 0


def _file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _diag(bmin: list[float], bmax: list[float]) -> float:
    return math.hypot(bmax[0] - bmin[0], bmax[1] - bmin[1], bmax[2] - bmin[2])


def _get_or_create_geometry(session: Session, file_bytes: bytes, filename: str) -> GeometryRecord:
    h = _file_hash(file_bytes)
    existing = session.execute(
        select(GeometryRecord).where(GeometryRecord.file_hash == h)
    ).scalar_one_or_none()
    if existing:
        return existing

    ext = Path(filename).suffix.lower() or ".step"
    geom = GeometryRecord(filename=filename, file_hash=h, stored_path="")
    session.add(geom)
    session.flush()

    path = get_geom_dir() / f"{geom.id}{ext}"
    path.write_bytes(file_bytes)
    geom.stored_path = str(path)

    tess = load_step_tessellation(str(path))
    geom.face_count = len(tess.faces)
    geom.triangle_count = tess.triangle_count
    geom.bbox_min_x, geom.bbox_min_y, geom.bbox_min_z = tess.bbox_min
    geom.bbox_max_x, geom.bbox_max_y, geom.bbox_max_z = tess.bbox_max
    geom.diag_mm = _diag(tess.bbox_min, tess.bbox_max)
    return geom


def _setup_summaries(setup: ModelSetup) -> tuple[str, str, float]:
    fixed = sorted({c.face_id for c in setup.constraints if c.type == "fixed"})
    fixed_str = ",".join(str(x) for x in fixed)
    load_types = sorted({lo.type for lo in setup.loads})
    load_str = ",".join(load_types)
    fx = sum(lo.fx for lo in setup.loads if lo.type == "force")
    fy = sum(lo.fy for lo in setup.loads if lo.type == "force")
    fz = sum(lo.fz for lo in setup.loads if lo.type == "force")
    mag = math.sqrt(fx * fx + fy * fy + fz * fz)
    return fixed_str, load_str, mag


def save_analysis_run(
    file_bytes: bytes,
    filename: str,
    setup: ModelSetup,
    analysis_type: str,
    result_dict: dict[str, Any],
    *,
    mesh_element_size: float = 0.0,
    mesh_dim: int = 3,
    status: str = "completed",
    error_detail: str | None = None,
    notes: str | None = None,
) -> int:
    """Cozum sonucunu veritabanina yazar; analysis id dondurur."""
    ensure_db()
    fixed_str, load_str, force_mag = _setup_summaries(setup)
    with SessionLocal() as session:
        geom = _get_or_create_geometry(session, file_bytes, filename)
        row = AnalysisRecord(
            geometry_id=geom.id,
            analysis_type=analysis_type,
            status=status,
            mesh_element_size=float(result_dict.get("elementSize", mesh_element_size) or 0),
            mesh_dim=mesh_dim,
            node_count=int(result_dict.get("nodeCount", 0)),
            tet_count=int(result_dict.get("tetCount", 0)),
            material_name=setup.material.name,
            youngs_modulus=setup.material.youngs_modulus,
            poisson_ratio=setup.material.poisson_ratio,
            density=setup.material.density,
            constraint_count=len(setup.constraints),
            load_count=len(setup.loads),
            fixed_face_ids=fixed_str,
            load_types=load_str,
            total_force_mag=force_mag,
            setup_json=setup.model_dump_json(),
            max_disp=float(result_dict.get("maxDisp", 0)),
            max_von_mises=float(result_dict.get("maxVonMises", 0)),
            error_detail=error_detail,
            notes=notes,
        )
        session.add(row)
        session.flush()
        session.add(
            AnalysisResultRecord(
                analysis_id=row.id,
                result_json=json.dumps(result_dict),
            )
        )
        session.commit()
        return row.id


def _apply_filters(stmt: Select, f: AnalysisFilters):
    if f.geometry_id is not None:
        stmt = stmt.where(AnalysisRecord.geometry_id == f.geometry_id)
    if f.analysis_type:
        stmt = stmt.where(AnalysisRecord.analysis_type == f.analysis_type)
    if f.material_name:
        stmt = stmt.where(AnalysisRecord.material_name == f.material_name)
    if f.status:
        stmt = stmt.where(AnalysisRecord.status == f.status)
    if f.mesh_element_size_min is not None:
        stmt = stmt.where(AnalysisRecord.mesh_element_size >= f.mesh_element_size_min)
    if f.mesh_element_size_max is not None:
        stmt = stmt.where(AnalysisRecord.mesh_element_size <= f.mesh_element_size_max)
    if f.youngs_min is not None:
        stmt = stmt.where(AnalysisRecord.youngs_modulus >= f.youngs_min)
    if f.youngs_max is not None:
        stmt = stmt.where(AnalysisRecord.youngs_modulus <= f.youngs_max)
    if f.max_disp_min is not None:
        stmt = stmt.where(AnalysisRecord.max_disp >= f.max_disp_min)
    if f.max_disp_max is not None:
        stmt = stmt.where(AnalysisRecord.max_disp <= f.max_disp_max)
    if f.max_vm_min is not None:
        stmt = stmt.where(AnalysisRecord.max_von_mises >= f.max_vm_min)
    if f.max_vm_max is not None:
        stmt = stmt.where(AnalysisRecord.max_von_mises <= f.max_vm_max)
    if f.fixed_face_id is not None:
        fid = str(f.fixed_face_id)
        stmt = stmt.where(
            or_(
                AnalysisRecord.fixed_face_ids == fid,
                AnalysisRecord.fixed_face_ids.like(f"{fid},%"),
                AnalysisRecord.fixed_face_ids.like(f"%,{fid},%"),
                AnalysisRecord.fixed_face_ids.like(f"%,{fid}"),
            )
        )
    if f.load_type:
        stmt = stmt.where(AnalysisRecord.load_types.contains(f.load_type))
    if f.created_after:
        stmt = stmt.where(AnalysisRecord.created_at >= f.created_after)
    if f.created_before:
        stmt = stmt.where(AnalysisRecord.created_at <= f.created_before)
    return stmt


def list_analyses(f: AnalysisFilters) -> tuple[list[dict[str, Any]], int]:
    ensure_db()
    with SessionLocal() as session:
        base = (
            select(AnalysisRecord)
            .join(GeometryRecord)
            .options(joinedload(AnalysisRecord.geometry))
            .order_by(AnalysisRecord.created_at.desc())
        )
        if f.filename_contains:
            base = base.where(
                GeometryRecord.filename.ilike(f"%{f.filename_contains}%")
            )
        base = _apply_filters(base, f)

        count_stmt = select(func.count()).select_from(base.subquery())
        total = session.execute(count_stmt).scalar_one()

        rows = session.execute(base.limit(f.limit).offset(f.offset)).scalars().all()
        return [_analysis_summary(r) for r in rows], total


def list_geometries() -> list[dict[str, Any]]:
    ensure_db()
    with SessionLocal() as session:
        rows = session.execute(
            select(GeometryRecord).order_by(GeometryRecord.created_at.desc())
        ).scalars().all()
        out = []
        for g in rows:
            cnt = session.execute(
                select(func.count()).where(AnalysisRecord.geometry_id == g.id)
            ).scalar_one()
            out.append(
                {
                    "id": g.id,
                    "filename": g.filename,
                    "faceCount": g.face_count,
                    "triangleCount": g.triangle_count,
                    "bboxMin": [g.bbox_min_x, g.bbox_min_y, g.bbox_min_z],
                    "bboxMax": [g.bbox_max_x, g.bbox_max_y, g.bbox_max_z],
                    "diagMm": g.diag_mm,
                    "analysisCount": cnt,
                    "createdAt": g.created_at.isoformat(),
                }
            )
        return out


def get_analysis_detail(analysis_id: int) -> dict[str, Any] | None:
    ensure_db()
    with SessionLocal() as session:
        row = session.execute(
            select(AnalysisRecord)
            .where(AnalysisRecord.id == analysis_id)
            .options(joinedload(AnalysisRecord.geometry))
        ).scalar_one_or_none()
        if not row:
            return None
        d = _analysis_summary(row)
        d["setup"] = json.loads(row.setup_json)
        d["notes"] = row.notes
        d["errorDetail"] = row.error_detail
        return d


def get_analysis_result(analysis_id: int) -> dict[str, Any] | None:
    ensure_db()
    with SessionLocal() as session:
        res = session.execute(
            select(AnalysisResultRecord).where(
                AnalysisResultRecord.analysis_id == analysis_id
            )
        ).scalar_one_or_none()
        if not res:
            return None
        return json.loads(res.result_json)


def delete_analysis(analysis_id: int) -> bool:
    ensure_db()
    with SessionLocal() as session:
        row = session.get(AnalysisRecord, analysis_id)
        if not row:
            return False
        session.delete(row)
        session.commit()
        return True


def get_filter_options() -> dict[str, Any]:
    """Raporlama UI icin benzersiz filtre secenekleri."""
    ensure_db()
    with SessionLocal() as session:
        types = session.execute(
            select(AnalysisRecord.analysis_type).distinct()
        ).scalars().all()
        materials = session.execute(
            select(AnalysisRecord.material_name).distinct()
        ).scalars().all()
        load_types = session.execute(
            select(AnalysisRecord.load_types).distinct()
        ).scalars().all()
        lt_set: set[str] = set()
        for s in load_types:
            if s:
                lt_set.update(x.strip() for x in s.split(",") if x.strip())
        return {
            "analysisTypes": sorted(t for t in types if t),
            "materialNames": sorted(m for m in materials if m),
            "loadTypes": sorted(lt_set),
        }


def export_dataset_csv(f: AnalysisFilters) -> str:
    """Surrogate regression icin duz CSV: girdiler + hedefler."""
    rows, _ = list_analyses(AnalysisFilters(**{**f.__dict__, "limit": 10_000, "offset": 0}))
    header = [
        "analysis_id",
        "geometry_id",
        "filename",
        "created_at",
        "analysis_type",
        "mesh_element_size",
        "youngs_modulus",
        "poisson_ratio",
        "density",
        "constraint_count",
        "load_count",
        "fixed_face_ids",
        "load_types",
        "total_force_mag",
        "node_count",
        "tet_count",
        "max_disp",
        "max_von_mises",
        "diag_mm",
        "face_count",
    ]
    def _cell(v: Any) -> str:
        s = str(v if v is not None else "")
        if "," in s or '"' in s:
            return '"' + s.replace('"', '""') + '"'
        return s

    lines = [",".join(header)]
    for r in rows:
        lines.append(",".join(_cell(r.get(k, "")) for k in header))
    return "\n".join(lines) + "\n"


def _analysis_summary(row: AnalysisRecord) -> dict[str, Any]:
    g = row.geometry
    return {
        "id": row.id,
        "geometryId": row.geometry_id,
        "filename": g.filename if g else "",
        "createdAt": row.created_at.isoformat(),
        "analysisType": row.analysis_type,
        "status": row.status,
        "meshElementSize": row.mesh_element_size,
        "meshDim": row.mesh_dim,
        "materialName": row.material_name,
        "youngsModulus": row.youngs_modulus,
        "poissonRatio": row.poisson_ratio,
        "density": row.density,
        "constraintCount": row.constraint_count,
        "loadCount": row.load_count,
        "fixedFaceIds": row.fixed_face_ids,
        "loadTypes": row.load_types,
        "totalForceMag": row.total_force_mag,
        "nodeCount": row.node_count,
        "tetCount": row.tet_count,
        "maxDisp": row.max_disp,
        "maxVonMises": row.max_von_mises,
        "faceCount": g.face_count if g else 0,
        "diagMm": g.diag_mm if g else 0,
        "bboxMin": [g.bbox_min_x, g.bbox_min_y, g.bbox_min_z] if g else [0, 0, 0],
        "bboxMax": [g.bbox_max_x, g.bbox_max_y, g.bbox_max_z] if g else [0, 0, 0],
    }
