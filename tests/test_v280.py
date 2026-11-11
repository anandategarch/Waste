"""Test — v2.8.1: pop-up detail + kolom % to BOM + 5 → 3 view.

Lingkup:
1. 8 → 5 → 3 view: file view_uang/view_peer/view_kualitas (v2.8.0) dan
   view_jelajah/view_waktu (v2.8.1) dihapus total; tab QTabWidget berisi
   tepat 3 judul yang diharapkan; help HTML tidak lagi menyebut tab yang
   dihapus.
2. Panel detail inline DIGANTI pop-up: klik baris tabel anomali membuka
   DetailDialog non-modal (satu instance dipakai ulang); tabel memenuhi
   seluruh tinggi view (tanpa splitter / tombol Rapikan Detail); hint
   lama "pilih baris utk detail" dihapus.
3. Kolom "% to BOM" (waste vs penjualan kuantiti) tampil di tabel
   anomali ter-ranking — nilai rasio diformat persen ('1,34%'), penanda
   'Cek' (tak ada data penjualan) diteruskan apa adanya.
4. Sidebar hide/unhide (v2.8.0, tetap): tombol ☰ Filter (checkable)
   menyembunyikan sidebar → QTabWidget melebar; dimunculkan → ukuran
   splitter tersimpan dipulihkan.
"""
from __future__ import annotations

import os
from pathlib import Path

# Harus diset sebelum PySide6 di-import (dilakukan lazy di dalam test).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
UI = REPO / "ui"

REMOVED_VIEW_FILES = [
    "view_uang.py", "view_peer.py", "view_kualitas.py",  # v2.8.0
    "view_jelajah.py", "view_waktu.py",                  # v2.8.1
]
REMOVED_TAB_TITLES = ["Uang", "Peer", "Kualitas Data", "Jelajah", "Waktu"]
# v2.17.0 rombak P0: Pipeline (entry point) index 0, Follow Up terakhir.
EXPECTED_TAB_TITLES = ["Pipeline", "Anomali", "Hari Mencurigakan",
                        "Banding Periode", "Follow Up"]  # v2.18.5: −Scorecard


def _qapp():
    """QApplication offscreen tunggal per proses (pola test_ui_structure)."""
    from PySide6.QtWidgets import QApplication
    import sys
    return QApplication.instance() or QApplication(sys.argv)


def _make_window():
    _qapp()
    from ui.app import MainWindow
    return MainWindow()


def _anomali_df(n: int = 4) -> pd.DataFrame:
    """df tiruan bergaya output pipeline — termasuk kolom % to BOM."""
    data = {
        "ANOMALY SCORE": [19 - i for i in range(n)],
        "ANOMALY STATUS": ["Prioritas Tinggi"] * n,
        "NAMA RESTO": [f"RESTO {i}" for i in range(n)],
        "NAMA BARANG": [f"BARANG {i}" for i in range(n)],
        "JENIS": ["BAHAN"] * n,
        "KETERANGAN": ["alasan A"] * n,
        "TOTAL": [float(1000 * (i + 1)) for i in range(n)],
        "% to BOM": [0.013358778625954198, "Cek", 0.0009149130832570906, 0.0][:n],
        "ANOMALY REASONS": ["S1 spike; S6 max/BOM"] * n,
    }
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


