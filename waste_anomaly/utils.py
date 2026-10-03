"""
utils.py — helper utilities untuk Waste Anomaly.

Berisi fungsi-fungsi kecil yang dipakai berulang di stages/signals/exporter.
Di-implementasikan setara dengan semantik Power Query M.

Fix log (v2.3.1):
  - L  : to_number sekarang menangani format "1.234,56" (Indonesia) DAN
         "1,234.56" (US) — dulu "1.234,56" salah jadi 123456.0.
  - L  : day_columns(0) kini return [] (dulu 0 diperlakukan falsy → 31 kolom).
  - H5 : load_config gagal baca → warnings.warn + default + key
         "_config_load_error" (dulu diam-diam pakai default).

Catatan dead code (audit L): fungsi berikut TIDAK dipanggil siapa pun di repo
ini (stages/signals/pipeline/loader/exporter/filters/ui_app) per grep terakhir,
TAPI sengaja DIPERTAHANKAN karena modul lain / import eksternal mungkin
memakai nama-nama ini (risiko merusak edit paralel agent lain):
  to_number, safe_sum, safe_min, now_iso, round_safe, pct,
  coerce_day_columns_numeric, fillna_numeric.
Yang aktif dipakai: load_config, CONFIG_PATH, to_text, safe_max, safe_mean,
safe_median, safe_count, safe_count_active, safe_div, position_of,
second_max, clamp, day_columns.
"""

from __future__ import annotations

import json
import math
import os
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


# ============================================================
# KONFIGURASI
# ============================================================

CONFIG_PATH = Path(__file__).resolve().parent / "config.json"

