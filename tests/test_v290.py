"""Test — v2.9.0: tab Hari Mencurigakan + istilah awam & tooltip + perf cache.

Tiga permintaan user (satu pesan):
1. "kerjakan untuk level hari" → Stage 15 day_focus + tab Hari Mencurigakan
   (bukti pembuktian read-only v2.8.3: 74% anomali bisa dilokalisasi ke hari).
2. "istilah misal S-1 Spike vs AVG bisa gak dipermudah lagi? atau buatkan
   tool tip biar aku mudah mencerna. Semua istilah ya bukan hanya S-1" →
   SIGNAL_PARTS + chip label Bahasa awam + COLUMN_TOOLTIPS di SEMUA header
   kolom / metrik detail / chip / KPI / kontrol filter.
3. "Cari juga potensi yang bikin lambat ketika klik tombol / unfilter" →
   LRU anomali_df per tanda tangan filter + cache teks model + cache fit
   LRU DataTable + blob pencarian (diukur: unfilter 461→87-95 ms, search
   1.456→~95 ms di data asli sandbox).

Headless: QT_QPA_PLATFORM=offscreen sebelum PySide6 (konvensi suite).
"""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
UI = REPO / "ui"


def _qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


# ============================================================
# [1] STAGE 15 — day_focus (unit, sintetis)
# ============================================================

def _df_hari() -> pd.DataFrame:
    """3 outlet, 1 item: outlet A salah ketik di hari 17 (70 vs tipikal 5).

    Outlet A: 29 hari × 5 + hari-17 = 70 (typo 10x).
    Outlet B: 30 hari × 5. Outlet C: 30 hari × 4.
    Semua baris ber-ANOMALY STATUS Potensi supaya jadi kandidat.
    """
    rows = []
    for resto in ("A.OUTLET", "B.OUTLET", "C.OUTLET"):
        data = {str(d): 5.0 if resto != "C.OUTLET" else 4.0
                for d in range(1, 31)}
        if resto == "A.OUTLET":
            data["17"] = 70.0  # salah ketik 7 → 70
        rows.append({
            "NAMA RESTO": resto, "NAMA BARANG": "ITEM UJI",
            "JENIS": "WASTE", "KETERANGAN": "Kualitas",
            **{str(d): data[str(d)] for d in range(1, 31)},
            "TOTAL": float(sum(data.values())),
            "ANOMALY STATUS": "Potensi Anomali",
            "ANOMALY SCORE": 9,
            "HARI MAX": 17.0 if resto == "A.OUTLET" else 1.0,
            "SCALE SIGNAL": "YES" if resto == "A.OUTLET" else "NO",
            "SINGLE DAY": "NO",
        })
    return pd.DataFrame(rows)


