# Waste Anomaly Detection

Python + PySide6 (Qt) **anomaly workbench** untuk deteksi anomali waste di cabang resto. Replika 1:1 dari **Power Query M code** untuk analisa waste per item, per cabang, per kategori — lengkap dengan **12 sinyal anomali**, composite scoring, **drill-down interaktif lintas-tab**, **filter profile persistence**, **comparison mode 2 cabang**, **analisa temporal (hari/minggu)**, **money view (prioritas magnitude)**, **benchmark peer aktif**, **data quality otomatis**, **compare periode bulan-ke-bulan**, **quadrant & rate league**, dan **27+ grafik** matplotlib embedded.

> **v2.6.0** — hasil "rebuild ulang UI": **UI baru PySide6/Qt berorientasi penemuan anomali** — landing langsung ke tabel anomali ter-ranking (skor ↓) + panel detail (12 sinyal, peer, uang, drill-down 1-klik), KPI mengikuti filter, **8 view** (Anomali · Jelajah · Waktu · Uang · Peer · Kualitas Data · Banding Periode · Pipeline) menggantikan 14 tab Tkinter, tabel tanpa cap baris (25.901 baris di-render virtualized + wrap + pewarnaan severity), **jaminan anti-terpotong struktural** (word-wrap semua teks; chart punya lantai ukuran + scroll; kolom tabel auto-fit proporsional; grid chart responsif 2↔1 kolom; tab tidak di-elide tanpa ellips), tombol duplikat/tak perlu dihapus (refresh global & popup log), tombol & fitur lama dipertahankan SEMUA (profil filter, export 10 sheet, compare periode, threshold editor), 2 bug core chart ikut diperbaiki (legend rate-league terpotong sejak lama; label tick weekday saling tumpuk). Core `waste_anomaly/` TIDAK tersentuh — golden regression utuh (25.901/399/41). Dependensi UI baru: `PySide6` (offline, satu kali `pip install`).
>
> **v2.5.1** — hasil "deep audit fitur baru + fix": audit ulang v2.5.0 atas kode asli (23 temuan: 4 HIGH / 12 MEDIUM / 7 LOW) → **isolasi exception per-chart di Dashboard** (DD-H1: sebelumnya satu chart gagal = chip ter-update + chart kosong + tabel stale), **sinkronisasi dropdown KETERANGAN lengkap di 6 titik** (DD-H2: Clear Filter & Muat Profil dulu membiarkan dropdown bohong), **KPI mengikuti filter + label konteks "X dari N baris"** (DD-M3), **rentang hari ketat** (DD-M1: 23.470 baris nol tidak lagi lolos — chip "(baris aktif)"), **search tak lagi cocok 'nan'/'&lt;NA&gt;'** (DD-L4), **FOCUS SCORE rank di subset aktif** (MO-M2: komponen magnitude kini berdaya-pembeda penuh, dulu terkompresi 90,6–100 oleh baris nol), **satuan eksplisit di money_top/judul temporal** (MO-M1), **normalisasi whitespace KETERANGAN** di dropdown/filter/agregat (DQ-M1), **min 30 entri aktif untuk tabel rasio alasan** (TE-M3: rasio sampel-kecil = artefak), **Compare Periode + kolom Hari Data & Waste/Hari** (PE-M1: bias 30-vs-31 hari), **split-source jujur "318 aktif dari 8.221 grup"** (DQ-L1), **format angka Indonesia tunggal** (IN-L1), **coalesce klik ganda** (DD-L2), + hardening `_on_pick` try/except + logging, label 'weekend' → 'pola hari mod-7' + catatan asumsi (TE-M1), + **test kontrak chart interaktif** (klik disimulasikan di Agg → nilai on_click ∈ kolom data; PR-H2).
>
> **v2.5.0** — hasil "kerjakan semua" (gelombang analisa): **4 tab analisa baru** (Temporal — pola hari/weekday; Money View + Benchmark — prioritas magnitude & peer aktif; Data Quality — 7 pemeriksaan otomatis; Compare Periode — bandingkan 2 workbook), **drill-down kini ada di SEMUA tab analisa** (klik chart di Visualisasi, double-click baris di Hasil/Quadrant/Money → filter + lompat ke Dashboard; + dropdown KETERANGAN), **5 chart baru** (waste per hari + highlight hari peak mod-7, weekday effect, heatmap alasan×hari, Pareto item per satuan, top money rows per FOCUS), **export Excel 10 sheet** (+Waste per Hari, Alasan×Hari, Money View, Data Quality), **KPI jujur per satuan**. 4 modul analisa baru + **320 test** (naik dari 150). Detail di **Changelog v2.5.0**.
>
> **v2.4.1** (hasil "double check") — perbaikan **path frozen-mode PyInstaller**: config.json / filters.json / folder data / log kini disimpan BERDAMPINGAN EXE (dulu hilang senyap karena menulis ke _MEIPASS temp yang terhapus saat exit — kebalikan klaim BUILD_EXE.bat), + **12 pesan log duplikat dibersihkan**, + **10 test baru path frozen** (total 150 test).
>
> **v2.4.0** — hasil "kerjakan semua" (2025): **arsitektur modular** (god-object 3.256 baris / 102 metode dipecah jadi paket `ui/` — 14 file mixin, verbatim terverifikasi + 11 test struktural), **cancel run jujur** (hook antar-stage — CPU benar-benar berhenti), **validasi skema input** (anti degradasi senyap header lowercase), **exporter streaming** (anti OOM 100k baris), **logging framework** (rotating file + hook exception Tk), **140 test**, **CI GitHub Actions**, **packaging .exe** + ikon aplikasi. Detail di **Changelog v2.4.0**.

## Cara Pakai

### 1. Setup (sekali saja)
Jalankan `SETUP.bat` di root folder. Install dependencies:
- pandas, numpy (data processing)
- openpyxl (Excel I/O)
- matplotlib (visualisasi grafik)

### 2. Siapkan Workbook Input — `DATA_WASTE.xlsx`

**Workflow Anda:**
```
Query data → Olah di Excel → Save as DATA_WASTE.xlsx → Replace file lama → Run pipeline
```

**Format standar input = `DATA_WASTE.xlsx`** (53 kolom). Anda olah data di Excel dulu (manual / Power Query / formula), lalu save dengan struktur standar ini. Pipeline idempotent — bisa di-run di file yang sudah berisi output sekalipun, semua derived columns akan di-drop & dihitung ulang otomatis.

**Letakkan `DATA_WASTE.xlsx` di mana saja** (folder Downloads, Documents, dll). Browse lewat UI saat run pipeline.

**Struktur 53 kolom yang diharapkan:**