# Default config minimal — dipakai baca config gagal (lihat load_config).
_DEFAULT_CONFIG = {
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


def load_config(config_path: str | os.PathLike | None = None) -> dict:
    """Muat config.json. Bila path tidak diberikan, pakai default di package.

    Perbaikan audit H5: kegagalan baca (file corrupt / JSON invalid / IO error)
    tidak lagi ditelan diam-diam:
      1. Emit warnings.warn("Config load gagal: ...") supaya kelihatan di
         console/log (default filter Python: sekali per lokasi).
      2. Return dict default + key "_config_load_error" berisi pesan error —
         pipeline/UI bisa memunculkannya ke user (aman diabaikan kalau tidak
         dipakai; tidak ada consumer yang iterasi seluruh key config).
    TIDAK raise — pipeline tetap jalan dengan default (perilaku lama).
    """
    p = Path(config_path) if config_path else CONFIG_PATH
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:  # JSONDecodeError / OSError / UnicodeDecodeError dll.
        warnings.warn(f"Config load gagal: {p}: {e} — pakai default")
        cfg = {k: (v.copy() if isinstance(v, (dict, list)) else v)
               for k, v in _DEFAULT_CONFIG.items()}
        cfg["_config_load_error"] = str(e)
        return cfg


# ============================================================
# KONVERSI TIPE (setara Table.TransformColumnTypes)
# ============================================================

def to_number(value: Any) -> float | None:
    """Setara Number.From(x). None/NaN/"" -> None. Numeric string di-parse.

    Heuristik pemisah desimal/ribuan (locale-agnostik — audit L; dulu
    "1.234,56" salah diparse jadi 123456.0):
      1. Kalau "." dan "," sama-sama ada: pemisah yang POSISINYA TERAKHIR
         adalah desimal, pemisah lain = ribuan.
           "1.234,56" → 1234.56   "1,234.56" → 1234.56   "1.234.567,8" → 1234567.8
      2. Kalau hanya satu jenis pemisah:
         - muncul LEBIH DARI SEKALI → ribuan: "1.234.567" → 1234567.0
         - muncul sekali, diikuti tepat 2 digit di akhir → desimal:
           "1,25" → 1.25, "12.34" → 12.34
         - muncul sekali, diikuti tepat 3 digit di akhir → ambigu; diputuskan
           sebagai RIBUAN (konteks Indonesia): "1.234" → 1234.0, "1,234" → 1234.0
         - selain itu (mis. "0,5", "1,2345") → desimal: "0,5" → 0.5
    Tanda negatif di depan tetap dihormati ("-1.234,56" → -1234.56).
    String yang tetap tak bisa diparse → None (tidak raise).
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None
        return float(value)
    if isinstance(value, str):
        s = value.strip().replace(" ", "").replace("\xa0", "")
        if s == "":
            return None
        # Pisahkan tanda di depan supaya heuristik pemisah konsisten ("-1.234").
        sign = ""
        if s and s[0] in "+-":
            sign, s = ("-" if s[0] == "-" else ""), s[1:]
        has_dot = "." in s
        has_comma = "," in s
        if has_dot and has_comma:
            # Kedua pemisah ada: yang POSISINYA TERAKHIR adalah desimal,
            # pemisah lain = ribuan.
            if s.rfind(",") > s.rfind("."):
                s = s.replace(".", "").replace(",", ".")
            else:
                s = s.replace(",", "")
        elif has_dot or has_comma:
            sep = "." if has_dot else ","
            parts = s.split(sep)
            tail = parts[-1]
            if len(parts) > 2:
                # >1 kemunculan → pemisah ribuan ("1.234.567" / "1,234,567")
                s = s.replace(sep, "")
            elif len(tail) == 2 and tail.isdigit():
                # sekali + tepat 2 digit di akhir → desimal ("1,25" / "12.34")
                if sep == ",":
                    s = s.replace(",", ".")
            elif len(tail) == 3 and tail.isdigit():
                # sekali + tepat 3 digit di akhir → ambigu; putuskan RIBUAN
                # (konteks Indonesia: "1.234" / "1,234")
                s = s.replace(sep, "")
            elif sep == ",":
                # selain itu ("0,5", "1,2345") → koma = desimal
                s = s.replace(",", ".")
        try:
            return float(sign + s)
        except ValueError:
            try:
                # Locale-agnostic terakhir: buang semua pemisah
                cleaned = (sign + s).replace(".", "").replace(",", "").replace(" ", "")
                return float(cleaned)
            except (ValueError, TypeError):
                return None
    # Tipe lain (np.int64, Decimal, dst.) — coba float() generik, gagal → None.
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def to_text(value: Any) -> str | None:
    """Setara Text.From(x). None -> None. Untuk angka: string kanonik (1.0 -> "1")."""
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
    """Setara List.Sum: skip None/NaN, return 0.0 kalau kosong.

    Contoh: safe_sum([1, None, 2.5]) → 3.5; safe_sum([]) → 0.0.
    """
    nums = [v for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))]
    return float(sum(nums)) if nums else 0.0


def safe_max(values: Iterable[float | None]) -> float | None:
    """Setara List.Max: skip None/NaN. Return None kalau kosong (di M error, di sini aman).

    Contoh: safe_max([1, None, 3]) → 3.0; safe_max([]) → None.
    """
    nums = [v for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))]
    return max(nums) if nums else None


def safe_min(values: Iterable[float | None]) -> float | None:
    """Setara List.Min: skip None/NaN. Return None kalau kosong.

    Contoh: safe_min([1, None, 3]) → 1.0; safe_min([]) → None.
    """
    nums = [v for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))]
    return min(nums) if nums else None


def safe_mean(values: Iterable[float | None]) -> float | None:
    """Setara List.Average: skip None/NaN. Return None kalau kosong.

    Contoh: safe_mean([2, 4]) → 3.0; safe_mean([None]) → None.
    """
    nums = [v for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))]
    return float(np.mean(nums)) if nums else None


def safe_median(values: Iterable[float | None]) -> float | None:
    """Setara List.Median: skip None/NaN. Return None kalau kosong.

    Contoh: safe_median([1, 3, 5]) → 3.0; safe_median([]) → None.
    """
    nums = [v for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))]
    return float(np.median(nums)) if nums else None


def safe_count(values: Iterable[float | None]) -> int:
    """Hitung jumlah nilai non-null/non-NaN.

    Contoh: safe_count([1, None, 2]) → 2; safe_count([]) → 0.
    """
    return sum(1 for v in values if v is not None and not (isinstance(v, float) and math.isnan(v)))


def safe_count_active(values: Iterable[float | None]) -> int:
    """Hitung jumlah hari aktif (non-null & > 0). Setara CountHari di M code.

    Contoh: safe_count_active([0, 2, None, 5]) → 2.
    """
    return sum(
        1 for v in values
        if v is not None
        and not (isinstance(v, float) and math.isnan(v))
        and v > 0
    )


def safe_div(numerator: float | None, denominator: float | None) -> float:
    """Pembagian aman. None/0 -> 0.0 (setara pola if x>0 then ... else 0 di M code).

    Contoh: safe_div(5, 2) → 2.5; safe_div(5, 0) → 0.0; safe_div(None, 2) → 0.0.
    """
    if numerator is None or denominator is None:
        return 0.0
    if denominator == 0:
        return 0.0
    return float(numerator) / float(denominator)


# ============================================================
# NAMA HARI / POSISI
# ============================================================

def position_of(values: list[float | None], target: float) -> int | None:
    """Setara List.PositionOf(HariList, MaxValue) + 1 (1-based).

    Contoh: position_of([None, 5, 7], 7) → 3; tidak ketemu/None → None.
    """
    if target is None:
        return None
    for i, v in enumerate(values):
        if v is not None and not (isinstance(v, float) and math.isnan(v)) and v == target:
            return i + 1
    return None


def second_max(values: list[float | None]) -> float | None:
    """Setara SortedAktif{1}: nilai terbesar KEDUA setelah sort desc.

    Contoh: second_max([5, 7, 3]) → 5.0; second_max([7]) → None.
    """
    nums = sorted(
        [v for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))],
        reverse=True,
    )
    return nums[1] if len(nums) >= 2 else None


# ============================================================
# LOG / TIDAK BERISIK
# ============================================================

def now_iso() -> str:
    """Timestamp lokal 'YYYY-MM-DD HH:MM:SS' (untuk log run)."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def round_safe(value: Any, digits: int = 2) -> float | None:
    """Pembulatan yang aman terhadap None/NaN. None input → None output.

    Contoh: round_safe(1.23456) → 1.23; round_safe(None) → None.
    """
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    return round(float(value), digits)


def pct(value: float | None, digits: int = 0) -> str | None:
    """Format rasio (0..1) sebagai persen string. None/NaN → None.

    Contoh: pct(0.256, 1) → "25.6%"; pct(None) → None.
    """
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    return f"{round(value * 100, digits)}%"


def clamp(value: int, lo: int, hi: int) -> int:
    """Setara logika JumlahKolom di M code (clamp 1..31): batasi value ke [lo, hi].

    Contoh: clamp(35, 1, 31) → 31; clamp(0, 1, 31) → 1.
    """
    return max(lo, min(hi, value))


def day_columns(key_akhir: int | None) -> list[str]:
    """Daftar nama kolom hari aktif: ["1", "2", ..., str(key_akhir)].

    Perbaikan audit L (dulu `if key_akhir else 31` → key_akhir=0 dianggap
    falsy dan salah return 31 kolom):
      - key_akhir None → ["1"]..["31"] (default bulan penuh).
      - key_akhir <= 0 → [] (tidak ada hari aktif; 0 hari = 0 kolom).
      - key_akhir > 31 → tetap di-clamp ke 31 (setara JumlahKolom M code;
        data harian tidak pernah lebih dari 31 kolom).
    Catatan caller: pipeline.py sudah clamp key_akhir ke 1..31 SEBELUM
    memanggil stages, jadi jalur [] hanya tercapai dari pemanggilan langsung.
    """
    if key_akhir is None:
        return [str(d) for d in range(1, 32)]
    n = int(key_akhir)
    if n <= 0:
        return []
    n = min(n, 31)
    return [str(i) for i in range(1, n + 1)]


def coerce_day_columns_numeric(df: pd.DataFrame, day_cols: list[str]) -> pd.DataFrame:
    """Paksa semua kolom hari jadi numeric (setara Table.TransformColumnTypes untuk "1".."31").

    Kolom yang tidak ada di df diabaikan. Return salinan df (input tidak termutasi).

    Contoh: df dengan kolom "1" berisi string "5" → kolom jadi float 5.0.
    """
    out = df.copy()
    for c in day_cols:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")
    return out


def fillna_numeric(series: pd.Series, fill: float = 0.0) -> pd.Series:
    """Isi NaN pada numeric series dengan nilai default (0.0).

    Contoh: fillna_numeric(pd.Series([1.0, np.nan])) → [1.0, 0.0].
    """
    return series.fillna(fill)
