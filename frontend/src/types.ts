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

export interface ModelSetup {
  material: Material;
  constraints: Constraint[];
  loads: Load[];
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
