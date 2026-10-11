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


APP_VERSION = "2.13.12"
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