class TestDayFocusUnit:

    def _annotate(self, df, key_akhir=31, config=None):
        from waste_anomaly.day_focus import annotate_day_evidence
        return annotate_day_evidence(df.copy(), key_akhir,
                                     config or {"thresholds": {}})

    def test_kolom_output_selalu_ada(self):
        from waste_anomaly.day_focus import DAY_FOCUS_COLS
        out = self._annotate(_df_hari())
        for col in DAY_FOCUS_COLS:
            assert col in out.columns, f"kolom {col} tidak dibuat"

    def test_typo_70_vs_tipikal_5_terdeteksi_hari_17(self):
        out = self._annotate(_df_hari())
        a = out[out["NAMA RESTO"] == "A.OUTLET"].iloc[0]
        assert int(a["HARI TERSANGKA"]) == 17
        assert a["NILAI HARI TERSANGKA"] == 70.0
        # tipikal cabang lain hari-17 = median(5, 4) = 4,5
        assert abs(a["TIPIKAL CABANG LAIN"] - 4.5) < 1e-9
        assert int(a["N CABANG PEMBANDING"]) == 2
        # rasio = 70 / 4,5 ≈ 15,6x → bukti YES
        assert a["RASIO VS CABANG LAIN"] > 5
        assert a["BUKTI HARI"] == "YES"
        assert "Hari 17" in str(a["ALASAN HARI"])
        assert "cabang lain" in str(a["ALASAN HARI"])

    def test_outlet_sendiri_dikeluarkan_dari_pembanding(self):
        """Outlet B (5,0 tiap hari) tidak boleh jadi pembanding dirinya
        sendiri — tipikalnya dari C saja (4,0)."""
        out = self._annotate(_df_hari())
        b = out[out["NAMA RESTO"] == "B.OUTLET"].iloc[0]
        # hari max B = hari 1; peer hari-1 = A(5) + C(4) → median 4,5
        assert int(b["N CABANG PEMBANDING"]) == 2
        assert abs(b["TIPIKAL CABANG LAIN"] - 4.5) < 1e-9

    def test_baris_normal_tanpa_bukti(self):
        df = _df_hari()
        df.loc[df["NAMA RESTO"] == "C.OUTLET", "ANOMALY STATUS"] = "Normal"
        out = self._annotate(df)
        c = out[out["NAMA RESTO"] == "C.OUTLET"].iloc[0]
        assert c["BUKTI HARI"] == "NO"
        assert str(c["ALASAN HARI"]) == ""

    def test_tanpa_kolom_hari_graceful(self):
        df = pd.DataFrame({
            "NAMA RESTO": ["A"], "NAMA BARANG": ["X"],
            "ANOMALY STATUS": ["Potensi Anomali"], "HARI MAX": [3.0],
            "TOTAL": [10.0],
        })
        out = self._annotate(df)
        assert "HARI TERSANGKA" in out.columns
        assert (out["BUKTI HARI"] == "NO").all()

    def test_df_kosong_tidak_crash(self):
        out = self._annotate(pd.DataFrame(columns=["NAMA RESTO"]))
        assert len(out) == 0
        assert "BUKTI HARI" in out.columns

    def test_threshold_rasio_bisa_diatur_config(self):
        # rasio 15,6x — naikkan threshold ke 20 → bukti lewat komponen lain
        out = self._annotate(_df_hari(),
                             config={"thresholds": {"TH_HARI_PEER_RATIO": 20.0}})
        a = out[out["NAMA RESTO"] == "A.OUTLET"].iloc[0]
        assert a["RASIO VS CABANG LAIN"] > 5  # rasio tetap dihitung
        # S12 scale YES + share 70/215 ≈ 32,5% → bukti tetap YES (komponen lain)
        assert a["BUKTI HARI"] == "YES"


# ============================================================
# [2] PIPELINE — Stage 15 pada fixture sample_workbook.xlsx
# ============================================================

