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
│       ├── solver.py        Gömülü lineer-statik FEM (tet4, numpy + scipy)
│       ├── database.py      SQLite bağlantısı
│       ├── db_models.py       Geometri + analiz ORM tabloları
│       ├── analysis_store.py  Kayıt, filtreleme, CSV export
│       ├── analysis_routes.py /api/dataset/* endpoint'leri
│       ├── explicit.py          OpenRadioss explicit orchestration
│       ├── radioss_deck.py      .rad Starter deck yazici
│       ├── radioss_runner.py    Starter + Engine subprocess
│       ├── radioss_result.py    Anim / VTK sonuc okuma
│       └── explicit_routes.py   /api/explicit/* endpoint'leri
│   └── data/                crash.db + geometries/*.step (gitignore)
└── frontend/         React + TypeScript + Vite + react-three-fiber (three.js)
    └── src/
        ├── App.tsx
        ├── api.ts
        ├── faceGeometry.ts  Per-face centroid/normal (glif konumlandırma)
        └── components/  Viewer, ModelView, MeshView, ResultView
```

**Yüzey seçimi nasıl çalışır:** Backend STEP'i OpenCASCADE ile okur ve her B-Rep yüzeyini ayrı üçgenleştirir; her üçgene `face_id` atanır (`triangleFaceIds`). Frontend bu veriyi three.js `BufferGeometry`'ye yükler; raycaster ile tıklanan üçgenin indeksinden `face_id` bulunur ve yüzey vertex-renkleriyle vurgulanır.

**Statik analiz (Faz 4) nasıl çalışır:** [backend/app/solver.py](backend/app/solver.py) harici bir binary olmadan çalışan, gömülü açık kaynak bir lineer-statik FEM çözücüsüdür. STEP, Gmsh ile 3B tetrahedra (tet4 / sabit-gerinim CST elemanı) mesh'ine çevrilir. Frontend'de seçilen yüzeyler (OCCT `face_id`) ile mesh yüzeyleri, **centroid eşleştirmesi** ile bağlanır; böylece sabit mesnetler (fixed → ilgili düğümlerin tüm serbestlik dereceleri sıfırlanır) ve yükler (kuvvet → yüzey düğümlerine dağıtılır; basınç → yüzey üçgenlerine dışa dönük normal boyunca uygulanır) doğru düğüm setlerine atanır. Global rijitlik matrisi `scipy` seyrek (sparse) formatta kurulur ve `spsolve` ile `K u = f` çözülür. Sonuç: düğüm deplasmanları + eleman gerilmelerinden nodal von Mises. **Sınırlama:** lineer tet4 elemanı eğilmede gerçeğe göre fazla "katı"dır; daha hassas sonuç için eleman boyutunu küçültün. İleride kuadratik tet (C3D10) veya alternatif çözücü olarak CalculiX/OpenRadioss eklenebilir.

**Sonuç son-işleme (Faz 5) nasıl çalışır:** [frontend/src/components/ResultView.tsx](frontend/src/components/ResultView.tsx) çözüm sonucunu (düğüm deplasmanları + nodal von Mises) doğrudan three.js `BufferGeometry` üzerinde işler. Görüntülenecek skaler alan (von Mises, deplasman büyüklüğü `|U|` veya bileşenler `Ux/Uy/Uz`) düğüm bazında hesaplanır ve jet renk haritasıyla vertex-renklerine çevrilir; kontur **sürekli** ya da **ayrık bant** (CAE tarzı bantlı kontur) olabilir. Renk aralığı otomatik (min–max) ya da manuel olarak sabitlenebilir. **Kesit (clip) düzlemi** three.js'in `localClippingEnabled` özelliğiyle modelin içini göstermek için X/Y/Z ekseninde kaydırılır. Deformasyon, `disp` vektörünün ölçeklenmesiyle uygulanır ve isteğe bağlı olarak `useFrame` ile animasyonlu (nefes alma) gösterilir. Ek olarak: mesh kenar overlay, tıklanan noktadaki değeri okuyan **prob** ve `canvas.toDataURL` ile **PNG ekran görüntüsü** dışa aktarma. (vtk.js yerine mevcut react-three-fiber render hattı kullanıldı; ikinci bir render motoru gerektirmez.)

**Radioss Keyword editörü:** Panelde **Radioss Keyword** bölümü STEP + mesh + BC’den otomatik `crash_0000.rad` blokları üretir; şablonlardan (`/MAT/LAW2`, `/INTER/TYPE7`, `/IMPVEL`, …) ek blok eklenebilir, sıra değiştirilir, metin düzenlenir ve `.rad` indirilir. Explicit çalıştırırken özel bloklar (mesh hariç) deck’e eklenir. API: `GET /api/keywords/templates`, `POST /api/keywords/generate`, `POST /api/keywords/compose`.

**Explicit crash (Faz 6) nasıl çalışır:** [backend/app/explicit.py](backend/app/explicit.py) STEP'i Gmsh ile tetra mesh'e çevirir, [backend/app/radioss_deck.py](backend/app/radioss_deck.py) ile OpenRadioss Starter girdisi (`crash_0000.rad`, LAW1 elastik, `/IMPVEL`, `/BCS/LAGR`) yazar ve kurulu OpenRadioss'ta `starter` + `engine` çalıştırır. Sonuçlar anim dosyalarından (ve isteğe bağlı `anim_to_vtk`) okunup web görüntüleyiciye kare dizisi olarak aktarılır. **Gereksinim:** `OPENRADIOSS_PATH` ortam değişkeni (Windows: `exec/starter_win64.exe`, `engine_win64.exe`). Kurulu değilse API 503 döner.

**Veri seti ve surrogate hazırlığı (DB):** Her başarılı `/api/solve` çağrısı otomatik olarak SQLite veritabanına (`backend/data/crash.db`) kaydedilir. STEP dosyaları içerik hash’i ile tekilleştirilir (`backend/data/geometries/`). Her kayıt; geometri özeti, mesh eleman boyutu `h`, analiz tipi, malzeme (E, ν, ρ), mesnet/yük yüzeyleri, özet sonuçlar (`max_disp`, `max_von_mises`) ve tam çözüm vektörünü (JSON) içerir. **Filtreleme:** dosya adı, geometri, analiz tipi, malzeme, mesh `h` aralığı, sabit yüzey ID, yük tipi. **Parametre taraması:** `POST /api/dataset/sweep` aynı model + BC ile birden fazla `h` değerinde çözüm üretir (regression veri seti). **Export:** `GET /api/dataset/analyses/export` düz CSV (girdi + hedef kolonlar). Ortam değişkeni `CRASH_DATABASE_URL` ile PostgreSQL’e geçilebilir (SQLAlchemy URL).

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
| Veri seti / ORM | SQLAlchemy + SQLite | MIT |

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

### OpenRadioss (Faz 6 — explicit)

1. [OpenRadioss releases](https://github.com/OpenRadioss/OpenRadioss/releases) indirin ve açın (ör. `C:\OpenRadioss`).
2. Ortam değişkeni (PowerShell, oturum için):

```powershell
$env:OPENRADIOSS_PATH = "C:\OpenRadioss"
$env:RAD_CFG_PATH = "$env:OPENRADIOSS_PATH\hm_cfg_files"
$env:PATH = "$env:OPENRADIOSS_PATH\extlib\hm_reader\win64;$env:OPENRADIOSS_PATH\extlib\intelOneAPI_runtime\win64;$env:PATH"
```

3. Backend'i yeniden başlatın; arayüzde **Explicit (OpenRadioss)** bölümünde kurulum durumu görünür.
4. Mesnet + (isteğe bağlı) başlangıç hızı tanımlayıp **Coz (Explicit Crash)** ile çalıştırın.

## Yol Haritası
- [x] **Faz 1** — STEP import, 3B görüntüleme, yüzey seçimi
- [x] **Faz 2** — Gmsh ile mesh üretimi ve görselleştirme (2D yüzey / 3D tetra, eleman boyutu kontrolü)
- [x] **Faz 2.5** — Midsurface (orta yüzey) çıkarımı + 2D shell mesh (ince cidarlı / sabit kalınlıklı planar parçalar)
- [x] **Faz 2.6** — 2D / shell mesh için dörtgen (quad) eleman seçeneği (Gmsh blossom recombination)
- [x] **Faz 3** — Malzeme tanımı + seçili yüzeylere sınır koşulu (fixed) / yük (basınç, kuvvet) atama, görselleştirme (renkli yüzeyler + kuvvet okları) ve model doğrulama
- [x] **Faz 4** — Lineer-statik yapısal çözüm: gömülü açık kaynak FEM çözücü (tet4, numpy+scipy), von Mises gerilme + deplasman kontur görselleştirmesi ve deformasyon ölçeği
- [x] **Faz 5** — Sonuç son-işleme: ek alanlar (von Mises, |U|, Ux/Uy/Uz), ayrık/sürekli kontur bantları, manuel renk aralığı, kesit (clip) düzlemi, mesh kenar overlay, deformasyon animasyonu, nokta probu ve PNG ekran görüntüsü dışa aktarma
- [x] **Faz 5.5** — SQLite veri seti: otomatik analiz kaydı, filtreleme/raporlama UI, mesh h parametre taraması, CSV export (surrogate regression)
- [x] **Faz 6** — OpenRadioss explicit dynamics: .rad deck üretimi, Starter+Engine, animasyon kareleri, UI + DB kaydı
