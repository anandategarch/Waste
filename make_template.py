"""
make_template.py — generate template workbook kosong dengan struktur standar.

Membuat template_REKAP_MENTAH.xlsx dengan:
  - Sheet 'REKAP_MENTAH' (53 kolom mengikuti struktur DATA_WASTE.xlsx user)
  - Sheet 'BOM' (3 kolom: Nomor #, Nama Barang, TOTAL BOM) — kosong, opsional
  - Sheet 'DATABASE_SATUAN' (12 kolom: NAMA ITEM + 11 kategori) — kosong, opsional

Template ini digunakan sebagai standar input untuk Waste Anomaly pipeline.
User tinggal isi sheet REKAP_MENTAH dengan data waste harian (kolom 1..31),
opsional isi sheet BOM dan DATABASE_SATUAN untuk mengaktifkan sinyal BOM/STATUS.

Run: python make_template.py
Output: data/template_REKAP_MENTAH.xlsx
"""

from pathlib import Path
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

OUT = Path(__file__).resolve().parent / "data" / "template_REKAP_MENTAH.xlsx"

# ============================================================
# COLUMN DEFINITIONS (sesuai struktur DATA_WASTE.xlsx user)
# ============================================================

# Header REKAP_MENTAH — 53 kolom (struktur user)
REKAP_HEADERS = [
    # Output M code (akan di-drop & dihitung ulang — boleh kosong di template)
    "STATUS", "HELPER", "MAX TOTAL", "AVG TOTAL", "TOTAL BOM", "% to BOM",
    "TOTAL", "AVG", "MAX",
    # Input utama (USER WAJIB ISI)
    "SOURCE DATA", "JENIS", "KETERANGAN", "NAMA BARANG", "NAMA RESTO", "SATUAN",
    # Hari 1..31 (USER WAJIB ISI dengan qty waste harian)
    *[str(i) for i in range(1, 32)],
    # Output turunan (akan dihitung ulang — boleh kosong)
    "Status2", "KETERANGAN GABUNGAN", "KONTRIBUSI TERBESAR", "SOURCE DATA GABUNGAN",
    "Count Hari", "RANGKING WASTE", "Rill % to BOM",
]

# Header BOM — 3 kolom (opsional, untuk sinyal BOM S6/S7)
BOM_HEADERS = ["Nomor #", "Nama Barang", "TOTAL BOM"]

# Header DATABASE_SATUAN — 12 kolom (opsional, untuk STATUS Sesuai/Tidak Sesuai)
SATUAN_HEADERS = [
    "NAMA ITEM",
    "CANCEL NOTA", "SUSUT", "TRIAL", "HANDLING",
    "KUALITAS EKSTERNAL", "KUALITAS", "KUALITAS INTERNAL",
    "EKSTERNAL", "INTERNAL", "ALAT MESIN", "OVERSTOCK",
]

# Sample row untuk REKAP_MENTAH (1 contoh baris supaya user tahu format)
REKAP_SAMPLE_ROW = {
    # Output cols (kosong, akan dihitung pipeline)
    "STATUS": "", "HELPER": "", "MAX TOTAL": "", "AVG TOTAL": "",
    "TOTAL BOM": "", "% to BOM": "", "TOTAL": "", "AVG": "", "MAX": "",
    # Input utama (contoh)
    "SOURCE DATA": "WASTE BAHAN DAN PACKAGING",
    "JENIS": "WASTE",
    "KETERANGAN": "Alat/ Mesin",
    "NAMA BARANG": "ADONAN GORENG MEKAR",
    "NAMA RESTO": "B.1001.MLGPAR",
    "SATUAN": "GR",
    # Hari 1..31 (contoh: day 5 = 50, day 15 = 100, lainnya 0)
    **{str(i): (50 if i == 5 else (100 if i == 15 else 0)) for i in range(1, 32)},
    # Output turunan (kosong)
    "Status2": "", "KETERANGAN GABUNGAN": "", "KONTRIBUSI TERBESAR": "",
    "SOURCE DATA GABUNGAN": "", "Count Hari": "", "RANGKING WASTE": "", "Rill % to BOM": "",
}


# ============================================================
# STYLE
# ============================================================

HEADER_FILL = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
HEADER_FONT = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
INPUT_FILL = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")  # green-100
INPUT_FONT = Font(name="Segoe UI", size=10, color="166534")  # green-800
OUTPUT_FILL = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")  # slate-100
OUTPUT_FONT = Font(name="Segoe UI", size=10, color="475569", italic=True)  # slate-600
THIN_BORDER = Border(
    left=Side(style="thin", color="E2E8F0"),
    right=Side(style="thin", color="E2E8F0"),
    top=Side(style="thin", color="E2E8F0"),
    bottom=Side(style="thin", color="E2E8F0"),
)

