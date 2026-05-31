import { useCallback, useEffect, useState } from "react";
import {
  datasetExportUrl,
  deleteAnalysis,
  fetchAnalyses,
  fetchAnalysisResult,
  fetchDatasetOptions,
  fetchGeometries,
} from "../api";
import type {
  AnalysisSummary,
  DatasetFilterParams,
  DatasetOptions,
  GeometrySummary,
  SolveResult,
} from "../types";

interface DatasetPanelProps {
  onLoadResult: (result: SolveResult) => void;
  refreshKey?: number;
}

const EMPTY_FILTERS: DatasetFilterParams = { limit: 100, offset: 0 };

export function DatasetPanel({ onLoadResult, refreshKey = 0 }: DatasetPanelProps) {
  const [filters, setFilters] = useState<DatasetFilterParams>(EMPTY_FILTERS);
  const [options, setOptions] = useState<DatasetOptions | null>(null);
  const [geometries, setGeometries] = useState<GeometrySummary[]>([]);
  const [items, setItems] = useState<AnalysisSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [{ items: rows, total: t }] = await Promise.all([
        fetchAnalyses(filters),
      ]);
      setItems(rows);
      setTotal(t);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Liste yuklenemedi");
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    fetchDatasetOptions().then(setOptions).catch(() => {});
    fetchGeometries().then(setGeometries).catch(() => {});
  }, []);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  const setF = (patch: Partial<DatasetFilterParams>) =>
    setFilters((prev) => ({ ...prev, ...patch, offset: 0 }));

  const clearFilters = () => setFilters(EMPTY_FILTERS);

  const handleDelete = async (id: number) => {
    if (!confirm(`Analiz #${id} silinsin mi?`)) return;
    try {
      await deleteAnalysis(id);
      if (selectedId === id) setSelectedId(null);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Silinemedi");
    }
  };

  const fmtDate = (iso: string) => {
    try {
      return new Date(iso).toLocaleString("tr-TR", { dateStyle: "short", timeStyle: "short" });
    } catch {
      return iso;
    }
  };

  return (
    <div className="dataset-panel">
      <div className="dataset-filters">
        <label className="field">
          <span>Dosya adi</span>
          <input
            type="text"
            placeholder="icerir..."
            value={filters.filename ?? ""}
            onChange={(e) => setF({ filename: e.target.value || undefined })}
          />
        </label>
        <label className="field">
          <span>Geometri</span>
          <select
            value={filters.geometry_id ?? ""}
            onChange={(e) =>
              setF({ geometry_id: e.target.value ? Number(e.target.value) : undefined })
            }
          >
            <option value="">Tumu</option>
            {geometries.map((g) => (
              <option key={g.id} value={g.id}>
                #{g.id} {g.filename} ({g.analysisCount})
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Analiz tipi</span>
          <select
            value={filters.analysis_type ?? ""}
            onChange={(e) => setF({ analysis_type: e.target.value || undefined })}
          >
            <option value="">Tumu</option>
            {(options?.analysisTypes ?? ["static_linear"]).map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Malzeme</span>
          <select
            value={filters.material_name ?? ""}
            onChange={(e) => setF({ material_name: e.target.value || undefined })}
          >
            <option value="">Tumu</option>
            {(options?.materialNames ?? []).map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Mesh h (min–max mm)</span>
          <div className="assign-row">
            <input
              type="number"
              placeholder="min"
              value={filters.mesh_es_min ?? ""}
              onChange={(e) =>
                setF({ mesh_es_min: e.target.value ? Number(e.target.value) : undefined })
              }
            />
            <input
              type="number"
              placeholder="max"
              value={filters.mesh_es_max ?? ""}
              onChange={(e) =>
                setF({ mesh_es_max: e.target.value ? Number(e.target.value) : undefined })
              }
            />
          </div>
        </label>
        <label className="field">
          <span>Sabit yuzey ID</span>
          <input
            type="number"
            placeholder="ornek: 3"
            value={filters.fixed_face_id ?? ""}
            onChange={(e) =>
              setF({ fixed_face_id: e.target.value ? Number(e.target.value) : undefined })
            }
          />
        </label>
        <label className="field">
          <span>Yuk tipi</span>
          <select
            value={filters.load_type ?? ""}
            onChange={(e) => setF({ load_type: e.target.value || undefined })}
          >
            <option value="">Tumu</option>
            {(options?.loadTypes ?? ["force", "pressure"]).map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="dataset-actions">
        <button className="btn" onClick={load} disabled={loading}>
          {loading ? "Yukleniyor..." : "Filtrele"}
        </button>
        <button className="btn" onClick={clearFilters}>
          Temizle
        </button>
        <a className="btn" href={datasetExportUrl(filters)} download="crash_dataset.csv">
          CSV Indir
        </a>
        <span className="muted dataset-count">{total} kayit</span>
      </div>

      {error && <p className="err">{error}</p>}

      <div className="dataset-table-wrap">
        <table className="dataset-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Tarih</th>
              <th>Dosya</th>
              <th>Tip</th>
              <th>h [mm]</th>
              <th>Malzeme</th>
              <th>BC</th>
              <th>Yuk</th>
              <th>|U| max</th>
              <th>vM max</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr>
                <td colSpan={11} className="muted">
                  Kayit yok. Cozum calistirdiginizde otomatik kaydedilir.
                </td>
              </tr>
            ) : (
              items.map((row) => (
                <tr
                  key={row.id}
                  className={row.id === selectedId ? "active" : ""}
                  onClick={() => setSelectedId(row.id)}
                >
                  <td>#{row.id}</td>
                  <td>{fmtDate(row.createdAt)}</td>
                  <td className="ellip" title={row.filename}>
                    {row.filename}
                  </td>
                  <td>{row.analysisType}</td>
                  <td>{row.meshElementSize.toFixed(2)}</td>
                  <td>{row.materialName}</td>
                  <td title={`yuzeyler: ${row.fixedFaceIds}`}>{row.constraintCount}</td>
                  <td title={row.loadTypes}>{row.loadCount}</td>
                  <td>{row.maxDisp.toFixed(4)}</td>
                  <td>{row.maxVonMises.toFixed(1)}</td>
                  <td className="row-actions">
                    <button
                      className="btn sm"
                      onClick={async (e) => {
                        e.stopPropagation();
                        try {
                          const full = await fetchAnalysisResult(row.id);
                          onLoadResult({
                            ...full,
                            filename: row.filename,
                            analysisId: row.id,
                          });
                        } catch (err) {
                          setError(err instanceof Error ? err.message : "Sonuc acilamadi");
                        }
                      }}
                    >
                      Ac
                    </button>
                    <button
                      className="x"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDelete(row.id);
                      }}
                    >
                      ×
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
