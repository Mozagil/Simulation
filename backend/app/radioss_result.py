"""OpenRadioss animasyon / cikti dosyalarini web goruntuleme formatina cevir."""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

try:
    import meshio
except ImportError:  # pragma: no cover
    meshio = None  # type: ignore


@dataclass
class ExplicitFrame:
    time_ms: float
    positions: list[float]
    disp: list[float]
    disp_mag: list[float]
    von_mises: list[float]


@dataclass
class ExplicitResult:
    positions: list[float]  # referans (ilk kare yuzey)
    disp: list[float]
    disp_mag: list[float]
    von_mises: list[float]
    frames: list[dict[str, Any]] = field(default_factory=list)
    node_count: int = 0
    tet_count: int = 0
    max_disp: float = 0.0
    max_von_mises: float = 0.0
    element_size: float = 0.0
    bbox_min: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    bbox_max: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    run_logs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "positions": self.positions,
            "disp": self.disp,
            "dispMag": self.disp_mag,
            "vonMises": self.von_mises,
            "frames": self.frames,
            "nodeCount": self.node_count,
            "tetCount": self.tet_count,
            "maxDisp": self.max_disp,
            "maxVonMises": self.max_von_mises,
            "elementSize": self.element_size,
            "bboxMin": self.bbox_min,
            "bboxMax": self.bbox_max,
            "runLogs": self.run_logs[-30:],
            "analysisType": "explicit_openradioss",
        }


def _parse_engine_out(work_dir: Path, run_name: str) -> dict[str, float]:
    """Engine .out dosyasindan kabaca maksimum deplasman arar."""
    stats = {"max_disp": 0.0, "max_von_mises": 0.0}
    for out in work_dir.glob(f"{run_name}*.out"):
        try:
            text = out.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for m in re.finditer(r"DISPLACEMENT.*?MAX.*?=\s*([\d.eE+-]+)", text, re.I):
            stats["max_disp"] = max(stats["max_disp"], float(m.group(1)))
        for m in re.finditer(r"VON\s*MIS.*?=\s*([\d.eE+-]+)", text, re.I):
            stats["max_von_mises"] = max(stats["max_von_mises"], float(m.group(1)))
    return stats


def _read_anim_binary_simple(path: Path) -> tuple[np.ndarray, np.ndarray] | None:
    """Basit Radioss anim (IEEE) okuma — yalnizca dugum koordinatlari MVP.

    Format surume gore degisir; basarisiz olursa None doner.
    """
    try:
        data = path.read_bytes()
        if len(data) < 256:
            return None
        # Son blokta float koordinatlar olabilir — sezgisel tarama
        n_floats = len(data) // 4
        floats = struct.unpack(f"{n_floats}f", data[: n_floats * 4])
        arr = np.array(floats, dtype=np.float64)
        if len(arr) % 3 != 0:
            return None
        n = len(arr) // 3
        if n < 4 or n > 500_000:
            return None
        coords = arr[: n * 3].reshape(n, 3)
        return coords, np.zeros((n, 3))
    except Exception:  # noqa: BLE001
        return None


def _surface_from_volume(
    ref_coords: np.ndarray,
    surf_tris: dict[int, np.ndarray],
    all_coords: np.ndarray,
    vm: np.ndarray | None = None,
) -> tuple[list[float], list[float], list[float], list[float]]:
    """Yuzey ucgenleri uzerinde goruntuleme vektorleri."""
    positions: list[float] = []
    disp: list[float] = []
    disp_mag: list[float] = []
    von: list[float] = []
    for tris in surf_tris.values():
        for tri in tris:
            for ni in tri:
                p0 = ref_coords[ni]
                p1 = all_coords[ni]
                d = p1 - p0
                positions.extend(p0.tolist())
                disp.extend(d.tolist())
                disp_mag.append(float(np.linalg.norm(d)))
                von.append(float(vm[ni]) if vm is not None and len(vm) > ni else 0.0)
    return positions, disp, disp_mag, von


def parse_explicit_results(
    work_dir: Path,
    run_name: str,
    ref_coords: np.ndarray,
    surf_tris: dict[int, np.ndarray],
    *,
    element_size: float,
    bbox_min: list[float],
    bbox_max: list[float],
    tet_count: int,
    run_logs: list[str],
    anim_to_vtk: Path | None = None,
) -> ExplicitResult:
    work_dir = Path(work_dir)
    stats = _parse_engine_out(work_dir, run_name)

    anim_files = sorted(work_dir.glob(f"{run_name}A*")) + sorted(work_dir.glob("*.anim"))
    frames: list[ExplicitFrame] = []

    vtk_files: list[Path] = []
    if anim_to_vtk and anim_to_vtk.is_file():
        import subprocess

        for anim in anim_files[:50]:
            if not anim.is_file():
                continue
            out_vtk = anim.with_suffix(".vtk")
            try:
                subprocess.run(
                    [str(anim_to_vtk), str(anim), str(out_vtk)],
                    cwd=str(work_dir),
                    capture_output=True,
                    timeout=120,
                    check=False,
                )
                if out_vtk.is_file():
                    vtk_files.append(out_vtk)
            except Exception:  # noqa: BLE001
                pass

    if meshio and vtk_files:
        for i, vf in enumerate(sorted(vtk_files)):
            try:
                m = meshio.read(vf)
                pts = np.asarray(m.points, dtype=np.float64)
                if pts.shape[0] != ref_coords.shape[0]:
                    continue
                d = pts - ref_coords
                vm = np.zeros(pts.shape[0])
                positions, disp, dm, von = _surface_from_volume(
                    ref_coords, surf_tris, pts, vm
                )
                frames.append(
                    ExplicitFrame(
                        time_ms=float(i),
                        positions=positions,
                        disp=disp,
                        disp_mag=dm,
                        von_mises=von,
                    )
                )
            except Exception:  # noqa: BLE001
                continue

    if not frames and anim_files:
        for i, anim in enumerate(anim_files[:30]):
            parsed = _read_anim_binary_simple(anim)
            if parsed is None:
                continue
            pts, _ = parsed
            if pts.shape[0] != ref_coords.shape[0]:
                continue
            positions, disp, dm, von = _surface_from_volume(ref_coords, surf_tris, pts)
            frames.append(
                ExplicitFrame(
                    time_ms=float(i),
                    positions=positions,
                    disp=disp,
                    disp_mag=dm,
                    von_mises=von,
                )
            )

    # Son kare veya referans
    if frames:
        last = frames[-1]
        positions, disp, disp_mag, von = (
            last.positions,
            last.disp,
            last.disp_mag,
            last.von_mises,
        )
        max_disp = max(max(last.disp_mag), stats["max_disp"])
    else:
        positions, disp, disp_mag, von = _surface_from_volume(
            ref_coords, surf_tris, ref_coords
        )
        max_disp = stats["max_disp"]

    max_vm = max(von) if von else stats["max_von_mises"]

    frame_dicts = [
        {
            "timeMs": f.time_ms,
            "positions": f.positions,
            "disp": f.disp,
            "dispMag": f.disp_mag,
            "vonMises": f.von_mises,
        }
        for f in frames
    ]

    return ExplicitResult(
        positions=positions,
        disp=disp,
        disp_mag=disp_mag,
        von_mises=von,
        frames=frame_dicts,
        node_count=int(ref_coords.shape[0]),
        tet_count=tet_count,
        max_disp=float(max_disp),
        max_von_mises=float(max_vm),
        element_size=element_size,
        bbox_min=bbox_min,
        bbox_max=bbox_max,
        run_logs=run_logs,
    )
