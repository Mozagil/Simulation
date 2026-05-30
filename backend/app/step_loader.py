"""STEP dosyasini OpenCASCADE (OCP) ile okuyup web viewport icin
ucgenlestirilmis (tessellated) geometriye donusturur.

Her yuzeye (B-Rep face) stabil bir `face_id` atanir ve her ucgenin
hangi yuzeye ait oldugu `triangle_face_ids` dizisinde tutulur. Bu sayede
frontend tarafindaki raycaster ile tiklanan ucgen -> yuzey eslemesi yapilir.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

from OCP.STEPControl import STEPControl_Reader
from OCP.IFSelect import IFSelect_RetDone
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
from OCP.TopoDS import TopoDS, TopoDS_Face
from OCP.TopLoc import TopLoc_Location
from OCP.BRep import BRep_Tool
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import (
    GeomAbs_Plane,
    GeomAbs_Cylinder,
    GeomAbs_Cone,
    GeomAbs_Sphere,
    GeomAbs_Torus,
    GeomAbs_BezierSurface,
    GeomAbs_BSplineSurface,
    GeomAbs_SurfaceOfRevolution,
    GeomAbs_SurfaceOfExtrusion,
    GeomAbs_OffsetSurface,
    GeomAbs_OtherSurface,
)
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib


_SURFACE_TYPES = {
    GeomAbs_Plane: "plane",
    GeomAbs_Cylinder: "cylinder",
    GeomAbs_Cone: "cone",
    GeomAbs_Sphere: "sphere",
    GeomAbs_Torus: "torus",
    GeomAbs_BezierSurface: "bezier",
    GeomAbs_BSplineSurface: "bspline",
    GeomAbs_SurfaceOfRevolution: "revolution",
    GeomAbs_SurfaceOfExtrusion: "extrusion",
    GeomAbs_OffsetSurface: "offset",
    GeomAbs_OtherSurface: "other",
}


@dataclass
class FaceInfo:
    id: int
    surface_type: str
    area: float
    triangle_count: int


@dataclass
class TessellationResult:
    positions: list[float] = field(default_factory=list)  # 9 float / ucgen
    triangle_face_ids: list[int] = field(default_factory=list)  # 1 int / ucgen
    faces: list[FaceInfo] = field(default_factory=list)
    bbox_min: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    bbox_max: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])

    @property
    def triangle_count(self) -> int:
        return len(self.triangle_face_ids)

    def to_dict(self) -> dict[str, Any]:
        return {
            "positions": self.positions,
            "triangleFaceIds": self.triangle_face_ids,
            "faces": [asdict(f) for f in self.faces],
            "bboxMin": self.bbox_min,
            "bboxMax": self.bbox_max,
            "triangleCount": self.triangle_count,
            "faceCount": len(self.faces),
        }


def _surface_type_name(face: TopoDS_Face) -> str:
    adaptor = BRepAdaptor_Surface(face)
    return _SURFACE_TYPES.get(adaptor.GetType(), "other")


def _face_area(face: TopoDS_Face) -> float:
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, props)
    return float(props.Mass())


def load_step_tessellation(
    path: str,
    linear_deflection: float | None = None,
    angular_deflection: float = 0.5,
) -> TessellationResult:
    """STEP dosyasini okuyup ucgenlestirir.

    linear_deflection None ise modelin bounding box buyuklugune gore otomatik
    secilir (daha buyuk modelde daha kaba mesh).
    """
    reader = STEPControl_Reader()
    status = reader.ReadFile(path)
    if status != IFSelect_RetDone:
        raise ValueError("STEP dosyasi okunamadi (gecersiz veya bozuk dosya).")

    reader.TransferRoots()
    shape = reader.OneShape()
    if shape.IsNull():
        raise ValueError("STEP dosyasinda gecerli bir kati/yuzey bulunamadi.")

    # Bounding box -> otomatik deflection ve kamera icin
    bbox = Bnd_Box()
    BRepBndLib.Add_s(shape, bbox)
    xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
    diag = ((xmax - xmin) ** 2 + (ymax - ymin) ** 2 + (zmax - zmin) ** 2) ** 0.5
    if linear_deflection is None:
        linear_deflection = max(diag * 0.001, 1e-3)

    BRepMesh_IncrementalMesh(shape, linear_deflection, False, angular_deflection, True)

    result = TessellationResult(
        bbox_min=[xmin, ymin, zmin],
        bbox_max=[xmax, ymax, zmax],
    )

    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    face_id = 0
    while explorer.More():
        face = TopoDS.Face_s(explorer.Current())
        reversed_orientation = face.Orientation() == TopAbs_REVERSED

        location = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation_s(face, location)

        tri_count = 0
        if triangulation is not None:
            trsf = location.Transformation()
            nb_tri = triangulation.NbTriangles()
            for i in range(1, nb_tri + 1):
                tri = triangulation.Triangle(i)
                n1 = tri.Value(1)
                n2 = tri.Value(2)
                n3 = tri.Value(3)
                if reversed_orientation:
                    n2, n3 = n3, n2

                for n in (n1, n2, n3):
                    p = triangulation.Node(n).Transformed(trsf)
                    result.positions.extend((p.X(), p.Y(), p.Z()))

                result.triangle_face_ids.append(face_id)
                tri_count += 1

        result.faces.append(
            FaceInfo(
                id=face_id,
                surface_type=_surface_type_name(face),
                area=_face_area(face),
                triangle_count=tri_count,
            )
        )

        face_id += 1
        explorer.Next()

    if not result.positions:
        raise ValueError("Geometri ucgenlestirilemedi (bos tessellation).")

    return result
