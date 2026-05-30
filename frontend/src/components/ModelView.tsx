import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import type { ThreeEvent } from "@react-three/fiber";
import type { Load, TessellationResult } from "../types";
import type { FaceGeom } from "../faceGeometry";

const BASE_COLOR = new THREE.Color("#8c97a8");
const HOVER_COLOR = new THREE.Color("#5da9e9");
const SELECT_COLOR = new THREE.Color("#f5a623");
const FIXED_COLOR = new THREE.Color("#e0564f");
const LOAD_COLOR = new THREE.Color("#54b15a");

export type FaceAssignment = "fixed" | "load";

interface ModelViewProps {
  data: TessellationResult;
  selectedFaceId: number | null;
  hoveredFaceId: number | null;
  assignments: Map<number, FaceAssignment>;
  loads: Load[];
  faceGeom: Map<number, FaceGeom>;
  onSelectFace: (faceId: number | null) => void;
  onHoverFace: (faceId: number | null) => void;
}

export function ModelView({
  data,
  selectedFaceId,
  hoveredFaceId,
  assignments,
  loads,
  faceGeom,
  onSelectFace,
  onHoverFace,
}: ModelViewProps) {
  const meshRef = useRef<THREE.Mesh>(null);

  // Modelin merkezine tasiyacagimiz offset (kamera/donus icin)
  const center = useMemo<[number, number, number]>(() => {
    const [minx, miny, minz] = data.bboxMin;
    const [maxx, maxy, maxz] = data.bboxMax;
    return [(minx + maxx) / 2, (miny + maxy) / 2, (minz + maxz) / 2];
  }, [data]);

  const geometry = useMemo(() => {
    const geom = new THREE.BufferGeometry();
    const positions = new Float32Array(data.positions);
    geom.setAttribute("position", new THREE.BufferAttribute(positions, 3));

    const colors = new Float32Array(positions.length);
    geom.setAttribute("color", new THREE.BufferAttribute(colors, 3));

    geom.computeVertexNormals();
    geom.computeBoundingBox();
    geom.computeBoundingSphere();
    return geom;
  }, [data]);

  // Renkleri secim/hover durumuna gore guncelle
  useEffect(() => {
    const colorAttr = geometry.getAttribute("color") as THREE.BufferAttribute;
    const ids = data.triangleFaceIds;
    for (let t = 0; t < ids.length; t++) {
      const faceId = ids[t];
      let c = BASE_COLOR;
      const assigned = assignments.get(faceId);
      if (assigned === "fixed") c = FIXED_COLOR;
      else if (assigned === "load") c = LOAD_COLOR;
      if (faceId === hoveredFaceId) c = HOVER_COLOR;
      if (faceId === selectedFaceId) c = SELECT_COLOR;
      const base = t * 3;
      for (let k = 0; k < 3; k++) {
        colorAttr.setXYZ(base + k, c.r, c.g, c.b);
      }
    }
    colorAttr.needsUpdate = true;
  }, [geometry, data.triangleFaceIds, selectedFaceId, hoveredFaceId, assignments]);

  const faceIdAt = (e: ThreeEvent<PointerEvent>): number | null => {
    if (e.faceIndex == null) return null;
    const id = data.triangleFaceIds[e.faceIndex];
    return id ?? null;
  };

  const arrows = useMemo(() => {
    const [minx, miny, minz] = data.bboxMin;
    const [maxx, maxy, maxz] = data.bboxMax;
    const diag = Math.hypot(maxx - minx, maxy - miny, maxz - minz) || 1;
    const len = diag * 0.18;

    const list: THREE.ArrowHelper[] = [];
    for (const lo of loads) {
      const fg = faceGeom.get(lo.face_id);
      if (!fg) continue;

      const dir = new THREE.Vector3();
      if (lo.type === "force") {
        dir.set(lo.fx, lo.fy, lo.fz);
        if (dir.lengthSq() === 0) continue;
      } else {
        // basinc: yuzey normali boyunca (+ disari, - iceri)
        const s = lo.value >= 0 ? 1 : -1;
        dir.set(fg.normal[0] * s, fg.normal[1] * s, fg.normal[2] * s);
      }
      dir.normalize();

      const origin = new THREE.Vector3(fg.centroid[0], fg.centroid[1], fg.centroid[2]);
      const arrow = new THREE.ArrowHelper(dir, origin, len, 0x54b15a, len * 0.32, len * 0.16);
      list.push(arrow);
    }
    return list;
  }, [loads, faceGeom, data.bboxMin, data.bboxMax]);

  return (
    <group position={[-center[0], -center[1], -center[2]]}>
      <mesh
        ref={meshRef}
        geometry={geometry}
        onPointerDown={(e) => {
          e.stopPropagation();
          onSelectFace(faceIdAt(e));
        }}
        onPointerMove={(e) => {
          e.stopPropagation();
          const id = faceIdAt(e);
          if (id !== hoveredFaceId) onHoverFace(id);
        }}
        onPointerOut={() => onHoverFace(null)}
      >
        <meshStandardMaterial
          vertexColors
          metalness={0.1}
          roughness={0.6}
          side={THREE.DoubleSide}
          flatShading
        />
      </mesh>
      <lineSegments>
        <wireframeGeometry args={[geometry]} />
        <lineBasicMaterial color="#2a2f3a" transparent opacity={0.12} />
      </lineSegments>
      {arrows.map((a, i) => (
        <primitive key={i} object={a} />
      ))}
    </group>
  );
}