| # | Kolom | Wajib? | Contoh |
|---|-------|--------|--------|
| 0-8 | STATUS, HELPER, MAX TOTAL, AVG TOTAL, TOTAL BOM, % to BOM, TOTAL, AVG, MAX | Opsional (akan dihitung ulang) | kosong / 0 |
| 9 | SOURCE DATA | ✅ Wajib | WASTE BAHAN DAN PACKAGING |
| 10 | JENIS | ✅ Wajib (filter: WASTE/SUSUT/TRIAL) | WASTE |
| 11 | KETERANGAN | ✅ Wajib | Alat/ Mesin, Cancel Nota, Eksternal, Internal, Over Stock, Handling, Kualitas, dll |
| 12 | NAMA BARANG | ✅ Wajib | ADONAN GORENG MEKAR |
| 13 | NAMA RESTO | ✅ Wajib | B.1001.MLGPAR |
| 14 | SATUAN | ✅ Wajib | GR, KG, PORSI |
| 15-45 | 1 .. 31 | ✅ Wajib (qty waste per hari) | 0 / 50 / 100 |
| 46-52 | Status2, KETERANGAN GABUNGAN, KONTRIBUSI TERBESAR, SOURCE DATA GABUNGAN, Count Hari, RANGKING WASTE, Rill % to BOM | Opsional (akan dihitung ulang) | kosong |

> **Idempotent:** Kalau ada kolom output (MAX, AVG, KETERANGAN GABUNGAN, dll) di file Anda — tidak masalah. Stage 1 akan auto-drop semua derived columns & recompute dari kolom hari 1..31.

**Opsional — sheet tambahan untuk aktifkan sinyal BOM & STATUS:**

| Sheet | Nama Kandidat | Kolom |
|-------|---------------|-------|
| BOM | `BOM`, `2  22 05`, `MASTER BOM` | `Nomor #` (= NAMA RESTO), `Nama Barang` (= NAMA BARANG), `TOTAL BOM` |
| DATABASE_SATUAN | `DATABASE_SATUAN`, `Database Satuan`, `SATUAN` | `NAMA ITEM`, `SUSUT`, `TRIAL`, `HANDLING`, `KUALITAS EKSTERNAL`, `KUALITAS`, `KUALITAS INTERNAL`, `EKSTERNAL`, `INTERNAL`, `ALAT MESIN`, `OVERSTOCK`, `CANCEL NOTA` |

Kalau sheet BOM/DATABASE_SATUAN tidak ada, sinyal BOM (S6/S7) & STATUS (Sesuai/Tidak Sesuai) tidak akan trigger tapi pipeline tetap jalan.

### 3. Jalankan (setiap kali)
Jalankan `MULAI.bat`. UI terbuka dengan **8 view** (v2.6.0 — rebuild PySide6; landing default = **Anomali**):

| View | Fungsi |
|------|--------|
| 🎯 Anomali (**default**) | Tabel anomali ter-ranking (skor ↓, tanpa cap baris, pewarnaan severity) + panel detail (12 sinyal S1–S12, peer, uang) + drill-down 1-klik (cabang/item/alasan) + ambang "Skor ≥" + KPI mengikuti filter |
| 🧭 Jelajah | Chart interaktif klik-untuk-filter + tabel data (5 sheet) + 12 chart statistik + banding 2 cabang |
| 🕐 Waktu | Pola waste per hari, kelas hari (mod-7), heatmap alasan×hari + tabel |
| 💰 Uang | Money view top-100, Pareto item, benchmark peer aktif, profil alasan |
| ⚖ Peer | Kuadran sistemik, rate league, benchmark SUSUT, share alasan per cabang, banding A/B |
| 🧪 Kualitas Data | 7 pemeriksaan kualitas otomatis (NBSP satuan, split-source, waste-tanpa-BOM, dll.) |
| 🔀 Banding Periode | Run saat ini vs workbook lain (normalisasi waste/hari, item baru/hilang) |
| ▶ Pipeline | Workbook + key akhir + Run/⏹Batal + progress + log + ringkasan + editor threshold |

Sidebar kiri (selalu terlihat): pencarian (debounce 300 ms), cabang, status, keterangan, rentang hari, profil filter tersimpan. Toolbar atas: **💾 Export Excel** (global — tidak duplikat per tab) + **❓ Bantuan**.

## Output Excel (10 Sheet) — via tombol "💾 Export Excel" di toolbar

Pipeline berjalan **in-memory** (cepat, idempotent). Setelah selesai, klik **💾 Export Excel** di toolbar untuk menyimpan laporan:

| Sheet | Isi |
|-------|-----|
| Detail | Semua baris — kolom mengikuti M code Final order (~70 kolom) |
| Anomali Prioritas | Hanya baris dengan `ANOMALY STATUS` = Prioritas Tinggi + Potensi Anomali |
| Per Cabang | Ringkasan per NAMA RESTO (jumlah baris, total waste, count anomali per status) |
| Top Items | Top 20 item by TOTAL waste (rank, total, max, cabang terpengaruh, count prioritas) |
| Pareto Alasan | Group by KETERANGAN — sum TOTAL, persentase, cumulative % |
| Log Run | Timestamp, parameter, summary stats, log lines pipeline |

> Export berjalan di background thread (UI tetap responsif) dengan penanganan `PermissionError` ramah: kalau file sedang dibuka di Excel, muncul pesan jelas "tutup dulu lalu ulangi". Perf: ~27 detik untuk 25.901 baris × 93 kolom (dulunya ~110 detik).

## Tab Dashboard — Drill-Down Interaktif (NEW v2.0)

Tab Dashboard adalah **pusat analisa** dengan layout profesional:

### KPI Cards (6 cards)
| Card | Warna | Isi |
|------|-------|-----|
| TOTAL BARIS | slate | Jumlah baris diproses |
| PRIORITAS TINGGI | red | Count anomali prioritas tinggi |
| POTENSI ANOMALI | orange | Count potensi anomali |
| PERLU REVIEW | amber | Count perlu review |
| TOTAL WASTE | teal | Sum TOTAL waste (qty) |
| CABANG | purple | Jumlah cabang unik |

### Filter Bar (8 cara drill-down — extended v2.1)
1. **Search box** — free-text search di semua kolom
2. **Dropdown Cabang** — pilih cabang spesifik
3. **Dropdown Status** — pilih status anomali
4. **JENIS checkboxes (NEW v2.1)** — multi-select WASTE/SUSUT/TRIAL
5. **Day Range (NEW v2.1)** — filter HARI MAX dalam range 1-31 (mis. "anomali yang peak di hari 5-15")
6. **Klik bar chart interaktif** — bar yang di-klik jadi filter aktif
7. **Double-click baris table** — drill-down ke cabang+item baris itu
8. **Filter Profile Save/Load (NEW v2.1)** — simpan state filter ke `filters.json`, load lagi kapan saja

### Active Filter Chips
Filter aktif muncul sebagai chip kuning di atas table. Klik `×` di chip untuk remove filter individual, atau klik `✕ Clear Filter` untuk clear semua.

