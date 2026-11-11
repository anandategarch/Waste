"""Test — fix wave 2 v2.7.0 (widgets / models / view anomali).

Mengunci 6 fix gelombang 2 (temuan audit V26):
- V26-C1  : tabel anomali memegang df PENUH via ``visible_cols`` → record
            terpilih / double-klik membawa 12 sinyal + ANOMALY REASONS +
            kolom peer/MAX ke panel detail (bukan irisan 7 kolom TABLE_COLS
            yang membuat 12 chip sinyal selalu abu-abu).
- V26-H4  : KpiStrip breakdown satuan memakai kolom 'total' + 'share_pct'
            unit_summary (fallback lama 'rows' = jumlah baris ditampilkan
            seolah total waste).
- V26-M1/L2: fmt_cell memformat numpy int/float (pemisah ribuan + rata
            kanan) dan menelan pd.NA/NaT/NaN.
- V26-M3  : tabel >3000 baris → word-wrap MATI + elide kanan '…' (teks
            tidak terpotong VERTIKAL saat _refit_rows di-skip); tabel
            kecil → wrap nyala (perilaku lama).
- V26-M4/L9: resize kolom manual → refit debounce 120ms; lebar yang
            dipasang sendiri tidak memicu jadwal refit (guard _in_fit).
- V26-L4/L12: double-klik = SATU render (coalesce v2.5.1 DD-L2); panel
            detail dibersihkan saat df terfilter berubah.

Headless: QT_QPA_PLATFORM=offscreen diset SEBELUM import PySide6
(pola tests/test_ui_structure.py).
"""
from __future__ import annotations

import os
import sys

# Harus diset sebelum PySide6 di-import (dilakukan lazy di dalam test).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pandas as pd

from ui.shared import fmt_id


def _qapp():
    """QApplication offscreen tunggal per proses (pola test_ui_structure)."""
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication(sys.argv)


def _anomali_df(n: int = 4) -> pd.DataFrame:
    """df tiruan bergaya output pipeline: TABLE_COLS + 12 sinyal + detail."""
    data = {
        "ANOMALY SCORE": [19 - i for i in range(n)],
        "ANOMALY STATUS": ["Prioritas Tinggi"] * n,
        "NAMA RESTO": [f"RESTO {i}" for i in range(n)],
        "NAMA BARANG": [f"BARANG {i}" for i in range(n)],
        "JENIS": ["BAHAN"] * n,
        "KETERANGAN": ["alasan A"] * n,
        "TOTAL": [float(1000 * (i + 1)) for i in range(n)],
        "MAX": [500.0] * n,
        "AVG": [50.0] * n,
        "HARI MAX": [12] * n,
        "SATUAN": ["GR"] * n,
        "TOTAL BOM": [900.0] * n,
        "MAX SHARE": [0.4] * n,
        "LAST DAY SHARE": [0.3] * n,
        "ANOMALY REASONS": ["S1 spike; S6 max/BOM"] * n,
        "PEER COUNT": [7] * n,
        "PEER MEDIAN TOTAL": [300.0] * n,
        "PEER MEDIAN MAX": [120.0] * n,
        "KATEGORI ANOMALI": ["SPIKE"] * n,
        "RANGKING WASTE": [i + 1 for i in range(n)],
    }
    for i in range(1, 13):
        # baris 0 (skor tertinggi) memicu S1 + S6
        data[f"_s{i}"] = [1 if (i in (1, 6) and r == 0) else 0
                          for r in range(n)]
    return pd.DataFrame(data)


def _make_view():
    """AnomaliView + AppContext dengan dataset anomali terisi."""
    _qapp()
    from ui.state import AppContext
    from ui.view_anomali import AnomaliView
    ctx = AppContext({})
    view = AnomaliView(ctx)
    ctx.set_dataset(_anomali_df(), {"key_akhir": 31})
    view._refresh_table()
    return view, ctx


# ============================================================
# FIX 1 (V26-C1) — record PENUH dari tabel anomali
# ============================================================

