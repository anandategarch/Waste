# Waste Anomaly Detection

**Anomaly workbench** Python + PySide6 (Qt) untuk deteksi anomali waste di cabang resto — replika 1:1 pipeline Power Query M code. Membaca rekap waste bulanan (Excel), menjalankan 14-stage pipeline in-memory, men-skor setiap baris dengan **12 sinyal anomali**, dan menyajikan hasilnya di UI 5 tab interaktif + export Excel 10 sheet.

> Versi **v2.18.5** · 1.197 test (pytest) · CI GitHub Actions (matrix Python × OS) · MIT License

## Fitur Utama

- **Sekali jalan** — pilih file rekap mentah → pipeline langsung, tanpa file olahan antara
- **Proses dari Folder** — pindai seluruh folder `.xlsx` (format BJMHAS, nama resto dari nama file), gabung jadi satu dataset
- **12 sinyal anomali** (S1–S12) + composite score → status Prioritas Tinggi / Potensi Anomali / Perlu Review / Normal
- **5 tab analisa**: Pipeline · Anomali · Hari Mencurigakan · Banding Periode · Follow Up
- **Drill-down interaktif** — klik baris = pop-up detail (ringkasan, chip sinyal, peta nilai per hari 1–31, tombol fokus cabang/item/alasan)
- **Filter funnel di judul semua kolom tabel** — daftar nilai bercentang + pencarian + Pilih Semua + **klik-ganda nilai = pilih hanya itu** + tombol ◉ Hanya Ini (hasil cari)
- **Banding multi-bulan** (1 file = 1 bulan; mode 📊 Tipikal = median gabungan ≥2 bulan) — hanya cabang yang ada di **kedua** bulan (resto baru/tutup disembunyikan, jumlahnya dilaporkan)
- **Follow Up** — centang ✓ baris mencurigakan → shortlist rekap + ekspor + impor hasil tindak lanjut
- **Data quality otomatis** — 7+1 pemeriksaan jalan di setiap run & ikut ke export
- **Tabel virtualized** — 25.901+ baris tanpa cap, sort numerik, warna status per baris

## Mulai Cepat (Windows)

```
1. Download & ekstrak repo (Code → Download ZIP)
2. Jalankan SETUP.bat        ← sekali saja: buat .venv + install 5 paket
3. Jalankan MULAI.bat        ← tiap kali pakai (tanpa jendela CMD hitam)
```

**Persyaratan:** Python 3.10+ · Windows (`.bat`). Mac/Linux: `python ui_app.py`.
**Dependensi:** pandas, numpy, openpyxl, PySide6, python-calamine (semua di-install `SETUP.bat`).

## Tiga Cara Memuat Data (tab Pipeline)

| Tombol | Untuk File | Perilaku |
|--------|-----------|----------|
| 🧮 Pilih File Sendiri | `DATA_WASTE.xlsx` standar 53 kolom | Pipeline langsung pada file |
| 🧮 Olah & Jalankan REKAP MENTAH… | Rekap mentah bulanan (mis. `REKAP MENTAH_01-31 AGUSTUS 2026_TEGAR.xlsx`) | Header diperbaiki, nilai dinormalisasi, TOTAL BOM diambil dari baris BOM — **sekali proses, tanpa file antara** |
| 📁 Proses dari Folder… | Folder berisi `.xlsx` format BJMHAS (sheet REKAP MENTAH tanpa kolom NAMA RESTO) | Semua file dipindai, resto disintesis dari nama file, digabung jadi satu dataset |

> **Banding bulan lalu (opsional):** tab Banding Periode → ＋ Tambah File… → pilih beberapa file sekaligus → jalankan pipeline → muncul Ringkasan, per jenis, mover, dan mode 📊 Tipikal.

## Format Input Standar (53 kolom)

| # | Kolom | Wajib? | Contoh |
|---|-------|--------|--------|
| 0–8 | STATUS, HELPER, MAX TOTAL, AVG TOTAL, TOTAL BOM, % to BOM, TOTAL, AVG, MAX | Opsional (dihitung ulang) | kosong |
| 9 | SOURCE DATA | ✅ | WASTE BAHAN DAN PACKAGING |
| 10 | JENIS | ✅ (filter: WASTE/SUSUT/TRIAL) | WASTE |
| 11 | KETERANGAN | ✅ | Cancel Nota, Internal, Kualitas, dll |
| 12 | NAMA BARANG | ✅ | ADONAN GORENG MEKAR |
| 13 | NAMA RESTO | ✅ | B.1001.MLGPAR |
| 14 | SATUAN | ✅ | GR, KG, PORSI |
| 15–45 | 1 .. 31 | ✅ (qty waste per hari) | 0 / 50 / 100 |
| 46–52 | Status2, KETERANGAN GABUNGAN, dll | Opsional (dihitung ulang) | kosong |

