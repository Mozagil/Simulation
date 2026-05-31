import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  fetchAnalysisResult,
  meshStep,
  midsurfaceShell,
  runParameterSweep,
  solveModel,
  tessellateStep,
  validateModel,
} from "./api";
import type {
  Constraint,
  Load,
  Material,
  MeshResult,
  SolveResult,
  TessellationResult,
  ValidationResult,
} from "./types";
import { Viewer } from "./components/Viewer";
import type { BackgroundMode, ViewMode } from "./components/Viewer";
import type { FaceAssignment } from "./components/ModelView";
import type { ProbeInfo, ResultField, SectionAxis } from "./components/ResultView";
import { FIELD_META, fieldStats, jetColor } from "./components/ResultView";
import { DatasetPanel } from "./components/DatasetPanel";
import { Section } from "./components/Section";
import { computeFaceGeometry } from "./faceGeometry";
import "./App.css";

const MATERIAL_PRESETS: Record<string, Material> = {
  Celik: { name: "Celik", youngs_modulus: 210000, poisson_ratio: 0.3, density: 7850 },
  Aluminyum: { name: "Aluminyum", youngs_modulus: 70000, poisson_ratio: 0.33, density: 2700 },
};

let _idCounter = 0;
const nextId = (prefix: string) => `${prefix}-${Date.now()}-${_idCounter++}`;

const rgbStr = (t: number) => {
  const [r, g, b] = jetColor(t);
  return `rgb(${Math.round(r * 255)},${Math.round(g * 255)},${Math.round(b * 255)})`;
};

/** Gosterge (legend) icin CSS gradient: bands>0 ayrik bantlar, aksi halde surekli. */
function legendCss(bands: number): string {
  if (bands > 0) {
    const segs: string[] = [];
    for (let i = 0; i < bands; i++) {
      const c = rgbStr((i + 0.5) / bands);
      segs.push(`${c} ${((i / bands) * 100).toFixed(2)}%`, `${c} ${(((i + 1) / bands) * 100).toFixed(2)}%`);
    }
    return `linear-gradient(to top, ${segs.join(",")})`;
  }
  const segs: string[] = [];
  const N = 24;
  for (let i = 0; i <= N; i++) segs.push(`${rgbStr(i / N)} ${((i / N) * 100).toFixed(1)}%`);
  return `linear-gradient(to top, ${segs.join(",")})`;
}

