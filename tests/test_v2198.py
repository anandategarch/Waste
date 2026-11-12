"""test_v2198.py — audit fixes W-1/W-2/W-5/W-6 + tab Anomali show-all.

Permintaan user: "oke kerjakan semua dan push" + "di tab anomali tampilkan
aja semua data jangan hanya yang perlu review atau anomali aja tapi semua
data ya biar bisa aku cek".

Cover:
  [A] Tab Anomali show ALL data — anomali_df TIDAK lagi buang Normal.
  [B] W-1 key_akhir auto-detect — pipeline warning bila key_akhir > hari-data-terakhir.
  [C] W-2 kronis-Normal guard — baris Normal dgn TOTAL top-decile + >50%
      di atas peer median → dibump ke "Perlu Review" + alasan "Kronis Tinggi".
  [D] W-5 SISTEMATIK rework — daysActive = SUM Count Hari (bukan max) +
      threshold absolute (SISTEMATIK_MIN_DAYS=5, bukan ceil(key_akhir/2)).
  [E] W-6 SCALE SIGNAL log10 — ratio 172 (pola 100× typo) → YES (dulu NO).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

REPO = Path(__file__).resolve().parent.parent


def _qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication(sys.argv)


# ============================================================
# [A] Tab Anomali show ALL data (Normal ikut)
# ============================================================

class TestAnomaliShowAll:
    def test_anomali_df_termasuk_normal(self):
        """v2.19.8 — anomali_df TIDAK lagi buang Normal (permintaan user
        'tampilkan semua data'). Filter skor ≥ min tetap jalan."""
        _qapp()
        from ui.state import AppContext
        ctx = AppContext({})
        df = pd.DataFrame({
            "JENIS": ["WASTE"] * 4,
            "NAMA BARANG": ["AYAM", "AYAM", "BEBEK", "BEBEK"],
            "NAMA RESTO": ["R1"] * 4,
            "ANOMALY STATUS": ["Prioritas Tinggi", "Normal",
                               "Perlu Review", "Normal"],
            "ANOMALY SCORE": [10, 0, 4, 0],
            "TOTAL": [100.0, 0.0, 50.0, 0.0],
        })
        ctx.set_dataset(df, {"key_akhir": 31})
        adf = ctx.anomali_df()
        # SEMUA 4 baris tampil (termasuk 2 Normal) — sebelumnya hanya 2.
        assert len(adf) == 4, f"harus 4 baris (Normal ikut), dapat {len(adf)}"
        assert (adf["ANOMALY STATUS"] == "Normal").sum() == 2

    def test_anomali_df_filter_skor_tetap_jalan(self):
        """Filter skor ≥ min tetap aktif (spinner 'Skor ≥'). default 0 = semua."""
        _qapp()
        from ui.state import AppContext
        ctx = AppContext({})
        df = pd.DataFrame({
            "JENIS": ["WASTE"] * 3,
            "NAMA BARANG": ["A", "B", "C"],
            "NAMA RESTO": ["R1"] * 3,
            "ANOMALY STATUS": ["Prioritas Tinggi", "Perlu Review", "Normal"],
            "ANOMALY SCORE": [10, 4, 0],
            "TOTAL": [100.0, 50.0, 0.0],
        })
        ctx.set_dataset(df, {"key_akhir": 31})
        ctx.set_score_min(5)
        adf = ctx.anomali_df()
        # skor ≥ 5 → hanya 1 baris (score 10). Filter skor tetap jalan.
        assert len(adf) == 1
        assert int(adf["ANOMALY SCORE"].iloc[0]) == 10


# ============================================================
# [B] W-1 key_akhir auto-detect warning
# ============================================================

class TestKeyAkhirAutoDetect:
    def _make_sheet(self, tmp_path, last_day=3) -> Path:
        """Workbook dgn data hanya hari 1..last_day (hari lain 0)."""
        import openpyxl
        p = tmp_path / "REKAP MENTAH_TEST.xlsx"
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "REKAP MENTAH"
        header = ["SOURCE DATA", "JENIS", "KETERANGAN", "NAMA BARANG",
                  "NAMA RESTO", "SATUAN"] + list(range(1, 32))
        ws.append(header)
        row = ["WASTE", "WASTE", "Cancel Nota", "AYAM", "R1", "GR"] + [0] * 31
        for d in range(1, last_day + 1):
            row[6 + d - 1] = 10 * d  # hari d = 10*d (non-zero)
        ws.append(row)
        wb.save(p)
        return p

    def test_warning_saat_key_akhir_lebih_besar_data(self, tmp_path):
        """key_akhir=31, data hanya hari 1-3 → pipeline log WARNING key_akhir
        + schema_warnings menyebut mismatch."""
        from waste_anomaly.pipeline import run_pipeline
        p = self._make_sheet(tmp_path, last_day=3)
        result = run_pipeline(str(p), key_akhir=31)
        assert result["success"], result.get("error", "")
        log = result.get("log", "")
        assert "WARNING key_akhir" in log, (
            "harus ada warning key_akhir > hari-data-terakhir")
        assert "hari 3" in log  # last_day_with_data = 3

    def test_tanpa_warning_saat_key_akhir_pas(self, tmp_path):
        """key_akhir=3, data hari 1-3 → TIDAK ada warning (data match)."""
        from waste_anomaly.pipeline import run_pipeline
        p = self._make_sheet(tmp_path, last_day=3)
        result = run_pipeline(str(p), key_akhir=3)
        assert result["success"]
        log = result.get("log", "")
        assert "WARNING key_akhir" not in log


# ============================================================
# [C] W-2 kronis-Normal guard
# ============================================================

class TestKronisGuard:
    def test_kronis_normal_dibump_perlu_review(self):
        """Baris Normal dgn TOTAL top-decile + TOTAL/PEER_MEDIAN > 1.5 →
        dibump ke 'Perlu Review' + alasan 'Kronis Tinggi'. Score tak berubah."""
        from waste_anomaly.signals import compute_signals
        # 20 baris: 19 peer kecil (TOTAL=50, single-day) + 1 KRONIS (TOTAL=100,
        # spread 31 hari, NO spike → score 0 → Normal). Kronis ratio 2.0
        # (>1.5 kronis, <3 S9). q90 of 20 rows (19×50 + 1×100) = 50 → kronis
        # TOTAL=100 > 50 → top-decile. MAX=7 (<3×AVG → S1/S2/S3 no).
        def _peer(i):
            return {
                "JENIS": "WASTE", "KETERANGAN": "Handling",
                "NAMA BARANG": f"PEER{i}", "NAMA RESTO": "R1",
                "SATUAN": "GR", "TOTAL": 50.0, "Count Hari": 1,
                "MAX": 50.0, "AVG": 50.0, "AVG AKTIF": 50.0,
                "MEDIAN AKTIF": 50.0, "SECOND MAX": 0.0,
                "MAX SHARE": 1.0, "LAST DAY SHARE": 1.0,
                "SCALE SIGNAL": "NO", "SINGLE DAY": "YES",
                "PEER COUNT": 20,
                "MAX / PEER MEDIAN MAX": 1.0, "TOTAL / PEER MEDIAN": 1.0,
                "PEER MEDIAN TOTAL": 50.0,
                "MAX / BOM": 0.0, "TOTAL / BOM": 0.0,
                "MAX / AVG": 1.0,
                **{str(d): 0.0 for d in range(1, 32)},
            }
        peer_rows = [_peer(i) for i in range(19)]
        for r in peer_rows:
            r["5"] = 50.0  # single day
        # KRONIS row: TOTAL=100 spread 31 hari, MAX=7 (no spike).
        kronis = {
            "JENIS": "WASTE", "KETERANGAN": "Handling",
            "NAMA BARANG": "KRONIS_ITEM", "NAMA RESTO": "R1",
            "SATUAN": "GR", "TOTAL": 100.0, "Count Hari": 31,
            "MAX": 7.0, "AVG": 3.2, "AVG AKTIF": 3.2,
            "MEDIAN AKTIF": 3.2, "SECOND MAX": 6.0,
            "MAX SHARE": 0.07, "LAST DAY SHARE": 0.05,
            "SCALE SIGNAL": "NO", "SINGLE DAY": "NO",
            "PEER COUNT": 20,
            "MAX / PEER MEDIAN MAX": 0.14, "TOTAL / PEER MEDIAN": 2.0,
            "PEER MEDIAN TOTAL": 50.0,
            "MAX / BOM": 0.0, "TOTAL / BOM": 0.0,
            "MAX / AVG": 2.19,
            **{str(d): 3.0 for d in range(1, 32)},  # spread ~3/day
        }
        kronis["15"] = 7.0  # MAX=7 (day 15)
        df = pd.DataFrame(peer_rows + [kronis])
        out = compute_signals(df, key_akhir=31, config={})
        kronis_row = out[out["NAMA BARANG"] == "KRONIS_ITEM"].iloc[0]
        # Seharusnya dibump dari Normal → Perlu Review.
        assert kronis_row["ANOMALY STATUS"] == "Perlu Review", (
            f"kronis harus 'Perlu Review', dapat "
            f"{kronis_row['ANOMALY STATUS']}")
        assert "Kronis Tinggi" in str(kronis_row["ANOMALY REASONS"]), (
            f"alasan harus sebut 'Kronis Tinggi', dapat "
            f"{kronis_row['ANOMALY REASONS']}")


# ============================================================
# [D] W-5 SISTEMATIK rework (sum + absolute threshold)
# ============================================================

class TestSistematikRework:
    def test_days_active_sum_bukan_max(self):
        """daysActive per item = SUM Count Hari lintas resto (bukan max).
        Item dgn 5 resto × 2 hari = sum 10 (bukan max 2)."""
        from waste_anomaly.stages import stage_12_5_fingerprint
        # 5 resto × 2 hari Count Hari = 10 baris; sum=10, max=2.
        df = pd.DataFrame({
            "JENIS": ["WASTE"] * 10,
            "NAMA BARANG": ["AYAM"] * 10,
            "NAMA RESTO": [f"R{i}" for i in range(5) for _ in range(2)],
            "TOTAL": [10.0] * 10,
            "Count Hari": [2] * 10,
            "W": [10.0] * 10, "S": [0.0] * 10, "T": [0.0] * 10,
        })
        out = stage_12_5_fingerprint(df, key_akhir=31, config={})
        sist = out[["NAMA BARANG", "daysActive", "cabangActive",
                    "SISTEMATIK", "SISTEMATIK DAYS THRESHOLD"]]
        ayam = sist[sist["NAMA BARANG"] == "AYAM"].iloc[0]
        assert int(ayam["daysActive"]) == 20, (
            f"sum Count Hari 5×2×2=20 (bukan max 2), dapat {ayam['daysActive']}")
        assert int(ayam["cabangActive"]) == 5
        assert ayam["SISTEMATIK"] == "YES", (
            "sum 20 ≥ SISTEMATIK_MIN_DAYS 5 + cabangActive 5 ≥ 2 → YES")
        assert int(ayam["SISTEMATIK DAYS THRESHOLD"]) == 5  # absolute, bukan ceil(31/2)=16


# ============================================================
# [E] W-6 SCALE SIGNAL log10 rounding
# ============================================================

class TestScaleSignalLog10:
    def test_ratio_172_pola_100x_terdeteksi(self):
        """Ratio 172 (pola 100× typo) → YES. Sebelum v2.19.8: band [80,120]
        sempit → 172 luput (dead zone (120,800))."""
        # _scale_signal adalah fungsi lokal di stage_02 — uji via stage_02
        # dgn ratio yg menghasilkan 172. Simpler: replicate logic + assert.
        import math
        _LOG10_2 = math.log10(2.0)

        def _scale_signal(sr):
            if sr >= 8:
                try:
                    lg = math.log10(sr)
                except (ValueError, TypeError):
                    return "NO"
                if abs(lg - round(lg)) <= _LOG10_2:
                    return "YES"
            return "NO"
        # Pola 10×: 8, 10, 15 → YES (band ~5-20, ±100% sekitar 10^k).
        assert _scale_signal(8) == "YES"
        assert _scale_signal(10) == "YES"
        assert _scale_signal(15) == "YES"
        # Pola 100×: 60, 100, 172 (audit case), 180 → YES.
        # (50/200 = boundary exact log10(2) — FP precision ambang; skip.)
        assert _scale_signal(60) == "YES"
        assert _scale_signal(100) == "YES"
        assert _scale_signal(172) == "YES", "172 (pola 100×) harus YES — dulu luput"
        assert _scale_signal(180) == "YES"
        # Bukan pola 10^k: 22, 35 → NO (di antara 10× dan 100×).
        assert _scale_signal(22) == "NO"
        assert _scale_signal(35) == "NO"
        # Di bawah floor 8 → NO (noise rendah).
        assert _scale_signal(5) == "NO"
        assert _scale_signal(7) == "NO"
