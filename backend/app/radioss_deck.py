"""OpenRadioss Starter (.rad) deck uretimi — tetra4 + LAW1 (elastik) MVP."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .models import Constraint, ExplicitParams, Load, Material
from .volume_mesh import VolumeMesh, face_to_surface


def _rho_tonne_mm3(density_kg_m3: float) -> float:
    """kg/m^3 -> tonne/mm^3 (Radioss tonne-mm biriminde yogunluk)."""
    return density_kg_m3 * 1e-12


def build_deck_lines(
    mesh: VolumeMesh,
    material: Material,
    constraints: list[Constraint],
    loads: list[Load],
    params: ExplicitParams,
    run_name: str = "crash",
) -> list[str]:
    """Tam Starter satir listesi (dosyaya yazmadan)."""
    n_nodes = mesh.coords.shape[0]
    # Radioss 1-based node id; gmsh tag sirasi ile eslestir
    tag_to_rid = {int(mesh.node_tags[i]): i + 1 for i in range(n_nodes)}

    fixed_nodes: set[int] = set()
    for c in constraints:
        if c.type != "fixed":
            continue
        st = face_to_surface(mesh, c.face_id)
        if st is None:
            continue
        for ni in mesh.surf_nodes.get(st, []):
            fixed_nodes.add(tag_to_rid[int(mesh.node_tags[ni])])

    vel_nodes: set[int] = set()
    vx, vy, vz = params.initial_velocity
    if abs(vx) + abs(vy) + abs(vz) > 0:
        for i in range(n_nodes):
            rid = tag_to_rid[int(mesh.node_tags[i])]
            if rid not in fixed_nodes:
                vel_nodes.add(rid)

    # Yuk yuzeylerindeki dugumlere ek hiz (basit MVP)
    for lo in loads:
        st = face_to_surface(mesh, lo.face_id)
        if st is None:
            continue
        for ni in mesh.surf_nodes.get(st, []):
            rid = tag_to_rid[int(mesh.node_tags[ni])]
            if rid not in fixed_nodes:
                vel_nodes.add(rid)

    lines: list[str] = [
        "#RADIOSS STARTER",
        "# Crash CAE — OpenRadioss explicit deck (otomatik)",
        "# Birim: mm, ms, tonne, MPa",
        "#---1----|----2----|----3----|----4----|----5----|----6----|----7----|----8----|----9----|---10----|",
        "/BEGIN",
        f"/RUN/{run_name}/1/",
        f"                         {params.end_time_ms:.6f}",
    ]

    dt = params.dt_ms if params.dt_ms and params.dt_ms > 0 else params.end_time_ms / max(params.output_frames, 1)
    lines.extend(
        [
            f"/DT/NODA/CST/{dt:.8e}",
            "/ANIM/DT",
            "#   TSTART     TFREQ",
            "0.000000 0.000000",
            "/ANIM/VECT/DISP",
            "/ANIM/VECT/VEL",
            "/ANIM/ELEM/VONM",
            "/MAT/LAW1/1",
            "Elastic",
            f"                         {_rho_tonne_mm3(material.density):.8e}",
            f"                         {material.youngs_modulus:.6f}",
            f"                         {material.poisson_ratio:.6f}",
            "/PROP/SOLID/1",
            "1",
            "/PART/1",
            "1",
            "1",
            "1",
        ]
    )

    # Nodes (chunked for readability)
    lines.append("/NODE")
    for i in range(n_nodes):
        rid = i + 1
        x, y, z = mesh.coords[i]
        lines.append(f"{rid:8d}{x:16.6f}{y:16.6f}{z:16.6f}")

    lines.append("/TETRA4/1")
    for e, tet in enumerate(mesh.tets):
        n1 = tet[0] + 1
        n2 = tet[1] + 1
        n3 = tet[2] + 1
        n4 = tet[3] + 1
        lines.append(f"{e + 1:8d}{n1:8d}{n2:8d}{n3:8d}{n4:8d}")

    if fixed_nodes:
        lines.append("/BCS/LAGR/1")
        lines.append("FixedNodes")
        for rid in sorted(fixed_nodes):
            lines.append(f"{rid:8d}")

    if abs(params.gravity) > 0:
        lines.extend(
            [
                "/GRAV/1",
                "Gravity",
                f"                         {params.gravity:.6f}",
                "                         0.000000",
                "                         0.000000",
                "                        -1.000000",
            ]
        )

    if vel_nodes and (abs(vx) + abs(vy) + abs(vz) > 0):
        lines.append("/IMPVEL/1")
        lines.append("InitVel")
        lines.append(f"                         {vx:.6f}")
        lines.append(f"                         {vy:.6f}")
        lines.append(f"                         {vz:.6f}")
        for rid in sorted(vel_nodes):
            lines.append(f"{rid:8d}")

    lines.append("/END")
    return lines


def write_starter_deck(
    mesh: VolumeMesh,
    material: Material,
    constraints: list[Constraint],
    loads: list[Load],
    params: ExplicitParams,
    out_path: Path,
    run_name: str = "crash",
    extra_lines_before_end: list[str] | None = None,
) -> Path:
    """crash_0000.rad dosyasini yazar."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = build_deck_lines(mesh, material, constraints, loads, params, run_name=run_name)
    if extra_lines_before_end:
        lines = lines[:-1] + extra_lines_before_end + ["/END"]
    out_path.write_text("\n".join(lines) + "\n", encoding="ascii", errors="replace")
    return out_path
