"""Ince cidarli (sabit kalinlikli) parcalar icin orta yuzey (midsurface) cikarimi.

Yontem: yuzey-eslestirme (face pairing). Birbirine paralel, ters yonlu, lateral
olarak ortusen ve aralarinda kucuk bir mesafe (kalinlik t) bulunan PLANAR yuzey
ciftleri bulunur. Her cift icin yuzeylerden biri t/2 kadar otelenerek orta yuzey
olusturulur ve kalinlik t kaydedilir.

Sinirlamalar (acik kaynak, MVP):
- Yalnizca duzlemsel (planar) duvarlar desteklenir; egri (silindir vb.) duvarlar
  henuz desteklenmez.
- Sabit/yaklasik sabit kalinlik varsayilir.
- Karmasik topolojide (cok sayida kesisme) orta yuzeyler ayri yuzeyler olarak
  uretilir; kesisim cizgilerinde otomatik birlestirme/uzatma yapilmaz.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from OCP.STEPControl import STEPControl_Reader, STEPControl_Writer, STEPControl_AsIs
from OCP.IFSelect import IFSelect_RetDone
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE
from OCP.TopoDS import TopoDS, TopoDS_Face, TopoDS_Compound
from OCP.BRep import BRep_Builder
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Plane
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.gp import gp_Trsf, gp_Vec, gp_Pnt, gp_Dir
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform


@dataclass
class _PlanarFace:
    face: TopoDS_Face
    origin: gp_Pnt
    normal: gp_Dir
    centroid: gp_Pnt
    area: float


@dataclass
class MidsurfacePair:
    thickness: float
    area: float


@dataclass
class MidsurfaceResult:
    shape: TopoDS_Compound
    pairs: list[MidsurfacePair]

    @property
    def surface_count(self) -> int:
        return len(self.pairs)

    @property
    def avg_thickness(self) -> float:
        if not self.pairs:
            return 0.0
        return sum(p.thickness for p in self.pairs) / len(self.pairs)


def _read_shape(path: str):
    reader = STEPControl_Reader()
    if reader.ReadFile(path) != IFSelect_RetDone:
        raise ValueError("STEP dosyasi okunamadi.")
    reader.TransferRoots()
    shape = reader.OneShape()
    if shape.IsNull():
        raise ValueError("STEP dosyasinda gecerli kati bulunamadi.")
    return shape


def _collect_planar_faces(shape) -> list[_PlanarFace]:
    faces: list[_PlanarFace] = []
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        face = TopoDS.Face_s(exp.Current())
        adaptor = BRepAdaptor_Surface(face)
        if adaptor.GetType() == GeomAbs_Plane:
            pln = adaptor.Plane()
            props = GProp_GProps()
            BRepGProp.SurfaceProperties_s(face, props)
            faces.append(
                _PlanarFace(
                    face=face,
                    origin=pln.Location(),
                    normal=pln.Axis().Direction(),
                    centroid=props.CentreOfMass(),
                    area=float(props.Mass()),
                )
            )
        exp.Next()
    return faces


def _vec(a: gp_Pnt, b: gp_Pnt) -> tuple[float, float, float]:
    return (b.X() - a.X(), b.Y() - a.Y(), b.Z() - a.Z())


def extract_midsurface(
    path: str,
    max_thickness_ratio: float = 0.5,
    area_ratio_tol: float = 0.35,
    lateral_tol_ratio: float = 0.3,
) -> MidsurfaceResult:
    """Orta yuzeyleri cikarir.

    max_thickness_ratio: t < ratio * sqrt(min_area) ise "ince" sayilir.
    area_ratio_tol: iki yuzeyin alanlari birbirine yakin olmali (|1 - a/b| < tol).
    lateral_tol_ratio: yuzeylerin lateral (duzlem ici) kaymasi sqrt(area)'nin bu
      orani kadarini gecmemeli.
    """
    shape = _read_shape(path)
    planar = _collect_planar_faces(shape)

    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)

    pairs: list[MidsurfacePair] = []
    used: set[int] = set()

    for i in range(len(planar)):
        if i in used:
            continue
        fi = planar[i]
        ni = (fi.normal.X(), fi.normal.Y(), fi.normal.Z())

        best_j = -1
        best_t = math.inf
        for j in range(i + 1, len(planar)):
            if j in used:
                continue
            fj = planar[j]
            nj = (fj.normal.X(), fj.normal.Y(), fj.normal.Z())

            dot = ni[0] * nj[0] + ni[1] * nj[1] + ni[2] * nj[2]
            if abs(dot) < 0.985:  # paralel degil
                continue

            # alan benzerligi
            amin, amax = min(fi.area, fj.area), max(fi.area, fj.area)
            if amax <= 0 or (1.0 - amin / amax) > area_ratio_tol:
                continue

            d = _vec(fi.centroid, fj.centroid)
            t = abs(d[0] * ni[0] + d[1] * ni[1] + d[2] * ni[2])  # normal yonunde mesafe
            if t < 1e-6:
                continue

            # lateral kayma (duzlem icindeki bilesen)
            lateral = math.sqrt(
                max(
                    (d[0] ** 2 + d[1] ** 2 + d[2] ** 2) - t * t,
                    0.0,
                )
            )
            char = math.sqrt(amin)
            if t > max_thickness_ratio * char:
                continue
            if lateral > lateral_tol_ratio * char:
                continue

            if t < best_t:
                best_t = t
                best_j = j

        if best_j >= 0:
            fj = planar[best_j]
            # daha buyuk yuzeyi taban al, t/2 kadar diger yuzeye dogru otele
            base = fi if fi.area >= fj.area else fj
            base_n = (base.normal.X(), base.normal.Y(), base.normal.Z())
            d = _vec(base.centroid, (fj.centroid if base is fi else fi.centroid))
            sign = 1.0 if (d[0] * base_n[0] + d[1] * base_n[1] + d[2] * base_n[2]) > 0 else -1.0
            shift = sign * best_t / 2.0

            trsf = gp_Trsf()
            trsf.SetTranslation(gp_Vec(base_n[0] * shift, base_n[1] * shift, base_n[2] * shift))
            mid_face = BRepBuilderAPI_Transform(base.face, trsf, True).Shape()
            builder.Add(compound, mid_face)

            pairs.append(MidsurfacePair(thickness=best_t, area=base.area))
            used.add(i)
            used.add(best_j)

    if not pairs:
        raise ValueError(
            "Orta yuzey cikarilamadi. Parca ince cidarli/sabit kalinlikli planar "
            "duvarlardan olusmuyor olabilir (egri duvarlar henuz desteklenmiyor)."
        )

    return MidsurfaceResult(shape=compound, pairs=pairs)


def write_step(shape, path: str) -> None:
    writer = STEPControl_Writer()
    writer.Transfer(shape, STEPControl_AsIs)
    if writer.Write(path) != IFSelect_RetDone:
        raise ValueError("Orta yuzey STEP olarak yazilamadi.")
