"""test_v2194.py — regresi 2 laporan user pasca-v2.19.3.

[D] SIMPAN KOREKSI masih WinError 5 (user: "masih gagal untuk simpan file.
kalau ubah nilai langsung timpa file nya jangan buat back up"):
    v2.19.3 sudah pre-check + retry 4×0,4 dtk — TAPI replace masih gagal
    pada file 9MB (Defender scan bisa lock detik-detikan, jendela 1,6 dtk
    tak cukup) + read-only attr Windows (file download) lolos sbg
    PermissionError padahal Excel TIDAK membuka. Fix v2.19.4:
      1. _clear_readonly — bersihkan atribut READ-ONLY Windows dulu
         (sebab umum WinError 5 BUKAN kunci Excel). POSIX no-op.
      2. BACKOFF LEBIH PANJANG — 8 jeda naik (0,3→2,0 dtk) = ~9 dtk
         jendela utk AV scan file 9MB.
      3. FALLBACK in-place — bila os.replace diblokir tapi open-tulis
         diizinkan (ACL deny-delete / state AV aneh): buka r+b, salin
         tmp ke asli, truncate, fsync.
      4. RESCUE _KOREKSI.xlsx — bila TOTAL gagal, file hasil (berisi
         koreksi) dinamai <nama>_KOREKSI.xlsx (siap dibuka Excel — beda
         dgn .tmp_write.PID tak dikenal Windows).
      5. backup=False default (user: "jangan buat back up").

[E] ZOOM Ctrl+scroll (user: "tambahin fitur buat zoom in dan zoom out
dengan cara ctrl scroll atas atau bawah"):
    ZoomManager (event filter app-wide) + shortcut keyboard. Font + QSS
    diskalakan bersama (build_qss(px) + app.setFont(pt)) + cache fit
    tabel dibuang (DataTable.zoom_refresh).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd  # noqa: F401  (dipakai fixture)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

REPO = Path(__file__).resolve().parent.parent


def _qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication(sys.argv)


# ============================================================
# [D] source_writer — v2.19.4 robust save chain
# ============================================================

class TestSourceWriterRobust:
    def _make_sheet(self, tmp_path) -> Path:
        """Workbook rekap mini: header + 1 baris data hari 1-5."""
        import openpyxl
        p = tmp_path / "REKAP MENTAH_TEST.xlsx"
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "REKAP MENTAH"
        ws.append(["SOURCE DATA", "JENIS", "KETERANGAN", "NAMA BARANG",
                   "NAMA RESTO", "SATUAN", 1, 2, 3, 4, 5])
        ws.append(["WASTE BAHAN DAN PACKAGING", "WASTE", "Cancel Nota",
                   "AYAM", "R1", "GR", 10, 0, 0, 0, 0])
        wb.save(p)
        return p

    def test_backup_default_false(self):
        """v2.19.4 — write_day_edits default backup=False (permintaan user
        'jangan buat back up'). Sebelumnya True."""
        import inspect
        from waste_anomaly.source_writer import write_day_edits
        sig = inspect.signature(write_day_edits)
        assert sig.parameters["backup"].default is False, (
            "default backup harus False sejak v2.19.4")

    def test_retry_delays_panjang_v2194(self):
        """v2.19.4 — 8 jeda backoff (vs 4×0,4 dtk v2.19.3) = ~9 dtk
        jendela utk AV scan file 9MB."""
        import waste_anomaly.source_writer as sw
        delays = sw._REPLACE_RETRY_DELAYS
        assert len(delays) == 8, f"v2.19.4 harus 8 jeda, dapat {len(delays)}"
        assert all(d > 0 for d in delays)
        # total jendela >= 5 dtk (cukup utk Defender scan xlsx 9MB).
        assert sum(delays) >= 5.0, (
            f"jendela retry terlalu pendek: {sum(delays)}s")

    def test_clear_readonly_posix_noop(self, tmp_path):
        """POSIX: st_fileattributes tak ada → _file_is_readonly False →
        _clear_readonly no-op (return False, tak chmod)."""
        import waste_anomaly.source_writer as sw
        p = self._make_sheet(tmp_path)
        # POSIX: no st_fileattributes attr → False
        assert sw._file_is_readonly(p) is False
        assert sw._clear_readonly(p, logger=None) is False

    def test_clear_readonly_windows_simulated(self, tmp_path, monkeypatch):
        """Simulasi Windows readonly attr: _file_is_readonly → True +
        os.chmod dipanggil utk bersihkan → return True."""
        import waste_anomaly.source_writer as sw
        p = self._make_sheet(tmp_path)
        called = {"chmod": False}
        real_chmod = os.chmod

        def spy_chmod(path, mode):
            called["chmod"] = True
            return real_chmod(path, mode)

        monkeypatch.setattr(sw.os, "chmod", spy_chmod)
        monkeypatch.setattr(sw, "_file_is_readonly", lambda _p: True)
        assert sw._clear_readonly(p, logger=None) is True
        assert called["chmod"] is True, "chmod harus dipanggil utk clear attr"

    def test_inplace_fallback_menyelamatkan_simpan(self, tmp_path, monkeypatch):
        """v2.19.4 — os.replace SELALU diblokir (PermissionError) TAPI
        open(src,'r+b') diizinkan → fallback IN-PLACE sukses: file asli
        ditimpa penuh + fsync, tmp dibuang, write OK (kasus ACL
        deny-delete / state AV aneh — replace ditolak, tulis boleh)."""
        import openpyxl
        import waste_anomaly.source_writer as sw
        p = self._make_sheet(tmp_path)
        monkeypatch.setattr(sw.time, "sleep", lambda *_a: None)
        # replace SELALU gagal (kunci permanen pada rename).
        monkeypatch.setattr(
            sw.os, "replace",
            lambda *_a: (_ for _ in ()).throw(PermissionError(
                5, "Access denied (ACL deny-delete)")))
        # open(src, "r+b") TIDAK diblokir → fallback in-place jalan.
        res = sw.write_day_edits(str(p), 2, {"3": 55.0}, logger=None,
                                 backup=False)
        assert res["ok"], "fallback in-place harus sukses"
        assert res["cells_written"] == 1
        # File asli ditimpa: nilai hari-3 sekarang 55.
        wb = openpyxl.load_workbook(str(p), read_only=True, data_only=True)
        ws = wb["REKAP MENTAH"]
        vals = next(ws.iter_rows(min_row=2, max_row=2, values_only=True))
        wb.close()
        assert vals[8] == 55, f"hari-3 harus 55 (in-place), dapat {vals[8]}"
        # tmp dibuang (in-place sukses → unlink tmp).
        leftovers = list(tmp_path.glob("*.tmp_write.*"))
        assert not leftovers, f"tmp tak boleh tersisa: {leftovers}"
        # Tidak ada file _KOREKSI (in-place sukses → tak perlu rescue).
        koreksi = list(tmp_path.glob("*_KOREKSI.xlsx"))
        assert not koreksi

    def test_rescue_koreksi_file_dibuat(self, tmp_path, monkeypatch):
        """v2.19.4 — TOTAL gagal (replace dst==src diblokir + open r+b
        diblokir) → file hasil diselamatkan sbg <nama>_KOREKSI.xlsx (siap
        dibuka Excel); file asli TIDAK berubah; pesan ramah menyebut
        _KOREKSI + path lengkap."""
        import openpyxl
        import waste_anomaly.source_writer as sw
        p = self._make_sheet(tmp_path)
        monkeypatch.setattr(sw.time, "sleep", lambda *_a: None)
        real_replace = os.replace

        # replace diblokir HANYA utk dst == src (Excel pegang file asli);
        # rename ke _KOREKSI (dst != src) diizinkan → rescue jalan.
        def selective_replace(a, b):
            if str(b) == str(p):
                raise PermissionError(5, "Excel pegang file asli")
            return real_replace(a, b)

        monkeypatch.setattr(sw.os, "replace", selective_replace)
        # open(src, "r+b") diblokir → fallback in-place juga gagal.
        real_open = open

        def blocked_open(path, mode="r", *a, **kw):
            if "r+b" in mode and str(path) == str(p):
                raise PermissionError(5, "Excel terbuka (r+b ditolak)")
            return real_open(path, mode, *a, **kw)

        monkeypatch.setattr(sw, "open", blocked_open, raising=False)
        try:
            sw.write_day_edits(str(p), 2, {"3": 55.0}, logger=None,
                               backup=False)
            raised = None
        except sw.SourceWriteError as e:
            raised = str(e)
        assert raised is not None, "total gagal → harus raise ramah"
        assert "DIBUKA di Excel" in raised
        assert "_KOREKSI" in raised, "pesan harus sebut file _KOREKSI"
        # File _KOREKSI.xlsx TERSIMPAN di folder sama.
        koreksi = list(tmp_path.glob("*_KOREKSI.xlsx"))
        assert len(koreksi) == 1, f"harus ada 1 file KOREKSI: {koreksi}"
        # File asli TIDAK berubah (hari-3 masih 0).
        wb = openpyxl.load_workbook(str(p), read_only=True, data_only=True)
        ws = wb["REKAP MENTAH"]
        vals = next(ws.iter_rows(min_row=2, max_row=2, values_only=True))
        wb.close()
        assert vals[8] == 0, "file asli tak boleh berubah (atomik)"
        # Tidak ada tmp_write tercecer (sudah di-rename ke _KOREKSI).
        leftovers = list(tmp_path.glob("*.tmp_write.*"))
        assert not leftovers, f"tmp harus sudah di-rename: {leftovers}"
        # File KOREKSI berisi koreksi (buka → hari-3 == 55).
        wbk = openpyxl.load_workbook(str(koreksi[0]), read_only=True,
                                     data_only=True)
        wsk = wbk["REKAP MENTAH"]
        valsk = next(wsk.iter_rows(min_row=2, max_row=2, values_only=True))
        wbk.close()
        assert valsk[8] == 55, "KOREKSI harus berisi koreksi (hari-3=55)"


# ============================================================
# [E] zoom — theme.build_qss + ZoomManager + DataTable.zoom_refresh
# ============================================================

class TestZoomTheme:
    def test_build_qss_default_sama_dgn_qss(self):
        """build_qss(None) / build_qss(UI_FONT_PX) → identik dgn QSS
        konstanta (no zoom = no perubahan)."""
        from ui.theme import QSS, UI_FONT_PX, build_qss
        assert build_qss() == QSS
        assert build_qss(UI_FONT_PX) == QSS

    def test_build_qss_scaled_mengganti_token(self):
        """build_qss(16) → token font-size 12px jadi 16px; 11px (hint/log)
        jadi round(16*11/12)=15px; tidak ada 12px/11px tersisa."""
        from ui.theme import UI_FONT_PX, build_qss
        scaled = build_qss(16)
        assert "font-size: 16px;" in scaled, "base token harus 16px"
        assert f"font-size: {UI_FONT_PX}px;" not in scaled, (
            "token 12px lama harus hilang")
        assert "font-size: 11px;" not in scaled, (
            "token 11px lama harus hilang (diganti minor)")
        # minor = round(16*11/12) = 15
        assert "font-size: 15px;" in scaled, "hint/log harus 15px"

    def test_build_qss_clamp_batas(self):
        """Px di-clamp 8-28 (zoom ekstrem tak pecah font)."""
        from ui.theme import build_qss
        assert build_qss(2) == build_qss(8)
        assert build_qss(999) == build_qss(28)

    def test_current_font_px_set_get(self):
        """set_current_font_px/current_font_px round-trip + clamp."""
        from ui.theme import UI_FONT_PX, current_font_px, set_current_font_px
        assert current_font_px() == UI_FONT_PX
        try:
            set_current_font_px(15)
            assert current_font_px() == 15
            set_current_font_px(2)  # clamp ke 8
            assert current_font_px() == 8
            set_current_font_px(999)  # clamp ke 28
            assert current_font_px() == 28
        finally:
            set_current_font_px(UI_FONT_PX)


class TestZoomManager:
    # v2.19.7 — ZoomManager._apply mutates app.setFont + app.setStyleSheet
    # (persistent app-wide state). Save/restore around each test supaya
    # test lain (mis. test_v270 lantai header) tak tercemar font zoom.
    @staticmethod
    def _save_state(app):
        from PySide6.QtGui import QFont
        return (QFont(app.font()), app.styleSheet())

    @staticmethod
    def _restore_state(app, state):
        from ui.theme import UI_FONT_PX, set_current_font_px
        orig_font, orig_ss = state
        app.setFont(orig_font)
        app.setStyleSheet(orig_ss)
        set_current_font_px(UI_FONT_PX)

    def test_level_clamp_dan_reset(self):
        """Zoom level: clamp 70-200, step 10, reset ke 100."""
        from PySide6.QtWidgets import QApplication, QWidget
        from ui.theme import UI_FONT_PX, set_current_font_px
        from ui.zoom import MAX_PCT, MIN_PCT, STEP_PCT, ZoomManager, px_for_pct
        app = _qapp()
        state = self._save_state(app)
        win = QWidget()
        try:
            zm = ZoomManager(app, win)
            assert zm.pct() == 100
            zm.zoom(-100)  # mentok bawah
            assert zm.pct() == MIN_PCT
            zm.zoom(100)  # mentok atas
            assert zm.pct() == MAX_PCT
            zm.reset()
            assert zm.pct() == 100
            # px_for_pct
            assert px_for_pct(100) == UI_FONT_PX
            assert px_for_pct(200) == UI_FONT_PX * 2
            assert px_for_pct(70) == round(UI_FONT_PX * 0.7)
            assert STEP_PCT == 10
        finally:
            self._restore_state(app, state)
            win.deleteLater()

    def test_set_level_absolute_dan_clamp(self):
        """set_level(pct) — set eksplisit (dipakai main() utk default 80%);
        clamp MIN..MAX; apply font+QSS."""
        from PySide6.QtWidgets import QApplication, QWidget
        from ui.theme import (QSS, UI_FONT_PX, current_font_px,
                              set_current_font_px)
        from ui.zoom import MAX_PCT, MIN_PCT, ZoomManager, px_for_pct
        app = _qapp()
        state = self._save_state(app)
        win = QWidget()
        try:
            set_current_font_px(UI_FONT_PX)
            app.setStyleSheet(QSS)
            zm = ZoomManager(app, win)
            assert zm.pct() == 100  # __init__ default 100 (main() apply 80)
            # set_level(80) — default aplikasi (permintaan user v2.19.7).
            zm.set_level(80)
            assert zm.pct() == 80
            # QSS + font diskalakan ke px = round(12*0.8) = 10.
            assert current_font_px() == px_for_pct(80)
            assert f"font-size: {px_for_pct(80)}px;" in app.styleSheet()
            # Clamp: set_level(0) → MIN_PCT; set_level(999) → MAX_PCT.
            zm.set_level(0)
            assert zm.pct() == MIN_PCT
            zm.set_level(999)
            assert zm.pct() == MAX_PCT
            # Idempoten: set_level ke nilai sama → no-op (tak apply ulang).
            before = zm.pct()
            zm.set_level(before)
            assert zm.pct() == before
        finally:
            self._restore_state(app, state)
            win.deleteLater()

    def test_event_filter_ctrl_wheel_zoom(self):
        """Ctrl+scroll: atas = zoom in (+10), bawah = zoom out (-10);
        event dicegal (return True). Wheel TANPA Ctrl → level tak berubah."""
        from PySide6.QtCore import QPointF, QPoint, Qt
        from PySide6.QtGui import QWheelEvent
        from PySide6.QtWidgets import QApplication, QWidget
        from ui.theme import UI_FONT_PX, set_current_font_px
        from ui.zoom import ZoomManager
        app = _qapp()
        state = self._save_state(app)
        target = QWidget()
        try:
            zm = ZoomManager(app, target)
            assert zm.pct() == 100

            def wheel(dy, mods):
                return QWheelEvent(
                    QPointF(10, 10), QPointF(10, 10),
                    QPoint(0, 0), QPoint(0, dy),
                    Qt.MouseButton.NoButton, mods,
                    Qt.ScrollPhase.NoScrollPhase, False)

            # Ctrl + scroll up → zoom in
            consumed = app.sendEvent(target, wheel(120,
                                      Qt.KeyboardModifier.ControlModifier))
            assert consumed is True, "ctrl+wheel harus dicegal (zoom)"
            assert zm.pct() == 110
            # Ctrl + scroll down → zoom out (balik 100)
            app.sendEvent(target, wheel(-120,
                          Qt.KeyboardModifier.ControlModifier))
            assert zm.pct() == 100
            # Wheel TANPA Ctrl → level tak berubah (bukan zoom)
            app.sendEvent(target, wheel(120,
                          Qt.KeyboardModifier.NoModifier))
            assert zm.pct() == 100
        finally:
            self._restore_state(app, state)
            target.deleteLater()

    def test_apply_ubah_stylesheet_dan_font(self):
        """zoom(3) → 130% → QSS px = round(12*1.3)=16 muncul di
        app.styleSheet(); current_font_px ikut 16."""
        from PySide6.QtWidgets import QApplication, QWidget
        from ui.theme import (QSS, UI_FONT_PX, current_font_px,
                              set_current_font_px)
        from ui.zoom import ZoomManager
        app = _qapp()
        state = self._save_state(app)
        win = QWidget()
        try:
            # Reset ke baseline.
            set_current_font_px(UI_FONT_PX)
            app.setStyleSheet(QSS)
            zm = ZoomManager(app, win)
            zm.zoom(3)  # 100 → 130
            assert zm.pct() == 130
            ss = app.styleSheet()
            assert "font-size: 16px;" in ss, (
                "QSS harus diskalakan ke 16px pada zoom 130%")
            assert f"font-size: {UI_FONT_PX}px;" not in ss
            assert current_font_px() == 16
        finally:
            self._restore_state(app, state)
            win.deleteLater()

    def test_datatable_zoom_refresh_buang_cache(self):
        """DataTable.zoom_refresh(): bersihkan _fit_cache; tabel kosong
        (model 0 baris) → no-op aman (tak crash)."""
        from PySide6.QtWidgets import QApplication
        from ui.widgets import DataTable
        app = _qapp()
        t = DataTable()
        try:
            assert hasattr(t, "zoom_refresh")
            assert hasattr(t, "_fit_cache")
            # Inject dummy cache entry.
            t._fit_cache[("dummy",)] = {"widths": {}}
            t.zoom_refresh()  # model kosong → no-op (tak crash)
            assert ("dummy",) not in t._fit_cache, (
                "zoom_refresh harus buang cache lama")
        finally:
            t.deleteLater()
