"""Test — v2.10.2: tabel banding besar + drill-down pop-up + kolom perubahan.

Fitur (disetujui user — "gas" + tambahan "pop up juga ya semua tab nya"):
1. Tabel pembanding bisa melebar 2 tingkat: tombol ⤢ (ciyutkan kartu daftar
   file) + ⛶ Layar Penuh (pop-out tab aktif, maximized, Esc kembali).
2. Pop-up drill-down SEMUA tab banding — rantai jawaban "total naik → resto
   mana yang naik → sampai item apa → hari apa": compare_level (resto/item/
   per JENIS/per hari) + drill_day_detail (hari 1-31 A vs B).
3. Kolom perubahan di tabel Anomali (kuadran tinggi/rendah, permintaan user
   "persen perubahan ke anomali juga sebagai analisa"): change_vs_history
   (BULAN LALU / PERUBAHAN % / PERUBAHAN — kunci resto×item×jenis×keterangan)
   + classify_change + filter combo "Perubahan:". Skor anomali TIDAK diubah
   (golden 484 utuh) — kolom additive murni.

Headless: QT_QPA_PLATFORM=offscreen sebelum PySide6 (konvensi suite).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
UI = REPO / "ui"

_DAY_COLS = [str(d) for d in range(1, 32)]


def _qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


# ============================================================
# Fixture — bulan pembanding sintetis (replika bukti MIE v2.10.0)
# ============================================================

def _wb_bulan(tmp_path: Path, name: str,
              handling_base: float = 2.0, cn24: float = 94.0) -> Path:
    rows = []

    def _row(jenis, ket, day24, base):
        data = {str(d): base for d in range(1, 32)}
        data["24"] = float(day24)
        rows.append({
            "SOURCE DATA": "WASTE BAHAN", "JENIS": jenis, "KETERANGAN": ket,
            "NAMA BARANG": "MIE (V.20)", "NAMA RESTO": "1042.KWGGAL",
            "SATUAN": "PCS", **data, "TOTAL": float(sum(data.values())),
        })

    _row("WASTE", "Handling", 100, handling_base)
    _row("WASTE", "Cancel Nota", cn24, 0.0)
    _row("BOM", "BOM", 42921, 2.0)     # wajib tersaring (bukti 43115 vs 194)
    _row("SO", "SO", 5.0, 1.0)
    out = tmp_path / name
    pd.DataFrame(rows).to_excel(out, sheet_name="REKAP MENTAH", index=False)
    return out


def _month_b(tmp_path: Path) -> dict:
    from waste_anomaly.period_history import load_history_file
    return load_history_file(_wb_bulan(tmp_path, "REKAP MENTAH JULI 2026.xlsx"))


def _df_a(spike: float = 400.0, base: float = 6.0,
          resto: str = "1042.KWGGAL", barang: str = "MIE (V.20)") -> pd.DataFrame:
    """Bulan berjalan (A) — MIE melonjak di hari 24."""
    data = {str(d): base for d in range(1, 32)}
    data["24"] = spike
    rows = []
    for jenis, ket, d24, b in (("WASTE", "Handling", spike, base),
                               ("WASTE", "Cancel Nota", 94.0, 0.0)):
        d = {str(x): b for x in range(1, 32)}
        d["24"] = float(d24)
        rows.append({"JENIS": jenis, "KETERANGAN": ket, "NAMA BARANG": barang,
                     "NAMA RESTO": resto, **d})
    return pd.DataFrame(rows)


def _month_a() -> dict:
    from waste_anomaly.period_history import aggregate_current
    return aggregate_current(_df_a(), 31, "September 2026")


# ============================================================
# [1] COMPARE_LEVEL — tabel per level (isi pop-up drill)
# ============================================================

class TestCompareLevel:
    def test_level_resto_nilai_dan_arah(self, tmp_path):
        from waste_anomaly.period_history import compare_level
        df = compare_level(_month_a(), _month_b(tmp_path), ["NAMA RESTO"])
        # A: handling 6*30+400=580 + CN 94 = 674 ; B: 254 → +165,35%
        assert list(df.columns) == ["NAMA RESTO", "Bulan Ini", "Pembanding",
                                    "Selisih", "Perubahan %"]
        assert len(df) == 1
        r = df.iloc[0]
        assert r["NAMA RESTO"] == "1042.KWGGAL"
        assert abs(r["Bulan Ini"] - 674.0) < 0.01
        assert abs(r["Pembanding"] - 254.0) < 0.01
        assert abs(r["Selisih"] - 420.0) < 0.01
        assert abs(r["Perubahan %"] - 165.354) < 0.05

    def test_level_item_semua_baris_tanpa_cap(self, tmp_path):
        from waste_anomaly.period_history import compare_level
        df = compare_level(_month_a(), _month_b(tmp_path),
                           ["NAMA RESTO", "NAMA BARANG"])
        # 1 kombinasi resto×item — tapi top_n=None → TIDAK dipotong 100
        assert len(df) == 1
        assert df.iloc[0]["NAMA BARANG"] == "MIE (V.20)"

    def test_top_n_memotong(self, tmp_path):
        from waste_anomaly.period_history import compare_level
        df = compare_level(_month_a(), _month_b(tmp_path),
                           ["NAMA RESTO"], top_n=0)
        assert len(df) == 0

    def test_filter_jenis_pakai_agg_jenis(self, tmp_path):
        from waste_anomaly.period_history import compare_level
        # Drill tab Per Jenis: JENIS=WASTE → 674 vs 254 (BOM/SO tersaring).
        df = compare_level(_month_a(), _month_b(tmp_path), ["NAMA RESTO"],
                           jenis="WASTE")
        assert abs(df.iloc[0]["Bulan Ini"] - 674.0) < 0.01
        assert abs(df.iloc[0]["Pembanding"] - 254.0) < 0.01
        # JENIS yang tak ada → kosong berformat (bukan raise)
        df2 = compare_level(_month_a(), _month_b(tmp_path), ["NAMA RESTO"],
                            jenis="TIDAK ADA")
        assert df2.empty

    def test_per_day_normalisasi_30_31_hari(self, tmp_path):
        from waste_anomaly.period_history import compare_level
        a = _month_a()
        a["key_akhir"] = 30  # bulan ini 30 hari
        b = _month_b(tmp_path)  # Juli = 31 hari
        df = compare_level(a, b, ["NAMA RESTO"], per_day=True)
        assert abs(df.iloc[0]["Bulan Ini"] - 674.0 / 30) < 0.01
        assert abs(df.iloc[0]["Pembanding"] - 254.0 / 31) < 0.01

    def test_sisi_kosong_nol_bukan_naik(self, tmp_path):
        from waste_anomaly.period_history import compare_level
        a = _month_a()
        a["agg"] = a["agg"].iloc[0:0]  # bulan ini kosong total
        df = compare_level(a, _month_b(tmp_path), ["NAMA RESTO"])
        r = df.iloc[0]
        assert r["Bulan Ini"] == 0.0
        assert abs(r["Pembanding"] - 254.0) < 0.01
        assert abs(r["Perubahan %"] + 100.0) < 0.01  # turun 100%

    def test_urutan_selisih_absolut_menurun(self, tmp_path):
        from waste_anomaly.period_history import compare_level
        a = _month_a()
        # Tambah resto kedua dgn selisih LEBIH KECIL → harus di bawah.
        extra = a["agg"].copy()
        extra["NAMA RESTO"] = "9999.RESTO"
        extra["TOTAL"] = 10.0
        a["agg"] = pd.concat([a["agg"], extra], ignore_index=True)
        df = compare_level(a, _month_b(tmp_path), ["NAMA RESTO"])
        assert df.iloc[0]["NAMA RESTO"] == "1042.KWGGAL"
        assert df["Selisih"].abs().is_monotonic_decreasing


# ============================================================
# [2] DRILL_DAY_DETAIL — rincian hari 1-31
# ============================================================

class TestDrillDayDetail:
    def test_kolom_dan_puncak_hari_24(self, tmp_path):
        from waste_anomaly.period_history import (
            DAY_DETAIL_COLS, drill_day_detail)
        df = drill_day_detail(_month_a(), _month_b(tmp_path),
                              "1042.KWGGAL", "MIE (V.20)")
        assert list(df.columns) == DAY_DETAIL_COLS
        assert list(df["HARI"]) == list(range(1, 32))
        # Hari 24: A = 400+94 = 494 (semua jenis digabung); B = 100+94 = 194.
        r24 = df[df["HARI"] == 24].iloc[0]
        assert abs(r24["Bulan Ini"] - 494.0) < 0.01
        assert abs(r24["Pembanding"] - 194.0) < 0.01
        assert abs(r24["Selisih"] - 300.0) < 0.01
        r1 = df[df["HARI"] == 1].iloc[0]
        assert abs(r1["Bulan Ini"] - 6.0) < 0.01
        assert abs(r1["Pembanding"] - 2.0) < 0.01

    def test_panjang_max_key_akhir(self, tmp_path):
        from waste_anomaly.period_history import drill_day_detail
        a = _month_a()
        a["key_akhir"] = 20  # bulan A hanya 20 hari
        df = drill_day_detail(a, _month_b(tmp_path), "1042.KWGGAL",
                              "MIE (V.20)")
        assert len(df) == 31  # max(20, 31)

    def test_item_tak_ada_nol_semua(self, tmp_path):
        from waste_anomaly.period_history import drill_day_detail
        df = drill_day_detail(_month_a(), _month_b(tmp_path),
                              "X.Y", "TIDAK ADA")
        assert (df["Bulan Ini"] == 0).all()
        assert (df["Pembanding"] == 0).all()

    def test_cocok_string_dgn_spasi(self, tmp_path):
        from waste_anomaly.period_history import drill_day_detail
        df = drill_day_detail(_month_a(), _month_b(tmp_path),
                              " 1042.KWGGAL ", " MIE (V.20) ")
        assert abs(df[df["HARI"] == 24]["Bulan Ini"].iloc[0] - 494.0) < 0.01


# ============================================================
# [3] AGREGAT BARU month dict (agg_jenis / agg_detail)
# ============================================================

class TestMonthAggregates:
    def test_load_history_file_ada_keduanya(self, tmp_path):
        from waste_anomaly.period_history import (
            AGG_DETAIL_COLS, AGG_JENIS_COLS)
        m = _month_b(tmp_path)
        assert list(m["agg_jenis"].columns) == AGG_JENIS_COLS
        assert list(m["agg_detail"].columns) == AGG_DETAIL_COLS
        j = m["agg_jenis"]
        assert len(j) == 1  # hanya WASTE (BOM/SO tersaring)
        assert j.iloc[0]["JENIS"] == "WASTE"
        assert abs(j.iloc[0]["TOTAL"] - 254.0) < 0.01
        d = m["agg_detail"].set_index("KETERANGAN")["TOTAL"]
        assert abs(d["Handling"] - 160.0) < 0.01
        assert abs(d["Cancel Nota"] - 94.0) < 0.01

    def test_aggregate_current_sama_bentuk(self):
        a = _month_a()
        assert not a["agg_jenis"].empty
        assert abs(a["agg_jenis"]["TOTAL"].sum() - 674.0) < 0.01
        det = a["agg_detail"].set_index("KETERANGAN")["TOTAL"]
        assert abs(det["Handling"] - 580.0) < 0.01

    def test_bulan_lama_tanpa_agregat_baru_tetap_aman(self):
        """Month dict lama (v2.10.1, tanpa agg_jenis) → frame kosong di UI."""
        from waste_anomaly.period_history import compare_level
        a = {"label": "A", "key_akhir": 31, "agg": _month_a()["agg"]}
        df = compare_level(a, dict(a), ["NAMA RESTO"])
        assert not df.empty  # agg lama tetap jalan utk level resto

    def test_typical_median_agg_detail(self, tmp_path):
        from waste_anomaly.period_history import (
            aggregate_current, typical_months)
        m1 = _month_b(tmp_path)  # Handling 160, CN 94
        df2 = _df_a(base=10.0)  # Handling 700, CN 94
        m2 = aggregate_current(df2, 31, "Agustus 2026")
        typ = typical_months([m1, m2])
        assert typ is not None
        d = typ["agg_detail"].set_index("KETERANGAN")["TOTAL"]
        assert abs(d["Handling"] - 430.0) < 0.01  # median(160, 700)
        assert abs(d["Cancel Nota"] - 94.0) < 0.01


# ============================================================
# [4] CLASSIFY_CHANGE — kategori kuadran perubahan
# ============================================================

class TestClassifyChange:
    def test_baru(self):
        from waste_anomaly.period_history import classify_change
        assert classify_change(100.0, None) == "Baru"
        assert classify_change(100.0, 0.0) == "Baru"
        assert classify_change(0.0, None) == "Stabil"  # tak ada nilai = netral

    def test_naik_tinggi(self):
        from waste_anomaly.period_history import classify_change
        assert classify_change(400.0, 187.0) == "Naik Tinggi"  # +114%
        assert classify_change(150.0, 100.0) == "Naik Tinggi"  # +50% (batas)

    def test_naik_sedang(self):
        from waste_anomaly.period_history import classify_change
        assert classify_change(125.0, 100.0) == "Naik Sedang"  # +25%

    def test_stabil_pct_dan_min_abs(self):
        from waste_anomaly.period_history import classify_change
        assert classify_change(110.0, 100.0) == "Stabil"  # +10% ≤ 20
        assert classify_change(105.0, 100.0) == "Stabil"   # +5% tapi Δ=5 < 10

    def test_turun_dan_turun_tinggi(self):
        from waste_anomaly.period_history import classify_change
        assert classify_change(75.0, 100.0) == "Turun"          # −25%
        assert classify_change(20.0, 100.0) == "Turun Tinggi"   # −80%

    def test_config_override(self):
        from waste_anomaly.period_history import classify_change
        cfg = {"thresholds": {"TH_CHANGE_HIGH": 30.0,
                              "TH_CHANGE_STABLE": 10.0,
                              "TH_CHANGE_MIN_ABS": 50.0}}
        # +25% tapi Δ = 25 < MIN_ABS 50 → Stabil (anti-noise)
        assert classify_change(125.0, 100.0, cfg) == "Stabil"
        # Δ besar + 35% ≥ 30 → Naik Tinggi
        assert classify_change(1350.0, 1000.0, cfg) == "Naik Tinggi"

    def test_config_rusak_pakai_default(self):
        from waste_anomaly.period_history import classify_change
        assert classify_change(400.0, 187.0, {"thresholds": "rusak"}) \
            == "Naik Tinggi"

    def test_kategori_lengkap_kontrak(self):
        from waste_anomaly.period_history import CHANGE_CATEGORIES
        assert CHANGE_CATEGORIES == ["Baru", "Naik Tinggi", "Naik Sedang",
                                     "Stabil", "Turun", "Turun Tinggi"]


# ============================================================
# [5] CHANGE_VS_HISTORY — kolom tabel Anomali
# ============================================================

class TestChangeVsHistory:
    def _anomali_df(self):
        df = _df_a()
        # Tambah satu baris item BARU (tidak ada bulan lalu).
        d = {str(x): 0.0 for x in range(1, 32)}
        d["15"] = 80.0
        df = pd.concat([df, pd.DataFrame([{
            "JENIS": "WASTE", "KETERANGAN": "Handling",
            "NAMA BARANG": "AYAM (BARU)", "NAMA RESTO": "1042.KWGGAL", **d}])],
            ignore_index=True)
        df["TOTAL"] = df[_DAY_COLS].sum(axis=1)
        return df

    def test_kolom_dan_nilai(self, tmp_path):
        from waste_anomaly.period_history import CHANGE_COLS, change_vs_history
        out = change_vs_history(self._anomali_df(), _month_b(tmp_path))
        for c in CHANGE_COLS:
            assert c in out.columns
        mie = out[out["NAMA BARANG"] == "MIE (V.20)"].set_index("KETERANGAN")
        assert abs(mie.loc["Handling", "BULAN LALU"] - 160.0) < 0.01
        assert abs(mie.loc["Handling", "PERUBAHAN %"] - 262.5) < 0.01
        assert mie.loc["Handling", "PERUBAHAN"] == "Naik Tinggi"
        assert abs(mie.loc["Cancel Nota", "BULAN LALU"] - 94.0) < 0.01
        assert mie.loc["Cancel Nota", "PERUBAHAN"] == "Stabil"

    def test_item_baru_label_baru(self, tmp_path):
        from waste_anomaly.period_history import change_vs_history
        out = change_vs_history(self._anomali_df(), _month_b(tmp_path))
        baru = out[out["NAMA BARANG"] == "AYAM (BARU)"].iloc[0]
        assert pd.isna(baru["BULAN LALU"])
        assert pd.isna(baru["PERUBAHAN %"])
        assert baru["PERUBAHAN"] == "Baru"

    def test_input_tidak_dimutasi(self, tmp_path):
        from waste_anomaly.period_history import change_vs_history
        df = self._anomali_df()
        before = list(df.columns)
        change_vs_history(df, _month_b(tmp_path))
        assert list(df.columns) == before  # kontrak 'konsumen hanya membaca'

    def test_pencocokan_abaikan_case_spasi(self, tmp_path):
        from waste_anomaly.period_history import change_vs_history
        df = self._anomali_df()
        df["KETERANGAN"] = df["KETERANGAN"].str.lower() + " "
        df["JENIS"] = " waste "
        out = change_vs_history(df, _month_b(tmp_path))
        mie = out[out["NAMA BARANG"] == "MIE (V.20)"]
        assert abs(mie["BULAN LALU"].max() - 160.0) < 0.01

    def test_baseline_none_kolom_netral(self):
        from waste_anomaly.period_history import change_vs_history
        out = change_vs_history(self._anomali_df(), None)
        assert pd.isna(out["BULAN LALU"]).all()
        assert (out["PERUBAHAN"] == "Stabil").all()

    def test_baseline_tipikal(self, tmp_path):
        from waste_anomaly.period_history import (
            aggregate_current, change_vs_history, typical_months)
        m1 = _month_b(tmp_path)
        m2 = aggregate_current(_df_a(base=10.0), 31, "Agustus 2026")
        typ = typical_months([m1, m2])
        out = change_vs_history(self._anomali_df(), typ)
        mie = out[(out["NAMA BARANG"] == "MIE (V.20)")
                  & (out["KETERANGAN"] == "Handling")].iloc[0]
        assert abs(mie["BULAN LALU"] - 430.0) < 0.01  # median(160, 700)

    def test_kolom_jenis_absen_fallback_resto_barang(self, tmp_path):
        from waste_anomaly.period_history import change_vs_history
        df = self._anomali_df().drop(columns=["JENIS", "KETERANGAN"])
        # Tanpa JENIS/KETERANGAN → kunci resto+barang: MIE = 674 vs 254.
        out = change_vs_history(df, _month_b(tmp_path))
        mie = out[out["NAMA BARANG"] == "MIE (V.20)"]
        assert len(mie) == 2
        assert (mie["BULAN LALU"] == 254.0).all()


# ============================================================
# [6] FORMAT & ISTILAH (models.py)
# ============================================================

class TestFormatDeltaPct:
    def test_nilai(self):
        from ui.models import fmt_delta_pct
        assert fmt_delta_pct(35.5) == "+35,5%"
        assert fmt_delta_pct(-12.0) == "-12,0%"
        assert fmt_delta_pct(0.0) == "0%"
        assert fmt_delta_pct(28.571) == "+28,6%"

    def test_nan_baru_none_kosong(self):
        from ui.models import fmt_delta_pct
        assert fmt_delta_pct(float("nan")) == "BARU"
        assert fmt_delta_pct(None) == ""
        assert fmt_delta_pct(pd.NA) == ""

    def test_delta_pct_cols_terpasang_di_model(self):
        from ui.models import DELTA_PCT_COLS
        assert "Perubahan %" in DELTA_PCT_COLS
        assert "PERUBAHAN %" in DELTA_PCT_COLS

    def test_cell_text_pakai_fmt_delta(self):
        _qapp()
        from ui.models import PandasTableModel
        # dtype=object supaya None TETAP None (kolom float mengubah None→NaN).
        m = PandasTableModel()
        m.set_dataframe(pd.DataFrame({
            "Perubahan %": pd.Series([35.5, float("nan"), None],
                                     dtype=object)}))
        assert m.data(m.index(0, 0), Qt_Display()) == "+35,5%"
        assert m.data(m.index(1, 0), Qt_Display()) == "BARU"
        assert m.data(m.index(2, 0), Qt_Display()) == ""

    def test_tabel_banding_perubahan_menantu(self):
        """Regresi v2.10.0: dulu '35,5' polos — kini '+35,5%' (jelas)."""
        _qapp()
        from ui.models import PandasTableModel
        m = PandasTableModel()
        m.set_dataframe(pd.DataFrame({
            "Metrik": ["Total Waste"], "Perubahan %": [28.571]}))
        assert m.data(m.index(0, 1), Qt_Display()) == "+28,6%"

    def test_num_cols_dan_tooltip(self):
        from ui.models import COLUMN_TOOLTIPS, _NUM_COLS
        for col in ("BULAN LALU", "PERUBAHAN %", "HARI", "Selisih"):
            assert col in _NUM_COLS
        for col in ("BULAN LALU", "PERUBAHAN %", "PERUBAHAN", "HARI"):
            tip = COLUMN_TOOLTIPS.get(col)
            assert tip and len(tip) > 10, f"{col} tanpa tooltip"


def Qt_Display():
    from PySide6.QtCore import Qt
    return Qt.ItemDataRole.DisplayRole


# ============================================================
# [7] STATE — baseline bersama (combo Banding ↔ Anomali)
# ============================================================

class TestBaselineState:
    def _ctx(self):
        _qapp()
        from ui.state import AppContext
        return AppContext({})

    def test_set_identitas_tanpa_signal_ganda(self):
        ctx = self._ctx()
        hits = []
        ctx.baseline_changed.connect(lambda: hits.append(1))
        b = {"label": "B"}
        ctx.set_banding_baseline(b)
        ctx.set_banding_baseline(b)  # objek sama → tidak emit ulang
        assert hits == [1]
        assert ctx.banding_baseline is b

    def test_effective_prioritas_combo_lalu_tipikal_lalu_terbaru(self):
        ctx = self._ctx()
        assert ctx.banding_baseline_effective() is None  # tanpa history
        m1 = {"label": "Juli 2026", "agg": pd.DataFrame(
            {"NAMA RESTO": ["R"], "NAMA BARANG": ["I"], "TOTAL": [1.0]})}
        m2 = {"label": "Agustus 2026", "agg": m1["agg"]}
        ctx.set_history([m1, m2], {"label": "Tipikal", "agg": m1["agg"]})
        # Tanpa pilihan combo → Tipikal
        assert ctx.banding_baseline_effective()["label"] == "Tipikal"
        # Pilihan combo menang
        ctx.set_banding_baseline(m1)
        assert ctx.banding_baseline_effective()["label"] == "Juli 2026"
        # Tanpa tipikal → bulan TERBARU (month_sort_key)
        ctx2 = self._ctx()
        ctx2.set_history([m1, m2], None)
        assert ctx2.banding_baseline_effective()["label"] == "Agustus 2026"

    def test_bulan_error_tidak_dipakai(self):
        ctx = self._ctx()
        bad = {"label": "RUSAK", "error": "x"}
        ctx.set_history([bad], None)
        assert ctx.banding_baseline_effective() is None


# ============================================================
# [8] UI — PeriodeView: perbesar, layar penuh, drill-down
# ============================================================

class TestPeriodeViewDrill:
    def _view(self, tmp_path):
        _qapp()
        from ui.state import AppContext
        from ui.view_periode import PeriodeView
        ctx = AppContext({})
        view = PeriodeView(ctx)
        # Suntik: bulan berjalan (A) + pembanding (B) termuat.
        df_a = _df_a()
        df_a["TOTAL"] = df_a[_DAY_COLS].sum(axis=1)
        ctx.set_dataset(df_a, {"key_akhir": 31})
        m = _month_b(tmp_path)
        p = str(tmp_path / "REKAP MENTAH JULI 2026.xlsx")
        view._entries = [{"path": p, "label": "Juli 2026"}]
        view._loaded[p] = m
        ctx.set_history([m], None)
        view._refresh_result()
        return view, ctx

    def test_kontrak_tombol_dan_dialog(self, tmp_path):
        view, _ = self._view(tmp_path)
        assert view._btn_expand is not None
        assert view._btn_full is not None
        assert hasattr(view, "_drill") and hasattr(view, "_full")

    def test_toggle_perbesar(self, tmp_path):
        view, _ = self._view(tmp_path)
        assert not view._card_files.isHidden()
        view._on_expand()
        assert view._card_files.isHidden()
        view._on_expand()
        assert not view._card_files.isHidden()

    def test_layar_penuh_tab_aktif(self, tmp_path):
        view, _ = self._view(tmp_path)
        view._on_fullscreen()
        assert view._full.isVisible()
        assert not view._full._table._model.dataframe.empty
        assert view._full._level == "tab"

    def test_drill_ringkasan_total_waste_ke_resto(self, tmp_path):
        view, _ = self._view(tmp_path)
        rec = pd.Series({"Metrik": "Total Waste", "Bulan Ini": 674,
                         "Pembanding": 254})
        view._on_tab_double("summary", rec)
        assert view._drill.isVisible()
        df = view._drill._table._model.dataframe
        assert view._drill._level == "resto"
        assert abs(df.iloc[0]["Bulan Ini"] - 674.0) < 0.01

    def test_drill_waste_per_hari_normalisasi(self, tmp_path):
        view, _ = self._view(tmp_path)
        rec = pd.Series({"Metrik": "Waste per Hari"})
        view._on_tab_double("summary", rec)
        df = view._drill._table._model.dataframe
        assert abs(df.iloc[0]["Bulan Ini"] - 674.0 / 31) < 0.01

    def test_drill_metrik_tak_dirinci_tidak_buka_dialog(self, tmp_path):
        view, _ = self._view(tmp_path)
        view._on_tab_double("summary", pd.Series({"Metrik": "Hari Data"}))
        assert not view._drill.isVisible()

    def test_drill_per_jenis(self, tmp_path):
        view, _ = self._view(tmp_path)
        view._on_tab_double("per_jenis", pd.Series({"JENIS": "WASTE"}))
        df = view._drill._table._model.dataframe
        assert view._drill._level == "resto"
        assert abs(df.iloc[0]["Pembanding"] - 254.0) < 0.01

    def test_rantai_resto_item_hari(self, tmp_path):
        view, _ = self._view(tmp_path)
        # Tab Cabang → item
        view._on_tab_double("branch",
                            pd.Series({"NAMA RESTO": "1042.KWGGAL"}))
        assert view._drill._level == "item"
        df_item = view._drill._table._model.dataframe
        assert "NAMA BARANG" in df_item.columns
        # Dari dialog item → hari (klik 2× via dispatch)
        view._drill_dispatch("item", {"resto": "1042.KWGGAL"},
                             pd.Series({"NAMA RESTO": "1042.KWGGAL",
                                        "NAMA BARANG": "MIE (V.20)"}))
        assert view._drill._level == "day"
        df_day = view._drill._table._model.dataframe
        assert list(df_day.columns)[0] == "HARI"
        assert abs(df_day[df_day["HARI"] == 24]["Bulan Ini"].iloc[0]
                   - 494.0) < 0.01

    def test_drill_item_mover_langsung_hari(self, tmp_path):
        view, _ = self._view(tmp_path)
        view._on_tab_double("items", pd.Series({
            "NAMA RESTO": "1042.KWGGAL", "NAMA BARANG": "MIE (V.20)"}))
        assert view._drill._level == "day"

    def test_drill_item_baru_hilang_juga_hari(self, tmp_path):
        view, _ = self._view(tmp_path)
        for key in ("new_items", "gone_items"):
            view._on_tab_double(key, pd.Series({
                "NAMA RESTO": "1042.KWGGAL", "NAMA BARANG": "MIE (V.20)"}))
            assert view._drill._level == "day"

    def test_dispatch_dari_jendela_layar_penuh(self, tmp_path):
        view, _ = self._view(tmp_path)
        view._on_fullscreen()
        # Klik 2× baris 'Total Waste' di jendela layar penuh:
        view._drill_dispatch("tab", {"tab_key": "summary"},
                             pd.Series({"Metrik": "Total Waste"}))
        assert view._drill.isVisible()
        assert view._drill._level == "resto"

    def test_tanpa_hasil_tidak_buka_pop_up(self, tmp_path):
        view, _ = self._view(tmp_path)
        view._clear_tables("kosong")
        view._on_tab_double("summary",
                            pd.Series({"Metrik": "Total Waste"}))
        assert not view._drill.isVisible()

    def test_breadcrumb_judul_jendela(self, tmp_path):
        view, _ = self._view(tmp_path)
        view._on_tab_double("summary", pd.Series({"Metrik": "Total Waste"}))
        view._drill_dispatch("resto", {},
                             pd.Series({"NAMA RESTO": "1042.KWGGAL"}))
        title = view._drill.windowTitle()
        assert "Item di" in title or "›" in title


# ============================================================
# [9] UI — AnomaliView: kolom perubahan + filter
# ============================================================

class TestAnomaliViewChange:
    def _view(self, tmp_path):
        _qapp()
        from ui.state import AppContext
        from ui.view_anomali import AnomaliView
        ctx = AppContext({})
        view = AnomaliView(ctx)
        df = _df_a()
        df["TOTAL"] = df[_DAY_COLS].sum(axis=1)
        df["ANOMALY SCORE"] = 10
        df["ANOMALY STATUS"] = "Perlu Review"
        ctx.set_dataset(df, {"key_akhir": 31})
        m = _month_b(tmp_path)
        ctx.set_history([m], None)
        view._refresh_table()
        return view, ctx, m

    def test_kolom_perubahan_muncul(self, tmp_path):
        view, _, _ = self._view(tmp_path)
        cols = view._table._model.dataframe.columns
        for c in ("BULAN LALU", "PERUBAHAN %", "PERUBAHAN",
                  "TOTAL BULAN LALU & % Selisih", "Selisih Bulan Lalu"):
            assert c in cols
        mie = view._table._model.dataframe
        # v2.21.0: tampilan GRUP per KETERANGAN — kedua baris fixture
        # (WASTE·MIE·KWGGAL, alasan Handling & Cancel Nota) kini DUA grup:
        # Handling: TOTAL 580 vs BULAN LALU 160 → Naik Tinggi (Selisih
        # 420); Cancel Nota: TOTAL 94 vs BULAN LALU 94 → Stabil.
        assert len(mie) == 3  # 2 grup + 1 baris pemisah
        h = mie[mie["KETERANGAN"] == "Handling"].iloc[0]
        assert abs(h["BULAN LALU"] - 160.0) < 0.01
        assert abs(h["TOTAL"] - 580.0) < 0.01
        assert h["PERUBAHAN"] == "Naik Tinggi"
        assert abs(h["Selisih Bulan Lalu"] - 420.0) < 0.01
        assert abs(h["TOTAL BULAN LALU & % Selisih"] - 160.0) < 0.01
        c = mie[mie["KETERANGAN"] == "Cancel Nota"].iloc[0]
        assert abs(c["BULAN LALU"] - 94.0) < 0.01
        assert abs(c["TOTAL"] - 94.0) < 0.01
        assert c["PERUBAHAN"] == "Stabil"
        assert abs(c["Selisih Bulan Lalu"] - 0.0) < 0.01
        assert str(h["KETERANGAN"]) == "Handling"  # nilai tunggal grup

    def test_tanpa_pembanding_kolom_tak_ada(self):
        _qapp()
        from ui.state import AppContext
        from ui.view_anomali import AnomaliView
        ctx = AppContext({})
        view = AnomaliView(ctx)
        df = _df_a()
        df["TOTAL"] = df[_DAY_COLS].sum(axis=1)
        df["ANOMALY SCORE"] = 10
        df["ANOMALY STATUS"] = "Perlu Review"
        ctx.set_dataset(df, {"key_akhir": 31})
        view._refresh_table()
        assert "BULAN LALU" not in view._table._model.dataframe.columns
        assert not view._cb_change.isEnabled()

    def test_combo_filter_kategori(self, tmp_path):
        view, _, _ = self._view(tmp_path)
        assert view._cb_change.isEnabled()
        assert view._cb_change.count() == 7  # Semua + 6 kategori
        n_all = len(view._table._model.dataframe)
        # v2.19.0: filter kategori LEVEL GRUP — 'Naik Tinggi' memilih grup
        # dgn kategori itu TANPA memangkas anggotanya (v2.21.0: fixture = 2
        # grup keterangan — grup Naik Tinggi = Handling dgn TOTAL utuh 580).
        # (Sinyal combo mengandung guard isVisible — view offscreen tak
        # terlihat → panggil handler langsung, meniru kondisi terlihat.)
        idx = [i for i in range(view._cb_change.count())
               if view._cb_change.itemData(i) == "Naik Tinggi"][0]
        view._cb_change.setCurrentIndex(idx)
        view._on_change_filter()
        df = view._table._model.dataframe
        assert len(df) == 1
        assert (df["PERUBAHAN"] == "Naik Tinggi").all()
        assert abs(df["TOTAL"].iloc[0] - 580.0) < 0.01  # TOTAL utuh grup
        # Kategori yang tak cocok (Turun Tinggi) → 0 grup tampil.
        idx = [i for i in range(view._cb_change.count())
               if view._cb_change.itemData(i) == "Turun Tinggi"][0]
        view._cb_change.setCurrentIndex(idx)
        view._on_change_filter()
        assert len(view._table._model.dataframe) == 0
        # Kembali ke Semua.
        view._cb_change.setCurrentIndex(0)
        view._on_change_filter()
        assert len(view._table._model.dataframe) == n_all

    def test_df_state_tidak_dimutasi(self, tmp_path):
        view, ctx, _ = self._view(tmp_path)
        assert "BULAN LALU" not in ctx.anomali_df().columns

    def test_table_cols_kontrak(self):
        # v2.19.0 — layout sampel user: BULAN LALU + PERUBAHAN % digabung
        # jadi 'TOTAL BULAN LALU & % Selisih' + kolom 'Selisih Bulan Lalu'.
        from ui.view_anomali import TABLE_COLS
        for col in ("PERUBAHAN", "TOTAL BULAN LALU & % Selisih",
                    "Selisih Bulan Lalu"):
            assert col in TABLE_COLS

    def test_detail_cols_kontrak(self):
        from ui.view_anomali import DETAIL_COLS
        for col in ("BULAN LALU", "PERUBAHAN %", "PERUBAHAN"):
            assert col in DETAIL_COLS


# ============================================================
# [10] CONFIG — threshold baru
# ============================================================

class TestConfigV2102:
    def test_threshold_baru_ada(self):
        cfg = json.loads((REPO / "waste_anomaly" / "config.json")
                         .read_text(encoding="utf-8"))
        t = cfg["thresholds"]
        assert t["TH_CHANGE_HIGH"] == 50.0
        assert t["TH_CHANGE_STABLE"] == 20.0
        assert t["TH_CHANGE_MIN_ABS"] == 10.0

    def test_versi_naik(self):
        from ui.shared import APP_VERSION
        assert APP_VERSION == "2.20.0"  # v2.15.0: sekali jalan (pin dinaikkan)


# ============================================================
# [11] v2.10.3 — REGRESI AUDIT DEEP (regex bulan underscore +
#      pop-up basi ditutup saat konteks banding berganti)
# ============================================================

class TestV2103RegexBulan:
    """FIX 1 (audit v2.10.3): `\\b` menolak nama bulan didahului underscore
    ("WASTE_SEPTEMBER_2026.xlsx" → None — underscore = word char, tak ada
    word-boundary). Lookbehind non-huruf menggantikannya."""

    def test_bulan_setelah_underscore_terdeteksi(self):
        from waste_anomaly.period_history import detect_month_label
        assert detect_month_label(
            "WASTE_SEPTEMBER_2026.xlsx") == "September 2026"
        assert detect_month_label(
            "01-31_SEPTEMBER_2026.xlsx") == "September 2026"
        assert detect_month_label("rekap_mentah_mei_2026.xlsx") == "Mei 2026"

    def test_bulan_menempel_huruf_tetap_ditolak(self):
        from waste_anomaly.period_history import (
            detect_month_label, month_sort_key)
        assert detect_month_label("XSEPTEMBER2026.xlsx") is None
        assert detect_month_label("SEPTEMBERS.xlsx") is None
        # v2.13.14 (gel-5 B23) — DITULIS ULANG JUJUR: assertion lama
        # mem-PIN month_sort_key("XJULI") == (0, 0) — nilai sentinel lama
        # yang justru menempatkan label tak-terparse sort PERTAMA (bug
        # audit B23). Kini sentinel (9999, 0) = TERAKHIR; nama bulan yang
        # menempel huruf tetap DITOLAK (parse None — bukan fallback).
        assert month_sort_key("XJULI") == (9999, 0)

    def test_bulan_dipisah_digit_kini_diterima(self):
        # "31SEPTEMBER" — digit langsung sebelum bulan: dulu \b menolak,
        # kini diterima (lebih toleran; salah positif huruf tetap ditolak).
        from waste_anomaly.period_history import detect_month_label
        assert detect_month_label(
            "REKAP31SEPTEMBER2026.xlsx") == "September 2026"

    def test_pola_lama_tetap_cocok(self):
        from waste_anomaly.period_history import detect_month_label
        assert detect_month_label(
            "REKAP MENTAH_01-31 AGUSTUS 2026_TEGAR.xlsx") == "Agustus 2026"
        assert detect_month_label("rekap juli 2025.xlsx") == "Juli 2025"
        assert detect_month_label("DATA.xlsx") is None


class TestV2103PopupBasi:
    """FIX 2 (audit v2.10.3): pop-up drill/layar penuh yang masih terbuka
    saat hasil banding digambar ulang / dikosongkan = tabel konteks LAMA
    (angka basi). Kini ditutup otomatis."""

    def _view(self, tmp_path):
        _qapp()
        from ui.state import AppContext
        from ui.view_periode import PeriodeView
        ctx = AppContext({})
        view = PeriodeView(ctx)
        df_a = _df_a()
        df_a["TOTAL"] = df_a[_DAY_COLS].sum(axis=1)
        ctx.set_dataset(df_a, {"key_akhir": 31})
        m = _month_b(tmp_path)
        p = str(tmp_path / "REKAP MENTAH JULI 2026.xlsx")
        view._entries = [{"path": p, "label": "Juli 2026"}]
        view._loaded[p] = m
        ctx.set_history([m], None)
        view._refresh_result()
        return view, ctx

    def test_clear_tables_menutup_pop_up(self, tmp_path):
        view, _ = self._view(tmp_path)
        view._on_fullscreen()
        assert view._full.isVisible()
        view._clear_tables("tes")
        assert not view._full.isVisible()

    def test_render_baru_menutup_pop_up_lama(self, tmp_path):
        view, _ = self._view(tmp_path)
        view._open_resto("🏬 tes resto")
        assert view._drill.isVisible()
        # refresh penuh (mis. combo berganti / data baru) → pop-up lama
        # menampilkan salinan konteks lama → harus tertutup.
        view._refresh_result()
        assert not view._drill.isVisible()
        # tabel utama tetap dirender normal (pop-up tutup ≠ hasil hilang).
        assert view._has_result
        assert not view._tables["summary"]._model.dataframe.empty

    def test_toggle_expand_tak_menutup_pop_up(self, tmp_path):
        view, _ = self._view(tmp_path)
        view._open_resto("🏬 tes resto")
        assert view._drill.isVisible()
        # ⤢ hanya layout (kartu file) — bukan perubahan konteks data.
        view._on_expand()
        assert view._drill.isVisible()
        assert view._card_files.isHidden()