class TestPipelineStage15:
    def _summary(self):
        from waste_anomaly.pipeline import run_pipeline
        sample = REPO / "sample_workbook.xlsx"
        if not sample.exists():
            import pytest
            pytest.skip("sample_workbook.xlsx tidak ada")
        return run_pipeline(str(sample), key_akhir=31)

    def test_kolom_bukti_hari_ada_di_output(self):
        from waste_anomaly.day_focus import DAY_FOCUS_COLS
        s = self._summary()
        assert s.get("success"), s.get("error")
        df = s["df"]
        for col in DAY_FOCUS_COLS:
            assert col in df.columns, f"{col} hilang dari output pipeline"

    def test_domain_bukti_hari(self):
        s = self._summary()
        df = s["df"]
        assert set(df["BUKTI HARI"].astype(str)) <= {"YES", "NO"}

    def test_summary_day_evidence_count(self):
        s = self._summary()
        n = int((s["df"]["BUKTI HARI"] == "YES").sum())
        assert s["day_evidence_count"] == n

    def test_hari_tersangka_dalam_1_31(self):
        s = self._summary()
        hm = pd.to_numeric(s["df"]["HARI TERSANGKA"], errors="coerce").dropna()
        assert ((hm >= 1) & (hm <= 31)).all()

    def test_reasons_pakai_istilah_awam(self):
        """v2.9.0: fragmen sinyal = Bahasa awam — jargon lama hilang."""
        s = self._summary()
        reasons = " | ".join(s["df"]["ANOMALY REASONS"].astype(str))
        for jargon in ("Spike vs AVG", "MAX jauh", "outlier", "Single-day"):
            assert jargon not in reasons, f"jargon '{jargon}' masih ada"

    def test_reasons_awam_tetap_memicu_chip(self):
        """Kontrak V26-C1: fragmen baru sinkron dgn deteksi chip UI."""
        from ui.view_anomali import SIGNALS
        from waste_anomaly.signals import SIGNAL_PARTS
        assert {c for c, _l, _f in SIGNALS} == {c for c, _f in SIGNAL_PARTS}
        s = self._summary()
        top = s["df"].sort_values("ANOMALY SCORE", ascending=False).iloc[0]
        reasons = str(top.get("ANOMALY REASONS") or "")
        frags = [f for _c, f in SIGNAL_PARTS if f in reasons]
        assert len(frags) > 0, "baris top tanpa sinyal (fixture lemah)"


# ============================================================
# [3] TAB HARI MENCURIGAKAN (UI offscreen)
# ============================================================

def _hari_df() -> pd.DataFrame:
    df = _df_hari()
    df["HARI TERSANGKA"] = [17.0, 1.0, 1.0]
    df["BUKTI HARI"] = ["YES", "NO", "NO"]
    df["ALASAN HARI"] = [
        "Hari 17: nilai 70 — 15,6x cabang lain (tipikal 4,5)", "", ""]
    df["NILAI HARI TERSANGKA"] = [70.0, 5.0, 4.0]
    df["TIPIKAL CABANG LAIN"] = [4.5, 4.5, np.nan]
    df["N CABANG PEMBANDING"] = [2, 2, 0]
    df["RASIO VS CABANG LAIN"] = [70 / 4.5, 5 / 4.5, np.nan]
    df["SHARE HARI TERSANGKA"] = [70 / 215.0, 5 / 150.0, np.nan]
    return df


def _make_hari_view(df=None):
    _qapp()
    from ui.state import AppContext
    from ui.view_hari import HariView
    ctx = AppContext({})
    view = HariView(ctx)
    ctx.set_dataset(df if df is not None else _hari_df(), {"key_akhir": 31})
    view._refresh_table()
    return view, ctx


