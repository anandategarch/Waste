"""Unit + smoke test — waste_anomaly.temporal (v2.5.0 "analisa temporal").

Lapisan (sintetis, cepat — pola test_signals.py):
1. waste_per_day        — agregat per hari (NaN, key_akhir, kolom terloncat).
2. weekday_pattern      — pola kelas mod-7 + aritmetika ratio_vs_mean.
3. weekday_effect       — pasangan kelas berdampingan (siklik 6-0-1-...).
4. reason_by_day        — matrix KETERANGAN x hari + Lainnya + header INT.
5. reason_weekday_ratio — efek peak-day per KETERANGAN (eksplisit & auto).
6. unit_summary         — normalisasi SATUAN NBSP/zero-width + share_pct.
7. TestDefensif         — df kosong / kolom hilang -> hasil kosong, no raise.
8. TestRealWorkbookSmoke — fixture ASLI DATA_WASTE.xlsx (read-only ~5-8 s),
   pola test_pipeline_regression.py: konsistensi TOTAL, rasio weekend +35%,
   dominasi GR.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from waste_anomaly.temporal import (
    _day_cols,
    reason_by_day,
    reason_weekday_ratio,
    unit_summary,
    waste_per_day,
    weekday_effect,
    weekday_pattern,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = REPO_ROOT / "DATA_WASTE.xlsx"

COLS_WPD = ["day", "total", "active_rows", "mean_per_active"]
COLS_WKP = [
    "mod_class", "days", "total", "active_rows", "mean_per_active", "ratio_vs_mean",
]
COLS_RWR = ["KETERANGAN", "peak_mean", "offpeak_mean", "ratio", "total"]
COLS_UNIT = [
    "SATUAN", "rows", "active_rows", "items", "total", "share_pct", "raw_values",
]

DEGENERATE_EFFECT = {
    "peak_classes": None,
    "peak_mean": 0.0,
    "offpeak_mean": 0.0,
    "ratio": None,
}


def make_frame(**cols) -> pd.DataFrame:
    """Frame sintetis dari kolom (nilai list per kolom) — tanpa fixture file."""
    return pd.DataFrame({k: list(v) for k, v in cols.items()})


# ============================================================
# HELPER _day_cols
# ============================================================

class TestDayColsHelper:
    def test_urut_int_nuansa_string(self):
        df = make_frame(**{"31": [1.0], "2": [1.0], "10": [1.0], "TOTAL": [1.0]})
        assert _day_cols(df) == ["2", "10", "31"]

    def test_kolom_bukan_hari_diabaikan(self):
        df = make_frame(AVG=[1.0], TOTAL=[1.0], MAX=[1.0], x=[1.0])
        assert _day_cols(df) == []

    def test_header_int_dinormalisasi_string(self):
        df = pd.DataFrame({1: [1.0], "2": [1.0], "TOTAL": [1.0]})
        assert _day_cols(df) == ["1", "2"]

    def test_df_kosong(self):
        assert _day_cols(pd.DataFrame()) == []


# ============================================================
# 1. waste_per_day
# ============================================================

class TestWastePerDay:
    def test_totals_dengan_nan_dan_negatif(self):
        df = make_frame(**{
            "1": [10.0, np.nan, -2.0],
            "2": [np.nan, 4.0, np.nan],
            "3": [5.0, 0.0, np.nan],
        })
        res = waste_per_day(df)
        assert list(res.columns) == COLS_WPD
        assert res["day"].tolist() == [1, 2, 3]
        # total = sum kolom (NaN=0, negatif ikut dijumlah);
        # active_rows hanya nilai > 0 (0 dan -2 tidak aktif)
        assert res["total"].tolist() == [8.0, 4.0, 5.0]
        assert res["active_rows"].tolist() == [1, 1, 1]
        assert res["mean_per_active"].tolist() == [8.0, 4.0, 5.0]
        assert pd.api.types.is_integer_dtype(res["day"])
        assert pd.api.types.is_integer_dtype(res["active_rows"])
        assert pd.api.types.is_float_dtype(res["total"])

    def test_key_akhir_membatasi_hari(self):
        df = make_frame(**{
            "1": [10.0], "2": [4.0], "3": [5.0], "4": [6.0], "5": [7.0],
        })
        assert waste_per_day(df, key_akhir=3)["day"].tolist() == [1, 2, 3]
        assert waste_per_day(df, key_akhir=1)["day"].tolist() == [1]

    def test_key_akhir_melebihi_data_tetap_aman(self):
        df = make_frame(**{"1": [10.0], "2": [4.0]})
        res = waste_per_day(df, key_akhir=99)
        assert res["day"].tolist() == [1, 2]  # hanya kolom yang ada

    def test_df_kosong(self):
        res = waste_per_day(pd.DataFrame())
        assert list(res.columns) == COLS_WPD
        assert len(res) == 0

    def test_tanpa_kolom_hari(self):
        res = waste_per_day(make_frame(TOTAL=[1.0], AVG=[2.0]))
        assert list(res.columns) == COLS_WPD
        assert len(res) == 0

    def test_kolom_hari_terloncat_hanya_yang_ada(self):
        # hanya '1', '2', '5' — hari 3/4 tidak dibuat nol
        df = make_frame(**{"1": [1.0], "2": [2.0], "5": [5.0]})
        res = waste_per_day(df)
        assert res["day"].tolist() == [1, 2, 5]
        assert waste_per_day(df, key_akhir=4)["day"].tolist() == [1, 2]

    def test_kolom_all_nan(self):
        res = waste_per_day(make_frame(**{"1": [np.nan], "2": [np.nan]}))
        assert res["total"].tolist() == [0.0, 0.0]
        assert res["active_rows"].tolist() == [0, 0]
        assert res["mean_per_active"].tolist() == [0.0, 0.0]


# ============================================================
# 2. weekday_pattern
# ============================================================

class TestWeekdayPattern:
    def test_pola_lengkap_per_kelas(self):
        df = make_frame(**{
            "1": [10.0, np.nan],
            "2": [20.0, np.nan],
            "5": [30.0, 60.0],
            "6": [15.0, np.nan],
            "7": [10.0, np.nan],
        })
        res = weekday_pattern(df)
        assert list(res.columns) == COLS_WKP
        # kelas tanpa hari (3, 4) tidak jadi baris
        assert res["mod_class"].tolist() == [0, 1, 2, 5, 6]
        assert res["days"].tolist() == ["7", "1", "2", "5", "6"]
        assert res["total"].tolist() == [10.0, 10.0, 20.0, 90.0, 15.0]
        assert res["active_rows"].tolist() == [1, 1, 1, 2, 1]
        assert res["mean_per_active"].tolist() == [10.0, 10.0, 20.0, 45.0, 15.0]
        # overall = 145 total / 6 aktif; ratio = mean / overall
        overall = 145.0 / 6.0
        expected = [10.0 / overall, 10.0 / overall, 20.0 / overall,
                    45.0 / overall, 15.0 / overall]
        assert res["ratio_vs_mean"].tolist() == pytest.approx(expected)

    def test_format_string_days(self):
        df = make_frame(**{
            "5": [1.0], "12": [1.0], "19": [1.0], "26": [1.0],
        })
        res = weekday_pattern(df)
        kelas5 = res[res["mod_class"] == 5]
        assert kelas5["days"].iloc[0] == "5, 12, 19, 26"

    def test_key_akhir_membatasi_kelas(self):
        df = make_frame(**{
            "1": [10.0], "2": [20.0], "5": [30.0], "6": [15.0], "7": [10.0],
        })
        res = weekday_pattern(df, key_akhir=1)
        assert res["mod_class"].tolist() == [1]
        assert res["ratio_vs_mean"].iloc[0] == pytest.approx(1.0)

    def test_penyebut_nol_ratio_nol(self):
        # tidak ada baris aktif sama sekali -> denominator 0 -> ratio 0
        res = weekday_pattern(make_frame(**{"1": [0.0], "2": [np.nan]}))
        assert res["total"].tolist() == [0.0, 0.0]
        assert res["ratio_vs_mean"].tolist() == [0.0, 0.0]

    def test_df_kosong_dan_tanpa_hari(self):
        for frame in (pd.DataFrame(), make_frame(TOTAL=[1.0])):
            res = weekday_pattern(frame)
            assert list(res.columns) == COLS_WKP
            assert len(res) == 0


# ============================================================
# 3. weekday_effect
# ============================================================

class TestWeekdayEffect:
    def test_peak_3x_kelas_5_6(self):
        # hari ≡ 5,6 (mod 7) = 30; hari lain = 10 -> rasio 3
        df = make_frame(**{
            "1": [10.0], "2": [10.0], "3": [10.0], "4": [10.0], "5": [30.0],
            "6": [30.0], "7": [10.0], "8": [10.0], "9": [10.0], "10": [10.0],
            "11": [10.0], "12": [30.0], "13": [30.0],
        })
        eff = weekday_effect(df)
        assert eff["peak_classes"] == (5, 6)
        assert eff["peak_mean"] == pytest.approx(30.0)
        assert eff["offpeak_mean"] == pytest.approx(10.0)
        assert eff["ratio"] == pytest.approx(3.0)

    def test_pasangan_siklik_6_0(self):
        # pasangan berdampingan melewati batas siklik: (6, 0) = hari 6 & 7
        df = make_frame(**{"1": [10.0], "2": [10.0], "6": [30.0], "7": [30.0]})
        eff = weekday_effect(df)
        assert eff["peak_classes"] == (6, 0)
        assert eff["ratio"] == pytest.approx(3.0)

    def test_kelas_tunggal_peak_none(self):
        # semua hari kelas 0 (7, 14) -> <2 kelas -> peak None
        eff = weekday_effect(make_frame(**{"7": [10.0], "14": [20.0]}))
        assert eff["peak_classes"] is None
        assert eff["ratio"] is None

    def test_dua_kelas_berdampingan_saja_offpeak_nol(self):
        eff = weekday_effect(make_frame(**{"5": [30.0], "6": [30.0]}))
        assert eff["peak_classes"] == (5, 6)
        assert eff["peak_mean"] == pytest.approx(30.0)
        assert eff["offpeak_mean"] == 0.0
        assert eff["ratio"] is None  # offpeak 0 -> ratio None

    def test_dua_kelas_tidak_berdampingan_peak_none(self):
        # kelas 1 & 3 tidak berdampingan -> tidak ada pasangan valid
        eff = weekday_effect(make_frame(**{"1": [10.0], "3": [10.0]}))
        assert eff["peak_classes"] is None

    def test_df_kosong_dan_tanpa_hari(self):
        for frame in (pd.DataFrame(), make_frame(TOTAL=[1.0])):
            eff = weekday_effect(frame)
            assert eff == DEGENERATE_EFFECT

    def test_key_akhir_membatasi(self):
        df = make_frame(**{"1": [10.0], "2": [10.0], "3": [10.0], "5": [30.0]})
        eff = weekday_effect(df, key_akhir=3)
        # hari tersisa kelas 1,2,3 (semua mean 10) -> pasangan pertama (1, 2)
        assert eff["peak_classes"] == (1, 2)
        assert eff["ratio"] == pytest.approx(1.0)


# ============================================================
# 4. reason_by_day
# ============================================================

def _reason_fixture() -> pd.DataFrame:
    return make_frame(**{
        "KETERANGAN": ["A", "A", "B", "C", "D"],
        "1": [10.0, 5.0, 1.0, np.nan, 2.0],
        "2": [np.nan, 5.0, 1.0, 3.0, np.nan],
        "3": [7.0, np.nan, np.nan, np.nan, np.nan],
    })


class TestReasonByDay:
    def test_agregasi_plus_lainnya(self):
        res = reason_by_day(_reason_fixture(), top_n=2)
        # Total: A=27, C=3, B=2, D=2 -> top 2 = A, C; sisa B+D -> Lainnya
        assert res["KETERANGAN"].tolist() == ["A", "C", "Lainnya"]
        a = res.iloc[0]
        assert (a[1], a[2], a[3], a["Total"]) == (15.0, 5.0, 7.0, 27.0)
        c = res.iloc[1]
        assert (c[1], c[2], c[3], c["Total"]) == (0.0, 3.0, 0.0, 3.0)  # NaN -> 0
        lainnya = res.iloc[2]
        assert (lainnya[1], lainnya[2], lainnya[3]) == (3.0, 1.0, 0.0)
        assert lainnya["Total"] == 4.0

    def test_lainnya_selalu_terakhir_walau_total_lebih_besar(self):
        res = reason_by_day(_reason_fixture(), top_n=2)
        # Lainnya total 4 > C total 3, tetapi tetap baris terakhir
        assert res.iloc[-1]["KETERANGAN"] == "Lainnya"
        assert res["Total"].iloc[0] == 27.0  # sort Total desc di top

    def test_header_hari_int_bukan_string(self):
        res = reason_by_day(_reason_fixture(), top_n=2)
        assert list(res.columns) == ["KETERANGAN", 1, 2, 3, "Total"]
        day_headers = [c for c in res.columns if c not in ("KETERANGAN", "Total")]
        assert all(isinstance(c, int) for c in day_headers)
        assert not any(isinstance(c, str) and c.isdigit() for c in res.columns)
        assert pd.api.types.is_float_dtype(res[1])

    def test_top_n_dihormati(self):
        res = reason_by_day(_reason_fixture(), top_n=3)
        # A(27), C(3), B(2) — tie B/D dipecah stabil (alfabetis); sisa D
        assert res["KETERANGAN"].tolist() == ["A", "C", "B", "Lainnya"]
        assert res.iloc[-1]["Total"] == 2.0
        assert len(res) == 4

    def test_top_n_melebihi_jumlah_group_tanpa_lainnya(self):
        res = reason_by_day(_reason_fixture(), top_n=10)
        assert res["KETERANGAN"].tolist() == ["A", "C", "B", "D"]
        assert "Lainnya" not in res["KETERANGAN"].values

    def test_key_akhir_membatasi_kolom_hari(self):
        res = reason_by_day(_reason_fixture(), key_akhir=2, top_n=2)
        assert list(res.columns) == ["KETERANGAN", 1, 2, "Total"]
        assert res.iloc[0]["Total"] == 20.0  # A: 10+5+5 (hari 3 terpotong)
        lainnya = res.iloc[-1]
        assert (lainnya[1], lainnya[2], lainnya["Total"]) == (3.0, 1.0, 4.0)

    def test_df_kosong_kolom_minimal(self):
        res = reason_by_day(pd.DataFrame())
        assert list(res.columns) == ["KETERANGAN", "Total"]
        assert len(res) == 0

    def test_tanpa_kolom_keterangan(self):
        res = reason_by_day(make_frame(**{"1": [1.0], "2": [2.0]}))
        assert list(res.columns) == ["KETERANGAN", 1, 2, "Total"]
        assert len(res) == 0

    def test_tanpa_kolom_hari(self):
        res = reason_by_day(make_frame(KETERANGAN=["A", "B"]))
        assert list(res.columns) == ["KETERANGAN", "Total"]
        assert len(res) == 0


# ============================================================
# 5. reason_weekday_ratio
# ============================================================

def _ratio_fixture() -> pd.DataFrame:
    return make_frame(**{
        "KETERANGAN": ["A", "B", "C"],
        "5": [100.0, 60.0, np.nan],
        "6": [100.0, np.nan, np.nan],
        "7": [50.0, np.nan, np.nan],
        "8": [50.0, np.nan, np.nan],
    })


class TestReasonWeekdayRatio:
    # v2.5.1: default min_active=30 menyembunyikan kategori sampel-kecil
    # (rasio artefak); test matemika rasio di bawah memakai min_active=0
    # (perilaku lama) supaya tetap menguji rumus, bukan filter.

    def test_peak_eksplisit(self):
        res = reason_weekday_ratio(
            _ratio_fixture(), peak_classes=(5, 6), min_active=0)
        assert list(res.columns) == COLS_RWR
        # A: peak (100+100)/2, offpeak (50+50)/2 -> ratio 2.0
        a = res.iloc[0]
        assert a["KETERANGAN"] == "A"
        assert a["peak_mean"] == pytest.approx(100.0)
        assert a["offpeak_mean"] == pytest.approx(50.0)
        assert a["ratio"] == pytest.approx(2.0)
        assert a["total"] == pytest.approx(300.0)

    def test_ratio_nan_bila_offpeak_nol_dan_sort_desc(self):
        res = reason_weekday_ratio(
            _ratio_fixture(), peak_classes=(5, 6), min_active=0)
        # B aktif hanya di hari peak -> offpeak 0 -> NaN; C tanpa waste -> NaN
        assert res["KETERANGAN"].tolist() == ["A", "B", "C"]
        assert np.isnan(res.iloc[1]["ratio"])  # B
        assert np.isnan(res.iloc[2]["ratio"])  # C (NaN paling akhir)
        assert res.iloc[1]["peak_mean"] == pytest.approx(60.0)
        assert res.iloc[1]["total"] == pytest.approx(60.0)
        assert res.iloc[2]["total"] == 0.0

    def test_auto_detect_sama_dengan_eksplisit(self):
        # weekday_effect pada fixture ini menemukan (5, 6) secara otomatis
        eksplisit = reason_weekday_ratio(
            _ratio_fixture(), peak_classes=(5, 6), min_active=0)
        otomatis = reason_weekday_ratio(_ratio_fixture(), min_active=0)
        assert_frame_equal(eksplisit, otomatis)

    def test_urutan_ratio_desc(self):
        df = make_frame(**{
            "KETERANGAN": ["X", "Y", "Z"],
            "5": [30.0, 90.0, 60.0],  # kelas 5 = peak
            "7": [30.0, 30.0, 30.0],  # kelas 0 = offpeak
        })
        res = reason_weekday_ratio(df, peak_classes=(5, 6), min_active=0)
        assert res["KETERANGAN"].tolist() == ["Y", "Z", "X"]  # 3.0, 2.0, 1.0
        assert res["ratio"].tolist() == pytest.approx([3.0, 2.0, 1.0])

    def test_min_active_default_menyembunyikan_kategori_kecil(self):
        """v2.5.1 (TE-M3): kategori < 30 entri aktif disembunyikan dari tabel
        rasio (rasio sampel-kecil = artefak) — kategori besar tetap tampil."""
        rows = []
        # 'Besar': 40 baris × 2 hari aktif = 80 entri aktif (>= 30)
        for _ in range(40):
            rows.append({"KETERANGAN": "Besar", "5": 100.0, "7": 50.0})
        # 'Kecil': 3 baris × 2 hari aktif = 6 entri aktif (< 30)
        for _ in range(3):
            rows.append({"KETERANGAN": "Kecil", "5": 100.0, "7": 50.0})
        df = pd.DataFrame(rows)

        res_default = reason_weekday_ratio(df, peak_classes=(5, 6))
        assert res_default["KETERANGAN"].tolist() == ["Besar"]

        res_all = reason_weekday_ratio(df, peak_classes=(5, 6), min_active=0)
        assert res_all["KETERANGAN"].tolist() == ["Besar", "Kecil"]
        # rasio kategori kecil identik dengan yang besar (data sama) —
        # artefak inilah yang disembunyikan default
        assert res_all["ratio"].tolist() == pytest.approx([2.0, 2.0])

    def test_df_kosong_tanpa_keterangan_tanpa_hari(self):
        frames = [
            pd.DataFrame(),
            make_frame(**{"5": [1.0], "6": [1.0]}),
            make_frame(KETERANGAN=["A"]),
        ]
        for frame in frames:
            res = reason_weekday_ratio(frame)
            assert list(res.columns) == COLS_RWR
            assert len(res) == 0

    def test_auto_detect_gagal_semua_hari_offpeak(self):
        # 1 kelas saja -> peak None -> semua hari dianggap offpeak, ratio 0
        df = make_frame(**{"KETERANGAN": ["A"], "7": [10.0]})
        res = reason_weekday_ratio(df, min_active=0)
        assert res["KETERANGAN"].tolist() == ["A"]
        assert res["peak_mean"].iloc[0] == 0.0
        assert res["offpeak_mean"].iloc[0] == pytest.approx(10.0)
        assert res["ratio"].iloc[0] == 0.0


# ============================================================
# 6. unit_summary
# ============================================================

class TestUnitSummary:
    def test_nbsp_dan_zero_width_collapse(self):
        # 'PACK\xa0' + 'PACK' -> SATU baris 'PACK'; 'GR\u200b' + 'GR' -> 'GR'
        df = make_frame(**{
            "SATUAN": ["PACK\xa0", "GR", "PACK", "GR\u200b", "GR", None],
            "NAMA BARANG": ["item1", "item2", "item1", "item3", "item2", "item4"],
            "TOTAL": [100.0, 500.0, 200.0, 300.0, 0.0, 50.0],
        })
        res = unit_summary(df)
        assert list(res.columns) == COLS_UNIT
        assert res["SATUAN"].tolist() == ["GR", "PACK", "(kosong)"]  # sort total desc

        pack = res[res["SATUAN"] == "PACK"].iloc[0]
        assert pack["rows"] == 2
        assert pack["items"] == 1
        assert pack["total"] == 300.0
        # raw_values menyebut kedua nilai asli (NBSP dan tanpa NBSP)
        assert set(pack["raw_values"].split("; ")) == {"PACK\xa0", "PACK"}

        gr = res[res["SATUAN"] == "GR"].iloc[0]
        assert gr["rows"] == 3
        assert gr["active_rows"] == 2  # TOTAL=0 tidak aktif
        assert gr["items"] == 2
        assert gr["total"] == 800.0
        assert set(gr["raw_values"].split("; ")) == {"GR", "GR\u200b"}

        kosong = res[res["SATUAN"] == "(kosong)"].iloc[0]
        assert kosong["rows"] == 1
        assert kosong["total"] == 50.0
        assert kosong["raw_values"] == ""

    def test_share_pct_jumlah_100(self):
        df = make_frame(SATUAN=["GR", "PCS"], TOTAL=[700.0, 300.0])
        res = unit_summary(df)
        assert res["share_pct"].sum() == pytest.approx(100.0)
        assert res["share_pct"].tolist() == pytest.approx([70.0, 30.0])

    def test_share_pct_nol_bila_total_nol(self):
        res = unit_summary(make_frame(SATUAN=["GR"], TOTAL=[0.0]))
        assert res["share_pct"].tolist() == [0.0]

    def test_tanpa_nama_barang_items_nol(self):
        res = unit_summary(make_frame(SATUAN=["GR", "GR"], TOTAL=[10.0, 20.0]))
        assert res["items"].tolist() == [0]
        assert res["total"].tolist() == [30.0]
        assert res["rows"].tolist() == [2]

    def test_df_kosong_dan_kolom_wajib_hilang(self):
        frames = [
            pd.DataFrame(),
            make_frame(TOTAL=[1.0]),            # SATUAN hilang
            make_frame(SATUAN=["GR"]),          # TOTAL hilang
        ]
        for frame in frames:
            res = unit_summary(frame)
            assert list(res.columns) == COLS_UNIT
            assert len(res) == 0


# ============================================================
# 7. DEFENSIF — semua fungsi, df kosong / kolom hilang
# ============================================================

class TestDefensif:
    @pytest.mark.parametrize("func", [waste_per_day, weekday_pattern])
    def test_frame_return_kosong(self, func):
        res = func(pd.DataFrame())
        assert isinstance(res, pd.DataFrame)
        assert len(res) == 0

    def test_semua_fungsi_tidak_raise_df_kosong(self):
        # inti aturan: JANGAN raise, apa pun inputnya
        empty = pd.DataFrame()
        waste_per_day(empty)
        waste_per_day(empty, key_akhir=31)
        weekday_pattern(empty)
        weekday_effect(empty)
        reason_by_day(empty)
        reason_by_day(empty, top_n=3)
        reason_weekday_ratio(empty)
        reason_weekday_ratio(empty, peak_classes=(5, 6))
        unit_summary(empty)

    def test_semua_fungsi_tidak_raise_frame_aneh(self):
        # kolom ada tapi tidak relevan (tanpa hari/KETERANGAN/SATUAN)
        weird = make_frame(TOTAL=[1.0], AVG=[2.0], MAX=[3.0])
        assert len(waste_per_day(weird)) == 0
        assert len(weekday_pattern(weird)) == 0
        assert weekday_effect(weird) == DEGENERATE_EFFECT
        assert len(reason_by_day(weird)) == 0
        assert len(reason_weekday_ratio(weird)) == 0
        assert len(unit_summary(weird)) == 0

    def test_frame_nol_baris_dengan_kolom_hari(self):
        frame = pd.DataFrame({"KETERANGAN": [], "1": [], "2": [], "SATUAN": []})
        assert len(waste_per_day(frame)) == 0
        assert weekday_effect(frame) == DEGENERATE_EFFECT
        assert len(reason_by_day(frame)) == 0
        assert len(unit_summary(frame)) == 0


# ============================================================
# 8. SMOKE — fixture ASLI DATA_WASTE.xlsx (read-only, ~5-8 s)
#    (pola test_pipeline_regression.py: angka real mengunci kontrak modul)
# ============================================================

@pytest.mark.skipif(
    not FIXTURE.exists(), reason="fixture DATA_WASTE.xlsx tidak ada di repo"
)
class TestRealWorkbookSmoke:
    @pytest.fixture(scope="class")
    def real_df(self) -> pd.DataFrame:
        return pd.read_excel(FIXTURE, sheet_name="Sheet1")

    def test_jumlah_per_hari_cocok_kolom_total(self, real_df):
        per_day = waste_per_day(real_df, key_akhir=30)
        kolom_total = float(real_df["TOTAL"].sum())
        assert per_day["total"].sum() == pytest.approx(kolom_total, rel=1e-6)
        # TOTAL di workbook dihitung s.d. hari 30 (audit AUDIT-DATA); default
        # (tanpa key_akhir) menambah hari-31 nyasar: 2 baris aktif, total 65.
        default = waste_per_day(real_df)
        selisih = default["total"].sum() - per_day["total"].sum()
        assert selisih == pytest.approx(65.0, rel=1e-6)

    def test_weekday_effect_pola_weekend(self, real_df):
        eff = weekday_effect(real_df)
        assert eff["peak_classes"] == (5, 6)
        assert eff["ratio"] is not None
        assert eff["ratio"] > 1.2  # pola real +35% (369,7 vs 273,6)

    def test_unit_summary_gr_dominan_pack_nbsp(self, real_df):
        res = unit_summary(real_df)
        gr = res[res["SATUAN"] == "GR"]
        assert len(gr) == 1
        assert float(gr["total"].iloc[0]) > 1e6
        # temuan data-quality real: 'PACK\xa0' (2.033 baris) + 'PACK' collapse
        pack = res[res["SATUAN"] == "PACK"]
        assert len(pack) == 1
        assert "PACK\xa0" in pack["raw_values"].iloc[0]
        assert res["share_pct"].sum() == pytest.approx(100.0, rel=1e-6)
