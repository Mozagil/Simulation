import { useMemo } from "react";
import * as THREE from "three";
import type { MeshResult } from "../types";

interface MeshViewProps {
  mesh: MeshResult;
}

export function MeshView({ mesh }: MeshViewProps) {
  const center = useMemo<[number, number, number]>(() => {
    const [minx, miny, minz] = mesh.bboxMin;
    const [maxx, maxy, maxz] = mesh.bboxMax;
    return [(minx + maxx) / 2, (miny + maxy) / 2, (minz + maxz) / 2];
  }, [mesh]);

  const geometry = useMemo(() => {
    const geom = new THREE.BufferGeometry();
    const positions = new Float32Array(mesh.positions);
    geom.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geom.computeVertexNormals();
    geom.computeBoundingSphere();
    return geom;
  }, [mesh]);

  // Gercek eleman kenarlari (quad'larda kosegen gosterilmez).
  // edges yoksa ucgen kenarlarina geri dusulur (wireframe).
  const edgeGeometry = useMemo(() => {
    if (!mesh.edges || mesh.edges.length === 0) return null;
    const geom = new THREE.BufferGeometry();
    geom.setAttribute(
      "position",
      new THREE.BufferAttribute(new Float32Array(mesh.edges), 3),
    );
    return geom;
  }, [mesh]);

  return (
    <group position={[-center[0], -center[1], -center[2]]}>
      <mesh geometry={geometry}>
        <meshStandardMaterial
          color="#3f7cac"
          metalness={0.05}
          roughness={0.8}
          side={THREE.DoubleSide}
          flatShading
          polygonOffset
          polygonOffsetFactor={1}
          polygonOffsetUnits={1}
        />
      </mesh>
      {edgeGeometry ? (
        <lineSegments geometry={edgeGeometry}>
          <lineBasicMaterial color="#dbe7f0" transparent opacity={0.6} />
        </lineSegments>
      ) : (
        <lineSegments>
          <wireframeGeometry args={[geometry]} />
          <lineBasicMaterial color="#dbe7f0" transparent opacity={0.55} />
        </lineSegments>
      )}
    </group>
  );
}
