import { useEffect, useMemo } from "react";
import { Canvas, useThree } from "@react-three/fiber";
import { GizmoHelper, GizmoViewport, Grid, OrbitControls } from "@react-three/drei";
import type { Load, MeshResult, SolveResult, TessellationResult } from "../types";
import { ModelView } from "./ModelView";
import type { FaceAssignment } from "./ModelView";
import { MeshView } from "./MeshView";
import { ResultView } from "./ResultView";
import type { ProbeInfo, ResultField, SectionAxis } from "./ResultView";
import type { FaceGeom } from "../faceGeometry";

export type BackgroundMode = "dark" | "light";
export type ViewMode = "geometry" | "mesh" | "result";

type Bbox = {
  bboxMin: [number, number, number];
  bboxMax: [number, number, number];
};

interface ViewerProps {
  data: TessellationResult | null;
  meshData: MeshResult | null;
  solveData: SolveResult | null;
  resultField: ResultField;
  deformScale: number;
  bands: number;
  rangeMin: number;
  rangeMax: number;
  showEdges: boolean;
  sectionAxis: SectionAxis;
  sectionPos: number;
  animate: boolean;
  onProbe: (info: ProbeInfo | null) => void;
  viewMode: ViewMode;
  selectedFaceId: number | null;
  hoveredFaceId: number | null;
  assignments: Map<number, FaceAssignment>;
  loads: Load[];
  faceGeom: Map<number, FaceGeom>;
  background: BackgroundMode;
  onSelectFace: (faceId: number | null) => void;
  onHoverFace: (faceId: number | null) => void;
}

const THEME = {
  dark: { bg: "#1b1e26", cell: "#2a2f3a", section: "#3a4252", gizmoLabel: "white" },
  light: { bg: "#f4f6fa", cell: "#c4ccd8", section: "#9aa6b8", gizmoLabel: "black" },
} as const;

function diagOf(box: Bbox): number {
  const [minx, miny, minz] = box.bboxMin;
  const [maxx, maxy, maxz] = box.bboxMax;
  const d = Math.hypot(maxx - minx, maxy - miny, maxz - minz);
  return d > 0 ? d : 1;
}

/** Aktif veri degistiginde kamerayi uygun mesafeye konumlandirir. */
function CameraFit({ box }: { box: Bbox | null }) {
  const { camera } = useThree();
  useEffect(() => {
    if (!box) return;
    const d = diagOf(box);
    camera.position.set(d * 0.9, d * 0.7, d * 0.9);
    camera.near = d * 0.001;
    camera.far = d * 100;
    camera.updateProjectionMatrix();
    camera.lookAt(0, 0, 0);
  }, [box, camera]);
  return null;
}

export function Viewer({
  data,
  meshData,
  solveData,
  resultField,
  deformScale,
  bands,
  rangeMin,
  rangeMax,
  showEdges,
  sectionAxis,
  sectionPos,
  animate,
  onProbe,
  viewMode,
  selectedFaceId,
  hoveredFaceId,
  assignments,
  loads,
  faceGeom,
  background,
  onSelectFace,
  onHoverFace,
}: ViewerProps) {
  const showResult = viewMode === "result" && solveData != null;
  const showMesh = viewMode === "mesh" && meshData != null;
  const activeBox: Bbox | null = showResult ? solveData : showMesh ? meshData : data;
  const gridSize = useMemo(() => (activeBox ? diagOf(activeBox) * 2 : 100), [activeBox]);
  const theme = THEME[background];

  return (
    <Canvas
      camera={{ position: [80, 60, 80], fov: 45 }}
      dpr={[1, 2]}
      gl={{ preserveDrawingBuffer: true }}
      onPointerMissed={() => {
        onSelectFace(null);
        onProbe(null);
      }}
    >
      <color attach="background" args={[theme.bg]} />
      <ambientLight intensity={0.6} />
      <directionalLight position={[50, 80, 60]} intensity={1.1} />
      <directionalLight position={[-60, -30, -50]} intensity={0.4} />

      <CameraFit box={activeBox} />

      {showResult && solveData ? (
        <ResultView
          solve={solveData}
          field={resultField}
          deformScale={deformScale}
          bands={bands}
          rangeMin={rangeMin}
          rangeMax={rangeMax}
          showEdges={showEdges}
          sectionAxis={sectionAxis}
          sectionPos={sectionPos}
          animate={animate}
          onProbe={onProbe}
        />
      ) : showMesh && meshData ? (
        <MeshView mesh={meshData} />
      ) : (
        data && (
          <ModelView
            data={data}
            selectedFaceId={selectedFaceId}
            hoveredFaceId={hoveredFaceId}
            assignments={assignments}
            loads={loads}
            faceGeom={faceGeom}
            onSelectFace={onSelectFace}
            onHoverFace={onHoverFace}
          />
        )
      )}

      <Grid
        args={[gridSize, gridSize]}
        cellSize={gridSize / 40}
        sectionSize={gridSize / 8}
        infiniteGrid
        fadeDistance={gridSize * 2.5}
        cellColor={theme.cell}
        sectionColor={theme.section}
        position={[0, activeBox ? -diagOf(activeBox) / 2 : 0, 0]}
      />

      <OrbitControls makeDefault enableDamping dampingFactor={0.1} />
      <GizmoHelper alignment="bottom-right" margin={[70, 70]}>
        <GizmoViewport axisColors={["#e0564f", "#54b15a", "#3b82c4"]} labelColor={theme.gizmoLabel} />
      </GizmoHelper>
    </Canvas>
  );
}
