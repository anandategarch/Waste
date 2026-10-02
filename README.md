# Waste Anomaly Detection

Python + Tkinter program untuk deteksi anomali waste di cabang resto. Replika 1:1 dari **Power Query M code** untuk analisa waste per item, per cabang, per kategori — lengkap dengan **12 sinyal anomali** dan composite scoring.

## Cara Pakai

### 1. Setup (sekali saja)
Jalankan `SETUP.bat` di root folder. Install dependencies:
- pandas, numpy (data processing)
- openpyxl (Excel I/O)

### 2. Siapkan Workbook Input
Satu file Excel `.xlsx` berisi **3 sheet** (atau named range):

| Sheet | Nama Kandidat | Wajib? | Kolom |
|-------|---------------|--------|-------|
| REKAP_MENTAH | `REKAP_MENTAH`, `Rekap Mentah`, `REKAP`, `Sheet1` | ✅ Wajib | `JENIS`, `NAMA BARANG`, `KETERANGAN`, `SATUAN`, `NAMA RESTO`, `SOURCE DATA`, `1`..`31` (hari), `KATEGORI`, `STATUS`, `PIC`, `PENYEBAB TERJADINYA WASTE`, `TOTAL` |
| BOM | `BOM`, `2  22 05`, `MASTER BOM` | Opsional | `Nomor #`, `Nama Barang`, `TOTAL BOM` |
| DATABASE_SATUAN | `DATABASE_SATUAN`, `Database Satuan`, `SATUAN` | Opsional | `NAMA ITEM`, `SUSUT`, `TRIAL`, `HANDLING`, `KUALITAS EKSTERNAL`, `KUALITAS`, `KUALITAS INTERNAL`, `EKSTERNAL`, `INTERNAL`, `ALAT MESIN`, `OVERSTOCK`, `CANCEL NOTA` |

> Sheet BOM & DATABASE_SATUAN opsional — kalau tidak ada, sinyal BOM dan STATUS akan di-skip tapi pipeline tetap jalan.

### 3. Jalankan (setiap kali)
Jalankan `MULAI.bat`. UI terbuka dengan 5 tab:

| Tab | Fungsi |
|-----|--------|
| 1. Run Pipeline | Browse workbook → isi Key Akhir (1-31) → Mulai Pipeline |
| 2. Hasil | Preview tabel hasil (Detail/Anomali Prioritas/Per Cabang/Top Items/Pareto) |
| 3. Ringkasan | Summary run terakhir (total baris, cabang, item, count per status) |
| 4. Konfigurasi | Editor threshold (simpan ke `waste_anomaly/config.json`) |
| 5. Bantuan | Instruksi pakai + 12 sinyal anomali + troubleshooting |

## Output Excel (6 Sheet)

| Sheet | Isi |
|-------|-----|
| Detail | Semua baris — kolom mengikuti M code Final order (~70 kolom) |
| Anomali Prioritas | Hanya baris dengan `ANOMALY STATUS` = Prioritas Tinggi + Potensi Anomali |
| Per Cabang | Ringkasan per NAMA RESTO (jumlah baris, total waste, count anomali per status) |
| Top Items | Top 20 item by TOTAL waste (rank, total, max, cabang terpengaruh, count prioritas) |
| Pareto Alasan | Group by KETERANGAN — sum TOTAL, persentase, cumulative % |
| Log Run | Timestamp, parameter, summary stats, log lines pipeline |

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
├── MULAI.bat                       ← ENTRY POINT (buka UI 5 tab)
├── SETUP.bat                       ← One-time install (pandas, numpy, openpyxl)
├── README.md                       ← File ini
├── .gitignore
├── ui_app.py                       ← UI Tkinter multi-tab (entry point)
├── waste_anomaly/
│   ├── __init__.py
│   ├── config.json                 ← Thresholds + sheet name candidates
│   ├── pipeline.py                 ← Orchestrator 14 stage
│   ├── loader.py                   ← Excel loaders (REKAP_MENTAH + BOM + DATABASE_SATUAN)
│   ├── stages.py                   ← 14 stage replika M code
│   ├── signals.py                  ← 12 sinyal anomali + composite score
│   ├── exporter.py                 ← Multi-sheet xlsx writer + formatting
│   └── utils.py                    ← Helper (Number.From, List.Sum, dll)
├── data/                           ← Letakkan workbook input di sini
│   └── README.md
└── output/                         ← Output Excel tersimpan di sini
    └── .gitkeep
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
3. Letakkan workbook Excel Anda di folder `data/`
4. Jalankan `SETUP.bat` (sekali saja)
5. Jalankan `MULAI.bat` (setiap kali)

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
| `ModuleNotFoundError: pandas` | Jalankan `SETUP.bat` dulu. |
| UI tidak terbuka | Pastikan Python 3.10+ terpasang (`python --version`). |

## Reference

- M code sumber: Power Query `Waste` query (private repo)
- Pattern UI: https://github.com/anandategarch/Inventory-Adjusment

## License

MIT — bebas pakai, modify, distribute.
