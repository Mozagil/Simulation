"""Faz 4: Gomulu lineer-statik FEA cozucusu (4 dugumlu tetrahedra, CST).

Tamamen acik kaynak ve harici binary gerektirmez (numpy + scipy). STEP'i Gmsh
ile 3B tet mesh'e cevirir, secili yuzeyleri (OCCT face_id) mesh yuzeylerine
centroid eslestirmesiyle baglar, sinir kosullari (fixed) ve yukleri (kuvvet/
basinc) uygular, K u = f sistemini cozer ve dugum deplasmani + von Mises
gerilmesi dondurur.

Not: CST tet4 elemani basit ve saglamdir ama gorece "kati" (stiff) davranir;
gercek analiz icin ileride C3D10 (kuadratik tet) veya CalculiX/OpenRadioss
alternatif cozucu olarak eklenebilir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import gmsh
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve

from OCP.STEPControl import STEPControl_Reader
from OCP.IFSelect import IFSelect_RetDone
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE
from OCP.TopoDS import TopoDS
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps

from .mesher import init_gmsh, _GMSH_LOCK
from .models import Material, Constraint, Load

_ELEM_TRIANGLE = 2
_ELEM_TETRA = 4


@dataclass
class SolveResult:
    positions: list[float] = field(default_factory=list)  # yuzey ucgenleri (9/ucgen)
    disp: list[float] = field(default_factory=list)  # dugum deplasman vektoru (9/ucgen)
    disp_mag: list[float] = field(default_factory=list)  # |u| (3/ucgen)
    von_mises: list[float] = field(default_factory=list)  # nodal vM (3/ucgen)
    node_count: int = 0
    tet_count: int = 0
    max_disp: float = 0.0
    max_von_mises: float = 0.0
    element_size: float = 0.0
    bbox_min: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    bbox_max: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])

    def to_dict(self) -> dict[str, Any]:
        return {
            "positions": self.positions,
            "disp": self.disp,
            "dispMag": self.disp_mag,
            "vonMises": self.von_mises,
            "nodeCount": self.node_count,
            "tetCount": self.tet_count,
            "maxDisp": self.max_disp,
            "maxVonMises": self.max_von_mises,
            "elementSize": self.element_size,
            "bboxMin": self.bbox_min,
            "bboxMax": self.bbox_max,
        }


def _occt_face_centroids(path: str) -> list[np.ndarray]:
    reader = STEPControl_Reader()
    if reader.ReadFile(path) != IFSelect_RetDone:
        raise ValueError("STEP okunamadi.")
    reader.TransferRoots()
    shape = reader.OneShape()
    centroids: list[np.ndarray] = []
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        face = TopoDS.Face_s(exp.Current())
        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face, props)
        c = props.CentreOfMass()
        centroids.append(np.array([c.X(), c.Y(), c.Z()]))
        exp.Next()
    return centroids


def _elasticity_matrix(E: float, nu: float) -> np.ndarray:
    f = E / ((1 + nu) * (1 - 2 * nu))
    g = (1 - 2 * nu) / 2
    D = np.array(
        [
            [1 - nu, nu, nu, 0, 0, 0],
            [nu, 1 - nu, nu, 0, 0, 0],
            [nu, nu, 1 - nu, 0, 0, 0],
            [0, 0, 0, g, 0, 0],
            [0, 0, 0, 0, g, 0],
            [0, 0, 0, 0, 0, g],
        ]
    ) * f
    return D


def _tet_B_and_volume(coords: np.ndarray) -> tuple[np.ndarray, float]:
    """coords: (4,3). Doner: B (6x12), V."""
    C = np.ones((4, 4))
    C[:, 1:] = coords
    detC = np.linalg.det(C)
    V = detC / 6.0
    Minv = np.linalg.inv(C)  # satir i: [a_i? ] -> grad N_i = Minv[1:4, i]
    grads = Minv[1:4, :]  # (3,4): grads[:,i] = (dNi/dx, dNi/dy, dNi/dz)

    B = np.zeros((6, 12))
    for i in range(4):
        bx, by, bz = grads[0, i], grads[1, i], grads[2, i]
        c0 = 3 * i
        B[0, c0 + 0] = bx
        B[1, c0 + 1] = by
        B[2, c0 + 2] = bz
        B[3, c0 + 0] = by
        B[3, c0 + 1] = bx
        B[4, c0 + 1] = bz
        B[4, c0 + 2] = by
        B[5, c0 + 0] = bz
        B[5, c0 + 2] = bx
    return B, V


def _von_mises(stress: np.ndarray) -> float:
    sx, sy, sz, txy, tyz, tzx = stress
    return float(
        np.sqrt(
            0.5
            * (
                (sx - sy) ** 2
                + (sy - sz) ** 2
                + (sz - sx) ** 2
                + 6 * (txy**2 + tyz**2 + tzx**2)
            )
        )
    )


def solve_static(
    path: str,
    material: Material,
    constraints: list[Constraint],
    loads: list[Load],
    element_size: float | None = None,
) -> SolveResult:
    face_centroids = _occt_face_centroids(path)

    with _GMSH_LOCK:
        init_gmsh()
        try:
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

            # Dugumler
            ntags, ncoords, _ = gmsh.model.mesh.getNodes()
            ntags = ntags.astype(np.int64)
            ncoords = ncoords.reshape(-1, 3)
            tag2idx = {int(t): i for i, t in enumerate(ntags)}
            n_nodes = len(ntags)
            coords = ncoords  # (N,3)

            # Tetler
            tet_node_tags = gmsh.model.mesh.getElementsByType(_ELEM_TETRA)[1].astype(np.int64)
            tets = np.array([tag2idx[int(t)] for t in tet_node_tags], dtype=np.int64).reshape(-1, 4)
            n_tets = tets.shape[0]
            if n_tets == 0:
                raise ValueError("Hacim mesh'i uretilemedi (tetrahedra bulunamadi).")

            # Yuzeyler: tag -> dugum index seti, ucgenler, centroid
            surf_nodes: dict[int, set[int]] = {}
            surf_tris: dict[int, np.ndarray] = {}
            surf_centroid: dict[int, np.ndarray] = {}
            for dim, tag in gmsh.model.getEntities(2):
                st, sc, _ = gmsh.model.mesh.getNodes(dim, tag, includeBoundary=True)
                if len(st) == 0:
                    continue
                idxs = {tag2idx[int(t)] for t in st}
                surf_nodes[tag] = idxs
                surf_centroid[tag] = coords[list(idxs)].mean(axis=0)
                try:
                    tri_tags = gmsh.model.mesh.getElementsByType(_ELEM_TRIANGLE, tag)[1].astype(np.int64)
                    surf_tris[tag] = np.array([tag2idx[int(t)] for t in tri_tags], dtype=np.int64).reshape(-1, 3)
                except Exception:  # noqa: BLE001
                    surf_tris[tag] = np.zeros((0, 3), dtype=np.int64)
        finally:
            mesh_size = element_size

    # face_id (OCCT) -> gmsh surface tag (en yakin centroid)
    surf_tags = list(surf_centroid.keys())
    surf_cs = np.array([surf_centroid[t] for t in surf_tags]) if surf_tags else np.zeros((0, 3))

    def face_to_surf(face_id: int) -> int | None:
        if face_id < 0 or face_id >= len(face_centroids) or len(surf_tags) == 0:
            return None
        d = np.linalg.norm(surf_cs - face_centroids[face_id], axis=1)
        return surf_tags[int(np.argmin(d))]

    # --- Global stiffness assembly ---
    D = _elasticity_matrix(material.youngs_modulus, material.poisson_ratio)
    n_dof = 3 * n_nodes
    # her tet: 12x12 -> 144 triplet
    rows = np.zeros(n_tets * 144, dtype=np.int64)
    cols = np.zeros(n_tets * 144, dtype=np.int64)
    vals = np.zeros(n_tets * 144, dtype=np.float64)
    Bs: list[np.ndarray] = []
    ptr = 0
    for e in range(n_tets):
        nodes = tets[e]
        ce = coords[nodes]
        B, V = _tet_B_and_volume(ce)
        Bs.append(B)
        Ke = V * (B.T @ D @ B)
        dofs = np.empty(12, dtype=np.int64)
        for a in range(4):
            dofs[3 * a + 0] = 3 * nodes[a]
            dofs[3 * a + 1] = 3 * nodes[a] + 1
            dofs[3 * a + 2] = 3 * nodes[a] + 2
        rr = np.repeat(dofs, 12)
        cc = np.tile(dofs, 12)
        rows[ptr : ptr + 144] = rr
        cols[ptr : ptr + 144] = cc
        vals[ptr : ptr + 144] = Ke.ravel()
        ptr += 144

    K = coo_matrix((vals, (rows, cols)), shape=(n_dof, n_dof)).tocsr()

    # --- Load vector ---
    f = np.zeros(n_dof)
    model_center = coords.mean(axis=0)
    for lo in loads:
        tag = face_to_surf(lo.face_id)
        if tag is None:
            continue
        if lo.type == "force":
            nodes = list(surf_nodes.get(tag, []))
            if not nodes:
                continue
            per = np.array([lo.fx, lo.fy, lo.fz]) / len(nodes)
            for n in nodes:
                f[3 * n : 3 * n + 3] += per
        elif lo.type == "pressure":
            tris = surf_tris.get(tag)
            if tris is None or tris.shape[0] == 0:
                continue
            for tri in tris:
                p0, p1, p2 = coords[tri[0]], coords[tri[1]], coords[tri[2]]
                nrm = np.cross(p1 - p0, p2 - p0)
                area2 = np.linalg.norm(nrm)
                if area2 == 0:
                    continue
                tri_c = (p0 + p1 + p2) / 3
                # disa dogru yonlendir (model merkezinden uzaklasacak sekilde)
                if np.dot(nrm, tri_c - model_center) < 0:
                    nrm = -nrm
                unit = nrm / area2
                area = 0.5 * area2
                nodal = lo.value * area / 3.0 * unit
                for n in tri:
                    f[3 * n : 3 * n + 3] += nodal

    # --- Boundary conditions (fixed) ---
    fixed_dofs: set[int] = set()
    for c in constraints:
        if c.type != "fixed":
            continue
        tag = face_to_surf(c.face_id)
        if tag is None:
            continue
        for n in surf_nodes.get(tag, []):
            fixed_dofs.update((3 * n, 3 * n + 1, 3 * n + 2))

    all_dofs = np.arange(n_dof)
    free = np.setdiff1d(all_dofs, np.array(sorted(fixed_dofs), dtype=np.int64))

    u = np.zeros(n_dof)
    if len(fixed_dofs) == 0 or len(free) == 0:
        # cozulemez; sifir deplasman dondur (uyari frontend/validate'de)
        pass
    else:
        Kff = K[free][:, free]
        ff = f[free]
        uf = spsolve(Kff.tocsc(), ff)
        u[free] = uf

    u_vec = u.reshape(n_nodes, 3)
    disp_mag = np.linalg.norm(u_vec, axis=1)

    # --- Stress recovery (nodal averaging) ---
    nodal_vm = np.zeros(n_nodes)
    nodal_cnt = np.zeros(n_nodes)
    for e in range(n_tets):
        nodes = tets[e]
        ue = u_vec[nodes].ravel()
        strain = Bs[e] @ ue
        stress = D @ strain
        vm = _von_mises(stress)
        for n in nodes:
            nodal_vm[n] += vm
            nodal_cnt[n] += 1
    nodal_cnt[nodal_cnt == 0] = 1
    nodal_vm /= nodal_cnt

    # --- Yuzey ucgenleri (gorsellestirme) ---
    result = SolveResult(
        node_count=n_nodes,
        tet_count=n_tets,
        max_disp=float(disp_mag.max()) if n_nodes else 0.0,
        max_von_mises=float(nodal_vm.max()) if n_nodes else 0.0,
        element_size=float(mesh_size),
        bbox_min=[xmin, ymin, zmin],
        bbox_max=[xmax, ymax, zmax],
    )
    for tag, tris in surf_tris.items():
        for tri in tris:
            for n in tri:
                result.positions.extend(coords[n].tolist())
                result.disp.extend(u_vec[n].tolist())
                result.disp_mag.append(float(disp_mag[n]))
                result.von_mises.append(float(nodal_vm[n]))

    return result
