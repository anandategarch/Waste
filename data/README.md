# Folder Data

Letakkan workbook Excel input Anda di sini.

## Template Standar (NEW v2.1.1)

File `template_REKAP_MENTAH.xlsx` adalah **template standar** untuk input pipeline. Copy file ini, rename sesuai kebutuhan, lalu isi.

## Format yang Didukung

- `.xlsx` (recommended)
- `.xlsm`
- `.xls` (legacy)

## Sheet yang Diperlukan

| Sheet | Nama Kandidat | Wajib? |
|-------|---------------|--------|
| REKAP_MENTAH | `REKAP_MENTAH`, `Rekap Mentah`, `REKAP`, `Sheet1`, `DATA_WASTE`, `DATA` | ✅ Wajib |
| BOM | `BOM`, `2  22 05`, `MASTER BOM` | Opsional |
| DATABASE_SATUAN | `DATABASE_SATUAN`, `Database Satuan`, `SATUAN` | Opsional |

## Struktur REKAP_MENTAH (53 kolom)

Template memakai struktur yang sama dengan `DATA_WASTE.xlsx` (output M code user). Kolom dibagi 2 warna:

### Warna Hijau (USER WAJIB ISI)
| Kolom | Tipe | Contoh |
|-------|------|--------|
| SOURCE DATA | text | WASTE BAHAN DAN PACKAGING |
| JENIS | text | WASTE / SUSUT / TRIAL (filter di stage 1) |
| KETERANGAN | text | Alat/ Mesin, Cancel Nota, Eksternal, Internal, Over Stock, Handling, Kualitas, dll |
| NAMA BARANG | text | ADONAN GORENG MEKAR |
| NAMA RESTO | text | B.1001.MLGPAR |
| SATUAN | text | GR, KG, PORSI |
| 1 .. 31 | number | qty waste untuk hari ke-N (0 kalau tidak ada) |

### Warna Abu-abu (OUTPUT — biarkan kosong, pipeline akan hitung)
| Kolom | Sumber |
|-------|--------|
| STATUS, HELPER, MAX TOTAL, AVG TOTAL, TOTAL BOM, % to BOM | Output Stage 1-10 |
| TOTAL, AVG, MAX, Status2, Count Hari | Output Stage 2 |
| KETERANGAN GABUNGAN, KONTRIBUSI TERBESAR, SOURCE DATA GABUNGAN | Output Stage 3 |
| RANGKING WASTE, Rill % to BOM | Output Stage 5-11 |

## Cara Pakai Template

1. Copy `template_REKAP_MENTAH.xlsx` ke folder kerja Anda
2. Rename (mis. `Waste_2025-09.xlsx`)
3. Buka di Excel
4. Sheet **PETUNJUK** berisi instruksi lengkap (baca dulu)
5. Sheet **REKAP_MENTAH**:
   - Hapus sample row (baris ke-2)
   - Isi data waste Anda mulai baris ke-2
   - Kolom hijau WAJIB diisi, kolom abu-abu BIARKAN KOSONG
6. (Opsional) Sheet **BOM**: isi kalau mau sinyal BOM aktif
7. (Opsional) Sheet **DATABASE_SATUAN**: isi kalau mau STATUS aktif
8. Save file
9. Jalankan `MULAI.bat` → Browse file Anda → Mulai Pipeline

## Tips

- Kalau workbook Anda punya nama sheet custom, edit `waste_anomaly/config.json` → `input_sheets` untuk tambah nama kandidat.
- Kalau kolom BOM/SATUAN punya nama lain, edit section `bom_columns` / `satuan_columns`.
- **Idempotent**: pipeline bisa di-run di file output sendiri (mis. `Waste_Anomaly_Report.xlsx`) — semua derived columns akan di-drop & dihitung ulang.
