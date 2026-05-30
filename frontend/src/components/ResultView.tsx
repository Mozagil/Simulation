import { useMemo } from "react";
import * as THREE from "three";
import type { SolveResult } from "../types";

export type ResultField = "vm" | "disp";

interface ResultViewProps {
  solve: SolveResult;
  field: ResultField;
  deformScale: number;
}

/** Mavi -> camgobegi -> yesil -> sari -> kirmizi (jet benzeri) renk eslestirme. t: 0..1 */
export function jetColor(t: number): [number, number, number] {
  const x = Math.min(1, Math.max(0, t));
  const r = Math.min(1, Math.max(0, 1.5 - Math.abs(4 * x - 3)));
  const g = Math.min(1, Math.max(0, 1.5 - Math.abs(4 * x - 2)));
  const b = Math.min(1, Math.max(0, 1.5 - Math.abs(4 * x - 1)));
  return [r, g, b];
}

export function ResultView({ solve, field, deformScale }: ResultViewProps) {
  const center = useMemo<[number, number, number]>(() => {
    const [minx, miny, minz] = solve.bboxMin;
    const [maxx, maxy, maxz] = solve.bboxMax;
    return [(minx + maxx) / 2, (miny + maxy) / 2, (minz + maxz) / 2];
  }, [solve]);

  const geometry = useMemo(() => {
    const scalar = field === "vm" ? solve.vonMises : solve.dispMag;
    const maxVal = field === "vm" ? solve.maxVonMises : solve.maxDisp;
    const inv = maxVal > 0 ? 1 / maxVal : 0;

    const nVerts = solve.positions.length / 3;
    const positions = new Float32Array(solve.positions.length);
    const colors = new Float32Array(solve.positions.length);

    for (let i = 0; i < nVerts; i++) {
      positions[i * 3 + 0] = solve.positions[i * 3 + 0] + solve.disp[i * 3 + 0] * deformScale;
      positions[i * 3 + 1] = solve.positions[i * 3 + 1] + solve.disp[i * 3 + 1] * deformScale;
      positions[i * 3 + 2] = solve.positions[i * 3 + 2] + solve.disp[i * 3 + 2] * deformScale;
      const [r, g, b] = jetColor(scalar[i] * inv);
      colors[i * 3 + 0] = r;
      colors[i * 3 + 1] = g;
      colors[i * 3 + 2] = b;
    }

    const geom = new THREE.BufferGeometry();
    geom.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geom.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    geom.computeVertexNormals();
    geom.computeBoundingSphere();
    return geom;
  }, [solve, field, deformScale]);

  return (
    <group position={[-center[0], -center[1], -center[2]]}>
      <mesh geometry={geometry}>
        <meshStandardMaterial
          vertexColors
          metalness={0.05}
          roughness={0.75}
          side={THREE.DoubleSide}
          flatShading
        />
      </mesh>
    </group>
  );
}