### 3 Interactive Charts
| # | Chart | Klik untuk Filter |
|---|-------|------------------|
| 1 | Status Bar | Klik bar → filter by status anomali |
| 2 | Cabang Bar | Klik bar → filter by cabang |
| 3 | Top Items Horizontal | Klik bar → filter by NAMA BARANG |

Bar aktif highlight dengan warna penuh, bar lain jadi abu-abu (visual feedback).

### Drill-Down Detail Table
- Sortable columns (klik header untuk sort asc/desc)
- Status coloring (red/orange/amber/green sesuai ANOMALY STATUS)
- Pagination otomatis (max 500 baris untuk performa)
- Double-click row → drill-down ke cabang+item
- Export current filtered view ke Excel

### Workflow Analisa Contoh
```
1. Buka tab Dashboard → lihat KPI cards
2. Klik bar "Prioritas Tinggi" di chart Status → table ter-filter
3. Klik bar "RESTO.PWKTAM" di chart Cabang → drill-down lebih dalam
4. Klik bar "Bawang Putih" di chart Top Items → fokus ke item itu
5. Active chips: [status: Prioritas Tinggi] [cabang: RESTO.PWKTAM] [item: Bawang Putih]
6. Search "Cancel Nota" → tambah filter keterangan
7. Export hasil filter ke Excel untuk laporan
```

## Tab Compare Cabang — Side-by-Side Analysis (NEW v2.1)

Tab ini untuk membandingkan 2 cabang secara langsung dengan 4 chart + metrics summary.

### Cara Pakai
1. Pilih **Cabang A** dan **Cabang B** dari dropdown (otomatis terisi dari data ter-load)
2. Lihat 4 chart comparison otomatis:
   - **Total Waste per JENIS** — grouped bar (WASTE/SUSUT/TRIAL)
   - **Status Anomali** — grouped bar (Prioritas Tinggi/Potensi/Review/Normal)
   - **Top Items** — horizontal grouped bar (top 8 items, A vs B)
   - **Metrics Comparison** — grouped bar (Avg/Max Score, Avg/Max Waste, Jml Prioritas)
3. Baca **Metrics Summary** di bawah chart dengan diff & % delta

### Metrics Summary (delta analysis)
Format: `Metric: A=value | B=value | ↑/↓ diff (pct%)`

Contoh output:
```
Cabang A: RESTO.PWKTAM  •  Cabang B: RESTO.KWGGAL

Total Waste: A=290 | B=327 | ↓ 37 (-12.8%)
Avg Waste/Barang: A=48.40 | B=54.40 | ↓ 6.00 (-11.0%)
Max Single Day: A=38.7 | B=30.4 | ↑ 8.3 (+27.3%)
Avg Anomali Score: A=8.3 | B=8.8 | ↓ 0.5 (-5.7%)
Max Anomali Score: A=12.0 | B=11.0 | ↑ 1.0 (+9.1%)
Jumlah Prioritas: A=4 | B=5
Jumlah Item: A=6 | B=6
```

### Export
Tombol "Export PNG…" simpan 4 chart comparison ke folder dengan nama `compare_<A>_vs_<B>_<chart>.png`.

## Tab Visualisasi — 12 Grafik (Static Gallery)

Setelah run pipeline, tab "Visualisasi" auto-load 12 grafik matplotlib embedded:

| # | Grafik | Tipe | Fungsi Analisa |
|---|--------|------|---------------|
| 1 | Distribusi Status | Pie/donut | % baris per ANOMALY STATUS (Prioritas Tinggi/Potensi/Review/Normal) |
| 2 | Waste per Cabang | Bar | Total waste qty per NAMA RESTO — identifikasi cabang problem |
| 3 | Top 10 Items | Horizontal bar | Item dengan waste tertinggi (siap untuk intervensi) |
| 4 | Status per Cabang | Stacked bar | Breakdown status anomali per cabang |
| 5 | Pareto Alasan | Bar + line | 80/20: keterangan mana yang kontribusi 80% waste |
| 6 | Heatmap Cabang×Item | Matrix | Spot outlier cell — cabang×item kombinasi bermasalah |
| 7 | Frekuensi Penyebab | Bar | Berapa kali tiap anomaly reason (S1-S12) muncul |
| 8 | Scatter MAX vs TOTAL | Scatter | Deteksi outlier: titik dekat garis identitas = single-day event |
| 9 | Box TOTAL per JENIS | Box plot | Distribusi waste per jenis (SUSUT/TRIAL/WASTE) |
| 10 | Score per Cabang | Grouped bar | Avg & max anomali score per cabang + threshold lines |
| 11 | Kategori per Cabang | Stacked bar | KATEGORI ANOMALI (Lonjakan Ekstrem / Non-Handling / Normal) per cabang |
| 12 | Distribusi JENIS | Donut | % baris per JENIS (WASTE/SUSUT/TRIAL) |

**Fitur:**
- Auto-refresh setelah pipeline selesai
- Tombol "⟳ Refresh Grafik" untuk re-render manual
- Tombol "Export Semua PNG…" untuk simpan 12 grafik ke folder (150 DPI, white background)
- Scrollable canvas (mouse wheel + scrollbar)
- Color palette: teal + pink + status colors (NO indigo/blue sesuai panduan)

## 12 Sinyal Anomali (S1-S12)

| # | Nama | Trigger | Skor |
|---|------|---------|------|
| S1 | Spike vs AVG | `Count≥2 & MAX/AVG≥3` | 1 |
| S2 | MAX vs AVG Aktif | `Count≥3 & MAX/AVG_AKTIF≥2.5` (≥4 → skor 2) | 1 atau 2 |
| S3 | MAX vs Median Aktif | `Count≥3 & MAX/MEDIAN_AKTIF≥3` | 2 |
| S4 | MAX Share | `MAX/TOTAL≥0.70` (≥0.50 → skor 1) | 1 atau 2 |
| S5 | MAX vs Second Max | `Count≥2 & MAX/SECOND_MAX≥3` | 1 |
| S6 | MAX / BOM | `MAX/TOTAL_BOM≥0.50` (≥0.25 → skor 1) | 1 atau 2 |
| S7 | TOTAL / BOM | `TOTAL/TOTAL_BOM≥1.00` (≥0.50 → skor 1) | 1 atau 2 |
| S8 | Peer MAX | `PeerCount≥3 & MAX/PeerMedMax≥3` (≥2 → skor 1) | 1 atau 2 |
| S9 | Peer TOTAL | `PeerCount≥3 & TOTAL/PeerMedTot≥3` | 1 |
| S10 | Single-day event | `Count=1 & (MaxBOM≥0.10 atau MaxPeer≥2)` | 1 |
| S11 | Last Day Share | `LastDay/TOTAL≥0.70` | 1 |
| S12 | Scale Signal | heuristic rasio (8-12 / 80-120 / 800-1200 / 8000-12000) | 2 |

**Max skor = 18.** Status final:
- `≥ 8` → **Prioritas Tinggi**
- `≥ 5` → **Potensi Anomali**
- `≥ 3` → **Perlu Review**
- `else` → **Normal**