class TestV270FullRecord:
    """Model memegang df penuh; kolom non-TABLE_COLS disembunyikan saja."""

    def test_model_memegang_df_penuh_bukan_irisan(self):
        view, _ = _make_view()
        dfm = view._table._model.dataframe
        assert "_s1" in dfm.columns
        assert "ANOMALY REASONS" in dfm.columns
        assert "PEER COUNT" in dfm.columns
        # kolom non-tabel tersembunyi, kolom tabel tampak
        cols = list(dfm.columns)
        assert view._table.isColumnHidden(cols.index("_s1"))
        assert view._table.isColumnHidden(cols.index("ANOMALY REASONS"))
        # v2.18.7: ANOMALY SCORE keluar dari TABLE_COLS (permintaan user
        # "kolom anomali score hapus aja") — kini disembunyikan seperti
        # kolom non-tabel lain (skor tetap di df: ranking + pop-up).
        assert view._table.isColumnHidden(cols.index("ANOMALY SCORE"))
        assert not view._table.isColumnHidden(cols.index("TOTAL"))
        # v2.18.7: JENIS selalu tampak (permintaan user "kasih kolom
        # jenis nya waste, susut atau trial")
        assert not view._table.isColumnHidden(cols.index("JENIS"))

    def test_sort_desc_tetap_berlaku(self):
        view, _ = _make_view()
        dfm = view._table._model.dataframe
        skor = pd.to_numeric(dfm["ANOMALY SCORE"])
        assert int(skor.iloc[0]) == int(skor.max())

    def test_record_terpilih_berisi_semua_kolom(self):
        view, _ = _make_view()
        view._table.setCurrentIndex(view._table.model().index(0, 0))
        rec = view._table.selected_record()
        assert rec is not None
        assert "_s1" in rec.index
        assert "_s12" in rec.index
        assert "ANOMALY REASONS" in rec.index
        assert "LAST DAY SHARE" in rec.index

    def test_panel_detail_menampilkan_sinyal_terpicu(self):
        """Inti V26-C1: 12 chip sinyal HIDUP (sebelumnya selalu abu-abu).
        v2.8.1: panel detail kini hidup di dalam pop-up (view._popup)."""
        from PySide6.QtWidgets import QApplication, QLabel
        view, _ = _make_view()
        # v2.18.6: pop-up dibuka lewat klik-ganda (bukan setCurrentIndex)
        view._table.double_clicked.emit(view._table._model.record(0))
        QApplication.processEvents()
        # baris skor tertinggi memicu S1 + S6 → chip '✓' muncul
        panel = view._popup._panel
        texts = [l.text() for l in panel._content.findChildren(QLabel)]
        assert any("✓" in t for t in texts), texts
        assert any(t.startswith("S1 ") or "S1 ·" in t for t in texts)
        # seksi alasan (butuh kolom ANOMALY REASONS — tidak ada di irisan lama)
        assert any(t == "Alasan terdeteksi" for t in texts)
        # judul panel memuat skor baris terpilih
        assert "Skor" in panel._title.text()

    def test_visible_cols_pada_datatable_murni(self):
        _qapp()
        from ui.widgets import DataTable
        df = pd.DataFrame({"A": [1, 2], "B": ["x", "yy"], "C": [3.5, 4.5]})
        t = DataTable()
        t.set_dataframe(df, visible_cols=["A"])
        assert not t.isColumnHidden(0)
        assert t.isColumnHidden(1)
        assert t.isColumnHidden(2)
        # persisten lintas _auto_columns (resize)
        t.resize(900, 400)
        t._auto_columns()
        assert t.isColumnHidden(1) and t.isColumnHidden(2)
        # record tetap PENUH (semua kolom ada di index)
        t.setCurrentIndex(t.model().index(0, 0))
        rec = t.selected_record()
        assert list(rec.index) == ["A", "B", "C"]

    def test_tanpa_visible_cols_perilaku_lama(self):
        _qapp()
        from ui.widgets import DataTable
        df = pd.DataFrame({"A": [1], "B": [2], "C": [3]})
        t = DataTable()
        t.set_dataframe(df)
        for c in range(3):
            assert not t.isColumnHidden(c)

    def test_narrow_hide_menumpuk_di_atas_visible_cols(self):
        _qapp()
        from PySide6.QtWidgets import QApplication
        from ui.widgets import DataTable
        app = QApplication.instance()
        df = pd.DataFrame({"A": [1], "B": [2], "C": [3], "D": [4]})
        t = DataTable()
        t.set_dataframe(df, narrow_hide=["B"], visible_cols=["A", "B", "D"])
        # C permanen hidden oleh visible_cols; B tampak saat lebar cukup
        assert t.isColumnHidden(2)
        t.resize(800, 400)
        app.processEvents()  # viewport offscreen baru update setelah event
        t._auto_columns()
        assert not t.isColumnHidden(1)
        # viewport sempit → B (narrow_hide) ikut disembunyikan, A/D tetap
        t.resize(210, 200)
        app.processEvents()
        t._auto_columns()
        assert t.isColumnHidden(1)
        assert not t.isColumnHidden(0)
        assert not t.isColumnHidden(3)


