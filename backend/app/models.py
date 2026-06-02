"""Faz 3: Simulasyon kurulumu icin veri modelleri (malzeme, sinir kosullari,
yukler) ve dogrulama mantigi. Bu yapi Faz 4'te CalculiX/OpenRadioss deck
uretiminin girdisini olusturur.
"""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, Field


class Material(BaseModel):
    name: str = "Celik"
    youngs_modulus: float = Field(210000.0, gt=0, description="E [MPa]")
    poisson_ratio: float = Field(0.3, ge=0, lt=0.5, description="Poisson orani")
    density: float = Field(7850.0, gt=0, description="Yogunluk [kg/m^3]")


class Constraint(BaseModel):
    id: str
    face_id: int
    type: Literal["fixed"] = "fixed"


class Load(BaseModel):
    id: str
    face_id: int
    type: Literal["pressure", "force"]
    # pressure: value [MPa] (yuzey normali boyunca, + disari)
    value: float = 0.0
    # force: bilesenler [N] (yuzeye dagitilir)
    fx: float = 0.0
    fy: float = 0.0
    fz: float = 0.0


class ExplicitParams(BaseModel):
    """OpenRadioss explicit dynamics parametreleri (Faz 6)."""

    end_time_ms: float = Field(1.0, gt=0, description="Simulasyon suresi [ms]")
    dt_ms: float | None = Field(None, gt=0, description="Sabit zaman adimi [ms]; None=otomatik")
    initial_velocity: list[float] = Field(
        default_factory=lambda: [0.0, 0.0, -5.0],
        min_length=3,
        max_length=3,
        description="Baslangic hizi [mm/ms] (= m/s)",
    )
    gravity: float = Field(0.0, description="Yercekimi ivmesi [mm/ms^2]; 9810 ~ 9.81 m/s^2")
    threads: int = Field(4, ge=1, le=64)
    output_frames: int = Field(20, ge=2, le=200, description="Animasyon kare sayisi hedefi")


class KeywordBlock(BaseModel):
    """OpenRadioss Starter keyword blogu (duzenlenebilir metin)."""

    id: str
    name: str
    category: str = "custom"
    enabled: bool = True
    lines: str


class KeywordComposeRequest(BaseModel):
    blocks: list[KeywordBlock] = Field(default_factory=list)


class ModelSetup(BaseModel):
    material: Material
    constraints: list[Constraint] = Field(default_factory=list)
    loads: list[Load] = Field(default_factory=list)
    explicit: ExplicitParams | None = None
    keyword_blocks: list[KeywordBlock] = Field(default_factory=list)


class ValidationResult(BaseModel):
    ok: bool
    constraint_count: int
    load_count: int
    fixed_faces: list[int]
    loaded_faces: list[int]
    total_force: list[float]  # [Fx, Fy, Fz] N (yalnizca force yuklerinin toplami)
    total_force_magnitude: float
    warnings: list[str]
    errors: list[str]


def validate_setup(setup: ModelSetup) -> ValidationResult:
    warnings: list[str] = []
    errors: list[str] = []

    fixed_faces = [c.face_id for c in setup.constraints if c.type == "fixed"]
    loaded_faces = sorted({lo.face_id for lo in setup.loads})

    fx = sum(lo.fx for lo in setup.loads if lo.type == "force")
    fy = sum(lo.fy for lo in setup.loads if lo.type == "force")
    fz = sum(lo.fz for lo in setup.loads if lo.type == "force")
    mag = math.sqrt(fx * fx + fy * fy + fz * fz)

    if not setup.constraints:
        warnings.append(
            "Hic sinir kosulu (mesnet) yok - statik analiz tekil (singular) olur."
        )
    if not setup.loads:
        warnings.append("Hic yuk tanimlanmadi - cozum sifir deformasyon verir.")

    # Ayni yuzeyde hem fixed hem load cakismasi uyarisi
    overlap = set(fixed_faces) & set(loaded_faces)
    if overlap:
        warnings.append(
            f"Su yuzeylerde hem mesnet hem yuk var: {sorted(overlap)}"
        )

    # Sifir buyuklukte yuk uyarisi
    for lo in setup.loads:
        if lo.type == "pressure" and lo.value == 0.0:
            warnings.append(f"Yuzey {lo.face_id}: basinc degeri sifir.")
        if lo.type == "force" and (lo.fx == 0 and lo.fy == 0 and lo.fz == 0):
            warnings.append(f"Yuzey {lo.face_id}: kuvvet bilesenleri sifir.")

    ok = len(errors) == 0
    return ValidationResult(
        ok=ok,
        constraint_count=len(setup.constraints),
        load_count=len(setup.loads),
        fixed_faces=fixed_faces,
        loaded_faces=loaded_faces,
        total_force=[fx, fy, fz],
        total_force_magnitude=mag,
        warnings=warnings,
        errors=errors,
    )