## Testing

**375 test** — golden regression end-to-end (fixture `DATA_WASTE.xlsx` 25.901 baris), unit test 12 sinyal S1–S12, join BOM & normalisasi kunci, presisi float, kontrak summary dict, validasi skema, cancel hook antar-stage, exporter dual-mode, logging framework, path frozen-mode, kontrak chart interaktif + semantik filter (v2.5.1), **dan 12 test struktural paket ui/ baru v2.6.0** (modul ada, mixin lama tak kembali, kontrak shared, kontrak view refresh/on_shown, worker QThread, manifest metode, MainWindow offscreen). Jalankan setiap kali mengubah kode — angka golden berubah tanpa alasan = regresi.

## Packaging — EXE Standalone

Jalankan `BUILD_EXE.bat` di Windows (butuh Python + SETUP.bat sekali). Hasil: `dist/WasteAnomalyDetection.exe` — aplikasi jalan **tanpa Python** di PC lain, lengkap dengan ikon (`assets/app_icon.ico`). PyInstaller di-install otomatis; konfigurasi build ada di `waste_anomaly.spec`.

## Struktur Project

```
Waste/
├── MULAI.bat                       ← ENTRY POINT (buka UI 10 tab)
├── SETUP.bat                       ← One-time install (pip install -r requirements.txt)
├── BUILD_EXE.bat                   ← Build .exe standalone (PyInstaller)
├── waste_anomaly.spec              ← Konfigurasi PyInstaller (icon, datas)
├── requirements.txt                ← Dependensi pinned (matplotlib >= 3.9, pandas 2.2.x)
├── README.md                       ← File ini
├── LICENSE                         ← MIT
├── .gitignore
├── ui_app.py                       ← LAUNCHER tipis (entry point lama tetap jalan)
├── ui/                             ← PAKET UI (v2.6.0 — rebuild PySide6)
│   ├── __init__.py                ← Eksport lazy (main, MainWindow)
│   ├── shared.py                  ← Kontrak publik (APP_DIR, _apply_filters, fmt_id)
│   ├── theme.py                   ← Palet warna + QSS global
│   ├── state.py                   ← AppContext: state tunggal + signal Qt
│   ├── models.py                  ← PandasTableModel (tabel virtualized, sort, severity)
│   ├── workers.py                 ← PipelineWorker / ExportWorker / PeriodWorker (QThread)
│   ├── widgets.py                 ← Blok anti-terpotong: WLabel, MplCanvas, ChartCard,
│   │                                 DataTable (auto-fit + wrap), KpiStrip, grid responsif
│   ├── app.py                     ← MainWindow (toolbar + sidebar + 8 view) + main()
│   ├── view_anomali.py            ← View 1 Anomali (default): ranking + detail + drill
│   ├── view_jelajah.py            ← View 2 Jelajah: chart interaktif + tabel + statistik
│   ├── view_waktu.py              ← View 3 Waktu (temporal)
│   ├── view_uang.py               ← View 4 Uang (money view + benchmark)
│   ├── view_peer.py               ← View 5 Peer (kuadran + rate league + banding A/B)
│   ├── view_kualitas.py           ← View 6 Kualitas Data
│   ├── view_periode.py            ← View 7 Banding Periode
│   └── view_pipeline.py           ← View 8 Pipeline (+ ringkasan + threshold editor)
├── assets/                         ← Ikon aplikasi (ico + png)
├── make_sample.py                  ← Generate sample workbook untuk testing
├── tests/                          ← Test suite pytest (150 test)
│   ├── conftest.py
│   ├── fixtures/ui_methods_manifest.txt  ← Manifest 102 metode (kunci struktural)
│   ├── test_pipeline_regression.py ← Golden regression 25.901 baris
│   ├── test_signals.py             ← Unit test S1–S12 (54 test)
│   ├── test_schema_and_cancel.py   ← Validasi skema + cancel hook
│   ├── test_exporter.py            ← Exporter dual-mode (normal/streaming)
│   ├── test_bom_join.py            ← Join BOM numerik
│   ├── test_key_normalization.py   ← Normalisasi kunci join
│   ├── test_float_precision.py     ← Presisi 15 digit (idempotency)
│   ├── test_logging.py             ← Logging framework
│   ├── test_frozen_paths.py        ← Path frozen-mode exe (seed sidecar)
│   └── test_ui_structure.py        ← Struktur paket ui/ (MRO + manifest)
├── .github/workflows/ci.yml        ← CI: matrix Python × OS, lint + 150 test
├── waste_anomaly/
│   ├── __init__.py                 ← __version__ single-source (2.5.0)
│   ├── frozen.py                   ← Resolusi path PyInstaller exe vs dev (v2.4.1)
│   ├── config.json                 ← Thresholds + sheet name candidates
│   ├── pipeline.py                 ← Orchestrator 14 stage + cancel_check
│   ├── schema.py                   ← Validasi skema input (anti degradasi senyap)
│   ├── logging_setup.py            ← Rotating file log + hook exception Tk
│   ├── loader.py                   ← Excel loaders (auto-detect sheet + normalisasi 15 digit)
│   ├── stages.py                   ← 14 stage replika M code (idempotent v2.3.2)
│   ├── signals.py                  ← 12 sinyal anomali + composite score (max 19)
│   ├── charts.py                   ← 12 static chart matplotlib
│   ├── dashboard.py                ← 6 interactive chart + 4 comparison chart
│   ├── filters.py                  ← Filter profile persistence
│   ├── exporter.py                 ← Multi-sheet xlsx writer + mode streaming
│   └── utils.py                    ← Helper (Number.From, List.Sum, dll)
├── data/                           ← (opsional) letakkan DATA_WASTE.xlsx di sini
│   └── README.md
├── logs/                           ← (auto-generated) rotating file log
├── output/                         ← Output Excel tersimpan di sini
│   └── .gitkeep
└── filters.json                    ← (auto-generated) saved filter profiles
```

## Stage Pipeline (14 Stage, replika M code)

| Stage | Fungsi |
|-------|--------|
| 1 | Source & cleanup: drop TOTAL/PIC/KATEGORI/STATUS/PENYEBAB, coerce hari 1-31 numeric, filter JENIS ∈ {SUSUT, TRIAL, WASTE} |
| 2 | Per-row daily stats: TOTAL, MAX, AVG, AVG AKTIF, MEDIAN AKTIF, SECOND MAX, HARI MAX, rasio, share, single-day, scale-signal |
| 3 | Reason summary: KETERANGAN GABUNGAN, KONTRIBUSI TERBESAR, SOURCE DATA GABUNGAN |
| 4 | Group totals: MAX TOTAL, AVG TOTAL by (KETERANGAN, NAMA BARANG, SOURCE DATA) |
| 5 | BOM join: TOTAL BOM, Rill % to BOM |
| 6 | Peer summary: PEER COUNT, PEER MEDIAN TOTAL, PEER MEDIAN MAX by (NAMA BARANG, JENIS, KETERANGAN, SOURCE DATA) |
| 7 | Top 3 summary: TopTotal list, TopBOM list per (JENIS, NAMA BARANG) |
| 8 | Merge semua summary (left joins) |
| 9 | DATABASE_SATUAN join: 11 kolom kategori helper |
| 10 | Helper / STATUS (Sesuai/Tidak Sesuai) / % to BOM |
| 11 | 12 sinyal anomali + ANOMALY SCORE + STATUS + REASONS + KATEGORI ANOMALI + RANGKING WASTE |
| 12 | Expand analysis (no-op — sudah di-expand di stage 11) |
| 13 | Cleanup temporary columns |
| 14 | Final column order (mengikuti M code) |

