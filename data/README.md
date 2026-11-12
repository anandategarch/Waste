# Folder Data (Opsional)

Letakkan `DATA_WASTE.xlsx` Anda di sini (atau di folder mana saja — browse via UI saat run pipeline).

## Workflow Anda

Tiga cara memuat data dari tab **Pipeline** (tanpa olah manual di Excel):

1. **Telusuri…** — file `DATA_WASTE.xlsx` standar 53 kolom
2. **🧮 Pilih REKAP MENTAH…** — file rekap mentah bulanan, sekali proses langsung jalan (jalur utama, mengaktifkan edit kuantiti dari tab Anomali)
3. **📁 Proses dari Folder…** — folder berisi file `.xlsx` format BJMHAS (nama resto diambil dari nama file), semua digabung otomatis

File lama cukup di-replace (overwrite) lalu run ulang — pipeline idempotent.

## Format Standar — `DATA_WASTE.xlsx` (53 kolom)

Pipeline idempotent — bisa di-run di file yang sudah berisi output M code (kolom MAX, AVG, KETERANGAN GABUNGAN, dll). Stage 1 akan auto-drop semua derived columns & recompute dari kolom hari 1..31.

### Kolom Input Wajib (user isi)
| Kolom | Tipe | Contoh |
|-------|------|--------|
| SOURCE DATA | text | WASTE BAHAN DAN PACKAGING |
| JENIS | text | WASTE / SUSUT / TRIAL (filter di stage 1) |
| KETERANGAN | text | Alat/ Mesin, Cancel Nota, Eksternal, Internal, Over Stock, Handling, Kualitas, dll |
| NAMA BARANG | text | ADONAN GORENG MEKAR |
| NAMA RESTO | text | B.1001.MLGPAR |
| SATUAN | text | GR, KG, PORSI |
| 1 .. 31 | number | qty waste untuk hari ke-N (0 kalau tidak ada) |

### Kolom Output (boleh kosong, pipeline akan hitung ulang)
STATUS, HELPER, MAX TOTAL, AVG TOTAL, TOTAL BOM, % to BOM, TOTAL, AVG, MAX, Status2, KETERANGAN GABUNGAN, KONTRIBUSI TERBESAR, SOURCE DATA GABUNGAN, Count Hari, RANGKING WASTE, Rill % to BOM

## Sheet Name Detection

Loader auto-detect sheet berikut (case-insensitive):
- `REKAP_MENTAH`, `Rekap Mentah`, `REKAP`, `Sheet1`, `DATA_WASTE`, `Data Waste`, `DATA`

Kalau nama sheet Anda beda, edit `waste_anomaly/config.json` → `input_sheets.rekap_mentah` untuk tambah nama kandidat.

## Sheet Opsional (untuk sinyal BOM & STATUS)

| Sheet | Nama Kandidat | Kolom |
|-------|---------------|-------|
| BOM | `BOM`, `2  22 05`, `MASTER BOM` | `Nomor #` (= NAMA RESTO), `Nama Barang` (= NAMA BARANG), `TOTAL BOM` |
| DATABASE_SATUAN | `DATABASE_SATUAN`, `Database Satuan`, `SATUAN` | `NAMA ITEM` (= NAMA BARANG), 11 kolom kategori (CANCEL NOTA, SUSUT, TRIAL, HANDLING, KUALITAS EKSTERNAL, KUALITAS, KUALITAS INTERNAL, EKSTERNAL, INTERNAL, ALAT MESIN, OVERSTOCK) |

Kalau sheet BOM/DATABASE_SATUAN tidak ada, sinyal BOM (S6/S7) & STATUS (Sesuai/Tidak Sesuai) tidak akan trigger tapi pipeline tetap jalan.

## Format yang Didukung

- `.xlsx` (recommended)
- `.xlsm`
- `.xls` — TIDAK didukung (save-as `.xlsx` dulu)