export default function App() {
  const [data, setData] = useState<TessellationResult | null>(null);
  const [meshData, setMeshData] = useState<MeshResult | null>(null);
  const [solveData, setSolveData] = useState<SolveResult | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [meshing, setMeshing] = useState(false);
  const [midsurfacing, setMidsurfacing] = useState(false);
  const [solving, setSolving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedFaceId, setSelectedFaceId] = useState<number | null>(null);
  const [hoveredFaceId, setHoveredFaceId] = useState<number | null>(null);
  const [background, setBackground] = useState<BackgroundMode>("dark");
  const [viewMode, setViewMode] = useState<ViewMode>("geometry");

  // Mesh kontrolleri
  const [elementSize, setElementSize] = useState<string>("");
  const [dim, setDim] = useState<number>(3);
  const [quad, setQuad] = useState<boolean>(false);

  // Midsurface mesh kontrolleri (bagimsiz)
  const [midElementSize, setMidElementSize] = useState<string>("");
  const [midQuad, setMidQuad] = useState<boolean>(false);

  // Model: malzeme + sinir kosullari + yukler
  const [material, setMaterial] = useState<Material>(MATERIAL_PRESETS.Celik);
  const [constraints, setConstraints] = useState<Constraint[]>([]);
  const [loads, setLoads] = useState<Load[]>([]);
  const [pressureVal, setPressureVal] = useState<string>("1");
  const [forceVec, setForceVec] = useState<{ x: string; y: string; z: string }>({
    x: "0",
    y: "0",
    z: "1000",
  });
  const [validation, setValidation] = useState<ValidationResult | null>(null);

  // Analiz (statik cozum)
  const [solveElementSize, setSolveElementSize] = useState<string>("");
  const [resultField, setResultField] = useState<ResultField>("vm");
  const [deformScale, setDeformScale] = useState<number>(0);

  // Faz 5: sonuc son-isleme (post-processing)
  const [bands, setBands] = useState<number>(0); // 0 = surekli
  const [showEdges, setShowEdges] = useState<boolean>(false);
  const [animate, setAnimate] = useState<boolean>(false);
  const [sectionAxis, setSectionAxis] = useState<SectionAxis>("none");
  const [sectionPos, setSectionPos] = useState<number>(50); // %
  const [rangeMode, setRangeMode] = useState<"auto" | "manual">("auto");
  const [rangeMinStr, setRangeMinStr] = useState<string>("");
  const [rangeMaxStr, setRangeMaxStr] = useState<string>("");
  const [probe, setProbe] = useState<ProbeInfo | null>(null);

  // Veri seti (surrogate / DB)
  const [datasetRefresh, setDatasetRefresh] = useState(0);
  const [lastAnalysisId, setLastAnalysisId] = useState<number | null>(null);
  const [sweepSizes, setSweepSizes] = useState<string>("4, 8, 16");
  const [sweeping, setSweeping] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const faceListRef = useRef<HTMLUListElement>(null);

  const handleFile = useCallback(async (f: File) => {
    setLoading(true);
    setError(null);
    setSelectedFaceId(null);
    setHoveredFaceId(null);
    setMeshData(null);
    setSolveData(null);
    setViewMode("geometry");
    setConstraints([]);
    setLoads([]);
    setValidation(null);
    setFile(f);
    try {
      const result = await tessellateStep(f);
      setData(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Bilinmeyen hata");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleMesh = useCallback(async () => {
    if (!file) return;
    setMeshing(true);
    setError(null);
    try {
      const size = elementSize ? parseFloat(elementSize) : 0;
      const result = await meshStep(file, Number.isFinite(size) ? size : 0, dim, quad);
      setMeshData(result);
      setViewMode("mesh");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Bilinmeyen hata");
    } finally {
      setMeshing(false);
    }
  }, [file, elementSize, dim, quad]);

  const handleMidsurface = useCallback(async () => {
    if (!file) return;
    setMidsurfacing(true);
    setError(null);
    try {
      const size = midElementSize ? parseFloat(midElementSize) : 0;
      const result = await midsurfaceShell(file, Number.isFinite(size) ? size : 0, midQuad);
      setMeshData(result);
      setViewMode("mesh");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Bilinmeyen hata");
    } finally {
      setMidsurfacing(false);
    }
  }, [file, midElementSize, midQuad]);

  const handleSolve = useCallback(async () => {
    if (!file) return;
    if (constraints.length === 0) {
      setError("En az bir sabit mesnet (fixed) tanimlayin - aksi halde sistem tekil olur.");
      return;
    }
    setSolving(true);
    setError(null);
    try {
      const size = solveElementSize ? parseFloat(solveElementSize) : 0;
      const result = await solveModel(
        file,
        { material, constraints, loads },
        Number.isFinite(size) ? size : 0,
      );
      setSolveData(result);
      setViewMode("result");
      if (result.analysisId != null) {
        setLastAnalysisId(result.analysisId);
        setDatasetRefresh((k) => k + 1);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Cozum hatasi");
    } finally {
      setSolving(false);
    }
  }, [file, material, constraints, loads, solveElementSize]);

  const handleSweep = useCallback(async () => {
    if (!file) return;
    if (constraints.length === 0) {
      setError("Parametre taramasi icin en az bir mesnet gerekli.");
      return;
    }
    const sizes = sweepSizes
      .split(/[,;\s]+/)
      .map((s) => parseFloat(s.trim()))
      .filter((n) => Number.isFinite(n) && n > 0);
    if (sizes.length === 0) {
      setError("Gecerli eleman boyutlari girin (ornek: 4, 8, 16).");
      return;
    }
    setSweeping(true);
    setError(null);
    try {
      const out = await runParameterSweep(file, { material, constraints, loads }, sizes);
      setDatasetRefresh((k) => k + 1);
      if (out.created.length > 0) {
        const last = out.created[out.created.length - 1];
        setLastAnalysisId(last.analysisId);
        const full = await fetchAnalysisResult(last.analysisId);
        setSolveData({ ...full, filename: file.name, analysisId: last.analysisId });
        setViewMode("result");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Tarama hatasi");
    } finally {
      setSweeping(false);
    }
  }, [file, material, constraints, loads, sweepSizes]);

  const handleLoadSavedResult = useCallback((result: SolveResult) => {
    setSolveData(result);
    setViewMode("result");
    setLastAnalysisId(result.analysisId ?? null);
    setError(null);
  }, []);

  const onInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) handleFile(f);
    e.target.value = "";
  };

  const selectedFace = useMemo(
    () => data?.faces.find((f) => f.id === selectedFaceId) ?? null,
    [data, selectedFaceId],
  );

  const faceGeom = useMemo(
    () => (data ? computeFaceGeometry(data) : new Map()),
    [data],
  );

  const dims = useMemo(() => {
    if (!data) return null;
    const [minx, miny, minz] = data.bboxMin;
    const [maxx, maxy, maxz] = data.bboxMax;
    return [maxx - minx, maxy - miny, maxz - minz] as [number, number, number];
  }, [data]);

  const assignments = useMemo(() => {
    const m = new Map<number, FaceAssignment>();
    for (const lo of loads) m.set(lo.face_id, "load");
    for (const c of constraints) m.set(c.face_id, "fixed");
    return m;
  }, [constraints, loads]);

  const fieldMeta = FIELD_META[resultField];

  // Secili alanin otomatik min/max'i
  const autoStats = useMemo(
    () => (solveData ? fieldStats(solveData, resultField) : { min: 0, max: 1 }),
    [solveData, resultField],
  );

  // Etkin renk araligi (otomatik veya manuel)
  const range = useMemo(() => {
    if (rangeMode === "manual") {
      const mn = parseFloat(rangeMinStr);
      const mx = parseFloat(rangeMaxStr);
      const lo = Number.isFinite(mn) ? mn : autoStats.min;
      const hi = Number.isFinite(mx) ? mx : autoStats.max;
      return hi > lo ? { min: lo, max: hi } : autoStats;
    }
    return autoStats;
  }, [rangeMode, rangeMinStr, rangeMaxStr, autoStats]);

  // Gosterge tik degerleri (ust = max, alt = min)
  const legendTicks = useMemo(() => {
    const NT = 4;
    const out: number[] = [];
    for (let i = 0; i <= NT; i++) out.push(range.max - ((range.max - range.min) * i) / NT);
    return out;
  }, [range]);

  // Alan / cozum degisince prob okumasini temizle
  useEffect(() => {
    setProbe(null);
  }, [resultField, solveData]);

  const enableManualRange = useCallback(() => {
    setRangeMinStr(autoStats.min.toFixed(fieldMeta.decimals));
    setRangeMaxStr(autoStats.max.toFixed(fieldMeta.decimals));
    setRangeMode("manual");
  }, [autoStats, fieldMeta.decimals]);

  const handleScreenshot = useCallback(() => {
    const canvas = document.querySelector<HTMLCanvasElement>(".viewport canvas");
    if (!canvas) return;
    const url = canvas.toDataURL("image/png");
    const a = document.createElement("a");
    const stem = (solveData?.filename ?? "sonuc").replace(/\.[^.]+$/, "");
    a.href = url;
    a.download = `${stem}_${resultField}.png`;
    a.click();
  }, [solveData, resultField]);

  // Viewport'ta hover edilen yuzeyi yuzey listesinde gorunur kil
  useEffect(() => {
    if (hoveredFaceId == null || !faceListRef.current) return;
    const el = faceListRef.current.querySelector<HTMLElement>(
      `[data-face="${hoveredFaceId}"]`,
    );
    el?.scrollIntoView({ block: "nearest" });
  }, [hoveredFaceId]);

  const addFixed = useCallback(() => {
    if (selectedFaceId == null) return;
    setValidation(null);
    setConstraints((prev) =>
      prev.some((c) => c.face_id === selectedFaceId)
        ? prev
        : [...prev, { id: nextId("c"), face_id: selectedFaceId, type: "fixed" }],
    );
  }, [selectedFaceId]);

  const addPressure = useCallback(() => {
    if (selectedFaceId == null) return;
    setValidation(null);
    const v = parseFloat(pressureVal) || 0;
    setLoads((prev) => [
      ...prev,
      { id: nextId("l"), face_id: selectedFaceId, type: "pressure", value: v, fx: 0, fy: 0, fz: 0 },
    ]);
  }, [selectedFaceId, pressureVal]);

  const addForce = useCallback(() => {
    if (selectedFaceId == null) return;
    setValidation(null);
    setLoads((prev) => [
      ...prev,
      {
        id: nextId("l"),
        face_id: selectedFaceId,
        type: "force",
        value: 0,
        fx: parseFloat(forceVec.x) || 0,
        fy: parseFloat(forceVec.y) || 0,
        fz: parseFloat(forceVec.z) || 0,
      },
    ]);
  }, [selectedFaceId, forceVec]);

  const removeConstraint = (id: string) => {
    setValidation(null);
    setConstraints((prev) => prev.filter((c) => c.id !== id));
  };
  const removeLoad = (id: string) => {
    setValidation(null);
    setLoads((prev) => prev.filter((l) => l.id !== id));
  };

  const handleValidate = useCallback(async () => {
    setError(null);
    try {
      const res = await validateModel({ material, constraints, loads });
      setValidation(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Dogrulama hatasi");
    }
  }, [material, constraints, loads]);

  const onPresetChange = (name: string) => {
    if (MATERIAL_PRESETS[name]) setMaterial(MATERIAL_PRESETS[name]);
    else setMaterial((m) => ({ ...m, name: "Ozel" }));
    setValidation(null);
  };

  const bcCount = constraints.length + loads.length;

  return (
    <div className="app">
      <header className="toolbar">
        <div className="brand">
          <span className="brand-mark">▣</span>
          <div>
            <h1>Crash CAE</h1>
            <p>STEP · Mesh · Sinir Kosullari</p>
          </div>
        </div>

        <div className="toolbar-actions">
          <fieldset className="radio-group" aria-label="Arka plan">
            <label>
              <input type="radio" name="bg" checked={background === "dark"} onChange={() => setBackground("dark")} />
              Koyu
            </label>
            <label>
              <input type="radio" name="bg" checked={background === "light"} onChange={() => setBackground("light")} />
              Beyaz
            </label>
          </fieldset>

          <button className="btn primary" onClick={() => fileInputRef.current?.click()} disabled={loading}>
            {loading ? "Yukleniyor..." : "STEP Ic Aktar"}
          </button>
          <input ref={fileInputRef} type="file" accept=".step,.stp" onChange={onInputChange} hidden />
          {data && (
            <span className="file-badge" title={data.filename}>
              {data.filename}
            </span>
          )}
        </div>
      </header>

      <div className="body">
        <main className="viewport">
          {error && <div className="overlay error">Hata: {error}</div>}
          {!data && !error && (
            <div className="overlay hint">
              <p>Baslamak icin bir <strong>.step / .stp</strong> dosyasi ice aktarin.</p>
              <p className="muted">Dondur · yakinlas · yuzeye tikla ve sinir kosulu/yuk ata.</p>
            </div>
          )}
          {data && (
            <div className="view-toggle">
              <button className={viewMode === "geometry" ? "active" : ""} onClick={() => setViewMode("geometry")}>
                Geometri
              </button>
              <button className={viewMode === "mesh" ? "active" : ""} onClick={() => setViewMode("mesh")} disabled={!meshData}>
                Mesh
              </button>
              <button className={viewMode === "result" ? "active" : ""} onClick={() => setViewMode("result")} disabled={!solveData}>
                Sonuc
              </button>
            </div>
          )}
          {data && viewMode !== "result" && (
            <div className="legend">
              <span><i className="sw sw-fixed" /> Mesnet</span>
              <span><i className="sw sw-load" /> Yuk</span>
              <span><i className="sw sw-sel" /> Secili</span>
            </div>
          )}
          {viewMode === "result" && solveData && (
            <div className="post-legend">
              <div className="pl-title">
                {fieldMeta.label}
                <span className="pl-unit">[{fieldMeta.unit}]</span>
              </div>
              <div className="pl-row">
                <div className="pl-bar" style={{ background: legendCss(bands) }} />
                <div className="pl-ticks">
                  {legendTicks.map((v, i) => (
                    <span key={i}>{v.toFixed(fieldMeta.decimals)}</span>
                  ))}
                </div>
              </div>
            </div>
          )}
          {viewMode === "result" && probe && (
            <div className="probe-box">
              <strong>
                {fieldMeta.label}: {probe.value.toFixed(fieldMeta.decimals)} {fieldMeta.unit}
              </strong>
              <span className="muted">
                x {probe.x.toFixed(1)} · y {probe.y.toFixed(1)} · z {probe.z.toFixed(1)}
              </span>
            </div>
          )}
          <Viewer
            data={data}
            meshData={meshData}
            solveData={solveData}
            resultField={resultField}
            deformScale={deformScale}
            bands={bands}
            rangeMin={range.min}
            rangeMax={range.max}
            showEdges={showEdges}
            sectionAxis={sectionAxis}
            sectionPos={sectionPos / 100}
            animate={animate}
            onProbe={setProbe}
            viewMode={viewMode}
            selectedFaceId={selectedFaceId}
            hoveredFaceId={hoveredFaceId}
            assignments={assignments}
            loads={loads}
            faceGeom={faceGeom}
            background={background}
            onSelectFace={setSelectedFaceId}
            onHoverFace={setHoveredFaceId}
          />
        </main>

        <aside className="panel wide">
          {!data && <p className="muted empty-note">Model yuklenmedi. Bir STEP dosyasi ice aktarin.</p>}

          {data && (
            <>
              <Section title="Geometri">
                <dl className="stats">
                  <div><dt>Dosya</dt><dd className="ellip" title={data.filename}>{data.filename}</dd></div>
                  <div><dt>Yuzey</dt><dd>{data.faceCount}</dd></div>
                  <div><dt>Ucgen</dt><dd>{data.triangleCount.toLocaleString()}</dd></div>
                  {dims && (
                    <div>
                      <dt>Olculer</dt>
                      <dd>{dims[0].toFixed(1)} × {dims[1].toFixed(1)} × {dims[2].toFixed(1)} mm</dd>
                    </div>
                  )}
                </dl>
              </Section>

              <Section title="Model" badge={bcCount || undefined}>
                <h3>Malzeme</h3>
                <div className="mesh-controls">
                  <label className="field">
                    <span>Hazir malzeme</span>
                    <select
                      value={MATERIAL_PRESETS[material.name] ? material.name : "Ozel"}
                      onChange={(e) => onPresetChange(e.target.value)}
                    >
                      <option value="Celik">Celik</option>
                      <option value="Aluminyum">Aluminyum</option>
                      <option value="Ozel">Ozel</option>
                    </select>
                  </label>
                  <div className="row3">
                    <label className="field">
                      <span>E (MPa)</span>
                      <input type="number" value={material.youngs_modulus}
                        onChange={(e) => { setMaterial((m) => ({ ...m, name: "Ozel", youngs_modulus: parseFloat(e.target.value) || 0 })); setValidation(null); }} />
                    </label>
                    <label className="field">
                      <span>Poisson</span>
                      <input type="number" step="0.01" value={material.poisson_ratio}
                        onChange={(e) => { setMaterial((m) => ({ ...m, name: "Ozel", poisson_ratio: parseFloat(e.target.value) || 0 })); setValidation(null); }} />
                    </label>
                    <label className="field">
                      <span>rho (kg/m³)</span>
                      <input type="number" value={material.density}
                        onChange={(e) => { setMaterial((m) => ({ ...m, name: "Ozel", density: parseFloat(e.target.value) || 0 })); setValidation(null); }} />
                    </label>
                  </div>
                </div>

                <h3>Secili Yuzey</h3>
                {selectedFace ? (
                  <>
                    <dl className="stats">
                      <div><dt>ID</dt><dd>#{selectedFace.id}</dd></div>
                      <div><dt>Tip</dt><dd>{selectedFace.surface_type}</dd></div>
                      <div><dt>Alan</dt><dd>{selectedFace.area.toFixed(2)} mm²</dd></div>
                    </dl>
                    <div className="assign">
                      <button className="btn full" onClick={addFixed}>Sabit Mesnet (Fixed)</button>
                      <div className="assign-row">
                        <input type="number" step="0.1" value={pressureVal}
                          onChange={(e) => setPressureVal(e.target.value)} title="Basinc [MPa], + disari" />
                        <button className="btn" onClick={addPressure}>Basinc Ekle (MPa)</button>
                      </div>
                      <div className="assign-row force">
                        <input type="number" value={forceVec.x} onChange={(e) => setForceVec((v) => ({ ...v, x: e.target.value }))} title="Fx [N]" />
                        <input type="number" value={forceVec.y} onChange={(e) => setForceVec((v) => ({ ...v, y: e.target.value }))} title="Fy [N]" />
                        <input type="number" value={forceVec.z} onChange={(e) => setForceVec((v) => ({ ...v, z: e.target.value }))} title="Fz [N]" />
                      </div>
                      <button className="btn full" onClick={addForce}>Kuvvet Ekle (N)</button>
                    </div>
                  </>
                ) : (
                  <p className="muted">Viewport'ta bir yuzeye tiklayin, sonra mesnet/yuk atayin.</p>
                )}

                <h3>Sinir Kosullari &amp; Yukler</h3>
                {bcCount === 0 ? (
                  <p className="muted">Henuz tanim yok.</p>
                ) : (
                  <ul className="bc-list">
                    {constraints.map((c) => (
                      <li key={c.id}>
                        <span className="tag fixed">FIX</span>
                        <span>Yuzey #{c.face_id}</span>
                        <button className="x" onClick={() => removeConstraint(c.id)}>×</button>
                      </li>
                    ))}
                    {loads.map((l) => (
                      <li key={l.id}>
                        <span className="tag load">{l.type === "pressure" ? "P" : "F"}</span>
                        <span>
                          Yuzey #{l.face_id}{" "}
                          {l.type === "pressure" ? `· ${l.value} MPa` : `· (${l.fx}, ${l.fy}, ${l.fz}) N`}
                        </span>
                        <button className="x" onClick={() => removeLoad(l.id)}>×</button>
                      </li>
                    ))}
                  </ul>
                )}
                <button className="btn primary full" onClick={handleValidate}>Modeli Dogrula</button>
                {validation && (
                  <div className={`validation ${validation.ok ? "ok" : "bad"}`}>
                    <dl className="stats">
                      <div><dt>Mesnet</dt><dd>{validation.constraint_count}</dd></div>
                      <div><dt>Yuk</dt><dd>{validation.load_count}</dd></div>
                      <div><dt>Toplam kuvvet</dt><dd>{validation.total_force_magnitude.toFixed(1)} N</dd></div>
                    </dl>
                    {validation.warnings.map((w, i) => (<p key={i} className="warn">⚠ {w}</p>))}
                    {validation.errors.map((e, i) => (<p key={i} className="err">✕ {e}</p>))}
                  </div>
                )}
              </Section>

              <Section title="Mesh">
                <div className="mesh-controls">
                  <label className="field">
                    <span>Eleman boyutu (mm)</span>
                    <input type="number" min={0} step="0.5" placeholder="otomatik" value={elementSize} onChange={(e) => setElementSize(e.target.value)} />
                  </label>
                  <label className="field">
                    <span>Eleman tipi</span>
                    <select value={dim} onChange={(e) => setDim(Number(e.target.value))}>
                      <option value={3}>Hacim (3D · tetra)</option>
                      <option value={2}>Yuzey (2D · shell)</option>
                    </select>
                  </label>
                  <label className="field">
                    <span>Eleman sekli (2D)</span>
                    <select value={quad ? "quad" : "tri"} onChange={(e) => setQuad(e.target.value === "quad")}>
                      <option value="tri">Ucgen (tri)</option>
                      <option value="quad">Dortgen (quad)</option>
                    </select>
                  </label>
                  <button className="btn primary full" onClick={handleMesh} disabled={meshing || midsurfacing}>
                    {meshing ? "Mesh uretiliyor..." : "Mesh Uret"}
                  </button>
                </div>
                {meshData && !meshData.isShell && (
                  <dl className="stats">
                    <div><dt>Dugum</dt><dd>{meshData.nodeCount.toLocaleString()}</dd></div>
                    {meshData.dim === 2 ? (
                      <>
                        <div><dt>Ucgen</dt><dd>{meshData.triangleCount.toLocaleString()}</dd></div>
                        <div><dt>Dortgen</dt><dd>{meshData.quadCount.toLocaleString()}</dd></div>
                      </>
                    ) : (
                      <>
                        <div><dt>Yuzey ucgen</dt><dd>{meshData.triangleCount.toLocaleString()}</dd></div>
                        <div><dt>Tetrahedra</dt><dd>{meshData.tetraCount.toLocaleString()}</dd></div>
                      </>
                    )}
                    <div><dt>Eleman boyutu</dt><dd>{meshData.elementSize.toFixed(2)} mm</dd></div>
                  </dl>
                )}
              </Section>

              <Section title="Midsurface Mesh" defaultOpen={false}>
                <div className="mesh-controls">
                  <label className="field">
                    <span>Eleman boyutu (mm)</span>
                    <input type="number" min={0} step="0.5" placeholder="otomatik" value={midElementSize} onChange={(e) => setMidElementSize(e.target.value)} />
                  </label>
                  <label className="field">
                    <span>Eleman sekli</span>
                    <select value={midQuad ? "quad" : "tri"} onChange={(e) => setMidQuad(e.target.value === "quad")}>
                      <option value="tri">Ucgen (tri)</option>
                      <option value="quad">Dortgen (quad)</option>
                    </select>
                  </label>
                  <button className="btn primary full" onClick={handleMidsurface} disabled={meshing || midsurfacing}>
                    {midsurfacing ? "Orta yuzey cikariliyor..." : "Midsurface + Shell Mesh"}
                  </button>
                  <p className="muted hint-small">
                    Yalnizca ince cidarli / sabit kalinlikli planar parcalar icindir.
                  </p>
                </div>
                {meshData && meshData.isShell && (
                  <dl className="stats">
                    <div><dt>Tip</dt><dd>Shell (2D)</dd></div>
                    <div><dt>Orta yuzey</dt><dd>{meshData.surfaceCount}</dd></div>
                    <div><dt>Kalinlik</dt><dd>{meshData.avgThickness?.toFixed(2)} mm</dd></div>
                    <div><dt>Dugum</dt><dd>{meshData.nodeCount.toLocaleString()}</dd></div>
                    <div><dt>Ucgen</dt><dd>{meshData.triangleCount.toLocaleString()}</dd></div>
                    <div><dt>Dortgen</dt><dd>{meshData.quadCount.toLocaleString()}</dd></div>
                  </dl>
                )}
              </Section>

              <Section title="Analiz (Statik)" badge={solveData ? "✓" : undefined}>
                <div className="mesh-controls">
                  <label className="field">
                    <span>Eleman boyutu (mm)</span>
                    <input type="number" min={0} step="0.5" placeholder="otomatik" value={solveElementSize} onChange={(e) => setSolveElementSize(e.target.value)} />
                  </label>
                  <button
                    className="btn primary full"
                    onClick={handleSolve}
                    disabled={solving || constraints.length === 0}
                    title={constraints.length === 0 ? "Once en az bir sabit mesnet ekleyin" : ""}
                  >
                    {solving ? "Cozuluyor..." : "Coz (Lineer Statik)"}
                  </button>
                  <p className="muted hint-small">
                    Gomulu acik kaynak cozucu (tet4). Mesnet + yuk gerekir. Lineer tet
                    elemani gorece katidir; daha hassas sonuc icin eleman boyutunu kucultun.
                  </p>
                </div>
                {solveData && (
                  <>
                    <dl className="stats">
                      <div><dt>Dugum</dt><dd>{solveData.nodeCount.toLocaleString()}</dd></div>
                      <div><dt>Tetrahedra</dt><dd>{solveData.tetCount.toLocaleString()}</dd></div>
                      <div><dt>Maks. deplasman</dt><dd>{solveData.maxDisp.toFixed(4)} mm</dd></div>
                      <div><dt>Maks. von Mises</dt><dd>{solveData.maxVonMises.toFixed(1)} MPa</dd></div>
                      <div><dt>Eleman boyutu</dt><dd>{solveData.elementSize.toFixed(2)} mm</dd></div>
                      {lastAnalysisId != null && (
                        <div><dt>Veritabani ID</dt><dd>#{lastAnalysisId}</dd></div>
                      )}
                    </dl>
                    <label className="field">
                      <span>Sonuc alani</span>
                      <select value={resultField} onChange={(e) => setResultField(e.target.value as ResultField)}>
                        <option value="vm">von Mises gerilme</option>
                        <option value="disp">Deplasman buyuklugu |U|</option>
                        <option value="ux">Deplasman Ux</option>
                        <option value="uy">Deplasman Uy</option>
                        <option value="uz">Deplasman Uz</option>
                      </select>
                    </label>
                    <label className="field">
                      <span>Deformasyon olcegi: {deformScale}×</span>
                      <input type="range" min={0} max={200} step={1} value={deformScale}
                        onChange={(e) => setDeformScale(Number(e.target.value))} />
                    </label>

                    <h3>Son Isleme (Post)</h3>
                    <label className="field">
                      <span>Kontur bandi</span>
                      <select value={bands} onChange={(e) => setBands(Number(e.target.value))}>
                        <option value={0}>Surekli (smooth)</option>
                        <option value={8}>8 bant</option>
                        <option value={12}>12 bant</option>
                        <option value={16}>16 bant</option>
                        <option value={24}>24 bant</option>
                      </select>
                    </label>

                    <label className="field">
                      <span>Renk araligi</span>
                      <select
                        value={rangeMode}
                        onChange={(e) => (e.target.value === "manual" ? enableManualRange() : setRangeMode("auto"))}
                      >
                        <option value="auto">Otomatik (min–max)</option>
                        <option value="manual">Manuel</option>
                      </select>
                    </label>
                    {rangeMode === "manual" && (
                      <div className="row3" style={{ gridTemplateColumns: "1fr 1fr" }}>
                        <label className="field">
                          <span>Min</span>
                          <input type="number" value={rangeMinStr} onChange={(e) => setRangeMinStr(e.target.value)} />
                        </label>
                        <label className="field">
                          <span>Max</span>
                          <input type="number" value={rangeMaxStr} onChange={(e) => setRangeMaxStr(e.target.value)} />
                        </label>
                      </div>
                    )}

                    <label className="field">
                      <span>Kesit (clip) ekseni</span>
                      <select value={sectionAxis} onChange={(e) => setSectionAxis(e.target.value as SectionAxis)}>
                        <option value="none">Kapali</option>
                        <option value="x">X ekseni</option>
                        <option value="y">Y ekseni</option>
                        <option value="z">Z ekseni</option>
                      </select>
                    </label>
                    {sectionAxis !== "none" && (
                      <label className="field">
                        <span>Kesit konumu: %{sectionPos}</span>
                        <input type="range" min={0} max={100} step={1} value={sectionPos}
                          onChange={(e) => setSectionPos(Number(e.target.value))} />
                      </label>
                    )}

                    <div className="post-toggles">
                      <label className="chk">
                        <input type="checkbox" checked={showEdges} onChange={(e) => setShowEdges(e.target.checked)} />
                        Mesh kenarlari
                      </label>
                      <label className="chk">
                        <input type="checkbox" checked={animate} onChange={(e) => setAnimate(e.target.checked)} />
                        Deformasyon animasyonu
                      </label>
                    </div>
                    {animate && deformScale === 0 && (
                      <p className="muted hint-small">Animasyon icin deformasyon olcegini artirin.</p>
                    )}

                    <button className="btn full" onClick={handleScreenshot}>Goruntuyu Kaydet (PNG)</button>
                    <p className="muted hint-small">
                      Viewport'ta sonuca tiklayarak o noktadaki degeri okuyabilirsiniz (prob).
                    </p>
                  </>
                )}

                <h3>Surrogate veri (parametre taramasi)</h3>
                <label className="field">
                  <span>Eleman boyutlari (mm, virgulle)</span>
                  <input
                    type="text"
                    value={sweepSizes}
                    onChange={(e) => setSweepSizes(e.target.value)}
                    placeholder="4, 8, 16"
                  />
                </label>
                <button
                  className="btn full"
                  onClick={handleSweep}
                  disabled={sweeping || !file || constraints.length === 0}
                >
                  {sweeping ? "Taraniyor..." : "Mesh h Taramasi (DB'ye kaydet)"}
                </button>
                <p className="muted hint-small">
                  Ayni geometri + BC ile birden fazla mesh boyutunda cozer; surrogate regression icin veri seti olusturur.
                </p>
              </Section>

              <Section title="Veri Seti" badge={datasetRefresh > 0 ? "●" : undefined} defaultOpen={false}>
                <DatasetPanel refreshKey={datasetRefresh} onLoadResult={handleLoadSavedResult} />
              </Section>

              <Section title="Yuzey Listesi" badge={data.faceCount} defaultOpen={false}>
                <ul className="face-list" ref={faceListRef}>
                  {data.faces.map((f) => (
                    <li
                      key={f.id}
                      data-face={f.id}
                      className={`${f.id === selectedFaceId ? "active" : ""} ${f.id === hoveredFaceId ? "hovered" : ""}`}
                      onClick={() => setSelectedFaceId(f.id)}
                      onMouseEnter={() => setHoveredFaceId(f.id)}
                      onMouseLeave={() => setHoveredFaceId(null)}
                    >
                      <span>#{f.id}</span>
                      <span className="muted">{f.surface_type}</span>
                      <span className="area">{f.area.toFixed(1)} mm²</span>
                    </li>
                  ))}
                </ul>
              </Section>
            </>
          )}
        </aside>
      </div>
    </div>
  );
}