## Persyaratan

- **Python 3.10+** (cek: `python --version`)
- **Windows** untuk `.bat` files (Mac/Linux: jalankan `python ui_app.py` langsung)
- Dependencies: pandas, numpy, openpyxl (di-install oleh `SETUP.bat`)

## Cara Download & Update

1. Download ZIP repo: https://github.com/anandategarch/Waste/archive/refs/heads/main.zip
2. Ekstrak
3. Jalankan `SETUP.bat` (sekali saja)
4. Siapkan `DATA_WASTE.xlsx` Anda (query → olah di Excel → save dengan struktur 53 kolom standar)
5. Jalankan `MULAI.bat` → Browse `DATA_WASTE.xlsx` Anda → Mulai Pipeline

**Untuk run berikutnya (data baru):**
1. Replace `DATA_WASTE.xlsx` Anda dengan file baru (overwrite / copy paste)
2. Jalankan `MULAI.bat` → Browse file → Mulai Pipeline

> **Tip:** Pipeline idempotent. Bisa di-run di file output sendiri (`Waste_Anomaly_Report.xlsx`) atau file `DATA_WASTE.xlsx` yang sudah berisi output M code — semua derived columns akan di-drop & dihitung ulang oleh Stage 1.

## CLI Mode (tanpa UI)

```python
from waste_anomaly.pipeline import run_pipeline

summary = run_pipeline(
    workbook_path="data/rekap.xlsx",
    key_akhir=31,
    output_path="output/Waste_Anomaly_Report.xlsx",
    progress_callback=lambda msg, pct: print(f"[{pct:.0f}%] {msg}"),
)
print(summary)
```

## Custom Thresholds

Edit `waste_anomaly/config.json` → section `thresholds`. Atau pakai tab "⚙ Konfigurasi" di UI.

```json
{
  "thresholds": {
    "TH_SPIKE": 3,
    "TH_MAX_AVG_AKTIF": 2.5,
    "TH_PEER_HIGH": 3,
    "STATUS_PRIORITAS": 8,
    "STATUS_POTENSI": 5,
    "STATUS_REVIEW": 3,
    "S2_SCORE2_MIN": 4,
    "S10_BOM_MIN": 0.10,
    "QUADRANT_THRESHOLD": 0.5,
    ...
  }
}
```

> Konfigurasi korup otomatis diperingatkan (warning di log + tab Ringkasan) dan pipeline lanjut dengan default — tidak lagi diam-diam mengganti threshold.

## Troubleshooting

| Error | Solusi |
|-------|--------|
| `Tidak menemukan sheet untuk 'rekap_mentah'` | Pastikan workbook punya sheet `DATA_WASTE` / `Sheet1` / `REKAP_MENTAH` / `DATA`. Atau edit `config.json` → `input_sheets.rekap_mentah` untuk tambah nama kandidat. |
| `BOM sheet tidak ditemukan` | BOM join dilewati. Sinyal S6/S7 tidak trigger. Tambahkan sheet `BOM` / `MASTER BOM` untuk mengaktifkan. |
| `DATABASE_SATUAN tidak ditemukan` | Kolom HELPER/STATUS dari input dipertahankan; kalau tidak ada sama sekali tidak bisa dihitung ulang. Tambahkan sheet `DATABASE_SATUAN` untuk mengaktifkan. |
| `File .xls` | Tidak didukung — save-as `.xlsx` dulu. |
| `File output sedang dibuka di Excel` | Tutup filenya di Excel, lalu klik Export ulang (pesan errornya sekarang jelas). |
| `ModuleNotFoundError: pandas / matplotlib` | Jalankan `SETUP.bat` dulu. Atau manual: `pip install pandas numpy openpyxl matplotlib`. |
| Tab Visualisasi kosong | Pastikan sudah run pipeline. Klik "⟳ Refresh Grafik" manual kalau tidak auto-load. |
| Grafik matplotlib error di Linux headless | Set env: `export MPLBACKEND=TkAgg` sebelum jalankan `python ui_app.py`. |
| UI tidak terbuka | Pastikan Python 3.10+ terpasang (`python --version`). |

## Changelog v2.6.0 — "Rebuild Ulang": PySide6 Anomaly Workbench

**Perintah user:** *rebuild ulang UI tapi tetap di Python offline, jangan ada teks yang terpotong atau grafik yang terpotong, orientasi UI untuk temukan anomali; UI/tombol tak perlu atau duplikat hapus.*

### UI baru (total rebuild — 15 file Tkinter dihapus, 16 file PySide6)
- **Framework**: Tkinter → **PySide6 6.x (Qt6)** — layout system yang menegosiasikan ukuran widget (jaminan struktural anti-terpotong); app tetap 100% offline (`pip install PySide6` sekali).
- **Orientasi anomali**: view default = **Anomali** — tabel 797 baris anomali ter-ranking skor tanpa cap, pewarnaan severity per baris, panel detail (12 sinyal, peer, uang, KETERANGAN) + drill 1-klik cabang/item/alasan + ambang **Skor ≥** + KPI terfilter.
- **8 view**: Anomali · Jelajah (gabungan Dashboard+Hasil+Viz+Compare lama) · Waktu · Uang · Peer (gabungan Quadrant+Rate+Compare) · Kualitas Data · Banding Periode · Pipeline (gabungan Run+Ringkasan+Konfigurasi+Bantuan-dialog).
- **State arsitektur**: god-object 109 metode → `AppContext(QObject)` (signal data_ready/filters_changed/status/log_line) + views berbayang — tiap view punya `refresh()`/`on_shown()` (lazy render H2 dipertahankan).
- **Tabel**: `PandasTableModel` + `QTableView` — virtualized 25.901 baris (dulu cap 500), sort numeric-aware klik header, auto-fit kolom proporsional ke viewport, **wrap multi-baris dengan tinggi baris dihitung manual** (bug Qt: `resizeRowsToContents` mengabaikan wrap), ElideNone, tooltip sel & header.
- **Chart anti-terpotong**: `MplCanvas` dengan lantai 85% lebar desain + melebar penuh saat window besar; `ChartCard` = QScrollArea (jendela kecil → scrollbar, bukan potong); **grid responsif** 2↔1 kolom + chart berdesain lebar selalu 1 baris penuh; re-placement ditunda ke tick berikutnya (viewport final).
- **Tombol/tabbars**: export Excel global di toolbar (dulu duplikat konteks), popup log → panel log permanen, "⟳ Refresh Semua" dihapus (render deterministik dari signal), tab label tak pernah terpotong tanpa ellips.
- **Fitur lama SEMUA dipertahankan**: profil filter (filters.json), export 10 sheet, compare periode + waste/hari, threshold editor + atomic save, banding 2 cabang, cancel antar-stage, keyboard Ctrl+F, ikon app, frozen-path sidecar exe.