**Sheet opsional** untuk mengaktifkan sinyal BOM (S6/S7) & STATUS:

| Sheet | Nama kandidat | Kolom kunci |
|-------|---------------|-------------|
| BOM | `BOM`, `MASTER BOM` | `Nomor #` (=NAMA RESTO), `Nama Barang`, `TOTAL BOM` |
| DATABASE_SATUAN | `DATABASE_SATUAN`, `SATUAN` | `NAMA ITEM` + kategori per jenis |

Tanpa sheet ini pipeline tetap jalan — sinyal BOM & STATUS tidak terpicu. Pipeline **idempotent**: kolom output lama di file di-drop & dihitung ulang otomatis.

## UI — 5 Tab (urutan alur kerja)

| Tab | Fungsi |
|-----|--------|
| ▶ Pipeline | Entry point: pilih workbook/folder, key akhir, Run/⏹Batal, progres per-stage, log, editor threshold |
| 🔍 Anomali | Pusat analisa: KPI strip 6 kartu, tabel ter-ranked skor, pop-up detail, % to BOM |
| 📅 Hari Mencurigakan | Bukti per-hari: HARI TERSANGKA, tipikal cabang lain, rasio vs bulan lalu |
| 📊 Banding Periode | Banding bulan-ke-bulan + mode Tipikal (median ≥2 bulan); hanya cabang yang ada di kedua bulan |
| ✅ Follow Up | Shortlist baris tercentang ✓ — format rekap, ekspor & impor hasil tindak lanjut |

## 12 Sinyal Anomali (S1–S12)

| # | Nama | Trigger | Skor |
|---|------|---------|------|
| S1 | Lonjakan vs rata-rata harian | Count≥2 & MAX/AVG≥3 | 1 |
| S2 | Lonjakan vs hari aktif | Count≥3 & MAX/AVG_AKTIF≥2,5 (≥4→2) | 1–2 |
| S3 | Lonjakan vs nilai tengah | Count≥3 & MAX/MEDIAN_AKTIF≥3 | 2 |
| S4 | Terpusat di satu hari | MAX/TOTAL≥0,70 (≥0,50→1) | 1–2 |
| S5 | Jauh di atas hari kedua | Count≥2 & MAX/SECOND_MAX≥3 | 1 |
| S6 | Puncak harian vs BOM | MAX/TOTAL_BOM≥0,50 (≥0,25→1) | 1–2 |
| S7 | Total bulanan vs BOM | TOTAL/TOTAL_BOM≥1,00 (≥0,50→1) | 1–2 |
| S8 | Puncak vs cabang lain | PeerCount≥3 & MAX/PeerMedMax≥3 (≥2→1) | 1–2 |
| S9 | Total vs cabang lain | PeerCount≥3 & TOTAL/PeerMedTot≥3 | 1 |
| S10 | Waste hanya satu hari | Count=1 & (MaxBOM≥0,10 atau MaxPeer≥2) | 1 |
| S11 | Menumpuk di hari terakhir | LastDay/TOTAL≥0,70 | 1 |
| S12 | Pola 10× (mungkin salah ketik) | heuristik rasio (8–12 / 80–120 / 800–1200 / 8000–12000) | 2 |

**Skor maksimum 18** → status: `≥8` Prioritas Tinggi · `≥5` Potensi Anomali · `≥3` Perlu Review · lainnya Normal.

## Export Excel (10 Sheet)

Klik **💾 Export Excel** di toolbar (background thread, UI tetap responsif):