# ============================================================
# FIX 2 (V26-H4) — KpiStrip breakdown satuan
# ============================================================

class TestV270KpiUnitNote:
    def test_unit_note_pakai_total_bukan_rows(self):
        _qapp()
        from ui.widgets import KpiStrip
        df = pd.DataFrame({
            "SATUAN": ["GR", "GR", "GR", "KG"],
            "TOTAL": [1000.0, 1000.0, 1000.0, 500.0],
            "NAMA BARANG": ["a", "b", "c", "d"],
        })
        note = KpiStrip()._unit_note(df)
        # total GR = 3.000,0 (bukan jumlah baris 3 → 'GR: 3,0')
        assert "GR: 3.000,0" in note
        assert "GR: 3,0" not in note
        # share_pct ikut ditampilkan (85,7% dari total 3.500)
        assert "(85,7%)" in note
        assert "(14,3%)" in note
        assert "indikatif" in note

    def test_update_from_menulis_catatan_satuan(self):
        _qapp()
        from ui.widgets import KpiStrip
        df = pd.DataFrame({
            "SATUAN": ["GR", "KG"],
            "TOTAL": [3000.0, 500.0],
            "NAMA BARANG": ["a", "b"],
        })
        strip = KpiStrip()
        strip.update_from(df, 2)
        assert fmt_id(3000.0, 1) in strip.lbl_units.text()
        assert "rows" not in strip.lbl_units.text()

    def test_unit_note_df_tanpa_kolom_satuan_kosong(self):
        _qapp()
        from ui.widgets import KpiStrip
        note = KpiStrip()._unit_note(pd.DataFrame({"TOTAL": [1.0]}))
        assert note == ""


# ============================================================
# FIX 3 (V26-M1/L2) — fmt_cell numpy + pd.NA
# ============================================================

class TestV270FmtCell:
    def test_numpy_int_terformat_ribuan(self):
        from ui.models import fmt_cell
        assert fmt_cell(np.int64(25901)) == fmt_id(25901, 0)
        assert fmt_cell(np.int64(25901)) == "25.901"

    def test_numpy_float_samadengan_python_float(self):
        from ui.models import fmt_cell
        assert fmt_cell(np.float32(1.5)) == fmt_cell(1.5) == "1,50"
        assert fmt_cell(np.float32(2.0)) == fmt_cell(2.0) == "2"
        assert fmt_cell(np.int64(7)) == fmt_cell(7) == "7"

    def test_na_nan_nat_tidak_bocor(self):
        from ui.models import fmt_cell
        assert fmt_cell(pd.NA) == ""
        assert fmt_cell(pd.NaT) == ""
        assert fmt_cell(None) == ""
        assert fmt_cell(float("nan")) == ""
        assert fmt_cell(np.float32("nan")) == ""
        assert fmt_cell("teks") == "teks"

    def test_alignment_numpy_int_rata_kanan(self):
        _qapp()
        from PySide6.QtCore import Qt
        from ui.models import PandasTableModel
        m = PandasTableModel(
            pd.DataFrame({"N": np.array([25901], dtype=np.int64)}))
        align = m.data(m.index(0, 0), Qt.TextAlignmentRole)
        assert align == int(Qt.AlignRight | Qt.AlignVCenter)


# ============================================================
# FIX 4 (V26-M3/M4/L9) — tabel raksasa + refit resize kolom
# ============================================================