class TestHariView:

    def test_mainwindow_5_tab_dengan_hari(self):
        # v2.12.0: 4 → 5 tab (+ Follow Up di indeks 1 — Hari bergeser ke 2).
        from ui.app import MainWindow
        _qapp()
        win = MainWindow()
        assert win._tabs.count() == 5
        assert win._tabs.tabText(1).split(" (")[0] == "Follow Up"
        assert win._tabs.tabText(2) == "Hari Mencurigakan"
        titles = [win._tabs.tabText(i).split(" (")[0] for i in range(5)]
        assert titles == ["Anomali", "Follow Up", "Hari Mencurigakan",
                          "Banding Periode", "Pipeline"]
        win.close()

    def test_render_tabel_bukti_default(self):
        view, _ = _make_hari_view()
        # default: hanya BUKTI YES → 1 baris (outlet A)
        assert view._table._model.rowCount() == 1
        rec = view._table._model.record(0)
        assert rec["NAMA RESTO"] == "A.OUTLET"

    def test_combo_semua_anomali(self):
        view, _ = _make_hari_view()
        view.show()
        _qapp().processEvents()
        view._cb_mode.setCurrentIndex(1)  # Semua anomali
        _qapp().processEvents()
        assert view._table._model.rowCount() == 3

    def test_dataset_tanpa_kolom_hari_placeholder(self):
        df = pd.DataFrame({
            "NAMA RESTO": ["A"], "NAMA BARANG": ["X"],
            "ANOMALY STATUS": ["Potensi Anomali"],
            "ANOMALY SCORE": [5],
        })
        view, _ = _make_hari_view(df)
        assert view._table._model.rowCount() == 0
        assert "bukti hari" in view._lbl_count.text()

    def test_klik_baris_buka_popup_dan_peta_hari(self):
        from PySide6.QtWidgets import QLabel
        view, _ = _make_hari_view()
        view._table.selectRow(0)
        rec = view._table.selected_record()
        assert rec is not None
        view._popup.show_record(rec)
        labels = view._popup._panel._content.findChildren(QLabel)
        # peta hari: sel ber-tooltip 'Hari N: ...' dan sel merah tersangka
        day_cells = [l for l in labels if l.toolTip().startswith("Hari ")]
        assert len(day_cells) >= 30, "peta hari 1-31 tidak ter-render"
        red = [l for l in day_cells if "#dc2626" in (l.styleSheet() or "")]
        assert red, "hari tersangka tidak disorot merah"
        assert red[0].text().startswith("17"), red[0].text()

    def test_refresh_dibungkus_busy_feedback(self):
        """Kontrak v2.8.3 tetap: titik tunggal render dibungkus (anti-beku)."""
        src = (UI / "view_hari.py").read_text(encoding="utf-8")
        assert "busy_feedback(" in src
        assert "_refresh_table_impl" in src

    def test_drill_down_double_klik(self):
        view, ctx = _make_hari_view()
        rec = view._table._model.record(0)
        view._on_double(rec)
        assert ctx.active_filters["cabang"] == "A.OUTLET"
        assert ctx.active_filters["item"] == "ITEM UJI"

    def test_kpi_rasio_terbesar(self):
        view, _ = _make_hari_view()
        assert "×" in view._kpi_rasio._value.text()


# ============================================================
# [4] ISTILAH AWAM + TOOLTIP SEMUA (permintaan #2)
# ============================================================

