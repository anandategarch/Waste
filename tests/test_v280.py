"""Test — v2.8.0: penyederhanaan UI + ruang vertikal tabel.

Lingkup:
1. 8 → 5 view: file view_uang/view_peer/view_kualitas dihapus total,
   tab QTabWidget berisi tepat 5 judul yang diharapkan, help HTML tidak
   lagi menyebut tab yang dihapus.
2. Tabel Anomali memanjang ke bawah: judul kartu satu baris (teks pendek),
   tinggi minimum tabel/kartu, rasio splitter tabel:detail = 5:2, dan
   tombol "Rapikan Detail" menyembunyikan panel detail → kartu tabel
   memenuhi hampir seluruh tinggi splitter.
3. Sidebar hide/unhide: tombol ☰ Filter (checkable) menyembunyikan sidebar
   → QTabWidget melebar; dimunculkan → ukuran splitter tersimpan
   dipulihkan.
"""
from __future__ import annotations

import os
from pathlib import Path

# Harus diset sebelum PySide6 di-import (dilakukan lazy di dalam test).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = Path(__file__).resolve().parent.parent
UI = REPO / "ui"

REMOVED_VIEW_FILES = ["view_uang.py", "view_peer.py", "view_kualitas.py"]
REMOVED_TAB_TITLES = ["Uang", "Peer", "Kualitas Data"]
EXPECTED_TAB_TITLES = ["Anomali", "Jelajah", "Waktu", "Banding Periode",
                       "Pipeline"]


def _qapp():
    """QApplication offscreen tunggal per proses (pola test_ui_structure)."""
    from PySide6.QtWidgets import QApplication
    import sys
    return QApplication.instance() or QApplication(sys.argv)


def _make_window():
    _qapp()
    from ui.app import MainWindow
    return MainWindow()


class TestHapusTigaView:
    def test_file_view_dihapus_dari_repo(self):
        for fname in REMOVED_VIEW_FILES:
            assert not (UI / fname).exists(), (
                f"ui/{fname} masih ada — harusnya dihapus total (v2.8.0)")

    def test_tab_tepat_lima_dengan_judul_benar(self):
        win = _make_window()
        try:
            assert win._tabs.count() == 5
            for i in range(win._tabs.count()):
                assert win._tabs.tabText(i) == EXPECTED_TAB_TITLES[i]
        finally:
            win.close()

    def test_ukuran_minimum_window_masih_1024x700(self):
        win = _make_window()
        try:
            assert win.minimumWidth() == 1024
            assert win.minimumHeight() == 700
        finally:
            win.close()


class TestTabelAnomaliMemanjang:
    def _view(self):
        win = _make_window()
        # Anomali = tab 0 (default) — view sudah ter-instantiate
        anom = win._views[0][1]
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

    def test_tinggi_minimum_tabel_dan_kartu(self):
        win, anom = self._view()
        try:
            assert anom._table.minimumHeight() >= 200, (
                "tabel boleh diperas di bawah 200px — baris terlihat "
                "tinggal sedikit (keluhan v2.8.0)")
            assert anom._split.widget(0).minimumHeight() >= 240
            assert anom._detail.minimumHeight() >= 150
        finally:
            win.close()

    def test_rasio_splitter_tabel_dominan(self):
        """Stretch tabel:detail = 5:2 (dulu 3:2 — detail mencuri 38% ruang
        walau kosong). Diverifikasi via source (setStretchFactor di __init__)."""
        import inspect
        from ui.view_anomali import AnomaliView
        src = inspect.getsource(AnomaliView.__init__)
        assert "setStretchFactor(0, 5)" in src, (
            "stretch tabel harus 5 (tabel dominan, v2.8.0)")
        assert "setStretchFactor(1, 2)" in src

    def test_kartu_tabel_tidak_bisa_collapsible(self):
        """Drag handle tidak boleh meruntuhkan tabel ke 0 — hanya detail
        yang boleh dirikan."""
        win, anom = self._view()
        try:
            assert anom._split.isCollapsible(0) is False
            assert anom._split.isCollapsible(1) is True
        finally:
            win.close()

    def test_tombol_rapikan_detail_ada(self):
        win, anom = self._view()
        try:
            assert anom._btn_detail.text().startswith("⌃ Rapikan Detail")
        finally:
            win.close()

    def test_rapikan_detail_tabel_memenuhi_splitter(self):
        """Toggle rikan → DetailPanel hidden → kartu tabel menyerap hampir
        seluruh tinggi splitter (minus handle 4px). Toggle kembali →
        panel muncul lagi + ukuran tersimpan dipulihkan."""
        from PySide6.QtWidgets import QApplication, QWidget
        win, anom = self._view()
        try:
            win.resize(1024, 700)
            win.show()
            QApplication.processEvents()
            QWidget.grab(anom)  # paksa layout offscreen
            QApplication.processEvents()
            sizes_before = anom._split.sizes()

            anom._toggle_detail()
            QApplication.processEvents()
            assert anom._detail.isHidden(), "panel detail harus hidden"
            assert anom._btn_detail.text().startswith("⌄ Tampilkan Detail")
            QApplication.processEvents()
            card_h = anom._split.widget(0).height()
            split_h = anom._split.height()
            # kartu tabel memenuhi splitter (toleransi handle)
            assert card_h >= split_h - 12, (
                f"kartu tabel {card_h}px belum memenuhi splitter {split_h}px")

            anom._toggle_detail()
            QApplication.processEvents()
            assert not anom._detail.isHidden(), "panel detail harus muncul"
            assert anom._btn_detail.text().startswith("⌃ Rapikan Detail")
            sizes_after = anom._split.sizes()
            assert sizes_after == sizes_before, (
                f"ukuran splitter tidak dipulihkan: {sizes_after} ≠ {sizes_before}")
        finally:
            win.close()


