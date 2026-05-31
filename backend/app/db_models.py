"""Surrogate / regression veri seti icin kalici ORM modelleri."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class GeometryRecord(Base):
    """STEP dosyasi ve geometri ozet metrikleri (surrogate girdileri icin)."""

    __tablename__ = "geometries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(512), index=True)
    file_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    stored_path: Mapped[str] = mapped_column(String(1024))
    face_count: Mapped[int] = mapped_column(Integer, default=0)
    triangle_count: Mapped[int] = mapped_column(Integer, default=0)
    bbox_min_x: Mapped[float] = mapped_column(Float, default=0.0)
    bbox_min_y: Mapped[float] = mapped_column(Float, default=0.0)
    bbox_min_z: Mapped[float] = mapped_column(Float, default=0.0)
    bbox_max_x: Mapped[float] = mapped_column(Float, default=0.0)
    bbox_max_y: Mapped[float] = mapped_column(Float, default=0.0)
    bbox_max_z: Mapped[float] = mapped_column(Float, default=0.0)
    diag_mm: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    analyses: Mapped[list["AnalysisRecord"]] = relationship(back_populates="geometry")


class AnalysisRecord(Base):
    """Tek bir cozum kosusu: mesh, malzeme, BC, yuk ve ozet sonuclar."""

    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    geometry_id: Mapped[int] = mapped_column(ForeignKey("geometries.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)

    analysis_type: Mapped[str] = mapped_column(String(64), index=True)  # static_linear, ...
    status: Mapped[str] = mapped_column(String(32), default="completed", index=True)

    # Mesh (filtreleme icin duz kolonlar)
    mesh_element_size: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    mesh_dim: Mapped[int] = mapped_column(Integer, default=3)
    node_count: Mapped[int] = mapped_column(Integer, default=0)
    tet_count: Mapped[int] = mapped_column(Integer, default=0)

    # Malzeme ozeti
    material_name: Mapped[str] = mapped_column(String(128), index=True, default="")
    youngs_modulus: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    poisson_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    density: Mapped[float] = mapped_column(Float, default=0.0)

    # Sinir kosulu / yuk ozeti (filtreleme)
    constraint_count: Mapped[int] = mapped_column(Integer, default=0)
    load_count: Mapped[int] = mapped_column(Integer, default=0)
    fixed_face_ids: Mapped[str] = mapped_column(String(512), default="")  # "1,5,12"
    load_types: Mapped[str] = mapped_column(String(128), default="")  # "force,pressure"
    total_force_mag: Mapped[float] = mapped_column(Float, default=0.0)

    # Tam kurulum (JSON)
    setup_json: Mapped[str] = mapped_column(Text, default="{}")

    # Sonuc ozeti (surrogate hedefleri)
    max_disp: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    max_von_mises: Mapped[float] = mapped_column(Float, default=0.0, index=True)

    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(512), nullable=True)

    geometry: Mapped["GeometryRecord"] = relationship(back_populates="analyses")
    result: Mapped["AnalysisResultRecord | None"] = relationship(
        back_populates="analysis", uselist=False, cascade="all, delete-orphan"
    )


class AnalysisResultRecord(Base):
    """Tam cozum vektoru (viewer + ML export)."""

    __tablename__ = "analysis_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_id: Mapped[int] = mapped_column(
        ForeignKey("analyses.id"), unique=True, index=True
    )
    result_json: Mapped[str] = mapped_column(Text)

    analysis: Mapped["AnalysisRecord"] = relationship(back_populates="result")
