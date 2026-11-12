"""Unit test — 12 sinyal anomali (signals.compute_signals), satu per satu.

Jantung aplikasi: S1..S12 + composite score + status cutoff. Setiap test
mengunci: trigger, non-trigger, boundary persis di threshold, dan semantik
NaN (kolom hilang TIDAK boleh meledak / me-trigger).

compute_signals membaca kolom kalkulasi pra-hitung (rasio, Count Hari, dst)
— test ini menyuntik nilai kolom secara langsung sehingga setiap sinyal
terisolasi dari stage 1-10.
"""

import numpy as np
import pandas as pd

from waste_anomaly.signals import compute_signals

CONFIG = {"thresholds": {}}


def make_df(**cols) -> pd.DataFrame:
    """Frame minimal 1 baris — kolom di-inject langsung via kwargs."""
    return pd.DataFrame([cols])


def run(df: pd.DataFrame) -> tuple[int, str]:
    out = compute_signals(df, key_akhir=31, config=CONFIG)
    return int(out["ANOMALY SCORE"].iloc[0]), str(out["ANOMALY STATUS"].iloc[0])


def reason_of(df: pd.DataFrame) -> str:
    out = compute_signals(df, key_akhir=31, config=CONFIG)
    return str(out["ANOMALY REASONS"].iloc[0])


# ============================================================
# S1 — Spike vs AVG: Count>=2 & MAX/AVG >= TH_SPIKE (3) → skor 1
# ============================================================

class TestS1SpikeVsAvg:
    def test_trigger(self):
        score, _ = run(make_df(**{"Count Hari": 2, "MAX / AVG": 3.0, "TOTAL": 10}))
        assert score == 1  # S1 aktif (boundary persis 3.0)

    def test_diatas_threshold(self):
        score, _ = run(make_df(**{"Count Hari": 2, "MAX / AVG": 5.0, "TOTAL": 10}))
        assert score == 1

    def test_non_trigger_di_bawah(self):
        score, _ = run(make_df(**{"Count Hari": 2, "MAX / AVG": 2.99, "TOTAL": 10}))
        assert score == 0

    def test_non_trigger_count_kurang(self):
        # rasio tinggi tapi hanya 1 hari aktif → gate gagal
        score, _ = run(make_df(**{"Count Hari": 1, "MAX / AVG": 9.9, "TOTAL": 10}))
        assert score == 0

    def test_nan_ratio_aman(self):
        score, _ = run(make_df(**{"Count Hari": 2, "MAX / AVG": np.nan, "TOTAL": 10}))
        assert score == 0

    def test_reason_teks(self):
        assert "Lonjakan vs rata-rata harian" in reason_of(make_df(**{"Count Hari": 2, "MAX / AVG": 3.0}))


# ============================================================
# S2 — MAX/AVG AKTIF: Count>=3 & ratio >= 2.5 → 1; >= S2_SCORE2_MIN (4) → 2
# ============================================================

class TestS2MaxVsAvgAktif:
    def test_skor1_di_ambang(self):
        score, _ = run(make_df(**{"Count Hari": 3, "MAX / AVG AKTIF": 2.5}))
        assert score == 1

    def test_skor2_di_ambang(self):
        score, _ = run(make_df(**{"Count Hari": 3, "MAX / AVG AKTIF": 4.0}))
        assert score == 2

    def test_skor1_di_antara(self):
        score, _ = run(make_df(**{"Count Hari": 3, "MAX / AVG AKTIF": 3.5}))
        assert score == 1

    def test_non_trigger_di_bawah(self):
        score, _ = run(make_df(**{"Count Hari": 3, "MAX / AVG AKTIF": 2.49}))
        assert score == 0

    def test_gate_count_2(self):
        score, _ = run(make_df(**{"Count Hari": 2, "MAX / AVG AKTIF": 9.0}))
        assert score == 0

    def test_skor2_config_override(self):
        cfg = {"thresholds": {"S2_SCORE2_MIN": 10}}
        df = make_df(**{"Count Hari": 3, "MAX / AVG AKTIF": 4.0})
        out = compute_signals(df, key_akhir=31, config=cfg)
        assert int(out["ANOMALY SCORE"].iloc[0]) == 1  # 4 < 10 → masih skor 1


# ============================================================
# S3 — MAX/MEDIAN AKTIF: Count>=3 & ratio >= 3 → skor 2
# ============================================================

class TestS3MaxVsMedianAktif:
    def test_trigger_boundary(self):
        score, _ = run(make_df(**{"Count Hari": 3, "MAX / MEDIAN AKTIF": 3.0}))
        assert score == 2

    def test_non_trigger_bawah(self):
        score, _ = run(make_df(**{"Count Hari": 3, "MAX / MEDIAN AKTIF": 2.999}))
        assert score == 0

    def test_gate_count(self):
        score, _ = run(make_df(**{"Count Hari": 2, "MAX / MEDIAN AKTIF": 3.0}))
        assert score == 0


