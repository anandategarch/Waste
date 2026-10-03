"""shared.py — konstanta, font registry, dan helper murni untuk paket ui/.

Pusat nama bersama yang dipakai semua modul mixin (base + 10 tab) dan
widget. Sebelumnya semua ini hidup di ui_app.py 3.2k baris (god-object);
sejak v2.4.0 kode UI dipecah dan file ini menjadi satu sumber kebenaran.

FONT REGISTRY (penting): F_* / FONT_NAME / MONO_NAME punya nilai default
di sini, lalu di-REBIND saat startup oleh AppBase._init_fonts() lewat
rebind_fonts(). Karena modul mixin meng-import nama-nama itu secara
statis (import-time binding), rebind memakai registry: setiap modul
mixin mendaftarkan diri via register_font_consumer() (lihat baris akhir
tiap file mixin) dan rebind_fonts() men-setattr ke semua modul terdaftar.
Perilaku akhir identik dengan pola `global` lama — hanya sekarang aman
lintas banyak file.
"""

from __future__ import annotations

import logging
import tkinter.font as tkfont
from pathlib import Path
from types import ModuleType

import pandas as pd

# ============================================================
# APP META — APP_DIR menunjuk REPO ROOT (parent dari paket ui/),
# bukan folder ui/ — dipakai untuk lokasi folder data/.
# ============================================================
APP_DIR = Path(__file__).resolve().parent.parent
APP_VERSION = "2.4.0"
APP_TITLE = "Waste Anomaly Detection — Pro Dashboard"

# F11 (v2.4.0): logger UI bersama — exception senyap kini tercatat ke file.
_LOGGER = logging.getLogger("waste_anomaly.ui")


# ============================================================
# FONT FALLBACK (M17)
# ============================================================

def _pick_font(candidates: list[str], default: str) -> str:
    """M17: kandidat font pertama yang tersedia di sistem; fallback default.

    Dipanggil sekali saat startup (root Tk sudah ada) — keluarga font di-probe
    via tkfont.families(). Font hardcoded (Segoe UI/Consolas) tidak ada di
    Linux/macOS → Tk fallback ke font sistem yang jelek; di sini kita pilih
    eksplisit: Segoe UI → Tahoma → DejaVu Sans → Helvetica.
    """
    try:
        families = set(tkfont.families())
        for name in candidates:
            if name in families:
                return name
    except Exception:
        _LOGGER.debug("Suppressed: probe gagal (headless) — pakai default", exc_info=True)
    return default


# ============================================================
# STYLE — nilai default; F_* di-rebind _init_fonts() via registry
# ============================================================
FONT_NAME = "Segoe UI"
MONO_NAME = "Consolas"
F_APP_TITLE = (FONT_NAME, 14, "bold")
F_CARD = (FONT_NAME, 10, "bold")
F_BODY = (FONT_NAME, 9)
F_HINT = (FONT_NAME, 8)
F_LOG = (MONO_NAME, 9)
F_KPI_NUM = (FONT_NAME, 18, "bold")
F_KPI_LABEL = (FONT_NAME, 8)

C_BG = "#f1f5f9"            # slate-100
C_CARD = "#ffffff"           # white
C_HEADER = "#0f172a"        # slate-900
C_FOOTER = "#e2e8f0"        # slate-200
C_TERM_BG = "#0b1220"
C_BORDER = "#e2e8f0"
C_TITLE_BG = "#f8fafc"      # slate-50 — bg title-bar kartu chart

# M18: grays ter-unify — JANGAN pakai literal #6B7280/#64748b/#1F2937/#475569
# lagi; cukup dua konstanta ini untuk semua teks sekunder/utama.
C_TEXT_MUTED = "#64748b"    # slate-500 — hint, label sekunder, status netral
C_TEXT_MAIN = "#1f2937"     # gray-800 — teks utama

# Status colors (match charts.py)
C_STATUS = {
    "Prioritas Tinggi": ("#dc2626", "#fef2f2"),  # (fg, bg-light)
    "Potensi Anomali":  ("#ea580c", "#fff7ed"),
    "Perlu Review":     ("#b45309", "#fffbeb"),
    "Normal":           ("#16a34a", "#f0fdf4"),
}


# ============================================================
# FONT REGISTRY (v2.4.0)
# ============================================================

_FONT_CONSUMERS: list[ModuleType] = []


def register_font_consumer(mod: ModuleType) -> None:
    """Modul mixin memanggil ini di akhir filenya (idempotent)."""
    if mod not in _FONT_CONSUMERS:
        _FONT_CONSUMERS.append(mod)


def rebind_fonts(**fonts) -> None:
    """Rebind nama font di shared DAN di semua modul konsumen terdaftar.

    Dipanggil AppBase._init_fonts() setelah probe font sistem — pengganti
    pola `global` lama (yang hanya berlaku saat semua kode di satu file).
    """
    g = globals()
    for name, value in fonts.items():
        g[name] = value
    for mod in _FONT_CONSUMERS:
        for name, value in fonts.items():
            setattr(mod, name, value)


# ============================================================
# PURE FILTER HELPER (M23 — satu implementasi, dipakai Dashboard & CSV export)
# ============================================================

def _apply_filters(df: pd.DataFrame, filters: dict | None,
                   day_min: int | None = None, day_max: int | None = None,
                   search: str = "") -> pd.DataFrame:
    """M23: filter df murni (tanpa side-effect, tanpa render).

    filters: dict key → nilai; None / list kosong di-skip.
      cabang→NAMA RESTO, item→NAMA BARANG, jenis→JENIS (list → isin),
      keterangan→KETERANGAN, status→ANOMALY STATUS.
    day_min/day_max: rentang HARI MAX (inklusif; baris HARI MAX null tetap
    lolos — konsisten perilaku lama).
    search: substring case-insensitive di SEMUA kolom (mask OR, vectorized).
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
            filtered = filtered[filtered[col].isin(val)]
        else:
            filtered = filtered[filtered[col] == val]

    # Rentang hari (HARI MAX in [day_min, day_max])
    if (day_min is not None and day_max is not None
            and "HARI MAX" in filtered.columns):
        hari_max = pd.to_numeric(filtered["HARI MAX"], errors="coerce")
        filtered = filtered[
            hari_max.between(day_min, day_max, inclusive="both")
            | hari_max.isna()  # baris HARI MAX null tetap lolos
        ]

    # Search — vectorized per-column OR mask (H1)
    search = (search or "").strip().lower()
    if search:
        mask = pd.Series(False, index=filtered.index)
        for col in filtered.columns:
            mask |= filtered[col].astype(str).str.lower().str.contains(
                search, regex=False, na=False
            )
        filtered = filtered[mask]
    return filtered


# M6: key filter mentah → label Indonesia untuk chip (dulu chip menampilkan
# "cabang: X" / "search: ..." mentah).
CHIP_LABELS = {
    "cabang": "Cabang", "status": "Status", "item": "Item", "search": "Cari",
    "jenis": "Jenis", "keterangan": "Keterangan", "hari": "Rentang Hari",
    "top": "Top",
}