class TestHapusLimaView:
    def test_file_view_dihapus_dari_repo(self):
        for fname in REMOVED_VIEW_FILES:
            assert not (UI / fname).exists(), (
                f"ui/{fname} masih ada — harusnya dihapus total")

    def test_file_modul_chart_dihapus(self):
        """v2.8.1: charts/dashboard/chart_helpers hanya hidup di Jelajah &
        Waktu — ikut dihapus total dari paket waste_anomaly."""
        for fname in ("charts.py", "dashboard.py", "chart_helpers.py"):
            assert not (REPO / "waste_anomaly" / fname).exists(), (
                f"waste_anomaly/{fname} masih ada — dead code pasca-hapus view")

    def test_tab_tepat_lima_dengan_judul_benar(self):
        # v2.12.0: 4 → 5 tab (+ Follow Up). v2.13.1: 5 → 6 (+ Scorecard
        # Cabang); v2.18.5: 6 → 5 (Scorecard dihapus permintaan user).
        # Judul dibandingkan tanpa badge '(N)' (badge muncul bila
        # ada centangan tersimpan).
        win = _make_window()
        try:
            assert win._tabs.count() == 5
            for i in range(win._tabs.count()):
                base = win._tabs.tabText(i).split(" (")[0]
                assert base == EXPECTED_TAB_TITLES[i]
        finally:
            win.close()

    def test_ukuran_minimum_window_masih_1024x700(self):
        # v2.13.15 (gel-6 D30 — ditulis ulang jujur): minimum TINGGI kini
        # ADAPTIF layar (dulu literal 700px — MELEBIHI tinggi layar pendek:
        # netbook 1024×600 / VM available 1366×648 → jendela tak termuat
        # penuh, audit D30). Kontrak baru: lebar tetap 1024; tinggi =
        # max(560, min(700, available-80)) — di layar biasa tetap 700,
        # di layar pendek turun sampai lantai 560. Batas atas 700 dipin
        # supaya layar tinggi TIDAK memaksa jendela raksasa.
        win = _make_window()
        try:
            assert win.minimumWidth() == 1024
            assert 560 <= win.minimumHeight() <= 700
            screen = win.screen().availableGeometry() if win.screen() else None
            if screen is not None:
                expect = max(560, min(700, screen.height() - 80))
                assert win.minimumHeight() == expect
        finally:
            win.close()