class TestV270BigTableWrap:
    def test_tabel_besar_wrap_mati_elide_kanan(self):
        _qapp()
        from PySide6.QtCore import Qt
        from ui.widgets import DataTable
        df = pd.DataFrame({
            "A": list(range(3001)),
            "B": ["teks panjang sekali ini memang sengaja " * 2] * 3001,
        })
        t = DataTable()
        t.set_dataframe(df)
        assert not t.wordWrap()
        assert t.textElideMode() == Qt.TextElideMode.ElideRight

    def test_tabel_kecil_wrap_nyala_elide_none(self):
        _qapp()
        from PySide6.QtCore import Qt
        from ui.widgets import DataTable
        t = DataTable()
        t.set_dataframe(pd.DataFrame({"A": list(range(10))}))
        assert t.wordWrap()
        assert t.textElideMode() == Qt.TextElideMode.ElideNone

    def test_df_none_mengembalikan_default(self):
        _qapp()
        from PySide6.QtCore import Qt
        from ui.widgets import DataTable
        t = DataTable()
        t.set_dataframe(pd.DataFrame({"A": list(range(3001))}))
        assert not t.wordWrap()
        t.set_dataframe(None)
        assert t.wordWrap()
        assert t.textElideMode() == Qt.TextElideMode.ElideNone


class TestV270SectionResizedRefit:
    def test_lebar_pilihan_sendiri_tidak_memicu_timer(self):
        _qapp()
        from ui.widgets import DataTable
        t = DataTable()
        t.set_dataframe(pd.DataFrame({"A": ["x"], "B": ["y"]}))
        # _auto_columns memasang lebar dalam mode _in_fit → tanpa jadwal refit
        assert not t._refit_timer.isActive()

    def test_resize_kolom_manual_memicu_refit_terjadwal(self):
        """V26-M4: user menyempitkan kolom → tinggi baris dihitung ulang
        (debounce 120ms, bukan refit per piksel)."""
        import time
        _qapp()
        from PySide6.QtWidgets import QApplication
        from ui.widgets import DataTable
        app = QApplication.instance()
        # dua kolom: kolom yang di-resize BUKAN kolom terakhir (kolom
        # terakhir di-stretch header → resizeSection-nya ditimpa)
        df = pd.DataFrame({
            "A": ["teks yang sangat panjang sekali ini " * 2] * 3,
            "B": ["x"] * 3,
        })
        t = DataTable()
        t.set_dataframe(df)
        t.resize(900, 400)
        app.processEvents()
        t._auto_columns()
        # v2.9.0: jendela tenang 300ms pasca-fit menelan resize deferred Qt
        # internal — tirukan drag user SETELAH jendela itu lewat.
        import time as _time
        t._fit_ts = _time.monotonic() - 1.0
        # sempitkan kolom manual (di luar _in_fit) → refit terjadwal
        t.horizontalHeader().resizeSection(0, 60)
        assert t._refit_timer.isActive()
        # proses event loop sampai timer timeout (batas 2 detik)
        deadline = time.time() + 2.0
        while t._refit_timer.isActive() and time.time() < deadline:
            app.processEvents()
            time.sleep(0.01)
        assert not t._refit_timer.isActive()
        # baris kini TINGGI (teks wrap multi-baris, tidak terpotong)
        assert t.rowHeight(0) > t.verticalHeader().defaultSectionSize()


# ============================================================
# FIX 5 (V26-L12) — panel detail tidak basi
# ============================================================

class TestV270DetailClear:
    def test_clear_mengembalikan_prompt_default(self):
        _qapp()
        from PySide6.QtWidgets import QApplication
        from ui.view_anomali import DetailPanel
        view, _ = _make_view()
        view._table.double_clicked.emit(view._table._model.record(0))
        QApplication.processEvents()
        panel = view._popup._panel
        assert "Skor" in panel._title.text()
        panel.clear()
        assert panel._title.text() == DetailPanel._PROMPT
        lay = panel._content.layout()
        assert lay is None or lay.count() == 0

    def test_refresh_table_membersihkan_panel_dan_seleksi(self):
        _qapp()
        from PySide6.QtWidgets import QApplication
        from ui.view_anomali import DetailPanel
        view, _ = _make_view()
        view._table.setCurrentIndex(view._table.model().index(0, 0))
        view._table.double_clicked.emit(view._table._model.record(0))
        QApplication.processEvents()
        assert view._table.selected_record() is not None
        assert "Skor" in view._popup._panel._title.text()
        # filter berubah → render ulang → panel + seleksi tidak basi
        # (v2.8.1: pop-up juga harus tertutup)
        view._refresh_table()
        assert view._popup.isHidden(), "pop-up harus tertutup saat refresh"
        assert view._popup._panel._title.text() == DetailPanel._PROMPT
        assert view._table.selected_record() is None


