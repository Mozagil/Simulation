"""Gmsh ile STEP geometrisinden sonlu eleman mesh'i uretir.

Faz 2: yuzey (2D, ucgen) veya hacim (3D, tetrahedra) mesh'i. Gorsellestirme
icin yuzey ucgenleri (boundary) dondurulur; istatistikler dugum/eleman sayisini
icerir.

Gmsh global durum tutar ve thread-safe degildir; bu yuzden tum cagrilar bir
kilit ile seri hale getirilir.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

import gmsh

_GMSH_LOCK = threading.Lock()

# Gmsh eleman tipleri
_ELEM_LINE = 1
_ELEM_TRIANGLE = 2
_ELEM_QUAD = 3
_ELEM_TETRA = 4


def init_gmsh() -> None:
    """Gmsh'i (ana thread'de) bir kez baslatir. initialize() signal handler
    kurdugu icin worker thread'de cagrilamaz; bu yuzden uygulama acilisinda
    cagrilir ve her istekte clear()/open() kullanilir.
    """
    if not gmsh.isInitialized():
        gmsh.initialize()
        gmsh.option.setNumber("General.Terminal", 0)


def shutdown_gmsh() -> None:
    if gmsh.isInitialized():
        gmsh.finalize()


@dataclass
class MeshResult:
    positions: list[float] = field(default_factory=list)  # dolgu ucgenleri, 9 float/ucgen
    edges: list[float] = field(default_factory=list)  # eleman kenarlari, 6 float/segment
    node_count: int = 0
    triangle_count: int = 0
    quad_count: int = 0
    tetra_count: int = 0
    element_size: float = 0.0
    dim: int = 3
    recombine: bool = False
    bbox_min: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    bbox_max: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])

    def to_dict(self) -> dict[str, Any]:
        return {
            "positions": self.positions,
            "edges": self.edges,
            "nodeCount": self.node_count,
            "triangleCount": self.triangle_count,
            "quadCount": self.quad_count,
            "tetraCount": self.tetra_count,
            "elementSize": self.element_size,
            "dim": self.dim,
            "recombine": self.recombine,
            "bboxMin": self.bbox_min,
            "bboxMax": self.bbox_max,
        }


def generate_mesh(
    path: str,
    element_size: float | None = None,
    dim: int = 3,
    recombine: bool = False,
) -> MeshResult:
    """STEP dosyasini okuyup mesh uretir.

    element_size None ise bounding box koseginin ~%5'i secilir.
    dim: 2 (yuzey) veya 3 (hacim).
    recombine: True ise (yalnizca dim=2) ucgenler dortgene (quad) donusturulur.
    """
    if dim not in (2, 3):
        raise ValueError("dim yalnizca 2 (yuzey) veya 3 (hacim) olabilir.")

    use_quad = recombine and dim == 2

    with _GMSH_LOCK:
        init_gmsh()
        try:
            gmsh.clear()
            gmsh.open(path)

            xmin, ymin, zmin, xmax, ymax, zmax = gmsh.model.getBoundingBox(-1, -1)
            diag = ((xmax - xmin) ** 2 + (ymax - ymin) ** 2 + (zmax - zmin) ** 2) ** 0.5
            if element_size is None or element_size <= 0:
                element_size = max(diag * 0.05, 1e-3)

            gmsh.option.setNumber("Mesh.MeshSizeMax", element_size)
            gmsh.option.setNumber("Mesh.MeshSizeMin", element_size * 0.1)
            # CAD egriliginden otomatik boyutlandirma
            gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 12)

            # RecombineAll opsiyonu istekler arasinda kalici oldugu icin her
            # seferinde acikca ayarlanir (aksi halde quad ayari sonraki tri
            # istegine sizar).
            gmsh.option.setNumber("Mesh.RecombineAll", 1 if use_quad else 0)
            if use_quad:
                # blossom = yuksek kalite dortgenlestirme
                gmsh.option.setNumber("Mesh.RecombinationAlgorithm", 1)

            gmsh.model.mesh.generate(dim)

            node_tags, node_coords, _ = gmsh.model.mesh.getNodes()
            coord_by_tag: dict[int, tuple[float, float, float]] = {}
            for i, tag in enumerate(node_tags):
                coord_by_tag[int(tag)] = (
                    node_coords[3 * i],
                    node_coords[3 * i + 1],
                    node_coords[3 * i + 2],
                )

            result = MeshResult(
                node_count=len(node_tags),
                element_size=float(element_size),
                dim=dim,
                recombine=use_quad,
                bbox_min=[xmin, ymin, zmin],
                bbox_max=[xmax, ymax, zmax],
            )

            edge_set: set[tuple[int, int]] = set()

            def add_edge(a: int, b: int) -> None:
                key = (a, b) if a < b else (b, a)
                if key in edge_set:
                    return
                edge_set.add(key)
                result.edges.extend(coord_by_tag[a])
                result.edges.extend(coord_by_tag[b])

            # Yuzey ucgenleri (dolgu + kenar)
            tri = _elements_of_type(_ELEM_TRIANGLE)
            for j in range(0, len(tri), 3):
                a, b, c = int(tri[j]), int(tri[j + 1]), int(tri[j + 2])
                for n in (a, b, c):
                    result.positions.extend(coord_by_tag[n])
                add_edge(a, b)
                add_edge(b, c)
                add_edge(c, a)
            result.triangle_count = len(tri) // 3

            # Yuzey dortgenleri (dolgu icin iki ucgene bolunur + kenar)
            quad = _elements_of_type(_ELEM_QUAD)
            for j in range(0, len(quad), 4):
                a, b, c, d = (
                    int(quad[j]),
                    int(quad[j + 1]),
                    int(quad[j + 2]),
                    int(quad[j + 3]),
                )
                for n in (a, b, c):
                    result.positions.extend(coord_by_tag[n])
                for n in (a, c, d):
                    result.positions.extend(coord_by_tag[n])
                add_edge(a, b)
                add_edge(b, c)
                add_edge(c, d)
                add_edge(d, a)
            result.quad_count = len(quad) // 4

            if dim == 3:
                tet_node_tags = _elements_of_type(_ELEM_TETRA)
                result.tetra_count = len(tet_node_tags) // 4

            if not result.positions:
                raise ValueError("Mesh uretildi fakat yuzey elemani bulunamadi.")

            return result
        finally:
            gmsh.clear()


def _elements_of_type(elem_type: int) -> list[int]:
    """Verilen tipteki tum elemanlarin dugum etiketlerini duz liste olarak doner."""
    try:
        _tags, node_tags = gmsh.model.mesh.getElementsByType(elem_type)
        return list(node_tags)
    except Exception:  # noqa: BLE001 - tip yoksa gmsh hata atabilir
        return []