class TestTabelAnomaliPenuhDanPopup:
    def _view(self):
        win = _make_window()
        # v2.17.0 rombak: Anomali kini di tab 1 (tab 0 = Pipeline entry point).
        anom = win._views[1][1]
        return win, anom

    def test_judul_kartu_satu_baris_pendek(self):
        """Judul 'Tabel Anomali Ter-ranking' (tanpa kalimat panjang yang
        dulu wrap 2-3 baris dan memakan ±100px tinggi kartu)."""
        from PySide6.QtWidgets import QLabel
        win, anom = self._view()
        try:
            titles = [l for l in anom._table.parentWidget().findChildren(QLabel)
                      if l.objectName() == "cardTitle"]
            assert titles, "judul kartu tidak ditemukan"
            assert titles[0].text() == "Tabel Anomali Ter-ranking"
        finally:
            win.close()

    def test_tanpa_splitter_tombol_rapikan_dan_hint_lama(self):
        """v2.8.1: splitter tabel:detail, tombol 'Rapikan Detail', dan hint
        'pilih baris utk detail' dihapus — detail kini pop-up."""
        import inspect
        from ui.view_anomali import AnomaliView
        win, anom = self._view()
        try:
            assert not hasattr(anom, "_split"), "splitter masih ada"
            assert not hasattr(anom, "_btn_detail"), "tombol Rapikan masih ada"
            assert not hasattr(anom, "_detail"), "panel detail inline masih ada"
            src = inspect.getsource(AnomaliView) + inspect.getsource(
                AnomaliView.__init__)
            assert "pilih baris utk detail" not in src.lower(), (
                "hint lama 'pilih baris utk detail' masih ada di view")
        finally:
            win.close()

    def test_tinggi_minimum_tabel_dan_kartu(self):
        win, anom = self._view()
        try:
            assert anom._table.minimumHeight() >= 200, (
                "tabel boleh diperas di bawah 200px — baris terlihat "
                "tinggal sedikit (keluhan v2.8.0)")
            card = anom._table.parentWidget()
            assert card.minimumHeight() >= 240
        finally:
            win.close()

    def test_tabel_memenuhi_tinggi_view(self):
        """Tanpa panel inline, kartu tabel menyerap sisa tinggi view
        (≥ 60% tinggi view pada 1024×700)."""
        from PySide6.QtWidgets import QApplication, QWidget
        win, anom = self._view()
        try:
            win.resize(1024, 700)
            win.show()
            QApplication.processEvents()
            QWidget.grab(anom)
            QApplication.processEvents()
            card = anom._table.parentWidget()
            assert card.height() >= anom.height() * 0.60, (
                f"kartu tabel {card.height()}px < 60% tinggi view "
                f"{anom.height()}px — tabel tidak memanjang penuh")
        finally:
            win.close()

    def test_klik_ganda_membuka_popup_detail(self):
        """v2.18.6: KLIK-GANDA baris → DetailDialog muncul + judul berisi
        skor; memilih baris (klik 1×/setCurrentIndex) TIDAK lagi membuka
        pop-up (permintaan user: klik tak sengaja sering memunculkannya)."""
        from PySide6.QtWidgets import QApplication
        view, _ = _make_view()
        QApplication.processEvents()
        # klik 1× (pilih baris) — pop-up TETAP tertutup
        view._table.setCurrentIndex(view._table.model().index(0, 0))
        QApplication.processEvents()
        popup = view._popup
        assert popup.isHidden(), (
            "klik 1× tak sengaja tidak boleh membuka pop-up (v2.18.6)")
        # klik-ganda → pop-up muncul
        view._table.double_clicked.emit(view._table._model.record(0))
        QApplication.processEvents()
        assert popup.isVisible(), "pop-up harus terbuka via klik-ganda"
        assert not popup.isModal(), "pop-up harus non-modal (tabel tetap hidup)"
        assert "Skor" in popup._panel._title.text()
        # isi panel: chip sinyal ter-render
        from PySide6.QtWidgets import QLabel
        texts = [l.text() for l in popup._panel._content.findChildren(QLabel)]
        assert any("S1" in t for t in texts), "chip 12 sinyal tidak ter-render"

    def test_popup_satu_instance_dipakai_ulang(self):
        """Pop-up TERBUKA → pilih baris lain → pop-up yang SAMA diperbarui
        (tidak menumpuk; konten mengikuti navigasi saat pop-up terbuka)."""
        from PySide6.QtWidgets import QApplication
        view, _ = _make_view()
        QApplication.processEvents()
        view._table.double_clicked.emit(view._table._model.record(0))
        first = view._popup
        title1 = first._panel._title.text()
        view._table.setCurrentIndex(view._table.model().index(1, 0))
        QApplication.processEvents()
        assert view._popup is first, "instance pop-up harus dipakai ulang"
        assert view._popup._panel._title.text() != title1, (
            "isi pop-up tidak diperbarui saat baris lain diklik")

    def test_popup_ditutup_saat_data_berubah(self):
        """Dataset/filter berubah → pop-up ditutup + dikosongkan (V26-L12:
        record yang ditampilkan bisa jadi tak lolos filter lagi)."""
        from PySide6.QtWidgets import QApplication
        from ui.view_anomali import DetailPanel
        view, _ = _make_view()
        QApplication.processEvents()
        view._table.double_clicked.emit(view._table._model.record(0))
        QApplication.processEvents()
        assert view._popup.isVisible()
        view._refresh_table()
        assert view._popup.isHidden(), "pop-up harus tertutup saat refresh"
        assert view._popup._panel._title.text() == DetailPanel._PROMPT

    def test_double_klik_tak_lagi_filter(self):
        """v2.13.5 (permintaan user "hilangkan yang klik 2x"): klik-2×
        baris TIDAK lagi memasang filter cabang+item — _on_double dihapus
        dari AnomaliView. v2.18.6: double_clicked kini punya subscriber
        (_open_popup_row — pop-up dibuka lewat klik-ganda), TETAP bukan
        filter: state filter & jumlah baris tak tersentuh."""
        view, ctx = _make_view()
        assert not hasattr(view, "_on_double"), (
            "_on_double harus dihapus bersama perilaku filter klik-2×")
        rec = view._table._model.record(0)
        n_before = view._table.model().rowCount()
        view._table.double_clicked.emit(rec)
        assert not any(ctx.active_filters.values()), (
            "klik-2× tidak boleh lagi memfilter")
        assert view._table.model().rowCount() == n_before

    def test_popup_muncul_lagi_baris_sama(self):
        """v2.13.5 → v2.18.6 (permintaan user: "klik sekali aja pop up
        langsung muncul… kadang bikin klik yang gak sengaja ketriger"):
        klik 1× (row_clicked) saat pop-up TERTUTUP = TANPA efek; pop-up
        dibuka lagi lewat KLIK-GANDA (double_clicked) — termasuk pada
        baris yang sama."""
        from PySide6.QtWidgets import QApplication
        view, _ = _make_view()
        QApplication.processEvents()
        rec = view._table._model.record(0)
        view._table.double_clicked.emit(rec)
        QApplication.processEvents()
        assert view._popup.isVisible()
        view._popup.close()
        QApplication.processEvents()
        assert view._popup.isHidden()
        # klik tunggal baris sama (index tak berubah → hanya jalur
        # row_clicked) — pop-up TETAP TERTUTUP (perilaku baru).
        view._table.row_clicked.emit(view._table.model().index(0, 0))
        QApplication.processEvents()
        assert view._popup.isHidden(), (
            "klik 1× tak sengaja tidak boleh membuka pop-up (v2.18.6)")
        # klik-ganda baris sama → pop-up muncul lagi.
        view._table.double_clicked.emit(rec)
        QApplication.processEvents()
        assert view._popup.isVisible(), (
            "klik-ganda harus membuka pop-up lagi")

    def test_hint_baru_menyebut_pop_up(self):
        """Hint menggambarkan perilaku baru: klik baris = pop-up detail."""
        import inspect
        from ui.view_anomali import AnomaliView
        src = inspect.getsource(AnomaliView.__init__)
        assert "pop-up" in src.lower(), (
            "hint harus menyebut 'pop-up' (perilaku detail v2.8.1)")