| Sheet | Isi |
|-------|-----|
| Detail | Semua baris (~70 kolom, urutan Final M code) |
| Anomali Prioritas | Baris Prioritas Tinggi + Potensi Anomali |
| Per Cabang | Ringkasan per resto: total waste, count anomali per status |
| Top Items | Top 20 item by TOTAL waste |
| Pareto Alasan | Group by KETERANGAN + cumulative % |
| Waste per Hari | Total per hari (analisa temporal) |
| Alasan x Hari | Matriks alasan × tanggal |
| Money View | Prioritas magnitude (top 100) |
| Data Quality | Hasil 7+1 pemeriksaan |
| Log Run | Timestamp, parameter, ringkasan, log pipeline |

## Struktur Project

```
Waste/
├── MULAI.bat / SETUP.bat / BUILD_EXE.bat   ← entry point, install, build exe
├── ui_app.py                               ← launcher tipis (pythonw, tanpa CMD)
├── ui/                                     ← paket UI PySide6 (13 file):
│   ├── app.py                              ← MainWindow + 5 tab + Bantuan F1
│   ├── view_pipeline / view_anomali / view_hari /
│   │   view_periode / view_followup.py
│   ├── workers.py                          ← QThread: pipeline/export/history
│   ├── models.py                           ← tabel virtualized (PandasTableModel)
│   └── widgets.py, theme.py, state.py, shared.py, followup_table.py, icons.py
├── waste_anomaly/                          ← engine:
│   ├── pipeline.py                         ← orchestrator 14 stage + cancel
│   ├── stages.py                           ← replika M code (idempotent)
│   ├── signals.py                          ← 12 sinyal + composite score
│   ├── rekap_import.py                     ← olah rekap mentah / folder BJMHAS
│   ├── day_focus.py / profile.py           ← bukti hari & profil baris
│   ├── period_history.py / period_compare.py ← banding multi-bulan
│   ├── temporal.py / priority.py / data_quality.py ← sheet analisa
│   ├── exporter.py                         ← xlsx writer + mode streaming
│   ├── schema.py / loader.py / logging_setup.py / frozen.py / utils.py
│   └── config.json                         ← thresholds + nama sheet (editable)
├── tests/                                  ← 54 file, 1.197 test pytest
├── .github/workflows/ci.yml                ← CI matrix Python × OS
├── sample_workbook.xlsx                    ← fixture test in-repo
└── requirements.txt · LICENSE · waste_anomaly.spec
```

> Data asli (rekap resto) **tidak di-track** (`.gitignore`) — letakkan file Anda di mana saja dan browse lewat UI.

## CLI Mode (tanpa UI)

```python
from waste_anomaly.pipeline import run_pipeline
from waste_anomaly.exporter import export_to_excel
from waste_anomaly.utils import load_config

summary = run_pipeline("data/rekap.xlsx", key_akhir=31,
                       progress_callback=lambda msg, pct: print(f"[{pct:.0f}%] {msg}"))
df = summary["df"]  # DataFrame hasil semua stage (in-memory)
print(summary["total_rows"], "baris •", summary["prioritas_count"], "prioritas")

result = export_to_excel(df, "output/Waste_Anomaly_Report.xlsx",
                         config=load_config(), key_akhir=summary["key_akhir"],
                         log_lines=summary["log"].splitlines())
```

## Custom Thresholds

Edit `waste_anomaly/config.json` → section `thresholds` (mis. `TH_SPIKE`, `STATUS_PRIORITAS`), atau pakai **editor threshold di tab Pipeline** (Simpan / Reset Default). Config korup otomatis diperingatkan di log & pipeline lanjut dengan default.

## Testing, CI & Packaging

- **Test:** `python -m pytest tests/ -x -q` — TESTS_FILE_PLACEHOLDER test (golden regression, unit sinyal, UI offscreen, validasi skema, dsb.)
- **CI:** GitHub Actions — lint (ruff) + full suite, matrix Python × OS
- **EXE standalone:** jalankan `BUILD_EXE.bat` di Windows → `dist/WasteAnomalyDetection.exe` (jalan tanpa Python, config & log tersimpan berdampingan exe)

## Troubleshooting

| Masalah | Solusi |
|---------|--------|
| Sheet `rekap_mentah` tidak ditemukan | Pastikan ada sheet `DATA_WASTE`/`REKAP_MENTAH`/`DATA`, atau tambah kandidat nama di `config.json` |
| `ModuleNotFoundError: pandas/PySide6` | Jalankan `SETUP.bat` dulu (membuat `.venv` lokal) |
| File `.xls` | Tidak didukung — save-as `.xlsx` dulu |
| Export gagal karena file terbuka di Excel | Tutup filenya, lalu klik Export ulang (pesan errornya menjelaskan) |
| UI error di Linux headless | `export QT_QPA_PLATFORM=offscreen` sebelum `python ui_app.py` |
| `pip install PySide6` gagal (path panjang Windows) | Pakai `SETUP.bat` versi terbaru (otomatis `.venv`); atau pindahkan folder ke path pendek |

