"""shared.py — konstanta + helper murni lintas UI (kontrak publik TIDAK berubah).

v2.6.0 (rebuild PySide6): UI lama (14 mixin Tkinter) diganti total. Kontrak
publik yang DIJAGA supaya test lama tetap hijau (tanpa perubahan):
- ``APP_DIR`` / ``app_dir()`` / ``bundle_res_dir()`` (tests/test_frozen_paths.py)
- ``_apply_filters`` / ``fmt_id`` (tests/test_filter_semantics.py)

Fungsi filter murni dipindah VERBATIM dari ui/shared.py v2.5.1 (semantik
DD-M1/DD-L4/DQ-M1/IN-L1 terkunci test).
"""
from __future__ import annotations

import logging
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


APP_VERSION = "2.6.1"
APP_TITLE = "Waste Anomaly Detection"

# Logger UI bersama — exception senyap tercatat ke logs/waste_anomaly.log.
_LOGGER = logging.getLogger("waste_anomaly.ui")


# ============================================================
# FORMAT ANGKA (v2.5.1, IN-L1 — satu konvensi Indonesia app-wide)
# ============================================================

def fmt_id(value: float, decimals: int = 0) -> str:
    """Format angka gaya Indonesia: ribuan '.', desimal ','.

    Contoh: fmt_id(9333117.5, 1) → '9.333.117,5'; fmt_id(25901) → '25.901'.
    """
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

def _apply_filters(df: pd.DataFrame, filters: dict | None,
                   day_min: int | None = None, day_max: int | None = None,
                   search: str = "") -> pd.DataFrame:
    """Filter df murni (tanpa side-effect, tanpa render).

    filters: dict key → nilai; None / list kosong di-skip.
      cabang→NAMA RESTO, item→NAMA BARANG, jenis→JENIS (list → isin),
      keterangan→KETERANGAN, status→ANOMALY STATUS.
    day_min/day_max: rentang HARI MAX (inklusif). v2.5.1 (DD-M1): baris
      HARI MAX null (≈ semua baris Kosong TOTAL=0) TIDAK lagi lolos.
    search: substring case-insensitive di kolom (mask OR, vectorized);
      v2.5.1 (DD-L4): sel NaN dikecualikan.
    v2.5.1 (DQ-M1): keterangan dibandingkan dengan normalisasi whitespace.
    """
    filtered = df.copy()
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

    # Rentang hari (HARI MAX in [day_min, day_max]) — ketat (DD-M1).
    if (day_min is not None and day_max is not None
            and "HARI MAX" in filtered.columns):
        hari_max = pd.to_numeric(filtered["HARI MAX"], errors="coerce")
        filtered = filtered[
            hari_max.between(day_min, day_max, inclusive="both")
            & hari_max.notna()
        ]

    # Search — vectorized per-column OR mask; notna() gate (DD-L4).
    search = (search or "").strip().lower()
    if search:
        mask = pd.Series(False, index=filtered.index)
        for col in filtered.columns:
            sub = filtered[col]
            if not sub.notna().any():
                continue
            mask |= sub.notna() & sub.astype(str).str.lower().str.contains(
                search, regex=False, na=False
            )
        filtered = filtered[mask]
    return filtered