class TestTooltipsDanIstilah:

    def test_fragment_sinyal_tanpa_jargon(self):
        from waste_anomaly.signals import SIGNAL_PARTS
        for _col, frag in SIGNAL_PARTS:
            for jargon in ("AVG", "MEDIAN", "Spike", "outlier", "peer",
                           "Single-day", "SCALE", "MAX", "TOTAL"):
                assert jargon not in frag, f"'{frag}' masih ber-jargon"

    def test_chip_label_awam_dan_berpenjelasan(self):
        from ui.view_anomali import SIGNALS, _CHIP_LABELS, _CHIP_TIPS
        for col, label, _frag in SIGNALS:
            assert "S" in label.split(" ·")[0]  # nomor sinyal dipertahankan
            assert col in _CHIP_TIPS and len(_CHIP_TIPS[col]) > 40, (
                f"tooltip chip {col} kosong/pendek")
            assert col in _CHIP_LABELS

    def test_kamus_kolom_menutup_semua_kolom_tabel(self):
        from ui.models import COLUMN_TOOLTIPS
        from ui.view_anomali import TABLE_COLS as T_ANOMALI
        from ui.view_hari import TABLE_COLS as T_HARI
        for col in set(T_ANOMALI) | set(T_HARI):
            assert col in COLUMN_TOOLTIPS, (
                f"kolom {col} tak ada di kamus tooltip (permintaan: SEMUA istilah)")

    def test_header_tooltip_model(self):
        from PySide6.QtCore import Qt
        from ui.models import PandasTableModel
        df = pd.DataFrame({"% to BOM": [0.05], "KOLOM TAK DIKAMUS": ["x"]})
        m = PandasTableModel(df)
        c = list(df.columns).index("% to BOM")
        tip = m.headerData(c, Qt.Horizontal, Qt.ToolTipRole)
        assert tip and "penjualan" in str(tip).lower()
        # kolom tanpa kamus → nama kolom (fallback tetap ada)
        c2 = list(df.columns).index("KOLOM TAK DIKAMUS")
        assert m.headerData(c2, Qt.Horizontal, Qt.ToolTipRole) == "KOLOM TAK DIKAMUS"

    def test_metrik_detail_bertooltip(self):
        from PySide6.QtWidgets import QLabel
        from ui.state import AppContext
        from ui.view_anomali import DetailPanel
        _qapp()
        panel = DetailPanel(AppContext({}))
        rec = _hari_df().iloc[0]
        panel.show_record(rec)
        keys = [l for l in panel._content.findChildren(QLabel)
                if l.toolTip()]
        assert keys, "label metrik pop-up tanpa tooltip kamus"

    def test_kpi_card_bertooltip(self):
        from ui.widgets import KpiStrip
        _qapp()
        strip = KpiStrip()
        for card in (strip.kpi_total, strip.kpi_prioritas, strip.kpi_waste):
            assert card.toolTip(), "KPI tanpa tooltip"

    def test_ratio_format_x(self):
        from ui.models import fmt_ratio_x
        assert fmt_ratio_x(404.0) == "404×"
        assert fmt_ratio_x(8.5) == "8,5×"
        assert fmt_ratio_x(float("nan")) == ""
        assert fmt_ratio_x(None) == ""

    def test_kolom_rasio_tampil_sebagai_x(self):
        from PySide6.QtCore import Qt
        from ui.models import PandasTableModel
        df = pd.DataFrame({"RASIO VS CABANG LAIN": [404.0, 8.5]})
        m = PandasTableModel(df)
        assert m.data(m.index(0, 0), Qt.DisplayRole) == "404×"
        assert m.data(m.index(1, 0), Qt.DisplayRole) == "8,5×"


# ============================================================
# [5] PERFORMA (kontrak cache, bukan timing — sandbox bervariasi)
# ============================================================

