"""
utils.py — helper utilities untuk Waste Anomaly.

Berisi fungsi-fungsi kecil yang dipakai berulang di stages/signals/exporter.
Di-implementasikan setara dengan semantik Power Query M.
"""

from __future__ import annotations

import json
import math
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


# ============================================================
# KONFIGURASI
# ============================================================

CONFIG_PATH = Path(__file__).resolve().parent / "config.json"


def load_config(config_path: str | os.PathLike | None = None) -> dict:
    """Muat config.json. Bila path tidak diberikan, pakai default di package."""
    p = Path(config_path) if config_path else CONFIG_PATH
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        # Fallback ke default minimal supaya pipeline tetap jalan
        return {
            "thresholds": {
                "TH_SPIKE": 3, "TH_MAX_AVG_AKTIF": 2.5, "TH_MAX_MEDIAN": 3,
                "TH_MAX_SECOND": 3, "TH_MAX_SHARE_WARN": 0.50,
                "TH_MAX_SHARE_HIGH": 0.70, "TH_MAX_BOM_WARN": 0.25,
                "TH_MAX_BOM_HIGH": 0.50, "TH_TOTAL_BOM_WARN": 0.50,
                "TH_TOTAL_BOM_HIGH": 1.00, "TH_PEER_MIN": 3,
                "TH_PEER_WARN": 2, "TH_PEER_HIGH": 3, "TH_LAST_SHARE": 0.70,
            },
            "non_handling_list": [
                "Alat/ Mesin", "Cancel Nota", "Eksternal", "Internal", "Over Stock",
            ],
            "default_key_akhir": 31,
        }


# ============================================================
# KONVERSI TIPE (setara Table.TransformColumnTypes)
# ============================================================

def to_number(value: Any) -> float | None:
    """Setara Number.From(x). None/NaN/"" -> None. Numeric string di-parse."""
    if value is None:
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None
        return float(value)
    if isinstance(value, str):
        s = value.strip()
        if s == "":
            return None
        # Ganti koma desimal Indonesia jika ada
        s = s.replace(",", ".")
        try:
            return float(s)
        except ValueError:
            try:
                # Format ribuan "1.234,56" sudah ditangani di atas; coba parse pakai locale-agnostic
                cleaned = s.replace(".", "").replace(" ", "")
                return float(cleaned)
            except (ValueError, TypeError):
                return None
    return None


def to_text(value: Any) -> str | None:
    """Setara Text.From(x). None -> None. Untuk angka: string kanonik."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return repr(value)
    if isinstance(value, int):
        return str(value)
    return str(value)


# ============================================================
# STATISTIK HARIAN (setara List.Sum / List.Max / List.Median)
# ============================================================

def safe_sum(values: Iterable[float | None]) -> float:
    """Setara List.Sum: skip None, return 0 kalau kosong."""
    nums = [v for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))]
    return float(sum(nums)) if nums else 0.0


def safe_max(values: Iterable[float | None]) -> float | None:
    """Setara List.Max: skip None. Return None kalau kosong (di M error, di sini aman)."""
    nums = [v for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))]
    return max(nums) if nums else None


def safe_min(values: Iterable[float | None]) -> float | None:
    nums = [v for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))]
    return min(nums) if nums else None


def safe_mean(values: Iterable[float | None]) -> float | None:
    """Setara List.Average: skip None. Return None kalau kosong."""
    nums = [v for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))]
    return float(np.mean(nums)) if nums else None


def safe_median(values: Iterable[float | None]) -> float | None:
    """Setara List.Median: skip None. Return None kalau kosong."""
    nums = [v for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))]
    return float(np.median(nums)) if nums else None


def safe_count(values: Iterable[float | None]) -> int:
    """Hitung jumlah nilai non-null."""
    return sum(1 for v in values if v is not None and not (isinstance(v, float) and math.isnan(v)))


def safe_count_active(values: Iterable[float | None]) -> int:
    """Hitung jumlah hari aktif (non-null & > 0). Setara CountHari di M code."""
    return sum(
        1 for v in values
        if v is not None
        and not (isinstance(v, float) and math.isnan(v))
        and v > 0
    )


def safe_div(numerator: float | None, denominator: float | None) -> float:
    """Pembagian aman. None/0 -> 0 (setara pola if x>0 then ... else 0 di M code)."""
    if numerator is None or denominator is None:
        return 0.0
    if denominator == 0:
        return 0.0
    return float(numerator) / float(denominator)


# ============================================================
# NAMA HARI / POSISI
# ============================================================

def position_of(values: list[float | None], target: float) -> int | None:
    """Setara List.PositionOf(HariList, MaxValue) + 1 (1-based)."""
    if target is None:
        return None
    for i, v in enumerate(values):
        if v is not None and not (isinstance(v, float) and math.isnan(v)) and v == target:
            return i + 1
    return None


def second_max(values: list[float | None]) -> float | None:
    """Setara SortedAktif{1}. 2nd largest setelah disortir desc."""
    nums = sorted(
        [v for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))],
        reverse=True,
    )
    return nums[1] if len(nums) >= 2 else None


# ============================================================
# LOG / TIDAK BERISIK
# ============================================================

def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def round_safe(value: Any, digits: int = 2) -> float | None:
    """Pembulatan yang aman terhadap None/NaN."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    return round(float(value), digits)


def pct(value: float | None, digits: int = 0) -> str | None:
    """Format sebagai persen. None -> None."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    return f"{round(value * 100, digits)}%"


def clamp(value: int, lo: int, hi: int) -> int:
    """Setara logika JumlahKolom di M code (clamp 1..31)."""
    return max(lo, min(hi, value))


def day_columns(key_akhir: int) -> list[str]:
    """Daftar nama kolom hari aktif: ["1", "2", ..., str(key_akhir)] (clamped 1..31)."""
    n = clamp(int(key_akhir) if key_akhir else 31, 1, 31)
    return [str(i) for i in range(1, n + 1)]


def coerce_day_columns_numeric(df: pd.DataFrame, day_cols: list[str]) -> pd.DataFrame:
    """Paksa semua kolom hari jadi numeric (setara Table.TransformColumnTypes untuk "1".."31")."""
    out = df.copy()
    for c in day_cols:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")
    return out


def fillna_numeric(series: pd.Series, fill: float = 0.0) -> pd.Series:
    """NaN -> 0 untuk numeric series."""
    return series.fillna(fill)