class TestKolomPctToBom:
    """v2.8.1: '% to BOM' = waste dibanding penjualan kuantiti — tampil
    di tabel anomali per-ranking; rasio sebagai persen; 'Cek' apa adanya."""

    def test_table_cols_memuat_pct_to_bom(self):
        from ui.view_anomali import TABLE_COLS
        assert "% to BOM" in TABLE_COLS
        # posisinya berdampingan dengan TOTAL (konteks pembacaan)
        assert TABLE_COLS.index("% to BOM") == TABLE_COLS.index("TOTAL") + 1

    def test_kolom_tampak_di_tabel(self):
        view, _ = _make_view()
        dfm = view._table._model.dataframe
        assert "% to BOM" in dfm.columns
        idx = list(dfm.columns).index("% to BOM")
        assert not view._table.isColumnHidden(idx), (
            "kolom % to BOM harus tampak di tabel anomali")

    def test_sel_ratio_tampil_sebagai_persen(self):
        """0.01335... → '1,34%' (bukan '0,00' mentah yang tak terbaca)."""
        from PySide6.QtCore import Qt
        view, _ = _make_view()
        dfm = view._table._model.dataframe
        row = 0  # nilai 0.013358778625954198 (fixture _anomali_df)
        col = list(dfm.columns).index("% to BOM")
        shown = view._table._model.data(
            view._table._model.index(row, col), Qt.DisplayRole)
        assert shown == "1,34%", f"tampilan {shown!r} harus '1,34%'"

    def test_sel_penanda_cek_diteruskan(self):
        """'Cek' = item tanpa data penjualan — ditampilkan apa adanya."""
        from PySide6.QtCore import Qt
        view, _ = _make_view()
        dfm = view._table._model.dataframe
        col = list(dfm.columns).index("% to BOM")
        shown = view._table._model.data(
            view._table._model.index(1, col), Qt.DisplayRole)
        assert shown == "Cek"

    def test_kolom_pct_fit_tanpa_scrollbar_di_viewport_sempit(self):
        """v2.8.1: 8 kolom — di viewport sempit (±740px) JENIS & KETERANGAN
        disembunyikan responsif (narrow_hide) supaya kolom inti + % to BOM
        tetap tampak.

        v2.12.3: funnel filter di header = chrome baru ±20px per kolom
        ber-funnel (5 kolom tabel anomali) — di 740px scrollbar
        horizontal KINI BOLEH muncul (konvensi 'scroll ≠ terpotong');
        jaminan yang TETAP: tidak ada judul kolom terpotong (lantai
        header) & kolom inti tampak. Di viewport normal (980px) header
        tetap muat tanpa scrollbar."""
        from PySide6.QtWidgets import QApplication, QWidget
        view, _ = _make_view()
        view.resize(740, 500)
        view.show()
        QApplication.processEvents()
        QWidget.grab(view)  # paksa layout offscreen
        QApplication.processEvents()
        view._table._auto_columns()
        QApplication.processEvents()
        dfm = view._table._model.dataframe
        t = view._table
        pct = list(dfm.columns).index("% to BOM")
        assert not t.isColumnHidden(pct), (
            "% to BOM harus tetap tampak di viewport sempit")
        j = list(dfm.columns).index("JENIS")
        # v2.18.7: JENIS keluar dari narrow_hide (permintaan user "kasih
        # kolom tambahan itu jenis nya waste, susut atau trial" — jenis
        # wajib terbaca di viewport sempit). Kolom skor juga keluar dari
        # tabel — lebar bekas kolom skor membuat KETERANGAN umumnya MUAT
        # di 740px kini (narrow_hide tetap terpasang utk viewport yang
        # lebih sempit lagi; jaminan yang dipin: % to BOM + JENIS tampak).
        assert not t.isColumnHidden(j), "JENIS kini selalu tampil (v2.18.7)"
        # v2.19.0: layout sampel user — KETERANGAN bukan lagi kolom tabel
        # (digabung per grup item×cabang); narrow_hide kini SOURCE DATA
        # GABUNGAN (kolom teks terpanjang) + PERUBAHAN.
        assert "SOURCE DATA GABUNGAN" in (t._narrow_hide or [])
        # LANTAI HEADER (anti-terpotong): tiap kolom tampak ≥ lebar
        # teks judulnya (+26 padding, +20 funnel bila ber-funnel).
        fm = t.fontMetrics()
        from ui.view_anomali import _HF_COLS
        for c in range(dfm.shape[1]):
            if t.isColumnHidden(c):
                continue
            name = str(dfm.columns[c])
            floor = fm.horizontalAdvance(name) + 26
            if name in _HF_COLS:
                floor += 20
            assert t.columnWidth(c) >= floor, (
                f"judul '{name}' terpotong: {t.columnWidth(c)}px < lantai "
                f"{floor}px")

        # viewport NORMAL (980px): tanpa scrollbar — funnel termasuk.
        view.resize(980, 500)
        QApplication.processEvents()
        QWidget.grab(view)
        QApplication.processEvents()
        view._table._auto_columns()
        QApplication.processEvents()
        total = t.horizontalHeader().length()
        avail = t.viewport().width()
        assert total <= avail + 2, (
            f"panjang header {total}px > viewport {avail}px — scrollbar "
            "horizontal padahal 980px harusnya cukup (termasuk funnel)")

    def test_fmt_pct_unit(self):
        from ui.models import fmt_pct
        assert fmt_pct(0.013358778625954198) == "1,34%"
        assert fmt_pct(0.0009149130832570906) == "0,09%"
        assert fmt_pct(0.8530465949820788) == "85,30%"
        assert fmt_pct(0.0) == "0,00%"
        assert fmt_pct("Cek") == "Cek"
        assert fmt_pct(None) == ""
        assert fmt_pct(float("nan")) == ""

    def test_pct_rata_kanan(self):
        from PySide6.QtCore import Qt
        from ui.models import PandasTableModel
        m = PandasTableModel(pd.DataFrame({"% to BOM": [0.5, "Cek"]}))
        align = m.data(m.index(0, 0), Qt.TextAlignmentRole)
        assert align == int(Qt.AlignRight | Qt.AlignVCenter)

    def test_sort_pct_numeric_cek_di_akhir(self):
        """Sort header % to BOM: numerik descending; 'Cek' (NaN) di akhir."""
        from PySide6.QtCore import Qt
        view, _ = _make_view()
        dfm = view._table._model.dataframe
        col = list(dfm.columns).index("% to BOM")
        view._table._model.sort(col, Qt.DescendingOrder)
        dfm = view._table._model.dataframe
        vals = list(dfm["% to BOM"])
        assert vals[0] == 0.013358778625954198, "ratio terbesar harus di atas"
        assert vals[-1] == "Cek", "'Cek' (non-numerik) harus sort paling akhir"

    def test_popup_metric_pct_juga_persen(self):
        """Panel detail pop-up: TOTAL / BOM & MAX SHARE tampil sebagai
        persen (dulu '0,30' mentah tak terbaca)."""
        from PySide6.QtWidgets import QApplication, QLabel
        from ui.view_anomali import DetailPanel
        _qapp()
        ctx_dummy = None
        from ui.state import AppContext
        ctx = AppContext({})
        panel = DetailPanel(ctx)
        panel.show()
        rec = pd.Series({
            "ANOMALY SCORE": 19, "ANOMALY STATUS": "Prioritas Tinggi",
            "NAMA RESTO": "R1", "NAMA BARANG": "B1",
            "TOTAL": 100.0, "MAX": 50.0, "AVG": 3.3, "HARI MAX": 12,
            "SATUAN": "GR", "TOTAL BOM": 7470.0, "% to BOM": 0.0134,
            "MAX / BOM": 0.0067, "TOTAL / BOM": 0.0134,
            "MAX SHARE": 0.4, "LAST DAY SHARE": 0.3,
            "ANOMALY REASONS": "S1 spike",
        })
        panel.show_record(rec)
        QApplication.processEvents()
        texts = [l.text() for l in panel._content.findChildren(QLabel)]
        assert "1,34%" in texts, f"% to BOM harus '1,34%' di pop-up: {texts[:12]}"
        assert "40,00%" in texts, "MAX SHARE harus tampil '40,00%'"
        assert "0,67%" in texts, "MAX / BOM harus tampil '0,67%'"