class TestPerfCacheV290:

    def _ctx(self):
        from ui.state import AppContext
        ctx = AppContext({})
        ctx.set_dataset(_hari_df(), {"key_akhir": 31})
        return ctx

    def test_anomali_lru_objek_sama_per_state(self):
        ctx = self._ctx()
        a = ctx.anomali_df()
        b = ctx.anomali_df()
        assert a is b, "memo identitas objek rusak (render bolak-balik mahal)"
        # state lain → objek lain; kembali ke state awal → objek awal
        ctx.set_filter("cabang", "A.OUTLET")
        c = ctx.anomali_df()
        assert c is not a
        ctx.reset_filters()
        ctx.filters_changed.emit()
        d = ctx.anomali_df()
        assert d is a, "LRU per tanda tangan filter tidak mengembalikan objek lama"

    def test_anomali_lru_dibersihkan_dataset_baru(self):
        ctx = self._ctx()
        a = ctx.anomali_df()
        ctx.set_dataset(_hari_df(), {"key_akhir": 31})
        b = ctx.anomali_df()
        assert b is not a
        assert len(ctx._anomali_cache) >= 1

    def test_model_cache_teks_dipakai_ulang(self):
        from PySide6.QtCore import Qt
        from ui.models import PandasTableModel
        df = pd.DataFrame({"TOTAL": [12345.6, 2.0]})
        m = PandasTableModel(df)
        m.data(m.index(0, 0), Qt.DisplayRole)
        assert (0, 0) in m._texts
        m.sort(0, 0)
        assert len(m._texts) == 0, "sort tidak membatalkan cache teks"

    def test_fit_lru_datatable(self):
        _qapp()
        from ui.widgets import DataTable
        df = _hari_df()
        t = DataTable()
        t.show()
        _qapp().processEvents()
        t.set_dataframe(df, sort_desc="ANOMALY SCORE",
                        narrow_hide=["JENIS", "KETERANGAN"],
                        visible_cols=["ANOMALY SCORE", "NAMA RESTO",
                                      "TOTAL", "ALASAN HARI"])
        assert len(t._fit_cache) == 1
        w1 = t.columnWidth(0)
        # render ulang df SAMA → hit (entri dipakai, bukan diukur ulang)
        t.set_dataframe(df, sort_desc="ANOMALY SCORE",
                        narrow_hide=["JENIS", "KETERANGAN"],
                        visible_cols=["ANOMALY SCORE", "NAMA RESTO",
                                      "TOTAL", "ALASAN HARI"])
        assert len(t._fit_cache) == 1
        assert t.columnWidth(0) == w1
        t.close()

    def test_blob_pencarian_ekuivalen_dgn_perkolom(self):
        from ui.shared import _apply_filters, _build_search_blob
        df = pd.DataFrame({
            "NAMA RESTO": ["A.OUTLET", "B.OUTLET", "C.OUTLET"],
            "NAMA BARANG": ["ITEM UJI", "MIE", "KEJU"],
            "TOTAL": [70.0, np.nan, 4.0],
            "JENIS": ["WASTE", "WASTE", "TRIAL"],
        })
        blob = _build_search_blob(df)
        for term in ("uji", "KEJU", "70", "nan", "waste", "z"):
            a = _apply_filters(df, None, search=term)
            b = _apply_filters(df, None, search=term, search_blob=blob)
            assert list(a.index) == list(b.index), (
                f"blob ≠ per-kolom untuk term {term!r}")
        # NaN tidak boleh cocok dicari 'nan'
        assert blob.iloc[1].split("\x01")[2] == ""

    def test_blob_pemisah_bukan_nul(self):
        """\x00 dipotong senyap oleh numpy/pandas (C-terminator) → harus \x01."""
        from ui.shared import _build_search_blob
        df = pd.DataFrame({"A": ["x"], "B": ["1"]})
        blob = _build_search_blob(df)
        assert "\x01" in blob.iloc[0]
        assert "\x00" not in blob.iloc[0]

    def test_set_dataset_menerima_blob_worker(self):
        from ui.state import AppContext
        from ui.shared import _build_search_blob
        df = _hari_df()
        blob = _build_search_blob(df)
        ctx = AppContext({})
        ctx.set_dataset(df, {"key_akhir": 31, "search_blob": blob})
        assert ctx._search_blob is blob
        assert ctx._search_blob_version == ctx.data_version


# ============================================================
# [6] SIGnals awam — unit signal lama tetap hijau dgn fragmen baru
# ============================================================

class TestSignalFragmentBaru:

    def test_s1_masuk_reasons(self):
        from waste_anomaly.signals import compute_signals
        df = pd.DataFrame({
            "Count Hari": [2], "MAX / AVG": [3.0],
            "MAX / AVG AKTIF": [np.nan], "MAX / MEDIAN AKTIF": [np.nan],
            "MAX / SECOND MAX": [np.nan], "MAX SHARE": [np.nan],
            "LAST DAY SHARE": [np.nan], "TOTAL BOM": [np.nan],
            "Rill % to BOM": [np.nan], "PEER COUNT": [0],
            "PEER MEDIAN TOTAL": [np.nan], "PEER MEDIAN MAX": [np.nan],
            "SCALE SIGNAL": ["NO"], "MAX": [3.0], "TOTAL": [10.0],
            "AVG": [1.0], "AVG AKTIF": [np.nan], "MEDIAN AKTIF": [np.nan],
            "SECOND MAX": [np.nan], "JENIS": ["WASTE"],
            "KETERANGAN": ["Kualitas"],
        })
        out = compute_signals(df, 31, {"thresholds": {}})
        assert "Lonjakan vs rata-rata harian" in str(out["ANOMALY REASONS"].iloc[0])
