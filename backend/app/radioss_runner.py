"""OpenRadioss Starter + Engine calistirma ve ortam kontrolu."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class OpenRadiossConfig:
    root: Path
    exec_dir: Path
    starter: Path
    engine: Path
    anim_to_vtk: Path | None


def find_openradioss() -> OpenRadiossConfig | None:
    root = os.environ.get("OPENRADIOSS_PATH")
    if not root:
        return None
    root_p = Path(root)
    exec_p = root_p / "exec"
    if os.name == "nt":
        starter = exec_p / "starter_win64.exe"
        engine = exec_p / "engine_win64.exe"
        anim = exec_p / "anim_to_vtk_win64.exe"
    else:
        starter = exec_p / "starter_linux64_gf"
        engine = exec_p / "engine_linux64_gf"
        anim = exec_p / "anim_to_vtk_linux64"
    if not starter.is_file() or not engine.is_file():
        return None
    return OpenRadiossConfig(
        root=root_p,
        exec_dir=exec_p,
        starter=starter,
        engine=engine,
        anim_to_vtk=anim if anim.is_file() else None,
    )


def openradioss_status() -> dict:
    cfg = find_openradioss()
    if not cfg:
        return {
            "installed": False,
            "message": "OPENRADIOSS_PATH tanimli degil veya exec/ starter/engine bulunamadi.",
            "install_hint": "https://github.com/OpenRadioss/OpenRadioss/releases",
        }
    return {
        "installed": True,
        "path": str(cfg.root),
        "starter": str(cfg.starter),
        "engine": str(cfg.engine),
        "anim_to_vtk": str(cfg.anim_to_vtk) if cfg.anim_to_vtk else None,
    }


def _env_for_run(cfg: OpenRadiossConfig, threads: int) -> dict[str, str]:
    env = os.environ.copy()
    env["OPENRADIOSS_PATH"] = str(cfg.root)
    env["RAD_CFG_PATH"] = str(cfg.root / "hm_cfg_files")
    env["OMP_NUM_THREADS"] = str(threads)
    env["KMP_STACKSIZE"] = "400m"
    if os.name == "nt":
        extra = [
            cfg.root / "extlib" / "hm_reader" / "win64",
            cfg.root / "extlib" / "intelOneAPI_runtime" / "win64",
        ]
        env["PATH"] = ";".join(str(p) for p in extra if p.is_dir()) + ";" + env.get("PATH", "")
    else:
        env["LD_LIBRARY_PATH"] = ":".join(
            [
                str(cfg.root / "extlib" / "hm_reader" / "linux64"),
                str(cfg.root / "lib"),
                env.get("LD_LIBRARY_PATH", ""),
            ]
        )
    return env


def run_openradioss(
    work_dir: Path,
    run_name: str,
    threads: int = 4,
    timeout_s: int = 3600,
) -> tuple[Path, list[str]]:
    """Starter + Engine calistirir. Doner: (work_dir, log satirlari)."""
    cfg = find_openradioss()
    if not cfg:
        raise RuntimeError(
            "OpenRadioss bulunamadi. OPENRADIOSS_PATH ortam degiskenini kurulum kokune ayarlayin."
        )

    work_dir = Path(work_dir)
    starter_in = work_dir / f"{run_name}_0000.rad"
    if not starter_in.is_file():
        raise FileNotFoundError(f"Starter dosyasi yok: {starter_in}")

    env = _env_for_run(cfg, threads)
    logs: list[str] = []

    def _run(cmd: list[str], cwd: Path) -> None:
        logs.append(f"$ {' '.join(cmd)}")
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        if proc.stdout:
            logs.extend(proc.stdout.splitlines()[-40:])
        if proc.stderr:
            logs.extend(proc.stderr.splitlines()[-20:])
        if proc.returncode != 0:
            raise RuntimeError(
                f"OpenRadioss hata (kod {proc.returncode}): {' '.join(cmd[-2:])}\n"
                + "\n".join(logs[-15:])
            )

    _run([str(cfg.starter), "-i", starter_in.name, "-np", "1"], work_dir)

    engine_in = work_dir / f"{run_name}_0001.rad"
    if not engine_in.is_file():
        # bazi surumlerde farkli isimlendirme
        candidates = list(work_dir.glob(f"{run_name}_0001.rad")) + list(work_dir.glob("*_0001.rad"))
        if not candidates:
            raise FileNotFoundError("Engine girdisi (_0001.rad) starter sonrasi olusmadi.")
        engine_in = candidates[0]

    _run([str(cfg.engine), "-i", engine_in.name], work_dir)
    return work_dir, logs