class TestSidebarDihapus:
    """v2.12.4 — sidebar filter kiri + tombol ☰ Filter DIHAPUS (permintaan
    user): tabel memakai lebar penuh jendela; filter lewat funnel judul
    kolom + tombol ✕ Hapus Filter di tab Anomali/Hari."""

    def test_tanpa_tombol_filter_di_toolbar(self):
        win = _make_window()
        try:
            from PySide6.QtGui import QAction
            acts = [a for a in win.findChildren(QAction)]
            texts = [a.text() for a in acts if a.text()]
            assert not any("☰" in t for t in texts), (
                f"aksi ☰ Filter masih ada di toolbar: {texts}")
            assert not hasattr(win, "_act_filter"), (
                "atribut _act_filter masih ada (sidebar toggle belum dihapus)")
        finally:
            win.close()

    def test_central_widget_tab_lebar_penuh(self):
        """Tanpa splitter/sidebar: QTabWidget = central widget → tabel
        memakai seluruh lebar jendela (dulu ±300px makan sidebar)."""
        from PySide6.QtWidgets import QApplication, QTabWidget, QSplitter
        win = _make_window()
        try:
            win.resize(1280, 800)
            win.show()
            QApplication.processEvents()
            from PySide6.QtWidgets import QWidget
            QWidget.grab(win)  # paksa layout offscreen
            QApplication.processEvents()
            assert isinstance(win.centralWidget(), QTabWidget), (
                "central widget bukan QTabWidget — splitter masih ada?")
            assert not win.findChildren(QSplitter), (
                "QSplitter masih dipakai (sidebar belum dihapus)")
            assert not hasattr(win, "_sidebar"), (
                "atribut _sidebar masih ada")
            assert win._tabs.width() >= win.width() - 12, (
                f"area tab {win._tabs.width()}px < lebar jendela "
                f"{win.width()}px — ada yang makan lebar")
        finally:
            win.close()

    def test_tanpa_widget_filter_sidebar(self):
        """Kontrol filter sidebar (combo cabang/status/keterangan, kotak
        cari, rentang hari, profil) tak ada lagi di jendela."""
        win = _make_window()
        try:
            for attr in ("_cb_cabang", "_cb_status", "_cb_ket",
                         "_ent_search", "_chk_hari", "_cb_profile"):
                assert not hasattr(win, attr), (
                    f"widget sidebar {attr} masih ada")
        finally:
            win.close()


