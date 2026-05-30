import type {
  MeshResult,
  ModelSetup,
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