### Perbaikan core (2 bug chart lama, tanpa menyentuh pipeline)
- `chart_rate_league`: legend "5% threshold (blatant)" terpotong di tepi figure SEJAK APLIKASI LAMA (bahkan pada ukuran desain) → legend dipindah ke bawah chart (ncol=2, label ringkas).
- `chart_weekday_effect`: label tick kelas hari ("(7, 14, 21, 28)…") saling tumpang tindih → dipadatkan tanpa spasi.

### Verifikasi (standar "no mistakes")
- E2E offscreen + data riil 25.901 baris: pipeline 17 s, golden regression **utuh** (25.901 baris / 399 anomali / 41 prioritas), 8 view render tanpa error, drill 797→49 baris, rentang hari, export Excel 8,8 MB sukses.
- **Audit visual AI (VLM) 13 screenshot — 13 PASS** (8 view + 3 state interaksi + 2 ukuran jendela kecil) setelah 6 iterasi perbaikan (kolom tabel auto-fit, wrap manual, grid responsif, lantai canvas, stretch kolom, elide tab). Bukti piksel: sel 2-baris ter-render lengkap; judul chart muat pada lantai 85%.
- 363 test lama tetap hijau (core tak tersentuh) + 12 test struktural baru.

## Changelog v2.5.0 — "Kerjakan Semua (Analisa)": 4 Tab Analisa Baru + Drill-Down Semua Tab

Dipicu audit analisa: 12 sinyal solid sebagai **detektor pola**, tapi ada 6 blind spot terukur — event single-day terbesar (96.480 GR BASIC MIE hari-9) lolos berlabel "Normal", baris Prioritas Tinggi hanya 0,5% dari total waste, peer mati untuk event langka (median termasuk cabang nol), tanpa analisa temporal (padahal pola hari mod-7 +35% ada di data), 119 baris waste tanpa BOM invisibel, dan agregat mencampur satuan. v2.5.0 menambal semuanya dengan **4 modul analisa murni baru + 4 tab UI baru + perluasan drill-down**.

### P1 — Tab "📅 Temporal" (analisa dimensi waktu)
- `waste_anomaly/temporal.py`: `waste_per_day`, `weekday_pattern` (kelas hari % 7), `weekday_effect` (deteksi pasangan kelas peak siklik), `reason_by_day` (matrix alasan×hari), `reason_weekday_ratio` (efek peak per alasan), `unit_summary`.
- Chart: **waste per hari** (hari peak di-highlight merah + catatan "+N%"), **weekday effect** (mean per baris aktif per kelas + garis rata-rata), **heatmap alasan×hari** (top-9 alasan, kapan terjadi). Tabel rasio alasan.
- Angka nyata pada data sampel: kelas peak (5,6) → +35% (369,7 vs 273,6); SUSUT +42%, Cancel Nota +39% di hari peak; TRIAL datar 1,00×; Kualitas Internal justru 0,58×.

### P2 — Tab "💰 Money View" (prioritas magnitude)
- `waste_anomaly/priority.py`: `money_view` (top waste rows APA PUN statusnya + Share %/Kumulatif %), `focus_score` (60% magnitude percentile + 40% anomali, 0-100), `focus_class` (Fokus Utama ≥ 70 / Sekunder ≥ 50 / Rutin), `benchmark_items`, `reason_profile`, `reason_share`, `susut_benchmark`.
- Chart: **top money rows** (diwarnai FOCUS CLASS), **Pareto item** (satuan eksplisit di label). Tabel money (top 100) + benchmark.
- Mengisi gap audit: top row KULIT PANGSIT GGPDAA 299.855 kini tampil teratas (sebelumnya "Normal" dan tak terlihat di view prioritas).

### P4 — Benchmark peer AKTIF (di tab Money View)
- Peer median dihitung **hanya dari cabang yang punya waste** pada item tsb — memperbaiki blind-spot peer lama (median termasuk cabang nol → rasio 0 → S8/S9/S10 mati justru untuk event langka).
- Data sampel: **239 pasangan item×cabang** kini ter-flag "Di Atas Peer" (≥ 2× median peer aktif) — dulu invisibel.

### P6 — Tab "🧹 Data Quality" (pemeriksaan otomatis)
- `waste_anomaly/data_quality.py` — 7 pemeriksaan defensif: nilai negatif (error); SATUAN spasi-tersembunyi/NBSP; SOURCE DATA varian kapital (memecah peer group); KETERANGAN terfragmentasi (prefix); waste tanpa BOM; grup resto×item terpecah antar source (dilute sinyal); baris nol (info struktur).
- Angka data sampel: 2.039 baris satuan 'PACK'NBSP, 12.086 baris source varian 'dan/DAN', 119 baris waste tanpa BOM (190.836 qty), 318 grup terpecah, 97 baris 'Kualitas' terfragmentasi.

### P9 — Tab "🔀 Compare Periode" (bulan ke bulan)
- `waste_anomaly/period_compare.py`: `auto_key_akhir` (deteksi hari aktif terbesar file B), `compare_periods` — summary 7 metrik, per-JENIS, cabang mover, item mover (top-100 |delta|), item baru/hilang.
- Worker thread + progress log + guard anti-run-bersamaan; hasil di 6 halaman tabel.

### P3/P5/P7 — Ekstensi Compare, KPI jujur, satuan
- Tab Compare: **chart profil alasan share %** 2 cabang + **tabel profil alasan semua cabang + benchmark SUSUT** (rank & share per cabang).
- KPI Dashboard: breakdown **per satuan** (GR/PCS/PACK + catatan campuran) + label serupa di Money View; Pareto item menulis satuan di label.

### P8 — Drill-down di SEMUA tab
- **Visualisasi**: 4 chart galeri (Status/Cabang/Top Items/Pareto Alasan) kini bisa **diklik** → set filter + lompat ke Dashboard (handler `on_click` baru di charts.py, kontrak sama dengan dashboard).
- **Hasil**: double-click baris Detail/Anomali → filter cabang+item + lompat.
- **Quadrant**: double-click baris item → filter item (semua cabang).
- **Money View**: double-click baris → filter cabang+item.
- **Dashboard**: dropdown filter **KETERANGAN** baru (sync 2 arah dengan chip/klik chart).