class TestDokumentasiJujur:
    def test_help_html_tak_menyebut_tab_dihapus(self):
        from ui.app import _HELP_HTML
        for title in REMOVED_TAB_TITLES:
            # v2.13.6 (gel-A audit): 'Kualitas Data' kini juga nama KARTU 🧪
            # di dalam tab Scorecard Cabang (resurface v2.13.2) — menyebut
            # kartu itu di Bantuan adalah dokumentasi SAH. Yang tetap
            # dilarang: mengiklankan sebagai TAB terpisah (pola seksi
            # '<h3>Tab …</h3>' / bold judul tab berdiri sendiri).
            if title == "Kualitas Data":
                assert "<h3>Tab Kualitas Data</h3>" not in _HELP_HTML, (
                    "Bantuan mengiklankan tab 'Kualitas Data' yang dihapus "
                    "seolah tab terpisah (yang sah = kartu di Scorecard)")
                continue
            assert f"<b>{title}</b>" not in _HELP_HTML, (
                f"Bantuan masih menyebut tab '{title}' yang sudah dihapus")

    def test_bantuan_menyebut_fitur_baru(self):
        from ui.app import _HELP_HTML
        assert "funnel" in _HELP_HTML.lower(), (
            "Bantuan harus menjelaskan filter funnel judul kolom (v2.12.4)")
        # changelog v2.12.4 BOLEH menyebut kata 'sidebar' ("dihapus") —
        # yang dilarang: instruksi memakai fitur yang sudah tak ada.
        assert "☰" not in _HELP_HTML, (
            "Bantuan masih menyebut tombol ☰ Filter yang sudah dihapus")
        assert "Ctrl+Shift+F" not in _HELP_HTML, (
            "Bantuan masih menyebut shortcut sidebar yang sudah dihapus")
        assert "Profil filter" not in _HELP_HTML, (
            "Bantuan masih menyebut profil filter sidebar yang dihapus")
        assert "pop-up" in _HELP_HTML.lower(), (
            "Bantuan harus menyebut detail pop-up (perilaku v2.8.1)")


