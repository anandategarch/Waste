"""test_v2186.py — v2.18.6: 2 permintaan user (UX pop-up detail).

[P1] POP-UP VIA KLIK-GANDA — "kenapa ya aku klik sekali aja pop up
     langsung muncul? ini kadang bikin klik yang gak sengaja ketriger
     munculin pop up."
     Pop-up detail (tab Anomali / Hari / Follow Up) HANYA terbuka lewat
     KLIK-GANDA atau Enter; klik 1× saat pop-up tertutup = tanpa efek.
     Saat pop-up SUDAH terbuka, klik-1×/panah tetap mengganti isinya
     (mengikuti navigasi). Sel ✓ tetap murni aksi centang (klik-ganda
     di sel ✓ TIDAK memancarkan double_clicked).
[P2] ✓ FOLLOW-UP DI POP-UP BANDING — "di tab banding periode pop up nya
     bisa klik follow up juga ya."
     Dialog drill Banding Periode level resto/item kini ber-kolom ✓
     (frame ber-__FPS diagregasi lintas jenis) — centang = masukkan
     SEMUA baris anomali terkait; lepas = keluarkan; ✓ dialog ikut
     disegarkan saat follow-up berubah di mana pun. Level hari tanpa ✓.
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = Path(__file__).resolve().parent.parent
UI = REPO / "ui"


def _qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


# ============================================================
# Fixture — view Anomali dgn dataset minimal (pola test_v2135)
# ============================================================

def _df_anomali() -> pd.DataFrame:
    data = {str(d): 0.0 for d in range(1, 31)}
    data["5"] = 90.0
    data["24"] = 819.0
    return pd.DataFrame([
        {"SOURCE DATA": "WASTE BAHAN DAN PACKAGING", "JENIS": "WASTE",
         "KETERANGAN": "Cancel Nota", "NAMA BARANG": "MIE",
         "NAMA RESTO": "RESTO 1", "SATUAN": "GR", "ANOMALY STATUS":
         "Prioritas Tinggi", **data, "TOTAL": float(sum(data.values()))},
        {"SOURCE DATA": "WASTE BAHAN DAN PACKAGING", "JENIS": "WASTE",
         "KETERANGAN": "Handling", "NAMA BARANG": "TEH",
         "NAMA RESTO": "RESTO 2", "SATUAN": "GR", "ANOMALY STATUS":
         "Perlu Review", **{str(d): 1.0 for d in range(1, 31)},
         "TOTAL": 30.0},
    ])


def _make_view():
    from ui.state import AppContext
    from ui.view_anomali import AnomaliView
    app = _qapp()
    ctx = AppContext({})
    ctx.set_dataset(_df_anomali(), {"key_akhir": 30})
    view = AnomaliView(ctx)
    view.show()
    view.refresh()
    app.processEvents()
    return view, ctx


# ============================================================
# [P1] POP-UP HANYA VIA KLIK-GANDA / ENTER
# ============================================================

class TestPopupViaKlikGanda:
    def test_klik_tunggal_tak_membuka_pop_up(self):
        """Klik 1× (row_clicked) saat pop-up tertutup = TANPA efek —
        inti permintaan user (klik tak sengaja sering memunculkan
        pop-up)."""
        from PySide6.QtWidgets import QApplication
        view, _ = _make_view()
        QApplication.processEvents()
        assert view._popup.isHidden()
        # klik tunggal baris 0 (jalur sinyal row_clicked)
        view._table.row_clicked.emit(view._table.model().index(0, 1))
        QApplication.processEvents()
        assert view._popup.isHidden(), (
            "klik 1× tak sengaja tidak boleh membuka pop-up")
        # pilih baris (currentRowChanged) pun tetap tertutup
        view._table.setCurrentIndex(view._table.model().index(1, 1))
        QApplication.processEvents()
        assert view._popup.isHidden()
        view.close()

    def test_klik_ganda_membuka_pop_up(self):
        from PySide6.QtWidgets import QApplication
        view, _ = _make_view()
        QApplication.processEvents()
        rec = view._table._model.record(0)
        view._table.double_clicked.emit(rec)
        QApplication.processEvents()
        assert view._popup.isVisible()
        assert "RESTO 1" in view._popup._panel._title.text()
        view.close()

    def test_enter_membuka_pop_up(self):
        """Enter/Return = padanan keyboard klik-ganda (jalur a11y tetap
        hidup setelah klik-1× dinetralkan)."""
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        view, _ = _make_view()
        QApplication.processEvents()
        view._table.setCurrentIndex(view._table.model().index(0, 1))
        view._popup.hide()
        QApplication.processEvents()
        assert view._popup.isHidden()
        QTest.keyClick(view._table, Qt.Key.Key_Return)
        QApplication.processEvents()
        assert view._popup.isVisible(), "Enter harus membuka pop-up"
        view.close()

    def test_popup_terbuka_klik_mengikuti(self):
        """Saat pop-up SUDAH terbuka, klik 1×/navigasi mengganti isi
        pop-up (perilaku lama dipertahankan utk navigasi aktif)."""
        from PySide6.QtWidgets import QApplication
        view, _ = _make_view()
        app = QApplication.instance() or QApplication([])
        app.processEvents()
        assert view._table.model().rowCount() >= 2, (
            "premis: ≥ 2 baris anomali tampil")
        view._table.double_clicked.emit(view._table._model.record(0))
        app.processEvents()
        assert view._popup.isVisible()
        assert "RESTO 1" in view._popup._panel._title.text()
        m = view._table.model()
        view._table.setCurrentIndex(m.index(1, 2))  # kolom non-✓
        app.processEvents()
        assert view._table.currentIndex().row() == 1
        view._table.row_clicked.emit(m.index(1, 2))
        app.processEvents()
        assert "RESTO 2" in view._popup._panel._title.text(), (
            "pop-up terbuka harus mengikuti baris yang dipilih")
        view.close()

    def test_sel_centang_klik_ganda_tak_memicu_pop_up(self):
        """Klik-ganda di sel ✓ = aksi centang murni — double_clicked
        TIDAK terpancar (guard _relay_row_click_ok di _on_double)."""
        from waste_anomaly.followup import CHECK_COL
        from ui.widgets import DataTable
        _qapp()
        t = DataTable()
        df = pd.DataFrame({"JENIS": ["WASTE", "TRIAL"]})
        df.insert(0, CHECK_COL, [False, False])
        t.set_dataframe(df)
        t.model().set_check_column(CHECK_COL)
        fired: list = []
        t.double_clicked.connect(lambda r: fired.append(r))
        relayed: list = []
        t.row_clicked.connect(lambda i: relayed.append(i))
        # klik-ganda seluruh sel ✓ (baris 0, kolom 0)
        t._on_double(t.model().index(0, 0))
        assert fired == [] and relayed == [], (
            "sel ✓ tak boleh memicu pop-up/relay")
        # sel normal: kedua sinyal terpancar
        t._on_double(t.model().index(0, 1))
        assert len(fired) == 1 and len(relayed) == 1
        t.close()

    def test_wiring_tiga_view(self):
        """Anomali / Hari / Follow Up: double_clicked tersambung ke
        _open_popup_row; row_clicked tetap tersambung (mengikuti pop-up
        yang terbuka)."""
        for fname in ("view_anomali.py", "view_hari.py",
                      "view_followup.py"):
            src = (UI / fname).read_text(encoding="utf-8")
            assert "self._table.double_clicked.connect(" \
                   "self._open_popup_row)" in src, fname
            assert "self._table.row_clicked.connect(" in src, fname

    def test_hint_menyebut_klik_ganda(self):
        from ui.view_anomali import DetailPanel
        assert "Klik-ganda" in DetailPanel._PROMPT


# ============================================================
# [P2] ✓ FOLLOW-UP DI POP-UP BANDING PERIODE
# ============================================================

def _month(label: str, rows: list[dict]) -> dict:
    def _frame(keys):
        recs = [{"NAMA RESTO": r["resto"], "NAMA BARANG": r["barang"],
                 "TOTAL": r["total"], **{k: r.get(k) for k in keys}}
                for r in rows]
        return pd.DataFrame(recs)

    agg = _frame(["JENIS"])
    for d in range(1, 21):
        agg[str(d)] = [r.get("hari", {}).get(str(d), 0.0) for r in rows]
    return {"label": label, "key_akhir": 20, "agg": agg,
            "jenis_totals": pd.DataFrame(
                [{"JENIS": "WASTE", "TOTAL": sum(r["total"] for r in rows)}]),
            "agg_jenis": _frame(["JENIS"]), "agg_detail": _frame([]),
            "resto_count": len({r["resto"] for r in rows}),
            "item_count": len({r["barang"] for r in rows}),
            "rows_kept": len(rows), "rows_raw": len(rows), "error": None}


_B_ROWS = [
    {"resto": "R1", "barang": "AYAM", "JENIS": "WASTE", "total": 80.0,
     "hari": {"5": 80.0}},
    {"resto": "R2", "barang": "AYAM", "JENIS": "WASTE", "total": 50.0,
     "hari": {"5": 50.0}},
]


def _periode_view():
    from ui.state import AppContext
    from ui.view_periode import PeriodeView
    app = _qapp()
    ctx = AppContext({})
    rows = []
    for resto, barang, status in (("R1", "AYAM", "Prioritas Tinggi"),
                                  ("R1", "MIE", "Normal"),
                                  ("R2", "AYAM", "Potensi Anomali")):
        data = {str(d): 0.0 for d in range(1, 21)}
        data["5"] = 30.0
        rows.append({"NAMA RESTO": resto, "NAMA BARANG": barang,
                     "JENIS": "WASTE", "KETERANGAN": "Handling",
                     "SATUAN": "GR", "ANOMALY STATUS": status,
                     **data, "TOTAL": float(sum(data.values()))})
    ctx.set_dataset(pd.DataFrame(rows), {"key_akhir": 20})
    view = PeriodeView(ctx)
    view._entries = [{"path": "b.xlsx", "label": "Juli 2026"}]
    view._loaded = {"b.xlsx": _month("Juli 2026", _B_ROWS)}
    view._combo_version = -1
    view._refresh_result()
    app.processEvents()
    return view, ctx, app


class TestDrillPopupFollowUp:
    def test_drill_resto_ber_kolom_centang(self):
        """Pop-up drill level resto punya kolom ✓ + __FPS (permintaan
        user: pop-up banding bisa klik follow-up)."""
        from waste_anomaly.followup import CHECK_COL
        from ui.view_periode import _FPS_COL
        view, _ctx, _app = _periode_view()
        view._open_resto("🏬 Resto penyumbang Total Waste")
        _app.processEvents()
        m = view._drill.table_model()
        cols = list(m.dataframe.columns)
        assert CHECK_COL in cols and _FPS_COL in cols
        assert view._drill.isVisible()
        # R1 punya baris anomali → fps terisi; ✓ awal = False (kosong)
        recs = m.dataframe
        r1 = recs[recs["NAMA RESTO"] == "R1"]
        assert len(r1) == 1 and len(r1.iloc[0][_FPS_COL]) >= 1
        assert not r1.iloc[0][CHECK_COL]
        view._close_popups()

    def test_centang_drill_masuk_follow_up(self):
        """✓ baris resto di pop-up drill → SEMUA baris anomali resto itu
        masuk Follow Up; lepas → keluar (pola tabel tab, Opsi A)."""
        from PySide6.QtCore import Qt
        from waste_anomaly.followup import CHECK_COL
        view, ctx, _app = _periode_view()
        view._open_resto("🏬 Resto penyumbang Total Waste")
        _app.processEvents()
        m = view._drill.table_model()
        df = m.dataframe
        row = int(df.index[df["NAMA RESTO"] == "R1"][0])
        check_col = df.columns.get_loc(CHECK_COL)
        assert len(ctx.followup_keys) == 0
        # CENTANG (setData → check_toggled → _on_dialog_check)
        assert m.setData(m.index(row, check_col), True,
                         Qt.ItemDataRole.CheckStateRole)
        _app.processEvents()
        # R1 anomali = 1 baris (AYAM Prioritas; MIE Normal tak ikut)
        assert len(ctx.followup_keys) == 1
        # LEPAS → keluar
        assert m.setData(m.index(row, check_col), False,
                         Qt.ItemDataRole.CheckStateRole)
        _app.processEvents()
        assert len(ctx.followup_keys) == 0
        view._close_popups()

    def test_drill_item_juga_ber_centang(self):
        from waste_anomaly.followup import CHECK_COL
        from ui.view_periode import _FPS_COL
        view, _ctx, _app = _periode_view()
        view._open_items("R1", jenis=None)
        _app.processEvents()
        m = view._drill.table_model()
        cols = list(m.dataframe.columns)
        assert CHECK_COL in cols and _FPS_COL in cols
        # item MIE @R1 = Normal → tanpa fps (✓ jujur tak tercentang)
        mie = m.dataframe[m.dataframe["NAMA BARANG"] == "MIE"]
        assert len(mie) == 1 and len(mie.iloc[0][_FPS_COL]) == 0
        view._close_popups()

    def test_drill_hari_tanpa_kolom_centang(self):
        """Level hari = rincian tanggal — bukan identitas baris anomali;
        tanpa ✓ (kontrak desain)."""
        from waste_anomaly.followup import CHECK_COL
        view, _ctx, _app = _periode_view()
        view._open_day("R1", "AYAM")
        _app.processEvents()
        m = view._drill.table_model()
        assert CHECK_COL not in list(m.dataframe.columns)
        view._close_popups()

    def test_drill_centang_disegarkan_dari_luar(self):
        """✓ berubah di tempat lain (mis. tabel tab) → kolom ✓ pop-up
        drill ikut jujur (refresh_followup_checks via
        _on_followup_changed)."""
        from waste_anomaly.followup import CHECK_COL
        from ui.view_periode import _FPS_COL
        view, ctx, _app = _periode_view()
        view._open_resto("🏬 Resto penyumbang Total Waste")
        _app.processEvents()
        m = view._drill.table_model()
        df = m.dataframe
        row = int(df.index[df["NAMA RESTO"] == "R1"][0])
        # tambahkan via ctx LANGSUNG (simulasi centang dari tab Anomali)
        fps = list(df.iloc[row][_FPS_COL])
        ctx.add_followup_many(fps)
        _app.processEvents()
        assert bool(df.iloc[row][CHECK_COL]) is True, (
            "✓ pop-up harus ikut state follow-up global")
        view._close_popups()


# ============================================================
# VERSI — pin triple (pola test_v2139)
# ============================================================

class TestVersi:
    def test_versi_pin(self):
        from ui.shared import APP_VERSION
        from waste_anomaly import __version__
        from waste_anomaly.utils import load_config
        assert APP_VERSION == __version__ == \
            load_config().get("version") == "2.18.6"