### Export & infrastruktur
- Export Excel kini **10 sheet**: +Waste per Hari, +Alasan×Hari, +Money View, +Data Quality (param `extra_sheets` di exporter — backward-compatible, default tetap 6).
- Bug diperbaiki saat pengembangan: `_wire_patch_click` meng-unpack `patch.contains()` (tuple truthy — patch pertama selalu match); item queue `period_done` 3-tuple (kontrak dispatcher); `load_rekap_mentah` butuh arg config.
- `ui/app.py` kini 15 mixin (14 tab); test struktural diperbarui (MRO dinamis, bukan posisi hard-coded).
- **320 test** (naik dari 150): 51 temporal + 40 priority + 58 data_quality + 21 period_compare + struktur diperbarui. CI: ruff fatal clean. Verifikasi E2E runtime (Xvfb): 14 tab render, drill-down 5 jalur, compare-periode 24 detik, export 10 sheet.

## Changelog v2.4.1 — "Double Check": Fix Path Frozen-Mode PyInstaller

Ditemukan saat verifikasi ulang menyeluruh v2.4.0 (semua klaim diuji runtime, bukan cuma percaya commit message).

### Bug — file user hilang senyap di mode exe (KRITIS)
- **Akar masalah**: `CONFIG_PATH` (utils.py), `PROFILES_PATH` (filters.py), dan `APP_DIR` (ui/shared.py) resolve dari `Path(__file__)`. Di exe PyInstaller, `__file__` menunjuk ke dir ekstraksi temp `_MEIPASS` yang **DIHAPUS saat aplikasi ditutup** — threshold yang disimpan lewat tab Konfigurasi, profil filter, dan folder `data/` lenyap tanpa jejak. Ke balikan dari klaim BUILD_EXE.bat ("config.json disimpan berdampingan dengan exe").
- **Fix**: modul baru `waste_anomaly/frozen.py` — satu sumber resolusi: file **writable** (config sidecar, filters.json, data/, logs) → folder **EXE** (`Path(sys.executable).parent`); resource **read-only** (ikon, config bundled) → `_MEIPASS` (`bundle_dir()`).
- **First-run seed**: saat exe dijalankan pertama kali, config bundled otomatis disalin ke `config.json` di samping exe — sekarang klaim BUILD_EXE.bat benar-benar terimplementasi. Folder read-only → fallback baca bundled (pipeline tetap jalan).
- **Ikon**: dicari di `bundle_res_dir()` (frozen) lalu `app_dir()` (dev) — jalan di kedua mode.
- **Log**: mode exe menulis `logs/` di samping exe (dulu `cwd` — bisa System32 kalau shortcut punya "Start in" berbeda).
- **Tab Konfigurasi** kini menampilkan & menulis ke path dinamis (`_active_config_path()`).

### Cleanup
- **12 pesan log duplikat** "Suppressed: Suppressed …" (sisa penggantian mekanis v2.4.0) → "Suppressed: …".
- Import `simpledialog` tak terpakai di `tab_dashboard.py` dihapus (F401/F811).
- Docstring `logging_setup` — contoh pemakaian `install_tk_exception_hook` dibenarkan.

### Test
- **+10 test** (`test_frozen_paths.py`): dev-path tak berubah (golden aman), seed first-run, sidecar existing menang (edit user bertahan), fallback read-only, roundtrip save/load profil frozen, `app_dir()`/`bundle_res_dir()`. Total **150 test** semua LULUS.

### Verifikasi runtime (bukan cuma test)
- Golden run data asli: 25.901 baris / 399 anomali / 41 prioritas — **MATCH** (key_akhir=31).
- Cancel mid-run: pipeline berhenti persis di gate Stage 2 (`cancelled=True`, log terpotong di gate) — **PASS**.
- Skema lowercase: gagal keras + saran rename — **PASS**.
- Exporter 60k baris: peak memori **7 MB** (dulu OOM ~1,8 GB) — **PASS**.

## Changelog v2.4.0 — "Kerjakan Semua": Arsitektur Modular + Infrastruktur Profesional Penuh

### Arsitektur — god-object dipecah (audit UI #1)
- **`ui_app.py` 3.256 baris / 102 metode → paket `ui/` 14 file**: 11 mixin (base + 10 tab) + shared + widgets + komposisi. Metode dipindah **VERBATIM via ekstraksi AST** (bukan tulis ulang) — terverifikasi: set 102 metode identik, 101/101 source identik byte-per-byte, 8 dekorator `@staticmethod`/`@classmethod` dipertahankan, MRO = 11 mixin + `tk.Tk`. Menambah tab ke-11 kini menyentuh **1 file baru + 1 baris komposisi** (dulu 5+ situs tersebar).
- **Registry font** menggantikan pola `global` lama (yang hanya bekerja saat semua kode di satu file): `shared.rebind_fonts()` mem-propagasi nilai font ke semua modul mixin saat startup.
- **`ui_app.py` tetap jadi entry point** — MULAI.bat & kebiasaan user tidak berubah.
- **11 test struktural permanen** (`test_ui_structure.py`): manifest 102 metode, MRO, anti-duplikat antarmixin, dekorator, registry font, APP_DIR repo-root.

### Cancel run yang jujur (audit UI #2)
- **Hook `cancel_check` antar-stage di pipeline** — tombol "⏹ Batalkan Run" kini benar-benar menghentikan CPU di gate stage berikutnya (dulu: flag hanya dicek SETELAH pipeline selesai — hasil dihitung sampai tuntas lalu dibuang). Teruji: cancel setelah Stage 1 → log berhenti di Stage 2, Stage 11+ tidak pernah dijalankan.

### Validasi skema input (audit data #5 — degradasi senyap)
- **`waste_anomaly/schema.py`**: header lowercase/missing kini **gagal keras dengan pesan actionable** (dulu: `success=True` dengan analisa setengah mati — semua baris "Normal" padahal ada spike). Deteksi: kolom wajib hilang + saran near-miss case-insensitive, header duplikat, kolom hari kosong, nilai JENIS asing (warning).

### Exporter streaming (audit data #2 — OOM 100k baris)
- **Dual-mode otomatis**: ≤35.000 baris → mode normal (formatting penuh); di atasnya → **openpyxl `write_only`** (memori konstan; terverifikasi 60k baris sukses — dulu OOM-kill ~1,8 GB). Threshold bisa di-override via `config["output"]["streaming_threshold"]`. Handler `MemoryError` dengan pesan ramah.

### Logging framework (audit UI #4)
- **Rotating file log** `logs/waste_anomaly.log` (1 MB × 3 backup) + `report_callback_exception` hook Tk — exception di callback kini tercatat, tidak hilang di stderr.
- **16 exception senyap (`except: pass`) diganti `_LOGGER.debug(...)`** — jejak audit penuh tanpa spam UI.