# ============================================================
# FIX 6 (V26-L4) — double-klik = satu render
# ============================================================

class TestV270DoubleKlikCoalesce:
    def test_double_klik_tak_lagi_filter_satu_render_pun(self):
        """v2.13.5: klik-2× → filter DIHAPUS (permintaan user) — _on_double
        & guard coalesce _batch_filters ikut hilang bersama subjeknya.
        v2.18.6: double_clicked kini punya subscriber _open_popup_row
        (pop-up via klik-ganda) — TETAP 0 render & 0 filter: membuka
        pop-up bukan memfilter/meng-render tabel."""
        from ui.view_anomali import DetailPanel
        view, ctx = _make_view()
        calls: list[int] = []
        orig = view._refresh_table

        def counting() -> None:
            calls.append(1)
            orig()

        view._refresh_table = counting
        try:
            assert not hasattr(view, "_on_double")
            assert not hasattr(view, "_batch_filters"), (
                "guard coalesce hanya dipakai _on_double — ikut dihapus")
            rec = view._table._model.record(0)
            view._table.double_clicked.emit(rec)
        finally:
            view._refresh_table = orig
        # v2.18.6: tanpa filter, tanpa render tabel — pop-up TERBUKA
        # (subscriber _open_popup_row), panel memuat record tsb.
        assert calls == []
        assert not any(ctx.active_filters.values())
        assert view._table.model().rowCount() > 0
        assert view._popup.isVisible()
        assert view._popup._panel._title.text() != DetailPanel._PROMPT


class TestChipSinyalDariReasonsRiil:
    """V26-C1 lanjutan (v2.7.0): _s1.._s12 di-drop pipeline → chip sinyal
    dibaca dari fragmen teks ANOMALY REASONS. Pipeline riil (sample) →
    jumlah chip ✓ HARUS sama dengan jumlah fragmen reasons baris tsb
    (sebelum v2.7.0: 0 chip di data riil — selalu abu-abu)."""

    def test_chip_terpicu_sama_dengan_fragmen_reasons(self):
        from pathlib import Path
        from PySide6.QtWidgets import QLabel
        _qapp()
        from waste_anomaly.pipeline import run_pipeline
        from waste_anomaly.signals import SIGNAL_PARTS

        sample = Path(__file__).resolve().parents[1] / "sample_workbook.xlsx"
        if not sample.exists():
            import pytest
            pytest.skip("sample_workbook.xlsx tidak ada")
        s = run_pipeline(str(sample), key_akhir=31)
        assert s.get("success")

        top = s["df"].sort_values("ANOMALY SCORE", ascending=False).iloc[0]
        reasons = str(top.get("ANOMALY REASONS") or "")
        n_frag = len([f for f in reasons.split(" | ") if f])
        assert n_frag > 0, "fixture sample harus punya baris ber-sinyal"

        # Panel detail: render record top (tanpa Qt view penuh — cukup panel)
        from ui.state import AppContext
        from ui.view_anomali import DetailPanel
        ctx = AppContext({})
        panel = DetailPanel(ctx)
        panel.show()
        panel.show_record(top)
        texts = [l.text() for l in panel._content.findChildren(QLabel)]
        triggered = [t for t in texts if "✓" in t]
        assert len(triggered) == n_frag, (len(triggered), n_frag)
        # fragmen kontrak: semua fragmen SIGNAL_PARTS sinkron dgn chip label
        from ui.view_anomali import SIGNALS
        assert {c for c, _l, _f in SIGNALS} == {c for c, _f in SIGNAL_PARTS}
