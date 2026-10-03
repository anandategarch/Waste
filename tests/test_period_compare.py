"""Unit test — period_compare (P9 v2.5.0): perbandingan dua periode run.

Kontrak yang dikunci:
- auto_key_akhir mendeteksi hari aktif terbesar (fallback 31).
- compare_periods: summary metrik, per-JENIS, branch & item movers,
  item baru/hilang; Delta % konvensi (old=0 & new>0 → NaN/∞).
- Semua jalur defensif: df kosong / kolom hilang → tabel kosong berdiformasi.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from waste_anomaly.period_compare import auto_key_akhir, compare_periods


def make_detail(rows: list[dict]) -> pd.DataFrame:
    """Frame Detail minimal: kolom kunci + TOTAL + ANOMALY STATUS."""
    base = {
        "NAMA RESTO": "1001.A",
        "NAMA BARANG": "ITEM X",
        "JENIS": "WASTE",
        "TOTAL": 0.0,
        "ANOMALY STATUS": "Normal",
    }
    return pd.DataFrame([{**base, **r} for r in rows])


# ============================================================
# auto_key_akhir
# ============================================================

class TestAutoKeyAkhir:
    def test_hari_aktif_terbesar(self):
        df = pd.DataFrame({"1": [0, 5], "28": [3, 0], "30": [0, 2], "31": [0, 0]})
        assert auto_key_akhir(df) == 30

    def test_hari_31_aktif(self):
        df = pd.DataFrame({"31": [1, 0]})
        assert auto_key_akhir(df) == 31

    def test_semua_nol_fallback_31(self):
        df = pd.DataFrame({"1": [0], "5": [0]})
        assert auto_key_akhir(df) == 31

    def test_tanpa_kolom_hari(self):
        df = pd.DataFrame({"TOTAL": [10]})
        assert auto_key_akhir(df) == 31

    def test_df_kosong(self):
        assert auto_key_akhir(pd.DataFrame()) == 31

    def test_header_float_dinormalisasi(self):
        # calamine-style header '5.0' → tidak dihitung kolom hari (bukan digit murni)
        df = pd.DataFrame({"5.0": [1]})
        assert auto_key_akhir(df) == 31


# ============================================================
# compare_periods — summary
# ============================================================

class TestSummary:
    def test_total_dan_delta(self):
        a = make_detail([{"TOTAL": 100}, {"TOTAL": 50}])
        b = make_detail([{"TOTAL": 200}])
        res = compare_periods(a, b)
        s = res["summary"].set_index("Metrik")
        assert s.loc["Total Waste", "Periode A"] == 150
        assert s.loc["Total Waste", "Periode B"] == 200
        assert abs(s.loc["Total Waste", "Delta %"] - (50 / 150 * 100)) < 1e-9

    def test_status_counter(self):
        a = make_detail([
            {"TOTAL": 10, "ANOMALY STATUS": "Prioritas Tinggi"},
            {"TOTAL": 0, "ANOMALY STATUS": "Prioritas Tinggi"},  # TOTAL 0 → tidak dihitung aktif, status tetap dihitung
        ])
        b = make_detail([{"TOTAL": 10, "ANOMALY STATUS": "Potensi Anomali"}])
        res = compare_periods(a, b)
        s = res["summary"].set_index("Metrik")
        assert s.loc["Anomali Prioritas", "Periode A"] == 2
        assert s.loc["Anomali Prioritas", "Periode B"] == 0
        assert s.loc["Potensi Anomali", "Periode B"] == 1

    def test_baris_aktif_dan_cabang(self):
        a = make_detail([
            {"NAMA RESTO": "A", "NAMA BARANG": "I1", "TOTAL": 5},
            {"NAMA RESTO": "A", "NAMA BARANG": "I2", "TOTAL": 0},
            {"NAMA RESTO": "B", "NAMA BARANG": "I1", "TOTAL": 7},
        ])
        b = make_detail([{"NAMA RESTO": "A", "NAMA BARANG": "I1", "TOTAL": 6}])
        res = compare_periods(a, b)
        s = res["summary"].set_index("Metrik")
        assert s.loc["Baris Aktif (>0)", "Periode A"] == 2
        assert s.loc["Baris Aktif (>0)", "Periode B"] == 1
        assert s.loc["Cabang Aktif", "Periode A"] == 2
        assert s.loc["Cabang Aktif", "Periode B"] == 1
        # Item aktif = item dgn waste > 0 (I2 bernilai 0 → tidak dihitung)
        assert s.loc["Item Aktif", "Periode A"] == 1

    def test_delta_pct_old_zero_new_positive_nan(self):
        a = make_detail([])  # kosong → total 0
        b = make_detail([{"TOTAL": 100}])
        res = compare_periods(a, b)
        s = res["summary"].set_index("Metrik")
        assert np.isnan(s.loc["Total Waste", "Delta %"])

    def test_kolom_summary_persis(self):
        res = compare_periods(pd.DataFrame(), pd.DataFrame())
        assert list(res["summary"].columns) == ["Metrik", "Periode A", "Periode B", "Delta %"]


# ============================================================
# compare_periods — branch & item movers
# ============================================================

class TestMovers:
    def test_branch_delta_dan_urutan(self):
        a = make_detail([
            {"NAMA RESTO": "R1", "TOTAL": 100},
            {"NAMA RESTO": "R2", "TOTAL": 100},
        ])
        b = make_detail([
            {"NAMA RESTO": "R1", "TOTAL": 90},   # delta -10
            {"NAMA RESTO": "R2", "TOTAL": 150},  # delta +50 → urutan pertama
        ])
        res = compare_periods(a, b)
        br = res["branch"]
        assert br.iloc[0]["NAMA RESTO"] == "R2"
        assert br.iloc[0]["Delta"] == 50
        assert br.iloc[1]["NAMA RESTO"] == "R1"
        assert br.iloc[1]["Delta"] == -10
        # Delta % R2 = +50%
        assert abs(br.iloc[0]["Delta %"] - 50.0) < 1e-9

    def test_item_movers_dan_cap(self):
        rows_a = [
            {"NAMA RESTO": "R1", "NAMA BARANG": f"I{i}", "TOTAL": 10} for i in range(5)
        ]
        rows_b = [
            {"NAMA RESTO": "R1", "NAMA BARANG": f"I{i}", "TOTAL": 10 + i * 10}
            for i in range(5)
        ]
        res = compare_periods(make_detail(rows_a), make_detail(rows_b), top_n=3)
        assert len(res["items"]) == 3
        # mover terbesar = I4 (delta 40)
        assert res["items"].iloc[0]["NAMA BARANG"] == "I4"
        assert res["items"].iloc[0]["Delta"] == 40

    def test_new_dan_gone_items(self):
        a = make_detail([
            {"NAMA RESTO": "R1", "NAMA BARANG": "HILANG", "TOTAL": 30},
            {"NAMA RESTO": "R1", "NAMA BARANG": "SAMA", "TOTAL": 10},
        ])
        b = make_detail([
            {"NAMA RESTO": "R1", "NAMA BARANG": "SAMA", "TOTAL": 12},
            {"NAMA RESTO": "R1", "NAMA BARANG": "BARU", "TOTAL": 99},
        ])
        res = compare_periods(a, b)
        assert list(res["new_items"]["NAMA BARANG"]) == ["BARU"]
        assert res["new_items"].iloc[0]["Total B"] == 99
        assert list(res["gone_items"]["NAMA BARANG"]) == ["HILANG"]
        assert res["gone_items"].iloc[0]["Total A"] == 30

    def test_agregasi_split_source(self):
        """(resto,item) sama di 2 baris (split SOURCE DATA) → total digabung."""
        a = make_detail([
            {"NAMA RESTO": "R1", "NAMA BARANG": "I1", "TOTAL": 40},
            {"NAMA RESTO": "R1", "NAMA BARANG": "I1", "TOTAL": 60},
        ])
        b = make_detail([{"NAMA RESTO": "R1", "NAMA BARANG": "I1", "TOTAL": 50}])
        res = compare_periods(a, b)
        assert res["items"].iloc[0]["Total A"] == 100
        assert res["items"].iloc[0]["Delta"] == -50


# ============================================================
# compare_periods — per JENIS & defensif
# ============================================================

class TestJenisDanDefensif:
    def test_per_jenis(self):
        a = make_detail([
            {"JENIS": "WASTE", "TOTAL": 100},
            {"JENIS": "SUSUT", "TOTAL": 50},
        ])
        b = make_detail([{"JENIS": "WASTE", "TOTAL": 80}])
        res = compare_periods(a, b)
        j = res["per_jenis"].set_index("JENIS")
        assert j.loc["WASTE", "Delta"] == -20
        assert j.loc["SUSUT", "Total B"] == 0

    def test_df_kosong_kedua_sisi(self):
        res = compare_periods(pd.DataFrame(), pd.DataFrame())
        # v2.5.1: 9 metrik (7 lama + Hari Data + Waste per Hari — PE-M1)
        assert res["summary"].shape[0] == 9
        assert res["branch"].empty
        assert res["items"].empty
        assert res["new_items"].empty
        assert res["gone_items"].empty
        assert res["per_jenis"].empty

    def test_normalisasi_panjang_periode(self):
        """v2.5.1 (PE-M1): Hari Data + Waste per Hari ada di summary —
        total mentah 30-hari vs 31-hari tidak boleh dibaca sebagai
        perubahan performa (bias hingga ~1/30)."""
        df_a = pd.DataFrame({
            "NAMA RESTO": ["R1"], "NAMA BARANG": ["I1"], "TOTAL": [310.0],
        })
        df_b = pd.DataFrame({
            "NAMA RESTO": ["R1"], "NAMA BARANG": ["I1"], "TOTAL": [310.0],
        })
        res = compare_periods(df_a, df_b, key_akhir_a=31, key_akhir_b=30)
        s = res["summary"].set_index("Metrik")
        assert int(s.loc["Hari Data", "Periode A"]) == 31
        assert int(s.loc["Hari Data", "Periode B"]) == 30
        # total sama, waste/hari berbeda karena panjang periode beda
        assert s.loc["Waste per Hari", "Periode A"] == pytest.approx(310.0 / 31)
        assert s.loc["Waste per Hari", "Periode B"] == pytest.approx(310.0 / 30)
        assert res["key_akhir_a"] == 31 and res["key_akhir_b"] == 30

    def test_key_akhir_auto_detect_tanpa_param(self):
        """v2.5.1: tanpa parameter, key_akhir auto-detect dari masing df."""
        df_a = pd.DataFrame({
            "NAMA RESTO": ["R1"], "NAMA BARANG": ["I1"], "TOTAL": [10.0],
            "1": [1.0], "2": [2.0],
        })
        res = compare_periods(df_a, df_a)
        assert res["key_akhir_a"] == 2
        assert res["key_akhir_b"] == 2

    def test_kolom_kunci_hilang(self):
        df = pd.DataFrame({"TOTAL": [10], "JENIS": ["WASTE"]})
        res = compare_periods(df, df)
        assert res["branch"].empty
        assert res["items"].empty
        assert res["summary"].loc[0, "Periode A"] == 0  # total 0 (tanpa kunci → tak ada item aktif)

    def test_labels_disimpan(self):
        res = compare_periods(pd.DataFrame(), pd.DataFrame(),
                              label_a="Jan 2025", label_b="Feb 2025")
        assert res["label_a"] == "Jan 2025"
        assert res["label_b"] == "Feb 2025"

    def test_total_nol_kedua_periode_delta_nol(self):
        res = compare_periods(pd.DataFrame(), pd.DataFrame())
        s = res["summary"].set_index("Metrik")
        assert s.loc["Total Waste", "Delta %"] == 0.0


# ============================================================
# SMOKE — fixture asli (konsistensi agregat)
# ============================================================

class TestRealDataSmoke:
    def test_agregat_item_sama_dengan_total(self):
        """Sum TOTAL baris aktif == sum agregat item (invarian konsistensi)."""
        raw = pd.read_excel("/home/z/Waste-audit/DATA_WASTE.xlsx", sheet_name="Sheet1")
        res = compare_periods(raw, raw)
        s = res["summary"].set_index("Metrik")
        total_expected = float(raw["TOTAL"].sum())
        assert abs(s.loc["Total Waste", "Periode A"] - total_expected) < 1e-6
        assert s.loc["Total Waste", "Delta %"] == 0.0  # A == B → delta 0
        # Tidak ada item baru/hilang saat membandingkan file dengan dirinya
        assert res["new_items"].empty
        assert res["gone_items"].empty
        # Branch teratas = cabang dgn |delta| 0 → total terbesar ada di daftar
        assert "1042.KWGGAL" in set(res["branch"]["NAMA RESTO"].head(5))
