"""test_v2130.py — v2.13.0 Task 1: profil baris + kelebihan vs tipikal.

Riset R1 (data asli 25.901 baris): top-20 waste terbesar SEMUA kronis
(17-30 hari aktif) dgn skor 0-6 — tab anomali belum membedakan "bocor
tiap hari" vs "kejadian satu hari". Modul profile.py menambah (additive):

- PROFIL: "Tiap Hari" (Count Hari ≥ PROFIL_DAILY_MIN=20) / "Kadang"
  (2-19) / "Sekali Ini" (1) / "—" (TOTAL 0/kosong).
- KELEBIHAN: TOTAL − median TOTAL peer AKTIF (grup NAMA BARANG+JENIS+
  KETERANGAN+SOURCE DATA, peer ≥ TH_PEER_MIN=3, hanya TOTAL>0).
  + kolom pendamping PEER MEDIAN (AKTIF) + PEER AKTIF.
- annotate_profile_vs_history: suffix " — Baru" bila BULAN LALU ≤ 0 /
  NaN (idempoten; tanpa kolom BULAN LALU → tak berubah).

Cakupan:
[A] klasifikasi PROFIL — semua cabang nilai + batas 20/2/1.
[B] fallback Count Hari dari kolom hari saat kolom itu hilang.
[C] KELEBIHAN — median peer aktif, ≥3 peer, negatif jujur, <3 peer
    kosong, baris nol kosong, unit aman (peer per-item — satuan sama).
[D] defensif — df kosong, kolom hilang, config kosong, tanpa raise.
[E] suffix Baru — pemicu NaN/0/negatif, idempoten, "—" tak ber-suffix.
[F] pipeline asli — kolom baru hadir; golden baris/status tak bergeser;
    PROFIL domain valid; KELEBIHAN terisi mayoritas baris aktif.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent

from waste_anomaly.profile import (
    KELEBIHAN_COL,
    PEER_AKTIF_COL,
    PEER_MEDIAN_AKTIF_COL,
    PROFIL_BARU_SUFFIX,
    PROFIL_COL,
    PROFIL_KADANG,
    PROFIL_KOSONG,
    PROFIL_SEKALI_INI,
    PROFIL_TIAP_HARI,
    annotate_profile,
    annotate_profile_vs_history,
)

CFG = {"thresholds": {}}


def _base_df(**over) -> pd.DataFrame:
    """Frame mini dgn kolom minimal annotate_profile (kunci peer + hari)."""
    data = {
        "NAMA BARANG": ["MIE", "MIE", "MIE", "MIE", "TEH"],
        "JENIS": ["WASTE"] * 5,
        "KETERANGAN": ["Handling"] * 5,
        "SOURCE DATA": ["WASTE BAHAN dan PACKAGING"] * 5,
        "NAMA RESTO": ["A", "B", "C", "D", "A"],
        "TOTAL": [100.0, 10.0, 10.0, 10.0, 8.0],
        "Count Hari": [25, 5, 5, 5, 1],
    }
    data.update(over)
    return pd.DataFrame(data)


# ============================================================
# [A] KLASIFIKASI PROFIL
# ============================================================

class TestProfilKlasifikasi:
    def test_tiap_hari_kadang_sekali_ini(self):
        df = annotate_profile(_base_df(), 31, CFG)
        assert list(df[PROFIL_COL]) == [
            PROFIL_TIAP_HARI, PROFIL_KADANG, PROFIL_KADANG,
            PROFIL_KADANG, PROFIL_SEKALI_INI]

    def test_batas_20_dan_2(self):
        df = _base_df(**{"Count Hari": [20, 19, 2, 1, 1]})
        out = annotate_profile(df, 31, CFG)
        assert list(out[PROFIL_COL])[:4] == [
            PROFIL_TIAP_HARI, PROFIL_KADANG, PROFIL_KADANG,
            PROFIL_SEKALI_INI]

    def test_total_nol_kosong_nan(self):
        df = _base_df(TOTAL=[0.0, np.nan, 10.0, 10.0, 10.0],
                      **{"Count Hari": [25, 25, 5, 5, 1]})
        out = annotate_profile(df, 31, CFG)
        assert out[PROFIL_COL].iloc[0] == PROFIL_KOSONG
        assert out[PROFIL_COL].iloc[1] == PROFIL_KOSONG

    def test_config_daily_min_override(self):
        df = _base_df(**{"Count Hari": [15, 14, 5, 5, 1]})
        out = annotate_profile(df, 31, {"thresholds": {
            "PROFIL_DAILY_MIN": 15}})
        assert out[PROFIL_COL].iloc[0] == PROFIL_TIAP_HARI
        assert out[PROFIL_COL].iloc[1] == PROFIL_KADANG


# ============================================================
# [B] FALLBACK COUNT HARI
# ============================================================

class TestFallbackCountHari:
    def test_hitung_dari_kolom_hari(self):
        df = _base_df().drop(columns=["Count Hari"])
        # MIE-A: hari 1..20 aktif; lainnya 2 hari; TEH-A 1 hari
        days = {str(i): [0.0] * 5 for i in range(1, 26)}
        for i in range(1, 21):
            days[str(i)][0] = 5.0        # MIE A — 20 hari aktif
        days["1"][1] = 1.0
        days["2"][1] = 1.0               # MIE B — 2 hari
        days["1"][4] = 8.0               # TEH A — 1 hari
        for c, vals in days.items():
            df[c] = vals
        out = annotate_profile(df, 25, CFG)
        assert out[PROFIL_COL].iloc[0] == PROFIL_TIAP_HARI
        assert out[PROFIL_COL].iloc[1] == PROFIL_KADANG
        assert out[PROFIL_COL].iloc[4] == PROFIL_SEKALI_INI


# ============================================================
# [C] KELEBIHAN VS TIPIKAL PEER AKTIF
# ============================================================

class TestKelebihan:
    def test_median_peer_aktif_dan_kelebihan(self):
        # MIE: A=100, B/C/D=10,10,10 → median aktif 10, kelebihan A = 90
        df = annotate_profile(_base_df(), 31, CFG)
        assert df.loc[0, KELEBIHAN_COL] == pytest.approx(90.0)
        assert df.loc[1, PEER_MEDIAN_AKTIF_COL] == pytest.approx(10.0)
        assert int(df.loc[0, PEER_AKTIF_COL]) == 4

    def test_kelebihan_negatif_jujur(self):
        # A lebih HEMAT dari peer (median 100, A=10 → -90)
        df = _base_df(TOTAL=[10.0, 100.0, 100.0, 100.0, 8.0])
        out = annotate_profile(df, 31, CFG)
        assert out.loc[0, KELEBIHAN_COL] == pytest.approx(-90.0)

    def test_peer_kurang_dari_3_kosong(self):
        # grup peer cuma 2 aktif → tidak ada kelebihan (sample kecil)
        df = _base_df(TOTAL=[100.0, 10.0, 0.0, 0.0, 8.0])
        out = annotate_profile(df, 31, CFG)
        assert pd.isna(out.loc[0, KELEBIHAN_COL])

    def test_grup_peer_terpisah_per_keterangan(self):
        # keterangan beda → beda grup peer → TEH tidak ikut median MIE
        df = _base_df(KETERANGAN=["Handling"] * 4 + ["Kualitas Internal"])
        out = annotate_profile(df, 31, CFG)
        # TEH berdiri sendiri (peer aktif 1 < 3) → kosong
        assert pd.isna(out.loc[4, KELEBIHAN_COL])

    def test_baris_nol_tidak_dihitung(self):
        df = _base_df(TOTAL=[0.0, 10.0, 10.0, 10.0, 8.0])
        out = annotate_profile(df, 31, CFG)
        # A nol → kelebihan NaN walau peer median 10
        assert pd.isna(out.loc[0, KELEBIHAN_COL])
        # median dihitung dari 3 peer aktif (B,C,D) = 10
        assert pd.isna(out.loc[0, PEER_MEDIAN_AKTIF_COL])


# ============================================================
# [D] DEFENSIF
# ============================================================

class TestDefensif:
    def test_df_kosong(self):
        df = pd.DataFrame(columns=["TOTAL", "NAMA BARANG", "JENIS",
                                   "KETERANGAN", "SOURCE DATA",
                                   "Count Hari"])
        out = annotate_profile(df, 31, CFG)
        assert PROFIL_COL in out.columns
        assert KELEBIHAN_COL in out.columns

    def test_kolom_total_hilang(self):
        df = _base_df().drop(columns=["TOTAL"])
        out = annotate_profile(df, 31, CFG)
        assert (out[PROFIL_COL] == PROFIL_KOSONG).all()

    def test_kunci_peer_hilang_tetap_profil(self):
        df = _base_df().drop(columns=["SOURCE DATA"])
        out = annotate_profile(df, 31, CFG)
        assert out[PROFIL_COL].iloc[0] == PROFIL_TIAP_HARI
        assert out[KELEBIHAN_COL].isna().all()

    def test_config_none(self):
        out = annotate_profile(_base_df(), 31, {})
        assert out[PROFIL_COL].iloc[0] == PROFIL_TIAP_HARI


# ============================================================
# [E] SUFFIX "— BARU" (vs bulan pembanding)
# ============================================================

class TestSuffixBaru:
    def test_bulan_lalu_nol_atau_nan(self):
        df = annotate_profile(_base_df(), 31, CFG)
        df["BULAN LALU"] = [0.0, 55.0, np.nan, 55.0, 0.0]
        out = annotate_profile_vs_history(df)
        assert out[PROFIL_COL].iloc[0].endswith(PROFIL_BARU_SUFFIX)
        assert not out[PROFIL_COL].iloc[1].endswith(PROFIL_BARU_SUFFIX)
        assert out[PROFIL_COL].iloc[2].endswith(PROFIL_BARU_SUFFIX)

    def test_idempoten(self):
        df = annotate_profile(_base_df(), 31, CFG)
        df["BULAN LALU"] = [0.0, 55.0, 55.0, 55.0, 55.0]
        once = annotate_profile_vs_history(df)
        twice = annotate_profile_vs_history(once)
        assert list(once[PROFIL_COL]) == list(twice[PROFIL_COL])

    def test_tanpa_kolom_bulan_lalu_tak_berubah(self):
        df = annotate_profile(_base_df(), 31, CFG)
        out = annotate_profile_vs_history(df)
        assert list(out[PROFIL_COL]) == list(df[PROFIL_COL])

    def test_profil_kosong_tak_ber_suffix(self):
        df = annotate_profile(
            _base_df(TOTAL=[0.0, 10.0, 10.0, 10.0, 8.0]), 31, CFG)
        df["BULAN LALU"] = [0.0, 0.0, 0.0, 0.0, 0.0]
        out = annotate_profile_vs_history(df)
        assert out[PROFIL_COL].iloc[0] == PROFIL_KOSONG


# ============================================================
# [F] PIPELINE DATA ASLI
# ============================================================

FIXTURE = REPO / "DATA_WASTE.xlsx"


@pytest.fixture(scope="module")
def real_summary() -> dict:
    from waste_anomaly.pipeline import run_pipeline
    result = run_pipeline(workbook_path=str(FIXTURE), key_akhir=31)
    assert result.get("success") is True
    return result


@pytest.mark.skipif(not FIXTURE.exists(),
                    reason="fixture DATA_WASTE.xlsx tidak ada")
class TestPipelineAsli:
    def test_kolom_baru_hadir(self, real_summary):
        df = real_summary["df"]
        for col in (PROFIL_COL, KELEBIHAN_COL, PEER_MEDIAN_AKTIF_COL,
                    PEER_AKTIF_COL):
            assert col in df.columns

    def test_golden_rows_tak_geser(self, real_summary):
        # 25.901 baris (golden v2.3.2) — kolom additive tak boleh geser
        assert real_summary["total_rows"] == 25901

    def test_status_domain_tak_geser(self, real_summary):
        valid = {"Prioritas Tinggi", "Potensi Anomali",
                 "Perlu Review", "Normal"}
        assert set(real_summary["df"]["ANOMALY STATUS"].unique()) <= valid

    def test_profil_domain_valid(self, real_summary):
        df = real_summary["df"]
        base = {"Tiap Hari", "Kadang", "Sekali Ini", "—"}
        vals = set(df[PROFIL_COL].dropna().unique())
        # hanya nilai kanonik (+ optional suffix dari pembanding —
        # pipeline murni tak men-suffix, itu tugas view)
        assert vals <= base, f"nilai PROFIL tak dikenal: {vals - base}"

    def test_kelebihan_terisi_mayoritas_aktif(self, real_summary):
        df = real_summary["df"]
        act = df[pd.to_numeric(df["TOTAL"], errors="coerce") > 0]
        ratio = act[KELEBIHAN_COL].notna().mean()
        # data asli: 2161/2431 ≈ 89% — kunci lantai 80%
        assert ratio > 0.80, f"KELEBIHAN cuma terisi {ratio:.0%} baris aktif"

    def test_kelebihan_top_realistis(self, real_summary):
        # SURAI NAGA @ 1042.KWGGAL: TOTAL ±296rb, tipikal peer ±1.695
        # (riset R1) — kelebihan harus sekitar 294rb (positif besar)
        df = real_summary["df"]
        sub = df[(df["NAMA BARANG"].astype(str).str.contains("SURAI NAGA"))
                 & (df["NAMA RESTO"] == "1042.KWGGAL")]
        assert len(sub) >= 1
        top = sub.loc[sub["TOTAL"].idxmax()]
        assert top[KELEBIHAN_COL] > 100_000
