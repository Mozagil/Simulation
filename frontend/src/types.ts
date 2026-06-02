export interface FaceInfo {
  id: number;
  surface_type: string;
  area: number;
  triangle_count: number;
}

export interface Material {
  name: string;
  youngs_modulus: number; // E [MPa]
  poisson_ratio: number;
  density: number; // [kg/m^3]
}

export interface Constraint {
  id: string;
  face_id: number;
  type: "fixed";
}

export interface Load {
  id: string;
  face_id: number;
  type: "pressure" | "force";
  value: number; // pressure [MPa]
  fx: number;
  fy: number;
  fz: number; // force [N]
}

export interface ExplicitParams {
  end_time_ms: number;
  dt_ms?: number | null;
  initial_velocity: [number, number, number];
  gravity: number;
  threads: number;
  output_frames: number;
}

export interface KeywordBlock {
  id: string;
  name: string;
  category: string;
  enabled: boolean;
  lines: string;
}

export interface KeywordTemplate {
  id: string;
  name: string;
  category: string;
  description: string;
  lines: string;
}

export interface ModelSetup {
  material: Material;
  constraints: Constraint[];
  loads: Load[];
  explicit?: ExplicitParams;
  keyword_blocks?: KeywordBlock[];
}

export interface ExplicitFrame {
  timeMs: number;
  positions: number[];
  disp: number[];
  dispMag: number[];
  vonMises: number[];
}

export interface ValidationResult {
  ok: boolean;
  constraint_count: number;
  load_count: number;
  fixed_faces: number[];
  loaded_faces: number[];
  total_force: [number, number, number];
  total_force_magnitude: number;
  warnings: string[];
  errors: string[];
}

export interface SolveResult {
  positions: number[]; // yuzey ucgenleri (9/ucgen)
  disp: number[]; // dugum deplasman vektoru (9/ucgen)
  dispMag: number[]; // |u| (3/ucgen)
  vonMises: number[]; // nodal vM (3/ucgen)
  nodeCount: number;
  tetCount: number;
  maxDisp: number; // [mm]
  maxVonMises: number; // [MPa]
  elementSize: number;
  bboxMin: [number, number, number];
  bboxMax: [number, number, number];
  filename: string;
  analysisId?: number;
  analysisType?: string;
  frames?: ExplicitFrame[];
  runLogs?: string[];
}

export interface OpenRadiossStatus {
  installed: boolean;
  message?: string;
  install_hint?: string;
  path?: string;
}

/** Veritabanindaki analiz ozeti (surrogate veri seti satiri). */
export interface AnalysisSummary {
  id: number;
  geometryId: number;
  filename: string;
  createdAt: string;
  analysisType: string;
  status: string;
  meshElementSize: number;
  meshDim: number;
  materialName: string;
  youngsModulus: number;
  poissonRatio: number;
  density: number;
  constraintCount: number;
  loadCount: number;
  fixedFaceIds: string;
  loadTypes: string;
  totalForceMag: number;
  nodeCount: number;
  tetCount: number;
  maxDisp: number;
  maxVonMises: number;
  faceCount: number;
  diagMm: number;
  bboxMin: [number, number, number];
  bboxMax: [number, number, number];
}

export interface DatasetFilterParams {
  geometry_id?: number;
  filename?: string;
  analysis_type?: string;
  material_name?: string;
  mesh_es_min?: number;
  mesh_es_max?: number;
  youngs_min?: number;
  youngs_max?: number;
  max_disp_min?: number;
  max_disp_max?: number;
  max_vm_min?: number;
  max_vm_max?: number;
  fixed_face_id?: number;
  load_type?: string;
  limit?: number;
  offset?: number;
}

export interface DatasetOptions {
  analysisTypes: string[];
  materialNames: string[];
  loadTypes: string[];
}

export interface GeometrySummary {
  id: number;
  filename: string;
  faceCount: number;
  triangleCount: number;
  diagMm: number;
  analysisCount: number;
  createdAt: string;
}

export interface TessellationResult {
  positions: number[];
  triangleFaceIds: number[];
  faces: FaceInfo[];
  bboxMin: [number, number, number];
  bboxMax: [number, number, number];
  triangleCount: number;
  faceCount: number;
  filename: string;
}

export interface MeshResult {
  positions: number[];
  edges: number[];
  nodeCount: number;
  triangleCount: number;
  quadCount: number;
  tetraCount: number;
  elementSize: number;
  dim: number;
  recombine: boolean;
  bboxMin: [number, number, number];
  bboxMax: [number, number, number];
  filename: string;
  // Midsurface shell mesh icin opsiyonel alanlar
  isShell?: boolean;
  surfaceCount?: number;
  avgThickness?: number;
  thicknesses?: number[];
}