class TestSidebarHideUnhide:
    def test_tombol_filter_checkable_di_toolbar(self):
        win = _make_window()
        try:
            act = win._act_filter
            assert act is not None, "aksi ☰ Filter tidak ada di toolbar"
            assert act.isCheckable()
            assert act.isChecked(), "default: sidebar terlihat (checked)"
            assert act.shortcut().toString().endswith("F")
        finally:
            win.close()

    def test_hide_unhide_ukuran_dipulihkan(self):
        """Sembunyikan → sidebar hidden + QTabWidget melebar; munculkan →
        sidebar kembali + ukuran splitter tersimpan dipulihkan."""
        from PySide6.QtWidgets import QApplication, QWidget
        win = _make_window()
        try:
            win.resize(1440, 900)
            win.show()
            QApplication.processEvents()
            QWidget.grab(win)  # paksa layout offscreen
            QApplication.processEvents()
            tabs_w_visible = win._tabs.width()
            assert not win._sidebar.isHidden()

            win._toggle_sidebar(False)
            QApplication.processEvents()
            assert win._sidebar.isHidden(), "sidebar harus hidden"
            QApplication.processEvents()
            assert win._tabs.width() > tabs_w_visible, (
                "QTabWidget tidak melebar setelah sidebar disembunyikan")

            win._toggle_sidebar(True)
            QApplication.processEvents()
            assert not win._sidebar.isHidden(), "sidebar harus muncul lagi"
            QApplication.processEvents()
            assert win._tabs.width() < win._split.width() - 100, (
                "sidebar kembali tapi area tab tidak menyusut — restore "
                "ukuran splitter gagal")
        finally:
            win.close()

    def test_toggle_dua_kali_idempoten(self):
        win = _make_window()
        try:
            win._toggle_sidebar(False)
            win._toggle_sidebar(True)
            win._toggle_sidebar(False)
            assert win._sidebar.isHidden()
            win._toggle_sidebar(True)
            assert not win._sidebar.isHidden()
        finally:
            win.close()


class TestDokumentasiJujur:
    def test_help_html_tak_menyebut_tab_dihapus(self):
        from ui.app import _HELP_HTML
        for title in REMOVED_TAB_TITLES:
            assert f"<b>{title}</b>" not in _HELP_HTML, (
                f"Bantuan masih menyebut tab '{title}' yang sudah dihapus")

    def test_bantuan_menyebut_toggle_baru(self):
        from ui.app import _HELP_HTML
        assert "Ctrl+Shift+F" in _HELP_HTML, (
            "Bantuan harus menyebut shortcut sidebar hide/unhide")
