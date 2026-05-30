import type { TessellationResult } from "./types";

export interface FaceGeom {
  centroid: [number, number, number];
  normal: [number, number, number];
}

/**
 * Tessellation verisinden her yuzey icin agirlikli centroid ve ortalama normal
 * hesaplar. Centroid, ucgen alanlariyla agirliklandirilir; normal, ucgen
 * geometrik normallerinin (alan agirlikli) toplamidir.
 *
 * Donen koordinatlar model uzayindadir (merkeze tasima viewport'ta yapilir).
 */
export function computeFaceGeometry(
  data: TessellationResult,
): Map<number, FaceGeom> {
  const pos = data.positions;
  const ids = data.triangleFaceIds;

  const acc = new Map<
    number,
    { cx: number; cy: number; cz: number; nx: number; ny: number; nz: number; w: number }
  >();

  for (let t = 0; t < ids.length; t++) {
    const o = t * 9;
    const ax = pos[o], ay = pos[o + 1], az = pos[o + 2];
    const bx = pos[o + 3], by = pos[o + 4], bz = pos[o + 5];
    const cx = pos[o + 6], cy = pos[o + 7], cz = pos[o + 8];

    // kenar vektorleri ve capraz carpim (alan*2 yonlu normal)
    const e1x = bx - ax, e1y = by - ay, e1z = bz - az;
    const e2x = cx - ax, e2y = cy - ay, e2z = cz - az;
    const nx = e1y * e2z - e1z * e2y;
    const ny = e1z * e2x - e1x * e2z;
    const nz = e1x * e2y - e1y * e2x;
    const area2 = Math.hypot(nx, ny, nz);
    const w = area2 * 0.5;

    const tcx = (ax + bx + cx) / 3;
    const tcy = (ay + by + cy) / 3;
    const tcz = (az + bz + cz) / 3;

    const id = ids[t];
    let a = acc.get(id);
    if (!a) {
      a = { cx: 0, cy: 0, cz: 0, nx: 0, ny: 0, nz: 0, w: 0 };
      acc.set(id, a);
    }
    a.cx += tcx * w;
    a.cy += tcy * w;
    a.cz += tcz * w;
    a.nx += nx;
    a.ny += ny;
    a.nz += nz;
    a.w += w;
  }

  const result = new Map<number, FaceGeom>();
  for (const [id, a] of acc) {
    const w = a.w > 0 ? a.w : 1;
    const nlen = Math.hypot(a.nx, a.ny, a.nz) || 1;
    result.set(id, {
      centroid: [a.cx / w, a.cy / w, a.cz / w],
      normal: [a.nx / nlen, a.ny / nlen, a.nz / nlen],
    });
  }
  return result;
}
