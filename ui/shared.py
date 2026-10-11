"""shared.py — konstanta + helper murni lintas UI (kontrak publik TIDAK berubah).

v2.6.0 (rebuild PySide6): UI lama (14 mixin Tkinter) diganti total. Kontrak
publik yang DIJAGA supaya test lama tetap hijau (tanpa perubahan):
- ``APP_DIR`` / ``app_dir()`` / ``bundle_res_dir()`` (tests/test_frozen_paths.py)
- ``_apply_filters`` / ``fmt_id`` (tests/test_filter_semantics.py)

Fungsi filter murni dipindah VERBATIM dari ui/shared.py v2.5.1 (semantik
DD-M1/DD-L4/DQ-M1/IN-L1 terkunci test).

v2.13.8 (gel-C deep audit): _build_search_blob + parameter
search/day_min/day_max/search_blob _apply_filters DIHAPUS — fitur kotak
cari & rentang hari dihapus dari UI sejak v2.12.4 (sidebar), blob worker
dihapus v2.13.7; cabang-cabang itu mati di produksi (audit D11). Yang
tersisa = semantik funnel yang HIDUP: cabang/item/jenis/keterangan/status.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from waste_anomaly.frozen import bundle_dir as _bundle_dir
from waste_anomaly.frozen import exe_dir as _exe_dir
from waste_anomaly.utils import norm_text as _norm_text

# ============================================================
# APP META — dev: repo root (parent paket ui/). Frozen exe: folder EXE
# (v2.4.1 — dipakai untuk folder data/ writable & fallback ikon).
# BUNDLE_DIR = resource read-only PyInstaller (_MEIPASS; dev = repo root).
# ============================================================
APP_DIR = _exe_dir()
BUNDLE_DIR = _bundle_dir()


def app_dir() -> Path:
    """APP_DIR dinamis (diuji unit tests/test_frozen_paths.py)."""
    return _exe_dir()


def bundle_res_dir() -> Path:
    """BUNDLE_DIR dinamis — resource bundled (ikon, config default)."""
    return _bundle_dir()


APP_VERSION = "2.13.14"
APP_TITLE = "Waste Anomaly Detection"


# ============================================================
# FORMAT ANGKA (v2.5.1, IN-L1 — satu konvensi Indonesia app-wide)
# ============================================================

def fmt_id(value: float, decimals: int = 0) -> str:
    """Format angka gaya Indonesia: ribuan '.', desimal ','.

    Contoh: fmt_id(9333117.5, 1) → '9.333.117,5'; fmt_id(25901) → '25.901'.
    v2.7.0 (V26-L2): None → '' (dulu teks 'None' bocor ke label KPI/panel
    saat nilai kosong lolos ke pemanggil langsung; NaN sudah '' sejak lama).
    """
    if value is None:
        return ""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    if f != f:  # NaN
        return ""
    s = f"{f:,.{decimals}f}"  # EN sementara: '9,333,117.5'
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


# ============================================================
# v2.13.14 (gel-5 C15) — LABEL SUMBER PEMBANDING "BULAN LALU"
# ============================================================
# Audit C15: kolom "BULAN LALU" berarti SUMBER BERBEDA antar tab (Anomali
# = bulan pilihan combo Banding Periode; Hari = bulan pembanding TERBARU
# yang termuat) tanpa label bulan — dua angka "bulan lalu" yang tak
# bisa dibandingkan antar tab. Helper satu sumber utk label dinamis.


def baseline_label(b) -> str | None:
    """Label tampilan pembanding utk judul/tooltip kolom (gel-5 C15).

    - dict Tipikal (months_count) → 'Tipikal (median N bulan)';
    - dict bulan file → label tampilannya (disp/label);
    - None/bentuk tak dikenal → None (pemanggil memakai label statis).
    """
    if not isinstance(b, dict):
        return None
    n = b.get("months_count")
    if n:
        return f"Tipikal (median {int(n)} bulan)"
    lbl = str(b.get("disp") or b.get("label") or "").strip()
    return lbl or None


# ============================================================
# v2.13.13 (gel-4 D7) — PESAN ERROR FILE RAMAH (BATAS UI)
# ============================================================
# Audit D7: error file korup dulunya tampil sebagai modal EN mentah
# ("File is not a zip file") tanpa saran — kontras jalur validasi skema
# yang ramah+saran. Worker/engine TETAP melempar error mentah (log &
# traceback jujur; pola _log_id gel-3: penerjemahan dilakukan DI BATAS
# UI saat pesan sampai ke dialog user — view_pipeline/view_periode).
# Pola tak dikenal → teks asli APA ADANYA (jujur, bukan tebakan).
_FILE_ERR_PATTERNS: list[tuple[str, str, str]] = [
    ("file is not a zip file",
     "File bukan workbook Excel (.xlsx) yang valid — isinya bukan arsip"
     " XLSX (file rusak/terpotong saat di-copy, atau format lain yang "
     "dinamai .xlsx).",
     "buka file di Excel lalu simpan ulang sebagai Excel Workbook "
     "(.xlsx), baru jalankan lagi"),
    ("no such file or directory",
     "File tidak ditemukan — sudah dipindah, diganti nama, atau dihapus.",
     "pilih ulang file lewat tombol Telusuri… di tab Pipeline"),
    ("permission denied",
     "File tidak bisa dibaca — sedang dipakai (dikunci) program lain, "
     "biasanya masih terbuka di Excel.",
     "tutup file-nya di Excel dulu, lalu coba lagi"),
    ("excel file format cannot be determined",
     "Isi file tidak dikenali sebagai Excel — file kosong atau bukan "
     "spreadsheet.",
     "periksa file terbuka benar di Excel dan berisi data rekap"),
    ("does not support the old .xls",
     "Format .xls lama (Excel 97-2003) tidak didukung pembaca Excel "
     "modern.",
     "buka di Excel lalu simpan sebagai .xlsx, baru jalankan lagi"),
]


def friendly_file_error(err: str) -> str:
    """v2.13.13 (gel-4 D7) — terjemahkan pesan error file EN mentah
    (openpyxl/pandas/Python) ke Bahasa Indonesia + SARAN, dipakai di
    BATAS UI (dialog modal view_pipeline / view_periode).

    5 pola dikenal (fragment lowercase — substring match); pola tak
    dikenal → teks asli apa adanya (bukan tebakan). Teks asli tetap
    dilampirkan di ekor supaya bisa dicocokkan dgn log/traceback yang
    menulis versi mentah (kontrak: worker TIDAK diubah)."""
    s = str(err or "")
    low = s.lower()
    for frag, indo, saran in _FILE_ERR_PATTERNS:
        if frag in low:
            return f"{indo}\n\nSaran: {saran}.\n\n(Teks asli: {s})"
    return s


# ============================================================
# PURE FILTER HELPER (M23 → v2.5.1 semantics, VERBATIM dari ui lama)
# ============================================================

def _apply_filters(df: pd.DataFrame, filters: dict | None) -> pd.DataFrame:
    """Filter df murni (tanpa side-effect, tanpa render).

    filters: dict key → nilai; None / list kosong di-skip.
      cabang→NAMA RESTO, item→NAMA BARANG, jenis→JENIS (list → isin),
      keterangan→KETERANGAN, status→ANOMALY STATUS.
    v2.5.1 (DQ-M1): keterangan dibandingkan dengan normalisasi whitespace.
    v2.12.1 (perf): TANPA salinan awal df. Dulu `filtered = df.copy()`
      dijalankan SEBELUM mask apa pun (25.901×53 = ~21 ms sia-sia di SETIAP
      ganti filter, termasuk saat kembali ke state TANPA filter — jalur
      'bersihkan/hapus filter' di laptop user ±2× lebih lambat). Kini:
      mask bekerja langsung di df (tiap mask memang menghasilkan frame
      baru) dan state kosong mengembalikan df ASLI (kontrak lama tetap:
      pemanggil hanya MEMBACA hasil — mask/slice kolom tetap objek baru).
    """
    # v2.12.1: fast path — tak ada kerja: kembalikan df apa adanya
    # (konsumen hanya membaca; anomali_df/KPI/display semuanya read-only
    # atau bekerja di salinannya sendiri).
    filters_active = any(
        v is not None and not (isinstance(v, list) and not v)
        for v in (filters or {}).values())
    if not filters_active:
        return df

    filtered = df
    col_map = {
        "cabang": "NAMA RESTO", "item": "NAMA BARANG", "jenis": "JENIS",
        "keterangan": "KETERANGAN", "status": "ANOMALY STATUS",
    }

    for key, val in (filters or {}).items():
        if val is None or (isinstance(val, list) and not val):
            continue
        col = col_map.get(key)
        if not col or col not in filtered.columns:
            continue
        if isinstance(val, list):
            if key == "keterangan":
                wanted = {_norm_text(v) for v in val}
                filtered = filtered[
                    filtered[col].astype(str).map(_norm_text).isin(wanted)
                ]
            else:
                filtered = filtered[filtered[col].isin(val)]
        elif key == "keterangan":
            target = _norm_text(val)
            filtered = filtered[
                filtered[col].astype(str).map(_norm_text) == target
            ]
        else:
            filtered = filtered[filtered[col] == val]
    return filtered
