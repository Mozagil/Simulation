"""Gmsh ile STEP'ten 3B tetra mesh cikarimi (solver + OpenRadioss ortak)."""

from __future__ import annotations

from dataclasses import dataclass

import gmsh
import numpy as np

from .mesher import _GMSH_LOCK, init_gmsh
from .solver import _occt_face_centroids

_ELEM_TRIANGLE = 2
_ELEM_TETRA = 4


@dataclass
class VolumeMesh:
    coords: np.ndarray  # (N, 3)
    tets: np.ndarray  # (E, 4) node indices 0-based
    node_tags: np.ndarray  # gmsh tags (for export)
    bbox_min: list[float]
    bbox_max: list[float]
    element_size: float
    surf_nodes: dict[int, set[int]]
    surf_tris: dict[int, np.ndarray]
    surf_centroid: dict[int, np.ndarray]
    face_centroids: list[np.ndarray]


def mesh_volume_from_step(path: str, element_size: float | None = None) -> VolumeMesh:
    face_centroids = _occt_face_centroids(path)

    with _GMSH_LOCK:
        init_gmsh()
        gmsh.clear()
        gmsh.open(path)

        xmin, ymin, zmin, xmax, ymax, zmax = gmsh.model.getBoundingBox(-1, -1)
        diag = ((xmax - xmin) ** 2 + (ymax - ymin) ** 2 + (zmax - zmin) ** 2) ** 0.5
        if element_size is None or element_size <= 0:
            element_size = max(diag * 0.08, 1e-3)
        gmsh.option.setNumber("Mesh.MeshSizeMax", element_size)
        gmsh.option.setNumber("Mesh.MeshSizeMin", element_size * 0.2)
        gmsh.option.setNumber("Mesh.RecombineAll", 0)
        gmsh.model.mesh.generate(3)

        ntags, ncoords, _ = gmsh.model.mesh.getNodes()
        ntags = ntags.astype(np.int64)
        ncoords = ncoords.reshape(-1, 3)
        tag2idx = {int(t): i for i, t in enumerate(ntags)}

        tet_tags = gmsh.model.mesh.getElementsByType(_ELEM_TETRA)[1].astype(np.int64)
        tets = np.array([tag2idx[int(t)] for t in tet_tags], dtype=np.int64).reshape(-1, 4)
        if tets.shape[0] == 0:
            raise ValueError("Hacim mesh'i uretilemedi (tetrahedra bulunamadi).")

        surf_nodes: dict[int, set[int]] = {}
        surf_tris: dict[int, np.ndarray] = {}
        surf_centroid: dict[int, np.ndarray] = {}
        for dim, tag in gmsh.model.getEntities(2):
            st, _, _ = gmsh.model.mesh.getNodes(dim, tag, includeBoundary=True)
            if len(st) == 0:
                continue
            idxs = {tag2idx[int(t)] for t in st}
            surf_nodes[tag] = idxs
            surf_centroid[tag] = ncoords[list(idxs)].mean(axis=0)
            try:
                tri_tags = gmsh.model.mesh.getElementsByType(_ELEM_TRIANGLE, tag)[1].astype(np.int64)
                surf_tris[tag] = np.array(
                    [tag2idx[int(t)] for t in tri_tags], dtype=np.int64
                ).reshape(-1, 3)
            except Exception:  # noqa: BLE001
                surf_tris[tag] = np.zeros((0, 3), dtype=np.int64)

    return VolumeMesh(
        coords=ncoords,
        tets=tets,
        node_tags=ntags,
        bbox_min=[xmin, ymin, zmin],
        bbox_max=[xmax, ymax, zmax],
        element_size=float(element_size),
        surf_nodes=surf_nodes,
        surf_tris=surf_tris,
        surf_centroid=surf_centroid,
        face_centroids=face_centroids,
    )


def face_to_surface(mesh: VolumeMesh, face_id: int) -> int | None:
    surf_tags = list(mesh.surf_centroid.keys())
    if face_id < 0 or face_id >= len(mesh.face_centroids) or not surf_tags:
        return None
    surf_cs = np.array([mesh.surf_centroid[t] for t in surf_tags])
    d = np.linalg.norm(surf_cs - mesh.face_centroids[face_id], axis=1)
    return surf_tags[int(np.argmin(d))]
