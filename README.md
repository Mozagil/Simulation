# Crash CAE — Açık Kaynak Simülasyon Platformu

Makine mühendisliği için web tabanlı, **tamamen açık kaynak** beslenen bir CAE ön/son işleme platformu. ANSYS SpaceClaim / ANSA / HyperMesh tarzı bir akış hedeflenir.

> Bu repo **Faz 1-2**'yi içerir: STEP içe aktarma → 3B görüntüleme (döndür/pan/zoom) → yüzey (face) seçimi → Gmsh ile mesh üretimi (2D/3D) ve görselleştirme.

## Mimari

```
Crash/
├── backend/          FastAPI + OpenCASCADE (OCP) + Gmsh + meshio
│   └── app/
│       ├── main.py          FastAPI uygulaması ve endpoint'ler
│       ├── step_loader.py   STEP okuma + per-face üçgenleştirme
│       ├── mesher.py        Gmsh ile mesh üretimi (2D/3D, tri/quad)
│       ├── midsurface.py    Orta yüzey çıkarımı (face pairing)
│       ├── models.py        Malzeme/BC/yük veri modeli + doğrulama
│       └── solver.py        Gömülü lineer-statik FEM (tet4, numpy + scipy)
└── frontend/         React + TypeScript + Vite + react-three-fiber (three.js)
    └── src/
        ├── App.tsx
        ├── api.ts
        ├── faceGeometry.ts  Per-face centroid/normal (glif konumlandırma)
        └── components/  Viewer, ModelView, MeshView, ResultView
```

**Yüzey seçimi nasıl çalışır:** Backend STEP'i OpenCASCADE ile okur ve her B-Rep yüzeyini ayrı üçgenleştirir; her üçgene `face_id` atanır (`triangleFaceIds`). Frontend bu veriyi three.js `BufferGeometry`'ye yükler; raycaster ile tıklanan üçgenin indeksinden `face_id` bulunur ve yüzey vertex-renkleriyle vurgulanır.

**Statik analiz (Faz 4) nasıl çalışır:** [backend/app/solver.py](backend/app/solver.py) harici bir binary olmadan çalışan, gömülü açık kaynak bir lineer-statik FEM çözücüsüdür. STEP, Gmsh ile 3B tetrahedra (tet4 / sabit-gerinim CST elemanı) mesh'ine çevrilir. Frontend'de seçilen yüzeyler (OCCT `face_id`) ile mesh yüzeyleri, **centroid eşleştirmesi** ile bağlanır; böylece sabit mesnetler (fixed → ilgili düğümlerin tüm serbestlik dereceleri sıfırlanır) ve yükler (kuvvet → yüzey düğümlerine dağıtılır; basınç → yüzey üçgenlerine dışa dönük normal boyunca uygulanır) doğru düğüm setlerine atanır. Global rijitlik matrisi `scipy` seyrek (sparse) formatta kurulur ve `spsolve` ile `K u = f` çözülür. Sonuç: düğüm deplasmanları + eleman gerilmelerinden nodal von Mises. **Sınırlama:** lineer tet4 elemanı eğilmede gerçeğe göre fazla "katı"dır; daha hassas sonuç için eleman boyutunu küçültün. İleride kuadratik tet (C3D10) veya alternatif çözücü olarak CalculiX/OpenRadioss eklenebilir.

**Midsurface (orta yüzey) nasıl çalışır:** [backend/app/midsurface.py](backend/app/midsurface.py) yüzey-eşleştirme (face pairing) yöntemiyle çalışır: birbirine paralel, alanları benzer, lateral örtüşen ve aralarında küçük bir mesafe (kalınlık `t`) bulunan planar yüzey çiftleri bulunur; her çift için yüzeylerden biri `t/2` ötelenerek orta yüzey üretilir ve kalınlık kaydedilir. Sonuç compound STEP olarak yazılıp Gmsh ile 2D (üçgen shell) mesh'lenir. **Sınırlamalar:** yalnızca düzlemsel (planar) duvarlar; eğri (silindir vb.) duvarlar ve karmaşık kesişim birleştirmeleri henüz desteklenmez.

## Kullanılan Açık Kaynak Araçlar

| Amaç | Araç | Lisans |
|------|------|--------|
| CAD çekirdeği / STEP okuma + topoloji | OpenCASCADE (cadquery-ocp) | LGPL |
| Mesh (sonraki faz) | Gmsh | GPL |
| Format dönüşümü | meshio | MIT |
| Lineer cebir / seyrek çözüm | NumPy + SciPy | BSD |
| Yapısal çözücü (lineer statik) | Gömülü FEM (tet4) | proje içi |
| Yapısal çözücü (gelecek alternatif) | CalculiX | GPL |
| Crash / explicit (sonraki faz) | OpenRadioss | AGPL-3.0 |
| 3B web görselleştirme | three.js / react-three-fiber | MIT |

## Kurulum

### Önkoşullar
- Python 3.13 (`py` launcher) ve Node.js 18+ / npm

### Backend
```powershell
cd backend
py -m venv .venv
# pip yoksa: curl.exe -sSL https://bootstrap.pypa.io/get-pip.py -o ../get-pip.py; .venv\Scripts\python.exe ../get-pip.py
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### Frontend
```powershell
cd frontend
npm install
```

## Çalıştırma

İki terminal açın:

**Backend** (port 8010):
```powershell
cd backend
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8010
```

**Frontend** (port 5173):
```powershell
cd frontend
npm run dev
```

Tarayıcıda `http://localhost:5173` açın. `/api` istekleri Vite tarafından backend'e proxy'lenir.

## Test

Örnek bir STEP dosyası üretmek için:
```powershell
cd backend
.venv\Scripts\python.exe make_test_step.py test_model.step
```
Ardından arayüzde **STEP İç Aktar** ile `backend/test_model.step` dosyasını yükleyin.

## Yol Haritası
- [x] **Faz 1** — STEP import, 3B görüntüleme, yüzey seçimi
- [x] **Faz 2** — Gmsh ile mesh üretimi ve görselleştirme (2D yüzey / 3D tetra, eleman boyutu kontrolü)
- [x] **Faz 2.5** — Midsurface (orta yüzey) çıkarımı + 2D shell mesh (ince cidarlı / sabit kalınlıklı planar parçalar)
- [x] **Faz 2.6** — 2D / shell mesh için dörtgen (quad) eleman seçeneği (Gmsh blossom recombination)
- [x] **Faz 3** — Malzeme tanımı + seçili yüzeylere sınır koşulu (fixed) / yük (basınç, kuvvet) atama, görselleştirme (renkli yüzeyler + kuvvet okları) ve model doğrulama
- [x] **Faz 4** — Lineer-statik yapısal çözüm: gömülü açık kaynak FEM çözücü (tet4, numpy+scipy), von Mises gerilme + deplasman kontur görselleştirmesi ve deformasyon ölçeği
- [ ] **Faz 5** — Sonuç son-işleme (vtk.js)
- [ ] **Faz 6** — OpenRadioss ile crash / explicit dynamics
