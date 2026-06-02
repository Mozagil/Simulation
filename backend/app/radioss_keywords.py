"""OpenRadioss Starter keyword sablonlari ve deck birlestirme."""

from __future__ import annotations

from typing import Any

from .models import KeywordBlock
from .radioss_deck import build_deck_lines
from .volume_mesh import mesh_volume_from_step


# Surukle-birak / ekle ile kullanilacak bos sablonlar
KEYWORD_TEMPLATES: list[dict[str, str]] = [
    {
        "id": "mat_law2",
        "name": "/MAT/LAW2",
        "category": "material",
        "description": "Johnson-Cook plastisite (crash celikleri)",
        "lines": "/MAT/LAW2/2\nJC_Steel\n                         7.850000E-09\n                         210000.0\n                         0.300000\n                         450.0\n                         0.002000\n                         1.0\n                         0.0\n                         1.0\n                         1.0",
    },
    {
        "id": "dt_noda",
        "name": "/DT/NODA/CST",
        "category": "control",
        "description": "Sabit nodal zaman adimi",
        "lines": "/DT/NODA/CST/1.000000E-07",
    },
    {
        "id": "anim_energy",
        "name": "/ANIM/ELEM",
        "category": "output",
        "description": "Eleman enerji / saat cikti",
        "lines": "/ANIM/ELEM/ENER\n/ANIM/ELEM/HOURG",
    },
    {
        "id": "grav",
        "name": "/GRAV",
        "category": "load",
        "description": "Yercekimi yuklemesi",
        "lines": "/GRAV/2\nGravity_Z\n                         9810.0\n                         0.000000\n                         0.000000\n                        -1.000000",
    },
    {
        "id": "impvel",
        "name": "/IMPVEL",
        "category": "load",
        "description": "Baslangic hizi (dugum listesi elle ekleyin)",
        "lines": "/IMPVEL/2\nInitVelocity\n                         0.000000\n                         0.000000\n                        -5.000000\n# node_id (her satir bir dugum)\n#       1",
    },
    {
        "id": "bcs_lagr",
        "name": "/BCS/LAGR",
        "category": "bc",
        "description": "Sabit dugumler (Lagrange)",
        "lines": "/BCS/LAGR/2\nFixedSet\n#       1",
    },
    {
        "id": "inter_type7",
        "name": "/INTER/TYPE7",
        "category": "contact",
        "description": "Genel kontak (ornek iskelet — part ID'leri duzenleyin)",
        "lines": "/INTER/TYPE7/1\nContact1\n                         1\n                         2\n                         0\n                         0",
    },
    {
        "id": "sensor",
        "name": "/SENSOR/ACCE",
        "category": "output",
        "description": "Ivme sensoru (ornek)",
        "lines": "/SENSOR/ACCE/1\nAccel_1\n                         1\n                         0.0",
    },
    {
        "id": "custom",
        "name": "Ozel blok",
        "category": "custom",
        "description": "Bos ozel keyword blogu",
        "lines": "# Ozel keyword satirlari\n",
    },
]


def list_templates() -> list[dict[str, str]]:
    return KEYWORD_TEMPLATES


def _split_lines_into_blocks(lines: list[str]) -> list[KeywordBlock]:
    """Satir listesini /KEYWORD basliklarina gore bloklara ayirir."""
    blocks: list[KeywordBlock] = []
    header_lines: list[str] = []
    current_name = ""
    current_lines: list[str] = []
    current_cat = "control"

    def flush() -> None:
        nonlocal current_name, current_lines, current_cat
        if not current_name and not current_lines:
            return
        text = "\n".join(current_lines).strip()
        if text:
            blocks.append(
                KeywordBlock(
                    id=f"blk_{len(blocks)}",
                    name=current_name or "block",
                    category=current_cat,
                    enabled=True,
                    lines=text,
                )
            )
        current_name = ""
        current_lines = []

    cat_map = {
        "/MAT": "material",
        "/PROP": "material",
        "/PART": "mesh",
        "/NODE": "mesh",
        "/TETRA": "mesh",
        "/BRICK": "mesh",
        "/BCS": "bc",
        "/GRAV": "load",
        "/IMP": "load",
        "/CLOAD": "load",
        "/INTER": "contact",
        "/ANIM": "output",
        "/DT": "control",
        "/RUN": "control",
        "/SENSOR": "output",
        "/BEGIN": "control",
        "/END": "control",
    }

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#RADIOSS") or (stripped.startswith("#") and not current_name):
            header_lines.append(line)
            continue
        if stripped.startswith("/"):
            flush()
            current_name = stripped.split()[0] if stripped else "/BLOCK"
            for prefix, cat in cat_map.items():
                if current_name.upper().startswith(prefix):
                    current_cat = cat
                    break
            current_lines = [line]
        elif current_name:
            current_lines.append(line)
        else:
            header_lines.append(line)

    flush()

    if header_lines:
        blocks.insert(
            0,
            KeywordBlock(
                id="header",
                name="#RADIOSS STARTER",
                category="header",
                enabled=True,
                lines="\n".join(header_lines).strip(),
            ),
        )
    return blocks


def compose_deck(blocks: list[KeywordBlock]) -> str:
    """Etkin bloklari birlestirir; /END yoksa ekler."""
    parts: list[str] = []
    has_end = False
    for b in blocks:
        if not b.enabled:
            continue
        text = b.lines.strip()
        if not text:
            continue
        parts.append(text)
        if text.upper().startswith("/END"):
            has_end = True
    if not has_end:
        parts.append("/END")
    return "\n".join(parts) + "\n"


def generate_deck_from_model(
    step_path: str,
    material,
    constraints,
    loads,
    params,
    *,
    run_name: str = "crash",
    element_size: float | None = None,
    extra_blocks: list[KeywordBlock] | None = None,
) -> dict[str, Any]:
    mesh = mesh_volume_from_step(step_path, element_size)
    lines = build_deck_lines(
        mesh, material, constraints, loads, params, run_name=run_name
    )
    blocks = _split_lines_into_blocks(lines)
    if extra_blocks:
        # /END oncesine ek bloklar
        end_idx = next((i for i, b in enumerate(blocks) if b.name.startswith("/END")), len(blocks))
        for j, eb in enumerate(extra_blocks):
            blocks.insert(end_idx + j, eb)
    deck = compose_deck(blocks)
    return {
        "deck": deck,
        "blocks": [b.model_dump() for b in blocks],
        "nodeCount": int(mesh.coords.shape[0]),
        "tetCount": int(mesh.tets.shape[0]),
        "elementSize": mesh.element_size,
        "runName": run_name,
    }