# ============================================================
# S4 — MAX SHARE: >= 0.70 → 2; >= 0.50 → 1
# ============================================================

class TestS4MaxShare:
    def test_skor2_boundary_high(self):
        score, _ = run(make_df(**{"MAX SHARE": 0.70}))
        assert score == 2

    def test_skor1_boundary_warn(self):
        score, _ = run(make_df(**{"MAX SHARE": 0.50}))
        assert score == 1

    def test_skor1_di_antara(self):
        score, _ = run(make_df(**{"MAX SHARE": 0.69}))
        assert score == 1

    def test_non_trigger(self):
        score, _ = run(make_df(**{"MAX SHARE": 0.4999}))
        assert score == 0


# ============================================================
# S5 — MAX/SECOND MAX: Count>=2 & ratio >= 3 → 1
# ============================================================

class TestS5MaxVsSecond:
    def test_trigger(self):
        score, _ = run(make_df(**{"Count Hari": 2, "MAX / SECOND MAX": 3.0}))
        assert score == 1

    def test_non_trigger(self):
        score, _ = run(make_df(**{"Count Hari": 2, "MAX / SECOND MAX": 2.99}))
        assert score == 0

    def test_gate_count(self):
        score, _ = run(make_df(**{"Count Hari": 1, "MAX / SECOND MAX": 5.0}))
        assert score == 0


# ============================================================
# S6 — MAX/BOM (via MAX & TOTAL BOM): >= 0.50 → 2; >= 0.25 → 1
# ============================================================

class TestS6MaxVsBom:
    def test_skor2(self):
        score, _ = run(make_df(**{"MAX": 50, "TOTAL BOM": 100}))
        assert score == 2  # 50/100 = 0.50 >> high(0.10)

    def test_skor1(self):
        # v2.19.9 W-3: warn 0.25 → 0.03 — 25/100 = 0.25 kini band HIGH.
        # Uji band warn dgn rasio antara warn(0.03) dan high(0.10).
        score, _ = run(make_df(**{"MAX": 5, "TOTAL BOM": 100}))
        assert score == 1  # 5/100 = 0.05 ∈ [0.03, 0.10) → warn

    def test_non_trigger(self):
        # v2.19.9 W-3: rasio di bawah warn(0.03) → 0.
        score, _ = run(make_df(**{"MAX": 2.9, "TOTAL BOM": 100}))
        assert score == 0  # 0.029 < 0.03

    def test_bom_nol_atau_nan_aman(self):
        # TOTAL BOM = 0 → rasio 0 (guarded), tidak div-by-zero
        score, _ = run(make_df(**{"MAX": 50, "TOTAL BOM": 0}))
        assert score == 0
        score, _ = run(make_df(**{"MAX": 50, "TOTAL BOM": np.nan}))
        assert score == 0


# ============================================================
# S7 — TOTAL/BOM: >= 1.00 → 2; >= 0.50 → 1
# ============================================================

class TestS7TotalVsBom:
    def test_skor2(self):
        score, _ = run(make_df(**{"TOTAL": 100, "TOTAL BOM": 100}))
        assert score == 2  # 1.0 >> high(0.35)

    def test_skor1(self):
        # v2.19.9 W-3: warn 0.50 → 0.10. Band warn: 15/100 = 0.15 ∈ [0.10, 0.35).
        score, _ = run(make_df(**{"TOTAL": 15, "TOTAL BOM": 100}))
        assert score == 1

    def test_non_trigger(self):
        # v2.19.9 W-3: di bawah warn(0.10) → 0.
        score, _ = run(make_df(**{"TOTAL": 9.9, "TOTAL BOM": 100}))
        assert score == 0


# ============================================================
# S8 — PEER MAX: PeerCount>=3 & MAX/PeerMedMax >= 3 → 2; >= 2 → 1
# ============================================================

class TestS8PeerMax:
    def test_skor2(self):
        score, _ = run(make_df(**{"PEER COUNT": 3, "MAX": 30, "PEER MEDIAN MAX": 10}))
        assert score == 2  # 30/10 = 3.0

    def test_skor1(self):
        score, _ = run(make_df(**{"PEER COUNT": 3, "MAX": 25, "PEER MEDIAN MAX": 10}))
        assert score == 1  # 2.5

    def test_gate_peer_count(self):
        # rasio ekstrem tapi peer < 3 → mati
        score, _ = run(make_df(**{"PEER COUNT": 2, "MAX": 100, "PEER MEDIAN MAX": 1}))
        assert score == 0

    def test_peer_median_nol_aman(self):
        score, _ = run(make_df(**{"PEER COUNT": 3, "MAX": 100, "PEER MEDIAN MAX": 0}))
        assert score == 0


