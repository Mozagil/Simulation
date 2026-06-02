import { useEffect, useMemo, useRef } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import type { ThreeEvent } from "@react-three/fiber";
import * as THREE from "three";
import type { SolveResult } from "../types";

export type ResultField = "vm" | "disp" | "ux" | "uy" | "uz";
export type SectionAxis = "none" | "x" | "y" | "z";

export interface ProbeInfo {
  x: number;
  y: number;
  z: number;
  value: number;
}

export const FIELD_META: Record<ResultField, { label: string; unit: string; decimals: number }> = {
  vm: { label: "von Mises", unit: "MPa", decimals: 1 },
  disp: { label: "Deplasman |U|", unit: "mm", decimals: 3 },
  ux: { label: "Deplasman Ux", unit: "mm", decimals: 3 },
  uy: { label: "Deplasman Uy", unit: "mm", decimals: 3 },
  uz: { label: "Deplasman Uz", unit: "mm", decimals: 3 },
};

/** Tek bir dugumun (vertex) secili alandaki skaler degeri. */
export function getScalar(solve: SolveResult, field: ResultField, i: number): number {
  switch (field) {
    case "vm":
      return solve.vonMises[i];
    case "disp":
      return solve.dispMag[i];
    case "ux":
      return solve.disp[i * 3 + 0];
    case "uy":
      return solve.disp[i * 3 + 1];
    case "uz":
      return solve.disp[i * 3 + 2];
    default:
      return 0;
  }
}

/** Secili alan icin min/max (otomatik renk araligi). */
export function fieldStats(solve: SolveResult, field: ResultField): { min: number; max: number } {
  const n = solve.positions.length / 3;
  if (n === 0) return { min: 0, max: 0 };
  let mn = Infinity;
  let mx = -Infinity;
  for (let i = 0; i < n; i++) {
    const v = getScalar(solve, field, i);
    if (v < mn) mn = v;
    if (v > mx) mx = v;
  }
  return { min: mn, max: mx };
}

/** Mavi -> camgobegi -> yesil -> sari -> kirmizi (jet benzeri) renk eslestirme. t: 0..1 */
export function jetColor(t: number): [number, number, number] {
  const x = Math.min(1, Math.max(0, t));
  const r = Math.min(1, Math.max(0, 1.5 - Math.abs(4 * x - 3)));
  const g = Math.min(1, Math.max(0, 1.5 - Math.abs(4 * x - 2)));
  const b = Math.min(1, Math.max(0, 1.5 - Math.abs(4 * x - 1)));
  return [r, g, b];
}

interface ResultViewProps {
  solve: SolveResult;
  field: ResultField;
  deformScale: number;
  bands: number; // 0 = surekli (smooth), >0 = ayrik kontur bandi sayisi
  rangeMin: number;
  rangeMax: number;
  showEdges: boolean;
  sectionAxis: SectionAxis;
  sectionPos: number; // 0..1 (normalize konum)
  animate: boolean;
  frameIndex?: number;
  onProbe?: (info: ProbeInfo | null) => void;
}