### Test & CI
- **140 test** (dari 44): +54 unit test S1–S12 (trigger/non-trigger/boundary persis di threshold/NaN/config-override), +13 skema & cancel, +13 exporter (paritas data antar-mode + streaming 60k), +5 logging, +11 struktural UI.
- **CI GitHub Actions**: matrix Python 3.10/3.12 × Ubuntu/Windows — lint fatal (ruff E9,F63,F7,F82) + seluruh test + smoke import.

### Packaging
- **`BUILD_EXE.bat` + `waste_anomaly.spec`** (PyInstaller): .exe standalone tanpa Python di PC target, `console=False`, ikon multi-resolusi.
- **Ikon aplikasi** (teal/coral, AI-generated) dipasang via `iconphoto` + `.ico` untuk exe.
- Versi single-source 2.4.0 di semua situs (`__init__`, `APP_VERSION`, config.json, MULAI.bat, README).

## Changelog v2.3.2 — Audit Profesional Lanjutan

### Critical / High
- **Idempotency sejati (F7)**: file Excel bisa mengandung *FP dust* (mis. `21.299999999999997` yang visually = `21.3`). Sebelumnya: run-1 vs run-ulang memberi **skor anomali berbeda** untuk data yang sama (402 → 403 — 5 baris di boundary threshold S3/S5 flip; terverifikasi test). Kini semua nilai float dinormalisasi ke **15 digit signifikan** (semantik penyimpanan Excel) saat load — konsisten dengan apa yang user & Power Query lihat. Golden: 399 anomali (41 prioritas, 358 potensi) — 4 dust-false-positive kini Normal, 1 dust-false-negative konsisten terdeteksi.
- **Join BOM numerik (F1)**: `stages.py` memakai normalisasi `_key_str` (loader) — outlet numerik `1049.0` kini **match** dengan `"1049"` di sheet BOM. Sebelumnya: join gagal diam-diam → TOTAL BOM semua NaN → sinyal S6/S7 tidak pernah trigger.
- **Test suite (44 test)**: `tests/` — golden regression end-to-end pada fixture `DATA_WASTE.xlsx` (25.901 baris), unit test normalisasi kunci, unit test join BOM, unit test presisi float, kontrak summary dict, validasi domain status, dan **test idempotency** (re-run pada output sendiri). Run: `python -m pytest tests/ -v` (~60 s).
- **requirements.txt (F5)**: dependensi di-pin dengan alasan (matplotlib ≥ 3.9 untuk `tick_labels`, pandas 2.2.x teruji, calamine opsional). SETUP.bat kini install dari file ini.

### Medium
- **LICENSE (MIT)** ditambahkan (README sudah mengklaim sejak awal).
- **QUADRANT_THRESHOLD (F4)** kini benar-benar dibaca dari config user oleh chart quadrant — sebelumnya hardcode 0.5, chart & tabel bisa tidak sinkron.
- **Reset Default config (F3)** kini mencakup 20/20 key (sebelumnya 6 key baru tidak pernah di-reset).
- **Save config atomic (F2)**: tmp + `os.replace` (pola `filters.py`) + validasi nilai > 0.
- **Single-source version (L2)**: `__init__.py`, `APP_VERSION`, MULAI.bat, README — semua 2.3.2.
- **MULAI.bat** banner diperbarui (10 tab, bukan 8).

## Changelog v2.3.1 — Deep Audit & Fix

### Critical (crash / korupsi data)
- **UI freeze permanen**: exception apa pun di queue-drain loop mematikan polling → progress macet + tombol Run stuck disabled. Loop kini reschedule-first + tiap item di-guard.
- **Crash log popup**: tombol X menghancurkan window tapi referensi tetap hidup → `TclError` berantai. Kini X = hide; popup auto-recreate; `append()` di-guard.
- **Scroll mouse rusak total**: 5 binding `bind_all` saling menimpa → wheel menggerakkan canvas yang tersembunyi; tab Konfigurasi tak bisa di-wheel; tabel double-scroll. Kini satu dispatcher global (Windows ±120 / macOS ±small / Linux Button-4/5).
- **Crash empty-data**: 0 baris valid setelah Stage 2 → `ValueError: Length mismatch`. Kini guard ramah + pesan jelas.
- **Kolom hilang diam-diam**: merge DATABASE_SATUAN menimpa kolom bentrok (`SATUAN`, `NAMA BARANG` jadi `_x/_y`). Kini merge hanya kolom yang dibutuhkan + detektor bentrok.
- **Bar chart menumpuk**: label ter-truncate duplikat → matplotlib menumpuk bar di posisi sama (data tersembunyi). Kini plot posisional + disambiguasi label.

### High (UX & performa)
- **Memory leak**: figure matplotlib tidak pernah di-dispose pada tiap re-render → RAM membengkak. Kini teardown penuh (disconnect cids → destroy widget → `fig.clf()`).
- **Render storm**: ~18 figure digambar sinkron setelah pipeline selesai → UI membeku. Kini lazy per-tab (render saat tab dibuka) + refresh hanya tab aktif.
- **Search lag**: tiap keystroke re-render 3 chart + 500 baris + `apply` row-wise. Kini debounce 300 ms + mask vectorized per-kolom.
- **Kalkulasi M-fidelity**: `KONTRIBUSI TERBESAR` kini agregasi per-KETERANGAN (23% baris dulu salah); `KETERANGAN GABUNGAN` urutan per kontribusi; nama kolom kanonik (spasi, bukan underscore).
- **Idempotency HELPER/STATUS**: re-run di output sendiri dulu menghancurkan 21.355 nilai HELPER/STATUS. Kini dipertahankan seperti TOTAL BOM.
- **Dead Output-Excel UI** dihapus → diganti tombol **💾 Export Laporan Excel** (background thread, `PermissionError` friendly, 3.5× lebih cepat).
- **Quadrant chart** kini pakai Key Akhir aktual (bukan hardcode /31) — titik tidak lagi mendarat di quadrant yang salah.
- **Profil filter**: save kini konfirmasi overwrite; restore tidak lagi double-render; file `filters.json` atomic-save + auto-backup saat korup.
- **Warna JENIS stabil** antar-run & antar-tab (dulu hash-based — bisa bentrok).
- **Spinbox TclError**: input non-numerik tidak lagi crash handler.

### Medium/Low
- Window centering + clamp untuk layar 1366×768; font fallback cross-platform; sort kolom numeric-aware + indikator ▲/▼; label "Menampilkan N dari M baris"; chip label Indonesia; konfirmasi keluar saat pipeline jalan; tombol **⏹ Batalkan Run**; shortcut Ctrl+R/Ctrl+F; status `Timestamp`/`Key Akhir`/warning-config di Ringkasan; progress bar monotonic 0→100; make_sample rng fix; bersih-bersih dead code & duplikasi (helper `_format_cell`, `_apply_filters`, `_export_figures_png`).

## Reference

- M code sumber: Power Query `Waste` query (private repo)
- Pattern UI: https://github.com/anandategarch/Inventory-Adjusment

## License

MIT — bebas pakai, modify, distribute.
