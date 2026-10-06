"""test_v2134.py — v2.13.4: fix "hari 30 error" (Banding Periode).

Laporan user: "kenapa periode pembanding hanya ada hari 30 error?
harusnya gak papa kan?" — baris 'Hari Data' (mis. 30 vs 31 hari) di tabel
Ringkasan banding menampilkan 'BARU' di kolom Perubahan %, terbaca
seperti error padahal bulan 30 hari wajar (September dsb.).

Akar: compare_quantity menandai Perubahan 'Hari Data' = None (kosong
SENGAJA — beda panjang bulan bukan kinerja), tapi kolom float64
mengubah None→NaN; fmt_delta_pct lalu menampilkan NaN='BARU' (label
"item baru" — om kosong di baris Hari Data).

Fix: kolom 'Perubahan %' summary dibangun ulang sebagai OBJECT supaya
None TETAP None → fmt_delta_pct(None) = '' (kosong, desain awal).
NaN asli (base=0, tanpa riwayat) TETAP 'BARU' — semantik item-baru
utuh. Kontrak pd.isna(None)=True → test lama tetap hijau.

Plus: situs fillna lama di compare_quantity/period_compare dinormalkan
ke coerce-numerik (pola compare_level) — FutureWarning downcasting
pandas 3.x hilang tanpa perubahan perilaku.
"""
from __future__ import annotations

import os
import warnings
from pathlib import Path

import pandas as pd

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = Path(__file__).resolve().parent.parent


def _qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _month(label, ka, rows):
    """Bulan sintetis: rows = [(resto, item, total)] — pola test_v2100."""
    days = {str(d): 0.0 for d in range(1, 32)}
    agg = pd.DataFrame(
        [{"NAMA RESTO": r, "NAMA BARANG": i, "TOTAL": t, "HARI AKTIF": 3,
          **days} for r, i, t in rows])
    jt = pd.DataFrame({"JENIS": ["WASTE"], "TOTAL": [sum(t for *_,
                                                          t in rows)]})
    return {"label": label, "agg": agg, "jenis_totals": jt, "key_akhir": ka}


# ============================================================
# [A] FIX UTAMA — 'Hari Data' bukan 'BARU'
# ============================================================

class TestHariDataBukanBaru:
    def test_none_tetap_none_bukan_nan(self):
        """Kolom object: None HARUS tetap None (float64 mengubahnya NaN)."""
        from waste_anomaly.period_history import compare_quantity
        a = _month("Bulan Ini", 30, [("R1", "X", 150.0)])
        b = _month("Agustus 2026", 31, [("R1", "X", 155.0)])
        s = compare_quantity(a, b)["summary"]
        v = s.set_index("Metrik").loc["Hari Data", "Perubahan %"]
        assert v is None, f"None berubah jadi {v!r} ({type(v)})"
        assert s["Perubahan %"].dtype == object

    def test_isna_kontrak_test_lama_utuh(self):
        """pd.isna(None) = True — kontrak test v2.10.0 tetap hijau."""
        from waste_anomaly.period_history import compare_quantity
        a = _month("Bulan Ini", 30, [("R1", "X", 150.0)])
        b = _month("Agustus 2026", 31, [("R1", "X", 155.0)])
        s = compare_quantity(a, b)["summary"]
        assert pd.isna(
            s.set_index("Metrik").loc["Hari Data", "Perubahan %"])

    def test_render_kosong_bukan_baru(self):
        """Jalur Qt: sel 'Hari Data' × 'Perubahan %' = '' — bukan 'BARU'.

        Ini bug yang DILIHAT user (v2.13.3 ke bawah: 'BARU' di baris
        hari 30 → dibaca error)."""
        _qapp()
        from PySide6.QtCore import Qt

        from ui.models import PandasTableModel
        from waste_anomaly.period_history import compare_quantity
        a = _month("Bulan Ini", 30, [("R1", "X", 180.0)])
        b = _month("Agustus 2026", 31, [("R1", "X", 140.0)])
        s = compare_quantity(a, b)["summary"]
        m = PandasTableModel()
        m.set_dataframe(s)
        texts = {m.data(m.index(r, 0), Qt.DisplayRole):
                 m.data(m.index(r, 3), Qt.DisplayRole)
                 for r in range(m.rowCount())}
        assert texts["Hari Data"] == "", texts
        assert texts["Total Waste"] == "+28,6%"
        # 180/30 = 6,0 vs 140/31 ≈ 4,516 → +32,9%
        assert texts["Waste per Hari"] == "+32,9%"

    def test_render_kosong_bulan_sama_panjang(self):
        """31 vs 31 pun tetap kosong (None selalu ada di 4-tuple)."""
        _qapp()
        from PySide6.QtCore import Qt

        from ui.models import PandasTableModel
        from waste_anomaly.period_history import compare_quantity
        a = _month("Bulan Ini", 31, [("R1", "X", 100.0)])
        b = _month("Agustus 2026", 31, [("R1", "X", 100.0)])
        s = compare_quantity(a, b)["summary"]
        m = PandasTableModel()
        m.set_dataframe(s)
        texts = {m.data(m.index(r, 0), Qt.DisplayRole):
                 m.data(m.index(r, 3), Qt.DisplayRole)
                 for r in range(m.rowCount())}
        assert texts["Hari Data"] == ""
        assert texts["Total Waste"] == "0%"

    def test_nan_asli_tetap_baru(self):
        """NaN dari base=0 (pembanding kosong) TETAP 'BARU' — semantik
        item-baru/tanpa-riwayat tidak dikorbankan oleh fix ini."""
        _qapp()
        from PySide6.QtCore import Qt

        from ui.models import PandasTableModel
        from waste_anomaly.period_history import compare_quantity
        a = _month("Bulan Ini", 30, [("R1", "X", 180.0)])
        empty = _month("Agustus 2026", 31, [])
        res = compare_quantity(a, empty)
        m = PandasTableModel()
        m.set_dataframe(res["summary"])
        assert m.data(m.index(0, 3), Qt.DisplayRole) == "BARU"

    def test_sort_kolom_object_jalan(self):
        """Sort klik header 'Perubahan %' (kolom object) — None di akhir."""
        _qapp()
        from PySide6.QtCore import Qt

        from ui.models import PandasTableModel
        from waste_anomaly.period_history import compare_quantity
        a = _month("Bulan Ini", 30, [("R1", "X", 180.0)])
        b = _month("Agustus 2026", 31, [("R1", "X", 140.0)])
        s = compare_quantity(a, b)["summary"]
        m = PandasTableModel()
        m.set_dataframe(s)
        m.sort(3, Qt.DescendingOrder)  # tidak raise = lolos
        order = [m.data(m.index(r, 0), Qt.DisplayRole)
                 for r in range(m.rowCount())]
        assert "Hari Data" in order and len(order) == 5