export function ResultView({
  solve,
  field,
  deformScale,
  bands,
  rangeMin,
  rangeMax,
  showEdges,
  sectionAxis,
  sectionPos,
  animate,
  frameIndex = 0,
  onProbe,
}: ResultViewProps) {
  const { gl } = useThree();

  const activeSolve = useMemo(() => {
    const frames = solve.frames;
    if (!frames?.length) return solve;
    const f = frames[Math.min(frameIndex, frames.length - 1)];
    return {
      ...solve,
      positions: f.positions,
      disp: f.disp,
      dispMag: f.dispMag,
      vonMises: f.vonMises,
    };
  }, [solve, frameIndex]);

  useEffect(() => {
    gl.localClippingEnabled = true;
  }, [gl]);

  const center = useMemo<[number, number, number]>(() => {
    const [minx, miny, minz] = solve.bboxMin;
    const [maxx, maxy, maxz] = solve.bboxMax;
    return [(minx + maxx) / 2, (miny + maxy) / 2, (minz + maxz) / 2];
  }, [solve]);

  // Temel pozisyonlar (deformasyonsuz) + deplasman vektoru
  const base = useMemo(() => {
    const ref = solve.frames?.length ? solve.frames[0] : solve;
    const basePos = new Float32Array(ref.positions);
    const dispArr = new Float32Array(activeSolve.disp);
    return { basePos, dispArr };
  }, [solve, activeSolve]);

  // Secili alanin dugum-bazli skaler degerleri
  const scalar = useMemo(() => {
    const n = activeSolve.positions.length / 3;
    const s = new Float32Array(n);
    for (let i = 0; i < n; i++) s[i] = getScalar(activeSolve, field, i);
    return s;
  }, [activeSolve, field]);

  const geometry = useMemo(() => {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(base.basePos), 3));
    g.setAttribute("color", new THREE.BufferAttribute(new Float32Array(base.basePos.length), 3));
    g.computeVertexNormals();
    g.computeBoundingSphere();
    return g;
  }, [base]);

  // Renkler: skaler + aralik + bant degisince guncellenir (her karede degil)
  useEffect(() => {
    const colorAttr = geometry.getAttribute("color") as THREE.BufferAttribute;
    const span = rangeMax - rangeMin;
    const inv = span > 0 ? 1 / span : 0;
    for (let i = 0; i < scalar.length; i++) {
      let t = (scalar[i] - rangeMin) * inv;
      t = Math.min(1, Math.max(0, t));
      if (bands > 0) {
        let bi = Math.floor(t * bands);
        if (bi >= bands) bi = bands - 1;
        t = (bi + 0.5) / bands;
      }
      const [r, g, b] = jetColor(t);
      colorAttr.setXYZ(i, r, g, b);
    }
    colorAttr.needsUpdate = true;
  }, [geometry, scalar, rangeMin, rangeMax, bands]);

  // Deformasyon (statik olcek veya animasyon) - her karede uygulanir
  const lastScale = useRef<number>(Number.NaN);
  useFrame((state) => {
    const hasFrames = (solve.frames?.length ?? 0) > 1;
    const factor =
      animate && !hasFrames ? 0.5 - 0.5 * Math.cos(state.clock.elapsedTime * 2.5) : 1;
    const eff = deformScale * factor;
    if (!animate && eff === lastScale.current) return;
    lastScale.current = eff;
    const posAttr = geometry.getAttribute("position") as THREE.BufferAttribute;
    const arr = posAttr.array as Float32Array;
    const { basePos, dispArr } = base;
    for (let k = 0; k < arr.length; k++) arr[k] = basePos[k] + dispArr[k] * eff;
    posAttr.needsUpdate = true;
    geometry.computeVertexNormals();
  });

  // Kesit (clipping) duzlemi - merkezlenmis koordinatlarda
  const clip = useMemo<THREE.Plane[]>(() => {
    if (sectionAxis === "none") return [];
    const idx = sectionAxis === "x" ? 0 : sectionAxis === "y" ? 1 : 2;
    const lo = solve.bboxMin[idx];
    const hi = solve.bboxMax[idx];
    const cWorld = lo + (hi - lo) * sectionPos;
    const cCentered = cWorld - center[idx];
    const normal = new THREE.Vector3();
    normal.setComponent(idx, -1);
    return [new THREE.Plane(normal, cCentered)];
  }, [sectionAxis, sectionPos, solve, center]);

  const handleDown = (e: ThreeEvent<PointerEvent>) => {
    e.stopPropagation();
    if (!onProbe) return;
    if (e.faceIndex == null) {
      onProbe(null);
      return;
    }
    const posAttr = geometry.getAttribute("position") as THREE.BufferAttribute;
    const tri = e.faceIndex;
    let best = -1;
    let bestD = Infinity;
    let bx = 0;
    let by = 0;
    let bz = 0;
    for (let j = 0; j < 3; j++) {
      const vi = tri * 3 + j;
      const wx = posAttr.getX(vi) - center[0];
      const wy = posAttr.getY(vi) - center[1];
      const wz = posAttr.getZ(vi) - center[2];
      const d = (wx - e.point.x) ** 2 + (wy - e.point.y) ** 2 + (wz - e.point.z) ** 2;
      if (d < bestD) {
        bestD = d;
        best = vi;
        bx = wx;
        by = wy;
        bz = wz;
      }
    }
    if (best >= 0) onProbe({ x: bx, y: by, z: bz, value: scalar[best] });
  };

  return (
    <group position={[-center[0], -center[1], -center[2]]}>
      <mesh geometry={geometry} onPointerDown={handleDown}>
        <meshStandardMaterial
          vertexColors
          metalness={0.05}
          roughness={0.75}
          side={THREE.DoubleSide}
          flatShading
          clippingPlanes={clip}
          clipShadows
        />
      </mesh>
      {showEdges && (
        <mesh geometry={geometry}>
          <meshBasicMaterial
            color="#10131a"
            wireframe
            transparent
            opacity={0.22}
            clippingPlanes={clip}
          />
        </mesh>
      )}
    </group>
  );
}