## Changelog

**v2.18.5** — UX Banding Periode + pembersihan (permintaan user): (1) **hanya cabang yang ada di kedua bulan** yang tampil — resto yang hanya ada bulan ini (belum ada pembanding) atau hanya di pembanding (tutup/ganti nama) disembunyikan dari semua tabel banding, jumlahnya dilaporkan di baris status; (2) **tombol sort dibalik** sesuai intuisi user — *Urut Naik* = nilai **terbesar** dulu, *Urut Turun* = terkecil dulu (dulu mengikuti konvensi Excel yang terasa kebalik; label kini eksplisit); (3) **pilih 1 nilai cepat** di menu filter funnel: klik-ganda nilai = tampilkan hanya itu + tombol ◉ *Hanya Ini* (centang hanya hasil pencarian) — tanpa uncek satu per satu; (4) **tab Scorecard Cabang dihapus** bersama dead code-nya (`ui/view_scorecard.py`, `waste_anomaly/insights.py`, alias `PEER_KEYS`).
**v2.18.4** — Fix Banding Periode lintas sumber: pencocokan cabang kini memakai *stem* kode resto di semua join (`BJMHAS` dari alur “Proses dari Folder” = `1216.BJMHAS` / `B.1001.MLGPAR` dari file pembanding DBS/Power Query) — dulu join exact 0-cocok → SELURUH item tampil BARU/HILANG palsu (v2.18.1 hanya memberi peringatan). Tercakup: Ringkasan/Cabang/Item/Baru/Hilang, drill-down (`compare_level` + `drill_day_detail`), kolom BULAN LALU di tab Anomali (`change_vs_history`) & NILAI BULAN LALU di tab Hari (`day_evidence_vs_history`); kolom tampil tetap nama asli sumber; nama wajar bertitik (`V.20`, `NO.1`) tak distrip; +23 test regresi.

**v2.18.3** — Fix kolom `TOTAL` blank pada file hasil "Proses dari Folder": sel TOTAL kosong di file gabungan kini diisi otomatis dengan jumlah kolom hari 1–31 (sel TOTAL memang dibiarkan kosong di file sumber — terukur 22/48.202 baris — atau kolom TOTAL tidak ada di sheet); baris tanpa satu pun nilai hari tetap kosong (jujur, tanpa fabrikasi 0). Nilai TOTAL yang sudah terisi dipertahankan. Analisa tidak berubah (pipeline & Banding Periode selalu menghitung ulang TOTAL dari kolom hari sesuai Key Akhir) — murni kejujuran file output; log folder + summary kini mencatat jumlah sel yang diisi; +8 test regresi.

**v2.18.2** — Fix "Proses dari Folder" salah baca sheet: pemilihan sheet rekap kini berbasis skor bukti (nama sheet, kolom `SOURCE DATA`, JENIS kanonik) — file workbook yang sheet seksi DEVIASI-nya muncul lebih duluan tidak lagi salah terbaca (bukti: 5/20 file folder DEVIASI WEEKLY salah data → Banding Periode salah semua); baris kosong interleaved dibuang; log folder kini menampilkan sheet terpilih + peringatan utk sheet meragukan; +19 test regresi.

**v2.18.1** — Audit tab Banding Periode: 4 bug fix — (1) file pembanding kini melewati helper pipeline yang sama (JENIS `'2.WASTE'` tidak lagi terbuang; header tergesar tergeser dimuat); (2) `key_akhir` pembanding dihitung dari baris waste saja (baris BOM di luar periode tak menggelembungkan); (3) peringatan eksplisit saat 0 cabang cocok (alur folder memakai nama file vs kode resto di pembanding); (4) +8 test regresi.

Riwayat lengkap per versi: lihat [Commit History](https://github.com/anandategarch/Waste/commits/main) — setiap rilis didokumentasikan detail di pesan commit.

## License

[MIT](LICENSE)