# ============================================================
# [B] FUNNEL HALAMAN RINGKASAN — None tampil '(kosong)'
# ============================================================

class TestFunnelNone:
    def test_menu_nilai_kosong(self):
        """Funnel kolom 'Perubahan %' halaman Ringkasan: None → teks
        '(kosong)' (pola _HeaderFilterMenu), bukan crash/'None' polos."""
        _qapp()
        from collections import OrderedDict

        from ui.widgets import _HeaderFilterMenu
        counts = OrderedDict([(28.6, 1), (None, 1), (-12.0, 3)])
        menu = _HeaderFilterMenu(None, "Perubahan %", "summary:Perubahan %",
                                 counts, None, lambda *a: None, None)
        items = [menu._lw.item(i).text()
                 for i in range(menu._lw.count())]
        assert any("(kosong)" in t for t in items), items
        menu.deleteLater()


# ============================================================
# [C] FUTUREWARNING DOWNCASTING HILANG
# ============================================================

class TestFutureWarningHilang:
    def test_compare_quantity_tak_ada_fillna_warning(self):
        """TOTAL object (fixture lama) — coerce numerik menggantikan
        fillna-dict; FutureWarning downcasting tak muncul lagi."""
        from waste_anomaly.period_history import compare_quantity
        a = _month("Bulan Ini", 30, [("R1", "X", 180.0)])
        b = _month("Agustus 2026", 31, [("R1", "X", 140.0)])
        # paksa TOTAL object dtype (jalur legacy fixture)
        a["agg"]["TOTAL"] = a["agg"]["TOTAL"].astype(object)
        b["agg"]["TOTAL"] = b["agg"]["TOTAL"].astype(object)
        a["jenis_totals"]["TOTAL"] = a["jenis_totals"]["TOTAL"].astype(
            object)
        b["jenis_totals"]["TOTAL"] = b["jenis_totals"]["TOTAL"].astype(
            object)
        with warnings.catch_warnings():
            warnings.simplefilter("error", FutureWarning)
            res = compare_quantity(a, b)
        # perilaku tetap: angka valid, bukan NaN massal
        row = res["summary"].set_index("Metrik").loc["Total Waste"]
        assert abs(float(row["Perubahan %"]) - 28.571) < 0.01

    def test_period_compare_tak_ada_fillna_warning(self):
        """Modul lama (dipakai test v2.5.0) — jalur yang sama dibersihkan."""
        from waste_anomaly.period_compare import compare_periods
        cols = ["NAMA RESTO", "NAMA BARANG", "JENIS", "TOTAL"]
        df_a = pd.DataFrame(
            [["R1", "X", "WASTE", 180.0]], columns=cols)
        df_b = pd.DataFrame(
            [["R1", "X", "WASTE", 140.0]], columns=cols)
        with warnings.catch_warnings():
            warnings.simplefilter("error", FutureWarning)
            compare_periods(df_a, df_b, label_a="A", label_b="B")


# ============================================================
# [D] DATA ASLI — baris Hari Data 30 vs 31 renders ''
# ============================================================

class TestDataAsli:
    def test_banding_asli_hari_data_kosong(self):
        """DATA_WASTE (Sep, 30 hari) vs REKAP MENTAH (Ags, 31 hari):
        sel 'Hari Data' × 'Perubahan %' = '' — jawaban laporan user
        'harusnya gak papa kan?' (benar: bulan 30 hari bukan error)."""
        _qapp()
        from PySide6.QtCore import Qt
        data = REPO / "DATA_WASTE.xlsx"
        rekap = REPO / "REKAP MENTAH_01-31 AGUSTUS 2026_TEGAR.xlsx"
        if not (data.exists() and rekap.exists()):
            import pytest
            pytest.skip("file data asli tidak ada di repo")
        from ui.models import PandasTableModel
        from waste_anomaly.period_history import (
            aggregate_current,
            compare_quantity,
            load_history_file,
        )
        from waste_anomaly.pipeline import run_pipeline
        summary = run_pipeline(str(data), 30)
        aug = load_history_file(str(rekap))
        assert aug.get("error") is None
        a = aggregate_current(summary["df"], 30)
        s = compare_quantity(a, aug)["summary"]
        m = PandasTableModel()
        m.set_dataframe(s)
        texts = {m.data(m.index(r, 0), Qt.DisplayRole):
                 m.data(m.index(r, 3), Qt.DisplayRole)
                 for r in range(m.rowCount())}
        assert texts["Hari Data"] == ""
        assert texts["Total Waste"] == "-0,2%"
        assert texts["Waste per Hari"] == "+3,1%"