# ============================================================
# S9 — PEER TOTAL: PeerCount>=3 & TOTAL/PeerMedTot >= 3 → 1
# ============================================================

class TestS9PeerTotal:
    def test_trigger(self):
        score, _ = run(make_df(**{"PEER COUNT": 3, "TOTAL": 30, "PEER MEDIAN TOTAL": 10}))
        assert score == 1

    def test_non_trigger(self):
        score, _ = run(make_df(**{"PEER COUNT": 3, "TOTAL": 29.9, "PEER MEDIAN TOTAL": 10}))
        assert score == 0

    def test_gate_peer_count(self):
        score, _ = run(make_df(**{"PEER COUNT": 2, "TOTAL": 100, "PEER MEDIAN TOTAL": 1}))
        assert score == 0


# ============================================================
# S10 — Single-day: Count==1 & (MaxBOM>=0.10 atau MaxPeer>=TH_PEER_WARN)
# ============================================================

class TestS10SingleDay:
    def test_trigger_via_bom(self):
        # v2.19.9 W-3: S10_BOM_MIN tetap 0.10 — 20/100 = 0.2 >= 0.10 → S10=1.
        # Rasio 0.2 kini juga >= S6 high(0.10) → S6=2. TOTAL = S10(1)+S6(2) = 3.
        score, _ = run(make_df(**{"Count Hari": 1, "MAX": 20, "TOTAL BOM": 100}))
        assert score == 3  # S10(1) + S6 high(2)

    def test_trigger_via_peer(self):
        score, _ = run(make_df(**{"Count Hari": 1, "MAX": 25, "PEER MEDIAN MAX": 10, "PEER COUNT": 3}))
        # MaxPeerRatio 2.5 >= TH_PEER_WARN(2) — gate peer-count S8 juga aktif:
        # 25/10 >= 3? tidak (2.5) → S8 skor 1 via warn band. Jadi total = S10(1) + S8(1) = 2
        assert score == 2

    def test_non_trigger_count_2(self):
        # v2.19.9 W-3: MaxBOM 0.2 kini >= high(0.10) → S6 menyala — S10 mati
        # (Count 2) tapi S6 = 2. Uji no-S10 + no-S6: rasio < warn 0.03.
        score, _ = run(make_df(**{"Count Hari": 2, "MAX": 2, "TOTAL BOM": 100}))
        assert score == 0  # S10 mati (Count 2); MaxBOM 0.02 < 0.03 → S6 mati

    def test_count1_tanpa_bom_dan_peer(self):
        score, _ = run(make_df(**{"Count Hari": 1, "MAX": 5, "TOTAL": 5}))
        assert score == 0


# ============================================================
# S11 — Last Day Share: >= 0.70 → 1
# ============================================================

class TestS11LastDayShare:
    def test_trigger(self):
        score, _ = run(make_df(**{"LAST DAY SHARE": 0.70}))
        assert score == 1

    def test_non_trigger(self):
        score, _ = run(make_df(**{"LAST DAY SHARE": 0.69}))
        assert score == 0


# ============================================================
# S12 — Scale Signal: string "YES" → 2
# ============================================================

class TestS12ScaleSignal:
    def test_trigger_yes(self):
        score, _ = run(make_df(**{"SCALE SIGNAL": "YES"}))
        assert score == 2

    def test_no_dan_nan_mati(self):
        assert run(make_df(**{"SCALE SIGNAL": "NO"}))[0] == 0
        assert run(make_df(**{"SCALE SIGNAL": np.nan}))[0] == 0
        assert run(make_df(**{"SCALE SIGNAL": "yes"}))[0] == 0  # case-sensitive


# ============================================================
# COMPOSITE — status cutoff: >=8 Prioritas, >=5 Potensi, >=3 Review
# ============================================================

