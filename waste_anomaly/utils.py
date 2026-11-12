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

v2.13.8 (gel-C deep audit): 17 fungsi MATI TOTAL dihapus (to_number,
to_text, safe_sum, safe_max, safe_min, safe_mean, safe_median, safe_count,
safe_count_active, safe_div, position_of, second_max, now_iso, round_safe,
pct, coerce_day_columns_numeric, fillna_numeric — nol call-site produksi/
test sejak vektorisasi penuh stage_02 di v2.2.0; semantik M kini hidup di
stages.py). Yang TERSISA dan benar-benar hidup: load_config + CONFIG_PATH
+ _DEFAULT_CONFIG + _seed_sidecar_config/_active_config_path (pipeline/
app/workers/view_pipeline), clamp + day_columns (stages/day_focus),
norm_text (ui/shared, priority, temporal).
"""

from __future__ import annotations

import json
import math
import os
import shutil
import warnings
from pathlib import Path

from .frozen import bundle_dir, exe_dir, is_frozen


# ============================================================
# KONFIGURASI
# ============================================================

# Dev mode: config.json di dalam paket (perilaku lama — tidak berubah).
# Frozen/exe mode: lihat _active_config_path() — sidecar di samping exe
# (v2.4.1: __file__ menunjuk _MEIPASS temp yang dihapus saat exit, jadi
# menyimpan threshold ke sana = hilang senyap).
CONFIG_PATH = Path(__file__).resolve().parent / "config.json"


def _seed_sidecar_config(bundled: Path, sidecar: Path) -> bool:
    """Frozen first-run: salin config bundled (_MEIPASS) → sidecar (folder exe).

    Mengimplementasikan klaim BUILD_EXE.bat "config.json disimpan berdampingan
    dengan exe saat pertama kali dijalankan". Gagal (folder read-only) → False,
    caller fallback baca bundled read-only.
    """
    try:
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(bundled, sidecar)
        return True
    except OSError:
        return False


def _active_config_path() -> Path:
    """Jalur config.json yang benar-benar dipakai (dinamis — frozen-aware).

    1. Dev: CONFIG_PATH klasik (waste_anomaly/config.json).
    2. Frozen + sidecar ada (entah user edit entah hasil seed) → sidecar.
    3. Frozen + sidecar belum ada → SEED dari bundled, lalu pakai sidecar.
    4. Frozen + seed gagal (exe folder read-only) → bundled read-only
       (pipeline tetap jalan; perubahan user tidak bisa disimpan).
    """
    if not is_frozen():
        return CONFIG_PATH
    sidecar = exe_dir() / "config.json"
    if sidecar.exists():
        return sidecar
    bundled = bundle_dir() / "waste_anomaly" / "config.json"
    if bundled.exists():
        if _seed_sidecar_config(bundled, sidecar) and sidecar.exists():
            return sidecar
        return bundled  # read-only fallback
    return sidecar  # tidak ada bundled juga — biarkan load_config warn+default


# Default config minimal — dipakai baca config gagal (lihat load_config).
# v2.7.0 (audit Task 1): thresholds kini 20/20 key — dulu hanya 14, padahal
# config.json bawaan berisi 20. 6 key yang hilang (STATUS_PRIORITAS,
# STATUS_POTENSI, STATUS_REVIEW, S2_SCORE2_MIN, S10_BOM_MIN,
# QUADRANT_THRESHOLD) membuat: (a) "Reset Default" UI v2.6.0 hanya me-reset
# 14/20 (regresi bug v2.3.2), (b) jalur fallback load_config (config rusak)
# kehilangan 6 key — selamat karena signals.py/stages.py/charts.py memakai
# .get(key, fallback) dengan nilai fallback identik, tapi duplikasi nilai
# default di 3 tempat itu rapuh. Nilai di bawah disalin PERSIS dari
# config.json bawaan.
_DEFAULT_CONFIG = {
    "thresholds": {
        "TH_SPIKE": 3, "TH_MAX_AVG_AKTIF": 2.5, "TH_MAX_MEDIAN": 3,
        "TH_MAX_SECOND": 3, "TH_MAX_SHARE_WARN": 0.50,
        "TH_MAX_SHARE_HIGH": 0.70,
        # v2.19.9 — W-3 recalibrasi empiris (p95/p99 data real 9MB
        # TEGAR; lama 0.25/0.50/0.50/1.00 TIDAK PERNAH fire — sinyal mati).
        "TH_MAX_BOM_WARN": 0.03, "TH_MAX_BOM_HIGH": 0.10,
        "TH_TOTAL_BOM_WARN": 0.10, "TH_TOTAL_BOM_HIGH": 0.35,
        "TH_PEER_MIN": 3,
        "TH_PEER_WARN": 2, "TH_PEER_HIGH": 3, "TH_LAST_SHARE": 0.70,
        "TH_HARI_PEER_RATIO": 5.0,
        "TH_HARI_HIST_RATIO": 3.0,
        # v2.10.2 — kategori perubahan tabel Anomali (classify_change):
        # HIGH = batas "Naik/Turun Tinggi" (%), STABLE = rentang "Stabil" (%),
        # MIN_ABS = selisih absolut minimum agar bermakna (anti-noise kecil).
        "TH_CHANGE_HIGH": 50.0,
        "TH_CHANGE_STABLE": 20.0,
        "TH_CHANGE_MIN_ABS": 10.0,
        "STATUS_PRIORITAS": 8, "STATUS_POTENSI": 5, "STATUS_REVIEW": 3,
        "S2_SCORE2_MIN": 4, "S10_BOM_MIN": 0.10,
        "QUADRANT_THRESHOLD": 0.50,
        # v2.13.0 — profil baris: jumlah hari aktif minimum agar PROFIL
        # "Tiap Hari" (di bawahnya: "Kadang"; tepat 1: "Sekali Ini").
        "PROFIL_DAILY_MIN": 20,
        # v2.19.8 — W-5: SISTEMATIK threshold absolute (sum Count Hari
        # per item lintas resto >= ini + cabangActive >= 2). Default 5
        # (sebelumnya ceil(key_akhir/2) yg mati pada file pendek).
        "SISTEMATIK_MIN_DAYS": 5,
        # v2.19.8 — W-2: KRONIS guard — baris Normal dgn TOTAL di
        # KRONIS_TOP_DECILE (0.9 = top-10%) + TOTAL/PEER_MEDIAN >
        # KRONIS_PEER_RATIO (1.5 = 50% di atas peer) dibump ke
        # "Perlu Review (Kronis Tinggi)".
        "KRONIS_TOP_DECILE": 0.9,
        "KRONIS_PEER_RATIO": 1.5,
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
    p = Path(config_path) if config_path else _active_config_path()
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:  # JSONDecodeError / OSError / UnicodeDecodeError dll.
        warnings.warn(f"Config load gagal: {p}: {e} — pakai default")
        cfg = {k: (v.copy() if isinstance(v, (dict, list)) else v)
               for k, v in _DEFAULT_CONFIG.items()}
        cfg["_config_load_error"] = str(e)
        return cfg


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


# ============================================================
# NORMALISASI TEKS KUNCI (v2.5.1 — fix DQ-M1/audit fragmentasi)
# ============================================================

_INVISIBLE_CHARS = ("\xa0", "\u200b", "\u200c", "\u200d", "\ufeff")


def norm_text(value: object) -> str:
    """Normalisasi kunci teks untuk filter/dropdown/agregat kategori.

    V2.5.1 (audit DQ-M1): fragmentasi spasi tersembunyi ('PACK\\xa0' vs
    'PACK', varian zero-width, spasi ganda) membuat nilai yang TAMPIL sama
    dianggap berbeda oleh equality filter & groupby — dropdown punya entri
    kembar-visual dan memilih satu tidak menangkap baris pasangannya.

    Aturan (whitespace SAJA — TIDAK mengubah huruf/kata):
      1. NBSP ('\xa0') → SPASI (NBSP = non-breaking space, pemisah kata
         juga; menghapusnya menyatukan kata: 'Kualitas\xa0Internal' salah
         jadi 'KualitasInternal').
      2. zero-width/BOM → dihapus.
      3. strip() di kedua ujung.
      4. spasi berurutan → satu spasi.

    Contoh: norm_text(' PACK\\xa0 ') → 'PACK';
    norm_text('Kualitas\\xa0Internal') → 'Kualitas Internal'; None/NaN → ''.
    """
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    text = str(value).replace("\xa0", " ")
    for ch in _INVISIBLE_CHARS:
        text = text.replace(ch, "")
    return " ".join(text.split())
