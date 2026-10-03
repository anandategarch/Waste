"""Unit + smoke test — waste_anomaly.priority (money view + prioritas magnitude v2.5.0).

Mengunci kontrak yang dibaca ui/: urutan kolom output PERSIS, matematika
Share % / Kumulatif %, benchmark peer AKTIF (median tidak diracuni cabang
nol — akar masalah sinyal peer mati untuk event langka), profil alasan per
cabang, dan ranking SUSUT. Ditutup satu smoke test read-only pada
DATA_WASTE.xlsx asli (pola test_pipeline_regression).

Run:  python -m pytest tests/test_priority.py -v
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from waste_anomaly.priority import (
    BENCHMARK_ITEMS_COLUMNS,
    FOCUS_HIGH,
    FOCUS_MID,
    MAX_ANOMALY_SCORE,
    MONEY_VIEW_COLUMNS,
    REASON_PROFILE_STATIC_COLUMNS,
    SUSUT_BENCHMARK_COLUMNS,
    benchmark_items,
    focus_class,
    focus_score,
    money_view,
    reason_profile,
    reason_share,
    susut_benchmark,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = REPO_ROOT / "DATA_WASTE.xlsx"

DETAIL_COLUMNS = [
    "NAMA RESTO", "NAMA BARANG", "JENIS", "KETERANGAN", "SATUAN",
    "TOTAL", "MAX", "Count Hari", "ANOMALY SCORE", "ANOMALY STATUS",
]


def detail(rows: list[dict]) -> pd.DataFrame:
    """Frame detail sintetis — default kanonik, override via dict per baris."""
    defaults = {
        "NAMA RESTO": "R1", "NAMA BARANG": "ITEM A", "JENIS": "WASTE",
        "KETERANGAN": "Handling", "SATUAN": "GR", "TOTAL": 0.0,
        "MAX": 0.0, "Count Hari": 0, "ANOMALY SCORE": 0,
        "ANOMALY STATUS": "Normal",
    }
    merged = [dict(defaults, **row) for row in rows]
    return pd.DataFrame(merged, columns=DETAIL_COLUMNS)


def bench_frame(rows: list[tuple]) -> pd.DataFrame:
    """(item, resto, total) → frame minimal untuk benchmark_items."""
    return pd.DataFrame(rows, columns=["NAMA BARANG", "NAMA RESTO", "TOTAL"])


def reason_frame(rows: list[tuple]) -> pd.DataFrame:
    """(resto, keterangan, jenis, total) → frame reason_profile/share/susut."""
    return pd.DataFrame(
        rows, columns=["NAMA RESTO", "KETERANGAN", "JENIS", "TOTAL"]
    )


# ============================================================
# focus_score — 60% percentile magnitude + 40% anomali
# ============================================================

class TestFocusScore:
    def test_nilai_known_4_baris(self):
        # v2.5.1 (MO-M2): rank dihitung di SUBSET aktif (TOTAL > 0).
        # TOTAL [100, 50, 25, 0] → subset [100, 50, 25]: pct [100, 66.7, 33.3];
        # baris 0 → magnitude 0 (bukan percentile 25 seperti dulu).
        # skor  [19, 0, 9, nan]  → anomaly pct [100, 0, 900/19, 0]
        df = detail([
            {"TOTAL": 100.0, "ANOMALY SCORE": 19},
            {"TOTAL": 50.0, "ANOMALY SCORE": 0},
            {"TOTAL": 25.0, "ANOMALY SCORE": 9},
            {"TOTAL": 0.0, "ANOMALY SCORE": float("nan")},
        ])
        got = focus_score(df)
        assert list(got.index) == list(df.index)
        assert pd.api.types.is_float_dtype(got)
        assert got.iloc[0] == pytest.approx(0.6 * 100.0 + 0.4 * 100.0)
        assert got.iloc[1] == pytest.approx(0.6 * (2.0 / 3.0 * 100.0) + 0.0)
        assert got.iloc[2] == pytest.approx(
            0.6 * (1.0 / 3.0 * 100.0) + 0.4 * (9.0 / 19.0 * 100.0))
        # baris nol: magnitude 0 (rank subset aktif) + anomali 0 = 0
        assert got.iloc[3] == pytest.approx(0.0)

    def test_rank_subset_aktif_vs_full(self):
        """v2.5.1 (MO-M2): komponen magnitude berdaya-pembeda PENUH di antara
        baris aktif — dulu 23.470 baris nol mengkompresi semua baris aktif ke
        percentile 90,6–100 (rentang efektif 5,4 poin dari budget 60)."""
        # 100 baris nol + 10 baris aktif bernilai berbeda
        rows = [{"TOTAL": 0.0, "ANOMALY SCORE": 0} for _ in range(100)]
        rows += [{"TOTAL": float(v), "ANOMALY SCORE": 0}
                 for v in range(1, 11)]
        df = detail(rows)
        got = focus_score(df)
        active_scores = got.iloc[100:]
        # baris aktif terkecil (TOTAL=1) → magnitude ~0 (bukan 90,6!)
        assert active_scores.iloc[0] < 10.0
        # baris aktif terbesar → magnitude 60 penuh
        assert active_scores.iloc[-1] == pytest.approx(60.0)
        # rentang magnitude efektif ~54 dari 60 (dulu hanya 5,4 poin)
        assert (active_scores.max() - active_scores.min()) > 50.0

    def test_skor_melebihi_max_diklip(self):
        # ANOMALY SCORE di luar 0..MAX tetap menghasilkan komponen 0..100
        df = detail([{"TOTAL": 100.0, "ANOMALY SCORE": MAX_ANOMALY_SCORE + 50}])
        assert focus_score(df).iloc[0] == pytest.approx(100.0)

    def test_total_nan_magnitude_nol(self):
        df = detail([
            {"TOTAL": 100.0, "ANOMALY SCORE": 19},
            {"TOTAL": float("nan"), "ANOMALY SCORE": 19},
        ])
        got = focus_score(df)
        assert got.iloc[0] == pytest.approx(100.0)
        # magnitude NaN → 0, sisanya 40% anomali
        assert got.iloc[1] == pytest.approx(0.4 * 100.0)

    def test_kolom_anomaly_score_hilang(self):
        df = pd.DataFrame({"TOTAL": [100.0, 50.0]})
        got = focus_score(df)
        assert got.iloc[0] == pytest.approx(60.0)
        assert got.iloc[1] == pytest.approx(30.0)

    def test_kolom_total_hilang(self):
        df = pd.DataFrame({"ANOMALY SCORE": [19, 0]})
        got = focus_score(df)
        assert got.iloc[0] == pytest.approx(40.0)
        assert got.iloc[1] == pytest.approx(0.0)

    def test_rentang_0_100(self):
        rng = np.random.default_rng(20240501)
        df = pd.DataFrame({
            "TOTAL": rng.choice([0.0, 5.0, 50.0, 500.0, float("nan")], size=50),
            "ANOMALY SCORE": rng.integers(-3, 25, size=50),
        })
        got = focus_score(df)
        assert (got >= 0.0).all()
        assert (got <= 100.0).all()

    def test_index_sejajar_df(self):
        df = detail([{"TOTAL": 100.0}, {"TOTAL": 50.0}])
        df.index = ["x9", "y7"]
        assert list(focus_score(df).index) == ["x9", "y7"]

    def test_df_kosong(self):
        got = focus_score(pd.DataFrame())
        assert len(got) == 0
        assert pd.api.types.is_float_dtype(got)


# ============================================================
# focus_class — batas kelas
# ============================================================

class TestFocusClass:
    def test_persis_70_fokus_utama(self):
        assert focus_class(70.0) == "Fokus Utama"
        assert focus_class(FOCUS_HIGH) == "Fokus Utama"

    def test_69_99_fokus_sekunder(self):
        assert focus_class(69.99) == "Fokus Sekunder"

    def test_persis_50_fokus_sekunder(self):
        assert focus_class(50.0) == "Fokus Sekunder"
        assert focus_class(FOCUS_MID) == "Fokus Sekunder"

    def test_49_9_rutin(self):
        assert focus_class(49.9) == "Rutin"

    def test_ekstrem(self):
        assert focus_class(100.0) == "Fokus Utama"
        assert focus_class(0.0) == "Rutin"


# ============================================================
# money_view — Pareto magnitude baris terbesar
# ============================================================

class TestMoneyView:
    @pytest.fixture()
    def frame(self) -> pd.DataFrame:
        # penyebut Share = 150 (baris TOTAL=0 dan NaN dihitung di penyebut
        # sum seluruh df, tapi tidak masuk view)
        return detail([
            {"NAMA RESTO": "R1", "NAMA BARANG": "A", "TOTAL": 100.0,
             "ANOMALY SCORE": 19, "ANOMALY STATUS": "Prioritas Tinggi"},
            {"NAMA RESTO": "R2", "NAMA BARANG": "B", "TOTAL": 50.0,
             "ANOMALY SCORE": 0, "ANOMALY STATUS": "Normal"},
            {"NAMA RESTO": "R3", "NAMA BARANG": "C", "TOTAL": 0.0,
             "ANOMALY SCORE": 5, "ANOMALY STATUS": "Perlu Review"},
            {"NAMA RESTO": "R4", "NAMA BARANG": "D", "TOTAL": float("nan"),
             "ANOMALY SCORE": 2, "ANOMALY STATUS": "Normal"},
        ])

    def test_share_dan_kumulatif(self, frame):
        mv = money_view(frame)
        assert len(mv) == 2
        assert "R3" not in mv["NAMA RESTO"].tolist()
        assert "R4" not in mv["NAMA RESTO"].tolist()
        assert mv["Share %"].tolist() == pytest.approx(
            [100.0 / 150.0 * 100.0, 50.0 / 150.0 * 100.0]
        )
        assert mv["Kumulatif %"].tolist() == pytest.approx(
            [100.0 / 150.0 * 100.0, 100.0]
        )
        assert mv["Share %"].sum() == pytest.approx(100.0)
        assert mv["Kumulatif %"].is_monotonic_increasing

    def test_urutan_kolom_dan_identitas(self, frame):
        mv = money_view(frame)
        assert list(mv.columns) == MONEY_VIEW_COLUMNS
        assert mv["NAMA BARANG"].tolist() == ["A", "B"]
        assert mv["TOTAL"].tolist() == [100.0, 50.0]
        assert mv["ANOMALY STATUS"].tolist() == ["Prioritas Tinggi", "Normal"]

    def test_focus_score_df_penuh(self, frame):
        # FOCUS dihitung pada df PENUH; rank magnitude di subset aktif
        # (v2.5.1): TOTAL [100, 50] → pct [100, 50] (bukan [100, 66,7]
        # yang menghitung baris 0/NaN ke dalam denominator rank).
        mv = money_view(frame)
        assert mv["FOCUS SCORE"].tolist() == pytest.approx([100.0, 30.0])
        assert mv["FOCUS CLASS"].tolist() == ["Fokus Utama", "Rutin"]

    def test_top_n(self, frame):
        mv1 = money_view(frame, top_n=1)
        assert len(mv1) == 1
        assert mv1["TOTAL"].iloc[0] == 100.0
        assert mv1["Kumulatif %"].iloc[0] == pytest.approx(100.0 / 150.0 * 100.0)
        mv0 = money_view(frame, top_n=0)
        assert len(mv0) == 0
        assert list(mv0.columns) == MONEY_VIEW_COLUMNS
        mv9 = money_view(frame, top_n=99)
        assert len(mv9) == 2

    def test_sort_total_desc_stabil(self):
        df = detail([
            {"NAMA BARANG": "X", "TOTAL": 50.0},
            {"NAMA BARANG": "Y", "TOTAL": 100.0},
            {"NAMA BARANG": "Z", "TOTAL": 50.0},
        ])
        mv = money_view(df)
        assert mv["NAMA BARANG"].tolist() == ["Y", "X", "Z"]

    def test_index_bebas_tidak_boleh_bocor(self):
        df = detail([
            {"NAMA BARANG": "A", "TOTAL": 100.0},
            {"NAMA BARANG": "B", "TOTAL": 50.0},
        ])
        df.index = ["x9", "y7"]
        mv = money_view(df)
        assert list(mv.columns) == MONEY_VIEW_COLUMNS
        assert mv["NAMA BARANG"].tolist() == ["A", "B"]
        assert list(mv.index) == [0, 1]

    def test_df_kosong_dan_kolom_hilang(self):
        empty = money_view(pd.DataFrame())
        assert len(empty) == 0
        assert list(empty.columns) == MONEY_VIEW_COLUMNS
        # satu kolom wajib hilang → tetap kosong dengan kolom kontrak
        df_no_satuan = detail([{"TOTAL": 10.0}]).drop(columns=["SATUAN"])
        mv = money_view(df_no_satuan)
        assert len(mv) == 0
        assert list(mv.columns) == MONEY_VIEW_COLUMNS

    def test_semua_total_nol(self):
        mv = money_view(detail([{"TOTAL": 0.0}, {"TOTAL": 0.0}]))
        assert len(mv) == 0
        assert list(mv.columns) == MONEY_VIEW_COLUMNS


# ============================================================
# benchmark_items — peer AKTIF (median hanya cabang ber-waste)
# ============================================================

class TestBenchmarkItems:
    def test_diatas_peer_dan_median_aktif(self):
        df = bench_frame([
            ("TEH", "R1", 10.0), ("TEH", "R2", 30.0), ("TEH", "R3", 30.0),
            ("TEH", "R4", 60.0), ("TEH", "R5", 0.0), ("TEH", "R6", 0.0),
        ])
        bm = benchmark_items(df)
        assert list(bm.columns) == BENCHMARK_ITEMS_COLUMNS
        teh = bm[bm["NAMA BARANG"] == "TEH"].set_index("NAMA RESTO")
        # R5/R6 (total 0) tidak jadi peer dan tidak muncul sebagai baris
        assert set(teh.index) == {"R1", "R2", "R3", "R4"}
        assert (teh["Peer Aktif"] == 4).all()
        # median AKTIF = median [10, 30, 30, 60] = 30 — bukan 20
        # (median yang termasuk cabang nol akan salah 20)
        assert (teh["Peer Median (aktif)"] == 30.0).all()
        assert teh.loc["R4", "Rasio vs Peer"] == pytest.approx(2.0)
        assert teh.loc["R4", "Flag"] == "Di Atas Peer"  # boundary 2.0 >= 2.0
        assert teh.loc["R2", "Flag"] == "Sesuai"
        assert teh.loc["R1", "Rasio vs Peer"] == pytest.approx(10.0 / 30.0)

    def test_peer_kecil(self):
        df = bench_frame([("KOPI", "R1", 50.0), ("KOPI", "R2", 80.0)])
        bm = benchmark_items(df)
        assert (bm["Peer Aktif"] == 2).all()
        assert (bm["Flag"] == "Peer Kecil").all()
        assert bm["Peer Median (aktif)"].tolist() == pytest.approx([65.0, 65.0])

    def test_median_tak_wajar_rasio_nan_flag_sesuai(self):
        # median tak-wajar (inf) → rasio NaN (inf/inf); Peer Aktif cukup
        # → flag tetap 'Sesuai' (bukan 'Di Atas Peer' maupun crash)
        df = bench_frame([
            ("ANEH", "R1", float("inf")),
            ("ANEH", "R2", float("inf")),
            ("ANEH", "R3", float("inf")),
        ])
        bm = benchmark_items(df)
        assert len(bm) == 3
        assert bm["Rasio vs Peer"].isna().all()
        assert (bm["Flag"] == "Sesuai").all()
        assert (bm["Peer Aktif"] == 3).all()

    def test_urutan_sort_rasio_desc_nan_akhir(self):
        df = bench_frame([
            ("TEH", "R1", 10.0), ("TEH", "R2", 30.0), ("TEH", "R3", 30.0),
            ("TEH", "R4", 60.0),
            ("KOPI", "R1", 50.0), ("KOPI", "R2", 80.0),
            ("ANEH", "R1", float("inf")),
            ("ANEH", "R2", float("inf")),
            ("ANEH", "R3", float("inf")),
        ])
        bm = benchmark_items(df)
        pairs = list(zip(bm["NAMA BARANG"], bm["NAMA RESTO"]))
        assert pairs == [
            ("TEH", "R4"),    # rasio 2.0
            ("KOPI", "R2"),   # 80/65 = 1.231
            ("TEH", "R2"),    # 1.0 (tie TOTAL 30 — urutan stabil)
            ("TEH", "R3"),    # 1.0
            ("KOPI", "R1"),   # 50/65 = 0.769
            ("TEH", "R1"),    # 10/30 = 0.333
            ("ANEH", "R1"),   # rasio NaN → selalu di akhir
            ("ANEH", "R2"),
            ("ANEH", "R3"),
        ]

    def test_param_min_peers_dan_ratio_flag(self):
        df = bench_frame([("KOPI", "R1", 50.0), ("KOPI", "R2", 80.0)])
        bm = benchmark_items(df, min_peers=2, ratio_flag=1.0)
        flags = bm.set_index("NAMA RESTO")["Flag"]
        assert flags["R2"] == "Di Atas Peer"  # 1.231 >= 1.0, 2 peer >= 2
        assert flags["R1"] == "Sesuai"        # 0.769 < 1.0

    def test_df_kosong_dan_kolom_hilang(self):
        empty = benchmark_items(pd.DataFrame())
        assert len(empty) == 0
        assert list(empty.columns) == BENCHMARK_ITEMS_COLUMNS
        df_no_total = pd.DataFrame({"NAMA BARANG": ["A"], "NAMA RESTO": ["R1"]})
        bm = benchmark_items(df_no_total)
        assert len(bm) == 0
        assert list(bm.columns) == BENCHMARK_ITEMS_COLUMNS

    def test_semua_total_nol(self):
        bm = benchmark_items(bench_frame([("A", "R1", 0.0), ("A", "R2", 0.0)]))
        assert len(bm) == 0
        assert list(bm.columns) == BENCHMARK_ITEMS_COLUMNS


# ============================================================
# reason_profile — profil alasan per cabang
# ============================================================

PROFILE_ROWS = [
    ("R1", "Handling", "WASTE", 60.0),
    ("R1", "Kualitas Eksternal", "WASTE", 40.0),
    ("R1", "Lain-lain", "WASTE", 0.0),
    ("R2", "Handling", "WASTE", 30.0),
    ("R2", "Kualitas Internal", "WASTE", 20.0),
    ("R2", "Handling", "SUSUT", 30.0),
    ("R3", "Handling", "WASTE", 0.0),
]


class TestReasonProfile:
    def test_kolom_dinamis_urut_total_global(self):
        prof = reason_profile(reason_frame(PROFILE_ROWS))
        # global: Handling 120, Kualitas Eksternal 40, Kualitas Internal 20,
        # Lain-lain 0 (hanya baris nol) → kolom terakhir
        assert list(prof.columns) == [
            "NAMA RESTO", "Handling", "Kualitas Eksternal",
            "Kualitas Internal", "Lain-lain", "TOTAL", "SUSUT %",
            "Alasan Dominan",
        ]

    def test_nilai_pivot_total_susut(self):
        prof = reason_profile(reason_frame(PROFILE_ROWS)).set_index("NAMA RESTO")
        assert prof["TOTAL"].to_dict() == {"R1": 100.0, "R2": 80.0, "R3": 0.0}
        assert prof["Handling"].to_dict() == {"R1": 60.0, "R2": 60.0, "R3": 0.0}
        assert prof["Kualitas Eksternal"].to_dict() == {
            "R1": 40.0, "R2": 0.0, "R3": 0.0,
        }
        assert prof["Kualitas Internal"].to_dict() == {
            "R1": 0.0, "R2": 20.0, "R3": 0.0,
        }
        # R2 punya 30 SUSUT dari TOTAL 80 → 37.5%; resto tanpa waste → 0
        assert prof["SUSUT %"].to_dict() == pytest.approx(
            {"R1": 0.0, "R2": 37.5, "R3": 0.0}
        )

    def test_alasan_dominan_dan_sort_total_desc(self):
        prof = reason_profile(reason_frame(PROFILE_ROWS))
        assert prof["NAMA RESTO"].tolist() == ["R1", "R2", "R3"]
        assert prof["Alasan Dominan"].tolist() == [
            "Handling (60.0%)", "Handling (75.0%)", "(kosong)",
        ]

    def test_df_kosong_dan_kolom_hilang(self):
        empty = reason_profile(pd.DataFrame())
        assert len(empty) == 0
        assert list(empty.columns) == REASON_PROFILE_STATIC_COLUMNS
        df_no_jenis = reason_frame(PROFILE_ROWS).drop(columns=["JENIS"])
        prof = reason_profile(df_no_jenis)
        assert len(prof) == 0
        assert list(prof.columns) == REASON_PROFILE_STATIC_COLUMNS


# ============================================================
# reason_share — share alasan satu cabang
# ============================================================

class TestReasonShare:
    def test_share_jumlah_100_sort_desc(self):
        df = reason_frame([
            ("R1", "Handling", "WASTE", 60.0),
            ("R1", "Kualitas Eksternal", "WASTE", 40.0),
            ("R1", "Lain-lain", "WASTE", 0.0),  # baris nol tidak dihitung
            ("R2", "Handling", "WASTE", 0.0),   # resto tanpa waste
        ])
        s = reason_share(df, "R1")
        assert s.index.tolist() == ["Handling", "Kualitas Eksternal"]
        assert s.tolist() == pytest.approx([60.0, 40.0])
        assert s.sum() == pytest.approx(100.0)
        assert pd.api.types.is_float_dtype(s)

    def test_cabang_tidak_ada(self):
        df = reason_frame([("R1", "Handling", "WASTE", 60.0)])
        assert len(reason_share(df, "R99")) == 0

    def test_cabang_tanpa_waste(self):
        df = reason_frame([("R1", "Handling", "WASTE", 0.0)])
        assert len(reason_share(df, "R1")) == 0

    def test_df_kosong(self):
        assert len(reason_share(pd.DataFrame(), "R1")) == 0


# ============================================================
# susut_benchmark — ranking SUSUT per cabang
# ============================================================

SUSUT_ROWS = [
    ("R1", "Handling", "SUSUT", 40.0),
    ("R1", "Kualitas Eksternal", "WASTE", 60.0),
    ("R2", "Handling", "SUSUT", 30.0),
    ("R2", "Kualitas Eksternal", "WASTE", 20.0),
    ("R3", "Handling", "WASTE", 100.0),  # tanpa SUSUT → keluar
    ("R4", "Handling", "SUSUT", 0.0),    # SUSUT nol → keluar
]


class TestSusutBenchmark:
    def test_rank_share_dan_sort(self):
        res = susut_benchmark(reason_frame(SUSUT_ROWS))
        assert list(res.columns) == SUSUT_BENCHMARK_COLUMNS
        assert res["NAMA RESTO"].tolist() == ["R1", "R2"]
        assert res["SUSUT"].tolist() == [40.0, 30.0]
        assert res["Share Cabang %"].tolist() == pytest.approx([40.0, 60.0])
        assert res["Rank"].tolist() == [1, 2]
        assert pd.api.types.is_integer_dtype(res["Rank"])

    def test_df_kosong_dan_kolom_hilang(self):
        empty = susut_benchmark(pd.DataFrame())
        assert len(empty) == 0
        assert list(empty.columns) == SUSUT_BENCHMARK_COLUMNS
        df_no_jenis = reason_frame(SUSUT_ROWS).drop(columns=["JENIS"])
        res = susut_benchmark(df_no_jenis)
        assert len(res) == 0
        assert list(res.columns) == SUSUT_BENCHMARK_COLUMNS

    def test_tanpa_baris_susut(self):
        df = reason_frame([("R1", "Handling", "WASTE", 10.0)])
        res = susut_benchmark(df)
        assert len(res) == 0
        assert list(res.columns) == SUSUT_BENCHMARK_COLUMNS


# ============================================================
# SMOKE DATA ASLI — DATA_WASTE.xlsx (read-only)
# ============================================================

class TestRealDataSmoke:
    """Smoke read-only pada fixture asli — pola test_pipeline_regression."""

    @pytest.mark.skipif(
        not FIXTURE.exists(), reason="fixture DATA_WASTE.xlsx tidak ada di repo"
    )
    def test_money_view_benchmark_data_asli(self):
        raw = pd.read_excel(FIXTURE, sheet_name="Sheet1")
        df = raw.copy()
        df["ANOMALY SCORE"] = 0     # raw belum lewat signals → dummy
        df["ANOMALY STATUS"] = "Normal"

        mv = money_view(df)
        assert list(mv.columns) == MONEY_VIEW_COLUMNS
        assert len(mv) > 0

        # Baris uang terbesar — persis temuan EVAL-DRILLDOWN-ANALISA
        top = mv.iloc[0]
        assert top["TOTAL"] == 299855.0
        assert top["NAMA RESTO"] == "1151.GGPDAA"
        assert top["NAMA BARANG"] == "KULIT PANGSIT (V.20)"
        assert top["JENIS"] == "WASTE"
        assert top["KETERANGAN"] == "Kualitas Eksternal"

        # Kumulatif naik monoton dan menutup 100% di baris terakhir
        assert mv["Kumulatif %"].is_monotonic_increasing
        assert float(mv["Kumulatif %"].iloc[-1]) == pytest.approx(100.0)

        # Konsentrasi per baris: butuh >= 7 item berbeda untuk 80% kumulatif
        n80 = int((mv["Kumulatif %"] < 80.0).sum()) + 1
        assert mv["NAMA BARANG"].iloc[:n80].nunique() >= 7

        # View per ITEM: 80% kumulatif tercapai dalam <= 12 baris
        # (Pareto 7 item dari 173 — konsentrasi ekstrem)
        num = pd.to_numeric(raw["TOTAL"], errors="coerce").fillna(0.0)
        per_item = (
            raw.assign(_T=num).groupby("NAMA BARANG")["_T"].sum().reset_index()
        )
        item_df = pd.DataFrame({
            "NAMA RESTO": "(semua cabang)",
            "NAMA BARANG": per_item["NAMA BARANG"],
            "JENIS": "(semua)",
            "KETERANGAN": "(semua)",
            "SATUAN": "-",
            "TOTAL": per_item["_T"],
            "MAX": float("nan"),
            "Count Hari": 0,
            "ANOMALY SCORE": 0,
            "ANOMALY STATUS": "Normal",
        })
        mv_item = money_view(item_df)
        n80_item = int((mv_item["Kumulatif %"] < 80.0).sum()) + 1
        assert 7 <= n80_item <= 12

        # Benchmark peer aktif pada data asli: minimal ada 'Di Atas Peer'
        bm = benchmark_items(df)
        assert list(bm.columns) == BENCHMARK_ITEMS_COLUMNS
        assert (bm["Flag"] == "Di Atas Peer").sum() >= 1