class TestCompositeStatus:
    def _row_score(self, score_val):
        # Injeksi via S3 (skor 2) + S4... lebih mudah: S12 YES (2) + kombinasi.
        # S6: MAX/TOTALBOM — pilih nilai untuk skor target.
        # Kita pakai S2 (0/1/2) + S3 (0/2) + S4 (0/1/2) + S12 (0/2) = 0..8
        cfg = {"thresholds": {}}
        row = {"Count Hari": 3, "SCALE SIGNAL": "YES"}
        # S2: MAX/AVG AKTIF
        # S3: MAX/MEDIAN AKTIF
        # S4: MAX SHARE
        return row, cfg

    def test_prioritas_boundary_8(self):
        # S2 skor2 (4.0) + S3 (3.0) + S4 (0.7) + S12 = 2+2+2+2 = 8 → Prioritas
        row = {
            "Count Hari": 3, "MAX / AVG AKTIF": 4.0,
            "MAX / MEDIAN AKTIF": 3.0, "MAX SHARE": 0.70, "SCALE SIGNAL": "YES",
        }
        _, status = run(make_df(**row))
        assert status == "Prioritas Tinggi"

    def test_potensi_boundary_5(self):
        # S2 skor1 (2.5) + S3 (3.0) + S4 (0.7) = 1+2+2 = 5 → Potensi
        row = {
            "Count Hari": 3, "MAX / AVG AKTIF": 2.5,
            "MAX / MEDIAN AKTIF": 3.0, "MAX SHARE": 0.70,
        }
        _, status = run(make_df(**row))
        assert status == "Potensi Anomali"

    def test_review_boundary_3(self):
        # S3 saja (Count 3, ratio 3.0) = 2 → Review? tidak, 2 < 3 → Normal.
        # S2(1) + S3(2) = 3 → Review
        row = {"Count Hari": 3, "MAX / AVG AKTIF": 2.5, "MAX / MEDIAN AKTIF": 3.0}
        _, status = run(make_df(**row))
        assert status == "Perlu Review"

    def test_normal(self):
        _, status = run(make_df(**{"Count Hari": 3, "MAX / AVG AKTIF": 1.5}))
        assert status == "Normal"

    def test_cutoff_dari_config(self):
        # STATUS_PRIORITAS dinaikkan jadi 99 → tidak ada yang Prioritas
        cfg = {"thresholds": {"STATUS_PRIORITAS": 99}}
        row = {
            "Count Hari": 3, "MAX / AVG AKTIF": 4.0,
            "MAX / MEDIAN AKTIF": 3.0, "MAX SHARE": 0.70, "SCALE SIGNAL": "YES",
        }
        out = compute_signals(make_df(**row), key_akhir=31, config=cfg)
        assert str(out["ANOMALY STATUS"].iloc[0]) == "Potensi Anomali"


# ============================================================
# ROBUSTNESS — empty df, semua NaN, single row tanpa kolom apa pun
# ============================================================

class TestSignalsRobustness:
    def test_empty_df(self):
        out = compute_signals(pd.DataFrame(), key_akhir=31, config=CONFIG)
        assert len(out) == 0

    def test_semua_nan(self):
        row = {c: np.nan for c in [
            "TOTAL", "MAX", "AVG", "AVG AKTIF", "MEDIAN AKTIF", "SECOND MAX",
            "MAX / AVG", "MAX / AVG AKTIF", "MAX / MEDIAN AKTIF", "MAX / SECOND MAX",
            "MAX SHARE", "LAST DAY SHARE", "Count Hari", "TOTAL BOM",
            "PEER COUNT", "PEER MEDIAN TOTAL", "PEER MEDIAN MAX",
        ]}
        score, status = run(make_df(**row))
        assert score == 0
        assert status == "Normal"

    def test_kolom_hilang_total(self):
        # df nyaris kosong — semua kolom kalkulasi hilang → tidak crash
        score, status = run(pd.DataFrame([{"NAMA BARANG": "X"}]))
        assert score == 0
        assert status == "Normal"

    def test_idempotent_format_ulas_rasio(self):
        # Sinyal hanya membaca rasio pra-hitung — tidak mengubah input
        df = make_df(**{"Count Hari": 2, "MAX / AVG": 3.5, "TOTAL": 10})
        out = compute_signals(df, key_akhir=31, config=CONFIG)
        assert out["MAX / AVG"].iloc[0] == 3.5
        assert df["MAX / AVG"].iloc[0] == 3.5  # input tidak termutasi

    def test_max_score_teoritis(self):
        # S1(1)+S2(2)+S3(2)+S4(2)+S5(1)+S6(2)+S7(2)+S8(2)+S9(1)+S10(0/1)+S11(1)+S12(2)
        # S10 eksklusif dengan gate count (Count==1) — pakai Count=2:
        # 1+2+2+2+1+2+2+2+1+0+1+2 = 18 (max tanpa S10; README: max 19 dengan S10)
        row = {
            "Count Hari": 3, "MAX / AVG": 3.5, "MAX / AVG AKTIF": 4.0,
            "MAX / MEDIAN AKTIF": 3.0, "MAX SHARE": 0.75,
            "MAX / SECOND MAX": 3.0,
            "MAX": 60, "TOTAL": 120, "TOTAL BOM": 100,  # S6: 0.6→2, S7: 1.2→2
            "PEER COUNT": 3, "PEER MEDIAN MAX": 20, "PEER MEDIAN TOTAL": 30,
            # S8: 60/20=3→2; S9: 120/30=4→1
            "LAST DAY SHARE": 0.8, "SCALE SIGNAL": "YES",
        }
        score, status = run(make_df(**row))
        assert score == 18, f"max skor tanpa S10 = 18, dapat {score}"
        assert status == "Prioritas Tinggi"
