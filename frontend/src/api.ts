import type {
  AnalysisSummary,
  DatasetFilterParams,
  DatasetOptions,
  GeometrySummary,
  MeshResult,
  KeywordBlock,
  KeywordTemplate,
  ModelSetup,
  OpenRadiossStatus,
  SolveResult,
  TessellationResult,
  ValidationResult,
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";

async function postForm<T>(endpoint: string, form: FormData): Promise<T> {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    method: "POST",
    body: form,
  });

  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      // ignore JSON parse errors
    }
    throw new Error(detail);
  }

  return (await res.json()) as T;
}

export async function tessellateStep(file: File): Promise<TessellationResult> {
  const form = new FormData();
  form.append("file", file);
  return postForm<TessellationResult>("/step/tessellate", form);
}

export async function meshStep(
  file: File,
  elementSize: number,
  dim: number,
  recombine: boolean,
): Promise<MeshResult> {
  const form = new FormData();
  form.append("file", file);
  form.append("element_size", String(elementSize));
  form.append("dim", String(dim));
  form.append("recombine", String(recombine));
  return postForm<MeshResult>("/mesh/generate", form);
}

export async function midsurfaceShell(
  file: File,
  elementSize: number,
  recombine: boolean,
): Promise<MeshResult> {
  const form = new FormData();
  form.append("file", file);
  form.append("element_size", String(elementSize));
  form.append("recombine", String(recombine));
  return postForm<MeshResult>("/midsurface/shell", form);
}

export async function solveModel(
  file: File,
  setup: ModelSetup,
  elementSize: number,
): Promise<SolveResult> {
  const form = new FormData();
  form.append("file", file);
  form.append("setup", JSON.stringify(setup));
  form.append("element_size", String(elementSize));
  return postForm<SolveResult>("/solve", form);
}

export async function validateModel(
  setup: ModelSetup,
): Promise<ValidationResult> {
  const res = await fetch(`${API_BASE}/model/validate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(setup),
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = JSON.stringify(body.detail);
    } catch {
      // ignore
    }
    throw new Error(detail);
  }
  return (await res.json()) as ValidationResult;
}

function buildQuery(params: Record<string, string | number | undefined>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== "") q.set(k, String(v));
  }
  const s = q.toString();
  return s ? `?${s}` : "";
}

export async function fetchDatasetOptions(): Promise<DatasetOptions> {
  const res = await fetch(`${API_BASE}/dataset/options`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as DatasetOptions;
}

export async function fetchGeometries(): Promise<GeometrySummary[]> {
  const res = await fetch(`${API_BASE}/dataset/geometries`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const body = (await res.json()) as { items: GeometrySummary[] };
  return body.items;
}

export async function fetchAnalyses(
  filters: DatasetFilterParams,
): Promise<{ items: AnalysisSummary[]; total: number }> {
  const res = await fetch(
    `${API_BASE}/dataset/analyses${buildQuery(filters as Record<string, string | number | undefined>)}`,
  );
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const body = (await res.json()) as { items: AnalysisSummary[]; total: number };
  return { items: body.items, total: body.total };
}

export async function fetchAnalysisResult(id: number): Promise<SolveResult> {
  const res = await fetch(`${API_BASE}/dataset/analyses/${id}/result`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as SolveResult;
}

export async function deleteAnalysis(id: number): Promise<void> {
  const res = await fetch(`${API_BASE}/dataset/analyses/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
}

export function datasetExportUrl(filters: DatasetFilterParams): string {
  return `${API_BASE}/dataset/analyses/export${buildQuery(filters as Record<string, string | number | undefined>)}`;
}

export async function runParameterSweep(
  file: File,
  setup: ModelSetup,
  elementSizes: number[],
  notes?: string,
): Promise<{ created: { analysisId: number; elementSize: number }[]; count: number }> {
  const form = new FormData();
  form.append("file", file);
  form.append("setup", JSON.stringify(setup));
  form.append("element_sizes", JSON.stringify(elementSizes));
  form.append("notes", notes ?? "");
  const res = await fetch(`${API_BASE}/dataset/sweep`, { method: "POST", body: form });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return (await res.json()) as { created: { analysisId: number; elementSize: number }[]; count: number };
}

export async function fetchExplicitStatus(): Promise<OpenRadiossStatus> {
  const res = await fetch(`${API_BASE}/explicit/status`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as OpenRadiossStatus;
}

export async function fetchKeywordTemplates(): Promise<KeywordTemplate[]> {
  const res = await fetch(`${API_BASE}/keywords/templates`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const body = (await res.json()) as { items: KeywordTemplate[] };
  return body.items;
}

export async function composeKeywords(blocks: KeywordBlock[]): Promise<{ deck: string }> {
  const res = await fetch(`${API_BASE}/keywords/compose`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ blocks }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as { deck: string };
}

export async function generateKeywords(
  file: File,
  setup: ModelSetup,
  elementSize: number,
  runName: string,
): Promise<{
  deck: string;
  blocks: KeywordBlock[];
  nodeCount: number;
  tetCount: number;
}> {
  const form = new FormData();
  form.append("file", file);
  form.append("setup", JSON.stringify(setup));
  form.append("element_size", String(elementSize));
  form.append("run_name", runName);
  return postForm("/keywords/generate", form);
}

export async function downloadKeywordsRad(blocks: KeywordBlock[], filename: string) {
  const res = await fetch(`${API_BASE}/keywords/export`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ blocks }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const text = await res.text();
  const blob = new Blob([text], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export async function runExplicit(
  file: File,
  setup: ModelSetup,
  elementSize: number,
): Promise<SolveResult> {
  const form = new FormData();
  form.append("file", file);
  form.append("setup", JSON.stringify(setup));
  form.append("element_size", String(elementSize));
  return postForm<SolveResult>("/explicit/run", form);
}
