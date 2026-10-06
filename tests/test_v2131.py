"""test_v2131.py — v2.13.1 Task 2: insights.py (analisa agregat cabang).

Modul insights.py (bahan tab Scorecard):
- resto_intensity  : waste vs BOM per cabang + kelebihan vs median peer.
- money_ranking    : peringkat baris berdasar KELEBIHAN (bukan TOTAL).
- coverage_report  : detektor INPUT KOSONG (item umum tak dilaporkan)
                     dgn verdict Berhenti Input / Memang Tak Pernah /
                     Perlu Pembanding / Lengkap.
- systemic_days    : hari naik serentak di banyak cabang (masalah bersama).
- weekday_real     : pola Senin..Minggu dari label bulan (fix proxy mod-7).
- scorecard        : tabel komposit per cabang (RANK = urutan kunjungan).

Cakupan: unit sintetis [A]-[F] + data asli [G] (golden ringan).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent

from waste_anomaly.insights import (
    COVERAGE_COLS,
    INTENSITY_COLS,
    MONEY_COLS,
    SCORECARD_COLS,
    SYSTEMIC_COLS,
    WEEKDAY_COLS,
    coverage_report,
    money_ranking,
    parse_month_label,
    resto_intensity,
    scorecard,
    systemic_days,
    weekday_real,
)


def _detail(n_resto: int = 4) -> pd.DataFrame:
    """Frame detail sintetis: item MIE dilaporkan semua resto; beda TOTAL."""
    rows = []
    for r in range(n_resto):
        rows.append({
            "NAMA RESTO": f"R{r}", "NAMA BARANG": "MIE", "JENIS": "WASTE",
            "KETERANGAN": "Handling", "SOURCE DATA": "W",
            "SATUAN": "GR", "TOTAL": float(100 + 10 * r),
            "TOTAL BOM": 10_000.0, "Count Hari": 25,
        })
    return pd.DataFrame(rows)


# ============================================================
# [A] RESTO INTENSITY
# ============================================================

class TestRestoIntensity:
    def test_kolom_dan_median(self):
        df = _detail()
        out = resto_intensity(df)
        assert list(out.columns) == INTENSITY_COLS
        # 4 resto identik BOM, TOTAL 100/110/120/130 → median intensitas =
        # nilai tengah (115/10000); kelebihan hanya resto > median
        med = float(out["TIPIKAL CABANG %"].iloc[0])
        assert 1.0 < med < 1.3
        top = out.iloc[0]
        assert top["KELEBIHAN"] > 0

    def test_cabang_tanpa_bom_cek(self):
        df = _detail(n_resto=2)
        df.loc[df["NAMA RESTO"] == "R1", "TOTAL BOM"] = np.nan
        out = resto_intensity(df)
        r1 = out[out["NAMA RESTO"] == "R1"].iloc[0]
        assert "Cek" in str(r1["SATUAN CATATAN"])

    def test_defensif(self):
        assert resto_intensity(pd.DataFrame()).empty
        assert list(resto_intensity(pd.DataFrame()).columns) == INTENSITY_COLS
        no_bom = _detail().drop(columns=["TOTAL BOM"])
        assert resto_intensity(no_bom).empty


# ============================================================
# [B] MONEY RANKING
# ============================================================

class TestMoneyRanking:
    def _df(self):
        df = _detail(n_resto=4)
        df["KELEBIHAN"] = [50.0, -5.0, 200.0, np.nan]
        df["PEER MEDIAN (AKTIF)"] = [50.0, 115.0, 100.0, 1.0]
        df["PROFIL"] = "Tiap Hari"
        df["ANOMALY STATUS"] = "Perlu Review"
        return df

    def test_hanya_kelebihan_positif(self):
        out = money_ranking(self._df(), top_n=10)
        assert list(out.columns) == MONEY_COLS
        assert set(out["NAMA RESTO"]) == {"R0", "R2"}
        assert out.iloc[0]["NAMA RESTO"] == "R2"  # kelebihan 200 teratas

    def test_rasio_dan_top_n(self):
        out = money_ranking(self._df(), top_n=1)
        assert len(out) == 1
        # R2: TOTAL 120 ÷ tipikal 100 = 1,2×
        assert out.iloc[0]["RASIO"] == pytest.approx(1.2)

    def test_defensif(self):
        df = _detail()  # tanpa kolom KELEBIHAN
        assert money_ranking(df).empty
        assert list(money_ranking(df).columns) == MONEY_COLS


# ============================================================
# [C] COVERAGE REPORT (detektor input kosong)
# ============================================================

def _cov_df() -> pd.DataFrame:
    """5 cabang; item MIE + NASI umum (dilaporkan 4/5); R4 tak input."""
    rows = []
    for r in ["R1", "R2", "R3", "R5"]:
        for it in ("MIE", "NASI"):
            rows.append({"NAMA RESTO": r, "NAMA BARANG": it,
                         "TOTAL": 10.0})
    rows.append({"NAMA RESTO": "R4", "NAMA BARANG": "MIE",
                 "TOTAL": 0.0})   # R4 nol utk MIE
    return pd.DataFrame(rows)


def _month(pairs: list[tuple[str, str]]) -> dict:
    agg = pd.DataFrame(pairs, columns=["NAMA RESTO", "NAMA BARANG"])
    agg["TOTAL"] = 10.0
    return {"label": "Agustus 2026", "agg": agg, "error": None}


class TestCoverageReport:
    def test_tak_input_tanpa_pembanding(self):
        out = coverage_report(_cov_df())
        assert list(out.columns) == COVERAGE_COLS
        r4 = out[out["NAMA RESTO"] == "R4"].iloc[0]
        assert r4["ITEM UMUM TAK INPUT"] >= 2  # MIE + NASI
        assert r4["STATUS INPUT"] == "Perlu Pembanding"
        r1 = out[out["NAMA RESTO"] == "R1"].iloc[0]
        assert r1["STATUS INPUT"] == "Lengkap"

    def test_berhenti_input_vs_memang_tak_pernah(self):
        df = _cov_df()
        # pembanding: R4 dulu AKTIF utk MIE (berhenti), NASI memang tak pernah
        months = [_month([("R1", "MIE"), ("R1", "NASI"), ("R4", "MIE")])]
        out = coverage_report(df, months)
        r4 = out[out["NAMA RESTO"] == "R4"].iloc[0]
        assert r4["STATUS INPUT"] == "Berhenti Input"
        assert "MIE" in str(r4["CONTOH ITEM"])

    def test_min_share_100_persen(self):
        out = coverage_report(_cov_df(), min_share=1.0)
        # semua item umum harus 5/5 → MIE & NASI bukan item umum → Lengkap
        assert (out["STATUS INPUT"] == "Lengkap").all()

    def test_defensif(self):
        assert coverage_report(pd.DataFrame()).empty
        no_resto = pd.DataFrame({"NAMA BARANG": ["MIE"], "TOTAL": [1.0]})
        assert coverage_report(no_resto).empty


# ============================================================
# [D] SYSTEMIC DAYS
# ============================================================

def _sys_df(n_resto: int = 20, spike_day: int = 5, spike_n: int = 6) -> pd.DataFrame:
    rows = []
    for r in range(n_resto):
        base = {"NAMA RESTO": f"R{r:02d}"}
        for d in range(1, 31):
            base[str(d)] = 10.0
        if r < spike_n:
            base[str(spike_day)] = 100.0  # ≥ 2× median cabang
        rows.append(base)
    return pd.DataFrame(rows)


class TestSystemicDays:
    def test_hari_sistemik_terdeteksi(self):
        out = systemic_days(_sys_df(), key_akhir=30)
        assert list(out.columns) == SYSTEMIC_COLS
        assert len(out) == 1
        assert int(out.iloc[0]["HARI"]) == 5
        assert int(out.iloc[0]["N"]) == 6

    def test_sedikit_cabang_bukan_sistemik(self):
        out = systemic_days(_sys_df(spike_n=2), key_akhir=30)
        assert out.empty  # 2 < threshold 3

    def test_defensif(self):
        assert systemic_days(pd.DataFrame()).empty
        no_resto = pd.DataFrame({"TOTAL": [1.0]})
        assert systemic_days(no_resto).empty


# ============================================================
# [E] WEEKDAY ASLI
# ============================================================

class TestWeekdayReal:
    def test_parse_label(self):
        assert parse_month_label("September 2026") == (2026, 9)
        assert parse_month_label("AGUSTUS 2026") == (2026, 8)
        assert parse_month_label("01-31 Desember 2026") == (2026, 12)
        assert parse_month_label("tanpa tahun") is None
        assert parse_month_label(None) is None

    def test_weekday_urut_senin_minggu(self):
        df = pd.DataFrame({str(d): [10.0] for d in range(1, 31)})
        out = weekday_real(df, "September 2026", key_akhir=31)
        assert list(out.columns) == WEEKDAY_COLS
        # September 2026: 1 Sep = Selasa; 30 hari → Senin 4, Selasa 5 dst
        selasa = out[out["HARI"] == "Selasa"].iloc[0]
        assert int(selasa["N HARI"]) == 5
        senin = out[out["HARI"] == "Senin"].iloc[0]
        assert int(senin["N HARI"]) == 4
        # hari 31 tidak ada pada bulan 30 hari
        assert out["N HARI"].sum() == 30

    def test_label_invalid_kosong(self):
        df = pd.DataFrame({str(d): [10.0] for d in range(1, 31)})
        assert weekday_real(df, "xxx").empty
        assert list(weekday_real(df, None).columns) == WEEKDAY_COLS


# ============================================================
# [F] SCORECARD KOMPOSIT
# ============================================================

class TestScorecard:
    def test_kolom_dan_rank(self):
        df = _detail(n_resto=4)
        out = scorecard(df, None, 31, {})
        assert list(out.columns) == SCORECARD_COLS
        assert list(out["RANK"]) == [1, 2, 3, 4]
        # tanpa pembanding: BARU/PULIH di-nol-kan (jujur)
        assert (out["BARU"] == 0).all() and (out["PULIH"] == 0).all()
        # resto kelebihan terbesar = RANK 1
        assert out.iloc[0]["NAMA RESTO"] == "R3"

    def test_dengan_pembanding_baru_pulih(self):
        df = _detail(n_resto=4)
        months = [_month([("R0", "MIE"), ("R1", "MIE")])]
        out = scorecard(df, months, 31, {})
        by = {r: row for r, row in zip(out["NAMA RESTO"],
                                      out.to_dict("records"))}
        assert by["R0"]["BARU"] == 0 and by["R0"]["PULIH"] == 0
        assert by["R2"]["BARU"] == 1   # aktif sekarang, absen pembanding
        assert by["R3"]["BARU"] == 1
        assert by["R1"]["PULIH"] == 0  # R1 aktif dua-duanya
        # tidak ada pembanding aktif utk R2/R3 → tidak ada pulih utk mereka

    def test_alasan_dominan_dan_tersangka(self):
        df = _detail(n_resto=2)
        df["KETERANGAN"] = ["Handling", "Kualitas"]
        df["BUKTI HARI"] = ["YES", "NO"]
        df["ANOMALY STATUS"] = ["Potensi Anomali", "Normal"]
        df["PROFIL"] = ["Tiap Hari", "Kadang"]
        out = scorecard(df, None, 31, {})
        by = {r: row for r, row in zip(out["NAMA RESTO"],
                                      out.to_dict("records"))}
        assert "Handling" in by["R0"]["ALASAN DOMINAN"]
        assert by["R0"]["HARI TERSANGKA"] == 1
        assert by["R0"]["ANOMALI"] == 1
        assert by["R0"]["ITEM TIAP HARI"] == 1

    def test_defensif(self):
        assert scorecard(pd.DataFrame()).empty
        assert list(scorecard(pd.DataFrame()).columns) == SCORECARD_COLS


# ============================================================
# [G] DATA ASLI (golden ringan)
# ============================================================

FIXTURE = REPO / "DATA_WASTE.xlsx"
PEMBANDING = REPO / "REKAP MENTAH_01-31 AGUSTUS 2026_TEGAR.xlsx"


@pytest.fixture(scope="module")
def real() -> dict:
    from waste_anomaly.period_history import load_history_file
    from waste_anomaly.pipeline import run_pipeline
    from waste_anomaly.utils import load_config
    s = run_pipeline(workbook_path=str(FIXTURE), key_akhir=31)
    assert s.get("success") is True
    months = []
    if PEMBANDING.exists():
        months = [load_history_file(str(PEMBANDING), load_config())]
    return {"df": s["df"], "months": months}


@pytest.mark.skipif(not FIXTURE.exists(), reason="fixture tidak ada")
class TestDataAsli:
    def test_intensity_rank1_kwggal(self, real):
        out = resto_intensity(real["df"])
        assert out.iloc[0]["NAMA RESTO"] == "1042.KWGGAL"
        assert out.iloc[0]["KELEBIHAN"] > 250_000

    def test_money_top_surai_naga(self, real):
        out = money_ranking(real["df"], top_n=10)
        assert "SURAI NAGA (V.30)" in str(out.iloc[0]["NAMA BARANG"])

    def test_coverage_mlgpar_35(self, real):
        out = coverage_report(real["df"], real["months"])
        ml = out[out["NAMA RESTO"] == "B.1001.MLGPAR"].iloc[0]
        assert int(ml["ITEM UMUM TAK INPUT"]) == 35

    def test_systemic_nol(self, real):
        assert systemic_days(real["df"], 31).empty

    def test_scorecard_20_resto_rank_utuh(self, real):
        out = scorecard(real["df"], real["months"], 31, {})
        assert len(out) == 20
        assert list(out["RANK"]) == list(range(1, 21))
        assert out.iloc[0]["NAMA RESTO"] == "1042.KWGGAL"