# ============================================================
# v2.8.3 — busy feedback saat apply/unapply filter (anti "freeze")
# ============================================================

class TestBusyFeedbackV283:
    """Apply/unapply filter → refresh sinkron berat (auto-fit kolom +
    ukur tinggi baris per sel; 75–460 ms di sandbox = 1–2+ dtk di laptop
    user) kini dibungkus busy_feedback: cursor sibuk + pesan status
    SEBELUM kerja berat, pulih + durasi SESUDAHnya."""

    def test_cursor_sibuk_aktif_selama_refresh_dan_pulih(self):
        """Selama _refresh_table bekerja, override cursor = BusyCursor;
        setelah selesai, cursor dipulihkan (stack kosong)."""
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication
        view, _ = _make_view()
        seen = []
        orig = view._refresh_table_impl
        view._refresh_table_impl = lambda: (
            seen.append(QApplication.overrideCursor()), orig())[-1]
        view._refresh_table()
        assert seen and seen[0] is not None, (
            "cursor sibuk tidak aktif selama refresh bekerja")
        assert seen[0].shape() == Qt.CursorShape.BusyCursor, (
            f"cursor selama kerja: {seen[0]} (harus BusyCursor)")
        assert QApplication.overrideCursor() is None, (
            "cursor tidak dipulihkan setelah refresh selesai")

    def test_jalur_sinyal_filter_juga_terbungkus(self):
        """ctx.set_filter → filters_changed → render tabel: jalur yang
        DIPAKAI USER saat apply funnel harus melewati busy_feedback juga
        (bukan hanya pemanggilan manual _refresh_table).
        (v2.13.8: set_day_range diganti set_filter — rentang hari sudah
        dihapus bersama sidebar; jalur sinyalnya tetap dikunci.)"""
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication
        view, ctx = _make_view()
        view.show()
        QApplication.processEvents()
        seen = []
        orig = view._refresh_table_impl
        view._refresh_table_impl = lambda: (
            seen.append(QApplication.overrideCursor()), orig())[-1]
        ctx.set_filter("jenis", ["WASTE"])
        QApplication.processEvents()
        assert seen, "set_filter tidak memicu render (jalur filter putus)"
        assert seen[0] is not None and seen[0].shape() == Qt.CursorShape.BusyCursor
        assert QApplication.overrideCursor() is None
        view.hide()

    def test_pesan_status_progres_lalu_selesai(self):
        """Status bar: '⏳ …' terkirim sebelum kerja, '✓ … selesai (X ms)'
        setelahnya — user tahu prosesnya hidup dan berapa lama."""
        view, ctx = _make_view()
        texts = []
        ctx.status.connect(lambda t, k: texts.append(t))
        view._refresh_table()
        assert any(t.startswith("⏳") for t in texts), (
            f"pesan progres ⏳ tidak terkirim: {texts}")
        assert any("selesai" in t for t in texts), (
            f"pesan selesai tidak terkirim: {texts}")

    def test_helper_aman_bersarang(self):
        """busy_feedback dalam busy_feedback: cursor tetap sibuk di lapisan
        dalam, kembali ke lapisan luar setelah inner selesai, None setelah
        keduanya (kontrak Qt override-stack)."""
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication
        from ui.widgets import busy_feedback
        _qapp()
        with busy_feedback():
            with busy_feedback():
                inner = QApplication.overrideCursor()
                assert inner is not None and inner.shape() == Qt.CursorShape.BusyCursor
            mid = QApplication.overrideCursor()
            assert mid is not None, "inner exit tidak kembali ke lapisan luar"
        assert QApplication.overrideCursor() is None, (
            "stack cursor bocor setelah semua lapisan selesai")

    def test_sumber_pakai_helper_di_titik_tunggal(self):
        """Kontrak sumber: helper ada di widgets.py; view_anomali membungkus
        _refresh_table (titik tunggal semua jalur render)."""
        wsrc = (UI / "widgets.py").read_text(encoding="utf-8")
        assert "def busy_feedback" in wsrc, "helper busy_feedback hilang dari widgets.py"
        vsrc = (UI / "view_anomali.py").read_text(encoding="utf-8")
        assert "busy_feedback(" in vsrc, (
            "view_anomali tidak memakai busy_feedback (feedback proses mati)")
        assert "_refresh_table_impl" in vsrc, (
            "pola wrapper _refresh_table_impl berubah — cek pembungkusan")