# Kolom yang USER WAJIB ISI (highlight green)
INPUT_COLS = {"SOURCE DATA", "JENIS", "KETERANGAN", "NAMA BARANG", "NAMA RESTO", "SATUAN"} | {str(i) for i in range(1, 32)}


# ============================================================
# BUILDER
# ============================================================

def build_template():
    wb = Workbook()
    wb.remove(wb.active)

    # --- Sheet 1: REKAP_MENTAH ---
    ws1 = wb.create_sheet("REKAP_MENTAH")
    # Header row
    for c_idx, header in enumerate(REKAP_HEADERS, start=1):
        cell = ws1.cell(row=1, column=c_idx, value=header)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = THIN_BORDER
    # Sample data row (row 2)
    for c_idx, header in enumerate(REKAP_HEADERS, start=1):
        val = REKAP_SAMPLE_ROW.get(header, "")
        cell = ws1.cell(row=2, column=c_idx, value=val if val != "" else None)
        # Color: green for input cols, slate for output cols
        if header in INPUT_COLS:
            cell.fill = INPUT_FILL
            cell.font = INPUT_FONT
        else:
            cell.fill = OUTPUT_FILL
            cell.font = OUTPUT_FONT
        cell.border = THIN_BORDER
    # Row 3+ kosong dengan border + color hint
    for r in range(3, 12):  # 10 empty rows with hints
        for c_idx, header in enumerate(REKAP_HEADERS, start=1):
            cell = ws1.cell(row=r, column=c_idx)
            if header in INPUT_COLS:
                cell.fill = INPUT_FILL
                cell.font = INPUT_FONT
            else:
                cell.fill = OUTPUT_FILL
                cell.font = OUTPUT_FONT
            cell.border = THIN_BORDER
    # Column widths
    for c_idx, header in enumerate(REKAP_HEADERS, start=1):
        if header in {"1", "2", "3", "4", "5", "6", "7", "8", "9", "10",
                       "11", "12", "13", "14", "15", "16", "17", "18", "19", "20",
                       "21", "22", "23", "24", "25", "26", "27", "28", "29", "30", "31"}:
            ws1.column_dimensions[get_column_letter(c_idx)].width = 6
        elif header in {"SOURCE DATA", "KETERANGAN GABUNGAN", "SOURCE DATA GABUNGAN", "KONTRIBUSI TERBESAR"}:
            ws1.column_dimensions[get_column_letter(c_idx)].width = 25
        else:
            ws1.column_dimensions[get_column_letter(c_idx)].width = 14
    ws1.row_dimensions[1].height = 32
    ws1.freeze_panes = "A2"
    # Auto filter
    last_col = get_column_letter(len(REKAP_HEADERS))
    ws1.auto_filter.ref = f"A1:{last_col}11"

    # --- Sheet 2: BOM ---
    ws2 = wb.create_sheet("BOM")
    for c_idx, header in enumerate(BOM_HEADERS, start=1):
        cell = ws2.cell(row=1, column=c_idx, value=header)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = THIN_BORDER
    # Sample row
    ws2.cell(row=2, column=1, value="B.1001.MLGPAR").fill = INPUT_FILL
    ws2.cell(row=2, column=1).font = INPUT_FONT
    ws2.cell(row=2, column=2, value="ADONAN GORENG MEKAR").fill = INPUT_FILL
    ws2.cell(row=2, column=2).font = INPUT_FONT
    ws2.cell(row=2, column=3, value=867332).fill = INPUT_FILL
    ws2.cell(row=2, column=3).font = INPUT_FONT
    for c_idx in range(1, 4):
        for r in range(3, 8):
            cell = ws2.cell(row=r, column=c_idx)
            cell.fill = INPUT_FILL
            cell.font = INPUT_FONT
            cell.border = THIN_BORDER
    ws2.column_dimensions["A"].width = 18
    ws2.column_dimensions["B"].width = 28
    ws2.column_dimensions["C"].width = 14
    ws2.row_dimensions[1].height = 28
    ws2.freeze_panes = "A2"

    # --- Sheet 3: DATABASE_SATUAN ---
    ws3 = wb.create_sheet("DATABASE_SATUAN")
    for c_idx, header in enumerate(SATUAN_HEADERS, start=1):
        cell = ws3.cell(row=1, column=c_idx, value=header)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = THIN_BORDER
    # Sample row (1 item, semua kategori = 1 = "Sesuai" jika MAX >= 0)
    for c_idx, header in enumerate(SATUAN_HEADERS, start=1):
        cell = ws3.cell(row=2, column=c_idx)
        if header == "NAMA ITEM":
            cell.value = "ADONAN GORENG MEKAR"
        else:
            cell.value = 1
        cell.fill = INPUT_FILL
        cell.font = INPUT_FONT
        cell.border = THIN_BORDER
    for c_idx, header in enumerate(SATUAN_HEADERS, start=1):
        for r in range(3, 8):
            cell = ws3.cell(row=r, column=c_idx)
            cell.fill = INPUT_FILL
            cell.font = INPUT_FONT
            cell.border = THIN_BORDER
    ws3.column_dimensions["A"].width = 28
    for c_idx in range(2, len(SATUAN_HEADERS) + 1):
        ws3.column_dimensions[get_column_letter(c_idx)].width = 12
    ws3.row_dimensions[1].height = 32
    ws3.freeze_panes = "B2"

    # --- Sheet 4: PETUNJUK ---
    ws4 = wb.create_sheet("PETUNJUK", 0)  # tab pertama
    instructions = [
        ("TEMPLATE WASTE ANOMALY DETECTION", True, 14),
        ("", False, 10),
        ("Cara pakai template ini:", True, 11),
        ("", False, 10),
        ("1. Sheet 'REKAP_MENTAH' — WAJIB ISI", True, 11),
        ("   • Isi kolom hijau (input): SOURCE DATA, JENIS, KETERANGAN, NAMA BARANG, NAMA RESTO, SATUAN", False, 10),
        ("   • Isi kolom hari 1..31 dengan qty waste harian (0 kalau tidak ada waste)", False, 10),
        ("   • Kolom abu-abu (output) BIARKAN KOSONG — pipeline akan hitung otomatis", False, 10),
        ("   • JENIS wajib: WASTE, SUSUT, atau TRIAL (baris lain akan di-drop)", False, 10),
        ("", False, 10),
        ("2. Sheet 'BOM' — OPSIONAL", True, 11),
        ("   • Isi kalau mau aktifkan sinyal BOM (S6, S7) dan Rill % to BOM", False, 10),
        ("   • Format: Nomor # = kode cabang (mis. B.1001.MLGPAR), Nama Barang, TOTAL BOM (qty)", False, 10),
        ("   • Nomor # harus sama dengan NAMA RESTO di sheet REKAP_MENTAH", False, 10),
        ("", False, 10),
        ("3. Sheet 'DATABASE_SATUAN' — OPSIONAL", True, 11),
        ("   • Isi kalau mau aktifkan STATUS (Sesuai/Tidak Sesuai) dan HELPER", False, 10),
        ("   • Format: NAMA ITEM + 11 kolom kategori (CANCEL NOTA, SUSUT, TRIAL, dll)", False, 10),
        ("   • Nilai 1 = Sesuai (MAX >= 0), nilai 0 = Sesuai (MAX = 0)", False, 10),
        ("   • NAMA ITEM harus sama dengan NAMA BARANG di sheet REKAP_MENTAH", False, 10),
        ("", False, 10),
        ("4. Save file & jalankan MULAI.bat", True, 11),
        ("   • Browse file Excel ini", False, 10),
        ("   • Isi Key Akhir (1-31) = cutoff hari terakhir analisa", False, 10),
        ("   • Klik 'Mulai Pipeline'", False, 10),
        ("", False, 10),
        ("Warna kolom:", True, 11),
        ("   • Hijau (DCFCE7) = USER WAJIB ISI", False, 10),
        ("   • Abu-abu (F1F5F9) = OUTPUT (kosongkan, pipeline akan hitung)", False, 10),
    ]
    for row_idx, (text, bold, size) in enumerate(instructions, start=1):
        cell = ws4.cell(row=row_idx, column=1, value=text)
        cell.font = Font(name="Segoe UI", size=size, bold=bold,
                         color="0F172A" if bold else "475569")
        cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
    ws4.column_dimensions["A"].width = 100
    # Make sheet PETUNJUK active
    wb.active = wb.sheetnames.index("PETUNJUK")

    # Save
    OUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT)
    print(f"Template dibuat: {OUT}")
    print(f"  Sheets: {wb.sheetnames}")
    print(f"  REKAP_MENTAH: {len(REKAP_HEADERS)} cols (sample row + 10 empty rows)")
    print(f"  BOM: {len(BOM_HEADERS)} cols (sample row + 5 empty rows)")
    print(f"  DATABASE_SATUAN: {len(SATUAN_HEADERS)} cols (sample row + 5 empty rows)")
    print(f"  PETUNJUK: instruksi cara pakai")


if __name__ == "__main__":
    build_template()
