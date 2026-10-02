# Waste Anomaly Detection

Python + Tkinter **professional dashboard** untuk deteksi anomali waste di cabang resto. Replika 1:1 dari **Power Query M code** untuk analisa waste per item, per cabang, per kategori — lengkap dengan **12 sinyal anomali**, composite scoring, **drill-down interaktif**, **filter profile persistence**, **comparison mode 2 cabang**, dan **22 grafik** matplotlib embedded.

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
Jalankan `MULAI.bat`. UI terbuka dengan **8 tab**:

| Tab | Fungsi |
|-----|--------|
| 📊 Dashboard | **PRO** — KPI cards + filter bar + 3 interactive charts + drill-down table |
| ⚖ Compare Cabang | **NEW v2.1** — Side-by-side analysis 2 cabang dengan 4 chart + metrics |
| 📋 Hasil | Preview tabel hasil (Detail/Anomali/Cabang/Top/Pareto) |
| 📈 Visualisasi | 12 grafik matplotlib gallery + export PNG |
| 🗂 Ringkasan | Summary run terakhir (total, cabang, item, count per status) |
| ▶ Run Pipeline | Browse workbook + Key Akhir + Run |
| ⚙ Konfigurasi | Editor threshold (simpan ke config.json) |
| ❓ Bantuan | Instruksi pakai + 12 sinyal + drill-down workflow |

## Output Excel (6 Sheet)

| Sheet | Isi |
|-------|-----|
| Detail | Semua baris — kolom mengikuti M code Final order (~70 kolom) |
| Anomali Prioritas | Hanya baris dengan `ANOMALY STATUS` = Prioritas Tinggi + Potensi Anomali |
| Per Cabang | Ringkasan per NAMA RESTO (jumlah baris, total waste, count anomali per status) |
| Top Items | Top 20 item by TOTAL waste (rank, total, max, cabang terpengaruh, count prioritas) |
| Pareto Alasan | Group by KETERANGAN — sum TOTAL, persentase, cumulative % |
| Log Run | Timestamp, parameter, summary stats, log lines pipeline |

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

## Struktur Project

```
Waste/
├── MULAI.bat                       ← ENTRY POINT (buka UI 8 tab)
├── SETUP.bat                       ← One-time install (pandas, numpy, openpyxl, matplotlib)
├── README.md                       ← File ini
├── .gitignore
├── ui_app.py                       ← UI Tkinter professional dashboard (v2.1)
├── make_sample.py                  ← Generate sample workbook untuk testing
├── waste_anomaly/
│   ├── __init__.py
│   ├── config.json                 ← Thresholds + sheet name candidates
│   ├── pipeline.py                 ← Orchestrator 14 stage
│   ├── loader.py                   ← Excel loaders (auto-detect sheet name)
│   ├── stages.py                   ← 14 stage replika M code (idempotent v2.1.1)
│   ├── signals.py                  ← 12 sinyal anomali + composite score (max 19)
│   ├── charts.py                   ← 12 static chart matplotlib
│   ├── dashboard.py                ← 6 interactive chart + 4 comparison chart
│   ├── filters.py                  ← Filter profile persistence
│   ├── exporter.py                 ← Multi-sheet xlsx writer + formatting
│   └── utils.py                    ← Helper (Number.From, List.Sum, dll)
├── data/                           ← (opsional) letakkan DATA_WASTE.xlsx di sini
│   └── README.md
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

Edit `waste_anomaly/config.json` → section `thresholds`. Atau pakai tab "4. Konfigurasi" di UI.

```json
{
  "thresholds": {
    "TH_SPIKE": 3,
    "TH_MAX_AVG_AKTIF": 2.5,
    "TH_PEER_HIGH": 3,
    ...
  }
}
```

## Troubleshooting

| Error | Solusi |
|-------|--------|
| `Tidak menemukan sheet untuk 'rekap_mentah'` | Pastikan workbook punya sheet `REKAP_MENTAH` / `Rekap Mentah` / `REKAP`. Atau edit `config.json` → `input_sheets.rekap_mentah` untuk tambah nama kandidat. |
| `BOM sheet tidak ditemukan` | BOM join dilewati. Sinyal S6/S7 tidak trigger. Tambahkan sheet `BOM` / `MASTER BOM` untuk mengaktifkan. |
| `DATABASE_SATUAN tidak ditemukan` | STATUS menjadi "Cek" untuk semua baris. Tambahkan sheet `DATABASE_SATUAN` untuk mengaktifkan. |
| `ModuleNotFoundError: pandas / matplotlib` | Jalankan `SETUP.bat` dulu. Atau manual: `pip install pandas numpy openpyxl matplotlib`. |
| Tab Visualisasi kosong | Pastikan sudah run pipeline. Klik "⟳ Refresh Grafik" manual kalau tidak auto-load. |
| Grafik matplotlib error di Linux headless | Set env: `export MPLBACKEND=TkAgg` sebelum jalankan `python ui_app.py`. |
| UI tidak terbuka | Pastikan Python 3.10+ terpasang (`python --version`). |

## Reference

- M code sumber: Power Query `Waste` query (private repo)
- Pattern UI: https://github.com/anandategarch/Inventory-Adjusment

## License

MIT — bebas pakai, modify, distribute.
