# Folder Data

Letakkan workbook Excel input Anda di sini. Workbook harus berisi minimal 1 sheet `REKAP_MENTAH`.

## Format yang Didukung

- `.xlsx` (recommended)
- `.xlsm`
- `.xls` (legacy)

## Sheet yang Diperlukan

| Sheet | Nama Kandidat | Wajib? |
|-------|---------------|--------|
| REKAP_MENTAH | `REKAP_MENTAH`, `Rekap Mentah`, `REKAP`, `Sheet1` | ✅ Wajib |
| BOM | `BOM`, `2  22 05`, `MASTER BOM` | Opsional |
| DATABASE_SATUAN | `DATABASE_SATUAN`, `Database Satuan`, `SATUAN` | Opsional |

## Struktur REKAP_MENTAH

| Kolom | Tipe | Contoh |
|-------|------|--------|
| KATEGORI | text | SUSUT, TRIAL, WASTE (akan di-drop di stage 1) |
| SOURCE DATA | text |Audit, Stock Opname, dll |
| JENIS | text | SUSUT, TRIAL, WASTE (filter di stage 1) |
| STATUS | text | (akan di-drop di stage 1) |
| NAMA BARANG | text | Ayam Fillet, Minyak Goreng, dll |
| KETERANGAN | text | Alat/ Mesin, Cancel Nota, Eksternal, Internal, Over Stock, Handling, Kualitas, dll |
| PENYEBAB TERJADINYA WASTE | text | (akan di-drop di stage 1) |
| SATUAN | text | kg, gram, porsi, buah |
| 1 .. 31 | number | waste qty untuk hari ke-N |
| TOTAL | number | pre-computed sum (akan di-drop & dihitung ulang) |
| NAMA RESTO | text | kode cabang, mis. RESTO.PWKTAM, RESTO.KWGGAL |
| PIC | text | (akan di-drop di stage 1) |

## Tips

- Kalau workbook Anda punya nama sheet custom, edit `waste_anomaly/config.json` → section `input_sheets`.
- Kalau kolom BOM/SATUAN punya nama lain, edit section `bom_columns` / `satuan_columns`.
