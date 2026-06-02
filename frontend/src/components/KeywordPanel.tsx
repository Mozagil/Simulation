import { useCallback, useEffect, useMemo, useState } from "react";
import {
  composeKeywords,
  downloadKeywordsRad,
  fetchKeywordTemplates,
  generateKeywords,
} from "../api";
import type { KeywordBlock, KeywordTemplate, Material, ModelSetup } from "../types";

const CAT_LABEL: Record<string, string> = {
  header: "Baslik",
  control: "Kontrol",
  material: "Malzeme",
  mesh: "Mesh",
  bc: "Sinir kosulu",
  load: "Yuk",
  contact: "Kontak",
  output: "Cikti",
  custom: "Ozel",
};

let _kid = 0;
const newId = () => `kw-${Date.now()}-${_kid++}`;

interface KeywordPanelProps {
  file: File | null;
  material: Material;
  constraints: ModelSetup["constraints"];
  loads: ModelSetup["loads"];
  explicit: ModelSetup["explicit"];
  solveElementSize: string;
  onBlocksChange?: (blocks: KeywordBlock[]) => void;
}

export function KeywordPanel({
  file,
  material,
  constraints,
  loads,
  explicit,
  solveElementSize,
  onBlocksChange,
}: KeywordPanelProps) {
  const [templates, setTemplates] = useState<KeywordTemplate[]>([]);
  const [blocks, setBlocks] = useState<KeywordBlock[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [deck, setDeck] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [runName, setRunName] = useState("crash");
  const [meta, setMeta] = useState<{ nodeCount?: number; tetCount?: number }>({});

  useEffect(() => {
    fetchKeywordTemplates().then(setTemplates).catch(() => {});
  }, []);

  useEffect(() => {
    onBlocksChange?.(blocks);
  }, [blocks, onBlocksChange]);

  const selected = useMemo(
    () => blocks.find((b) => b.id === selectedId) ?? blocks[0] ?? null,
    [blocks, selectedId],
  );

  const refreshPreview = useCallback(async (next: KeywordBlock[]) => {
    if (next.length === 0) {
      setDeck("");
      return;
    }
    try {
      const res = await composeKeywords(next);
      setDeck(res.deck);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Onizleme hatasi");
    }
  }, []);

  const setBlocksAndPreview = useCallback(
    (next: KeywordBlock[]) => {
      setBlocks(next);
      if (next.length > 0 && !next.some((b) => b.id === selectedId)) {
        setSelectedId(next[0].id);
      }
      void refreshPreview(next);
    },
    [refreshPreview, selectedId],
  );

  const updateBlock = (id: string, patch: Partial<KeywordBlock>) => {
    const next = blocks.map((b) => (b.id === id ? { ...b, ...patch } : b));
    setBlocksAndPreview(next);
  };

  const moveBlock = (id: string, dir: -1 | 1) => {
    const i = blocks.findIndex((b) => b.id === id);
    if (i < 0) return;
    const j = i + dir;
    if (j < 0 || j >= blocks.length) return;
    const next = [...blocks];
    [next[i], next[j]] = [next[j], next[i]];
    setBlocksAndPreview(next);
  };

  const removeBlock = (id: string) => {
    setBlocksAndPreview(blocks.filter((b) => b.id !== id));
  };

  const addTemplate = (tpl: KeywordTemplate) => {
    const block: KeywordBlock = {
      id: newId(),
      name: tpl.name,
      category: tpl.category,
      enabled: true,
      lines: tpl.lines,
    };
    setBlocksAndPreview([...blocks, block]);
    setSelectedId(block.id);
  };

  const handleGenerateFromModel = async () => {
    if (!file) {
      setError("Once STEP dosyasi ice aktarin.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const size = solveElementSize ? parseFloat(solveElementSize) : 0;
      const setup: ModelSetup = {
        material,
        constraints,
        loads,
        explicit,
        keyword_blocks: blocks,
      };
      const res = await generateKeywords(
        file,
        setup,
        Number.isFinite(size) ? size : 0,
        runName,
      );
      setBlocksAndPreview(res.blocks);
      setDeck(res.deck);
      setMeta({ nodeCount: res.nodeCount, tetCount: res.tetCount });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Uretim hatasi");
    } finally {
      setLoading(false);
    }
  };

  const handleDownload = () => {
    void downloadKeywordsRad(blocks, `${runName}_0000.rad`);
  };

  const copyDeck = async () => {
    try {
      await navigator.clipboard.writeText(deck);
    } catch {
      setError("Panoya kopyalanamadi");
    }
  };

  return (
    <div className="keyword-panel">
      <div className="keyword-toolbar">
        <label className="field">
          <span>Run adi</span>
          <input value={runName} onChange={(e) => setRunName(e.target.value)} />
        </label>
        <button
          className="btn primary"
          onClick={handleGenerateFromModel}
          disabled={loading || !file}
        >
          {loading ? "Uretiliyor..." : "Modelden Uret"}
        </button>
        <button className="btn" onClick={handleDownload} disabled={!deck}>
          .rad Indir
        </button>
        <button className="btn" onClick={copyDeck} disabled={!deck}>
          Kopyala
        </button>
      </div>

      {meta.nodeCount != null && (
        <p className="muted hint-small">
          Mesh: {meta.nodeCount.toLocaleString()} dugum · {meta.tetCount?.toLocaleString()} tetra
        </p>
      )}

      {error && <p className="err">{error}</p>}

      <label className="field">
        <span>Sablon ekle</span>
        <select
          defaultValue=""
          onChange={(e) => {
            const tpl = templates.find((t) => t.id === e.target.value);
            if (tpl) addTemplate(tpl);
            e.target.value = "";
          }}
        >
          <option value="">— Secin —</option>
          {templates.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name} — {t.description}
            </option>
          ))}
        </select>
      </label>

      <div className="keyword-split">
        <ul className="keyword-list">
          {blocks.length === 0 ? (
            <li className="muted">Henuz blok yok. Modelden Uret veya sablon ekleyin.</li>
          ) : (
            blocks.map((b) => (
              <li
                key={b.id}
                className={`${b.id === selected?.id ? "active" : ""} ${!b.enabled ? "off" : ""}`}
                onClick={() => setSelectedId(b.id)}
              >
                <label className="chk" onClick={(e) => e.stopPropagation()}>
                  <input
                    type="checkbox"
                    checked={b.enabled}
                    onChange={(e) => updateBlock(b.id, { enabled: e.target.checked })}
                  />
                </label>
                <span className="kw-name">{b.name}</span>
                <span className="tag">{CAT_LABEL[b.category] ?? b.category}</span>
                <span className="kw-actions">
                  <button type="button" className="x" title="Yukari" onClick={() => moveBlock(b.id, -1)}>
                    ↑
                  </button>
                  <button type="button" className="x" title="Asagi" onClick={() => moveBlock(b.id, 1)}>
                    ↓
                  </button>
                  <button type="button" className="x" onClick={() => removeBlock(b.id)}>
                    ×
                  </button>
                </span>
              </li>
            ))
          )}
        </ul>

        {selected && (
          <div className="keyword-editor">
            <label className="field">
              <span>Blok adi</span>
              <input
                value={selected.name}
                onChange={(e) => updateBlock(selected.id, { name: e.target.value })}
              />
            </label>
            <textarea
              className="keyword-textarea"
              spellCheck={false}
              value={selected.lines}
              onChange={(e) => updateBlock(selected.id, { lines: e.target.value })}
            />
          </div>
        )}
      </div>

      <label className="field">
        <span>Deck onizleme ({runName}_0000.rad)</span>
        <textarea className="keyword-preview" readOnly value={deck} spellCheck={false} />
      </label>

      <p className="muted hint-small">
        Explicit calistirirken bu bloklar (mesh haric) deck&apos;e eklenir. LAW2, kontak vb. icin
        sablon ekleyip duzenleyin.
      </p>
    </div>
  );
}
