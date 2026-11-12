"""zoom.py — v2.19.4 — ZOOM IN/OUT Ctrl+scroll (permintaan user).

Permintaan user: "tambahin fitur di aplikasi nya atau program nya buat
zoom in dan zoom out dengan cara ctrl scroll atas atau bawah" —
gestur Ctrl + roda mouse atas/bawah memperbesar/memperkecil teks SELURUH
UI (tabel anomali/hari/follow up, log pipeline, tombol, tab — semua).

MEKANISME (3 lapis yang HARUS jalan bersama):
  1. EVENT FILTER app-wide (QApplication.installEventFilter) — event
     wheel di widget APA PUN (tabel QTableView, QScrollArea tab
     Pipeline, log QPlainTextEdit) dicegat SEBELUM widget memprosesnya.
     Tanpa ini ctrl+scroll di dalam tabel akan di-scroll-vertikal biasa
     (QTableView memakan event wheel — tidak pernah sampai window).
  2. FONT + QSS diskalakan bersama:
       - QApplication.setFont(pt skala) → fontMetrics widget (dasar
         pengukuran tinggi baris DataTable._refit_rows) ikut besar —
         kalau hanya QSS yang berubah, teks sel membesar tapi tinggi
         baris diukur dgn font kecil → teks TERPOTONG (bukti piksel
         comment _header_font: font QSS ≠ font widget).
       - QApplication.setStyleSheet(build_qss(px)) → token font-size
         QSS (rendering seluruh widget) proporsional.
     Kedua-duanya dipasang TIAP zoom berubah (jangan hanya salah satu).
  3. CACHE FIT DIBUANG — DataTable menyimpan lebar kolom + tinggi baris
     dalam px (cache per-df) → semua basi saat font berubah →
     zoom_refresh() mengukur ulang. Tabel LAIN (non-DataTable) tanpa
     cache → otomatis benar (Qt mengukur ulang saat font berubah).

Batas: 70% … 200%, langkah 10% (persepsi "klik" scroll = 1 langkah;
roda berputar cepat menghasilkan beberapa event = beberapa langkah).
Ctrl+scroll tanpa berpindah level (sudah mentok) → event tetap dicekal
(anti scroll-vertikal tak sengaja saat user jelas minta zoom).

Shortcut keyboard (a11y — laptop tanpa mouse/trackpad terbatas):
  Ctrl+= / Ctrl++ → perbesar · Ctrl+- → perkecil · Ctrl+0 → reset 100%
(dipasang oleh MainWindow — modul ini hanya logika level + filter).

Level TIDAK dipersist (session-only): zoom adalah preferensi tampilan
sesaat (data samping / proyektor); simpan ke config = kembali mengejut
user yang lupa pernah zoom (bayangkan app "rusak" tiap startup).
"""
from __future__ import annotations

import weakref

from PySide6.QtCore import QObject, QEvent, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QStatusBar, QTableView

from .theme import (
    UI_FONT_FAMILY,
    UI_FONT_PX,
    build_qss,
    current_font_px,
    set_current_font_px,
)

MIN_PCT = 70   # zoom out terjauh (12px → 8px) — masih terbaca
MAX_PCT = 200  # zoom in terjauh  (12px → 24px)
STEP_PCT = 10  # satu "klik" roda = 10% (butuh ±3 klik utk terasa besar)

# Peredaman float: round(12 * pct/100) — 110% → 13px, 130% → 16px,
# 150% → 18px, 200% → 24px (tabel 5 tab + log semua proporsional).
_PX_MIN = 8
_PX_MAX = 28


def px_for_pct(pct: int) -> int:
    """Konversi level zoom (%) → px font dasar (clamp batas aman)."""
    return max(_PX_MIN, min(_PX_MAX, round(UI_FONT_PX * pct / 100.0)))


class ZoomManager(QObject):
    """Kendali zoom level + filter event Ctrl+scroll app-wide.

    Dipasang SEKALI oleh MainWindow:
        self._zoom = ZoomManager(QApplication.instance(), self)
    Filter hidup selama window hidup (parent=this → GC ikut window).
    """

    def __init__(self, app: QApplication, window) -> None:
        super().__init__(window)
        self._app = app
        # v2.19.4 — WEAKREF window: strong ref + Qt parent ownership = cycle
        # yang tak bisa dipecah gc → MainWindow bocor (test_v21314 D24).
        # Weakref: window lepas saat refcount turun (del) → ZoomManager
        # (anak Qt) ikut di-destroy C++ → app auto-uninstall event filter.
        self._win_ref = weakref.ref(window)
        self._pct = 100
        app.installEventFilter(self)

    # ------------------------------------------------------------
    # API publik (dipakai shortcut keyboard + test)
    # ------------------------------------------------------------
    def pct(self) -> int:
        """Level zoom aktif dalam persen (100 = default)."""
        return self._pct

    def zoom(self, steps: int) -> None:
        """Ubah level: steps +1 = perbesar 10%, -1 = perkecil 10%.
        Mentok batas → diam (tidak apply dua kali)."""
        new = max(MIN_PCT, min(MAX_PCT, self._pct + STEP_PCT * steps))
        if new == self._pct:
            return
        self._pct = new
        self._apply()

    def reset(self) -> None:
        """Kembali ke 100% (Ctrl+0 — standard 'actual size' browser-style)."""
        if self._pct == 100:
            return
        self._pct = 100
        self._apply()

    def set_level(self, pct: int) -> None:
        """Set level zoom eksplisit (clamped MIN..MAX) + apply. Dipakai
        MainWindow.main() utk default 80% saat aplikasi pertama dibuka
        (permintaan user: 'tampilan aplikasi pertama kali buka jadikan
        80% aja'). Berbeda dgn zoom(steps) (relative) — ini absolute."""
        new = max(MIN_PCT, min(MAX_PCT, int(pct)))
        if new == self._pct:
            return
        self._pct = new
        self._apply()

    # ------------------------------------------------------------
    # EVENT FILTER — jantung fitur (lihat docstring modul, lapis 1)
    # ------------------------------------------------------------
    def eventFilter(self, obj, event) -> bool:  # noqa: N802 (Qt API)
        if event.type() == QEvent.Type.Wheel:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                delta = event.angleDelta().y()
                if delta == 0:
                    delta = (event.pixelDelta().y()
                             if event.pixelDelta() is not None else 0)
                if delta:
                    self.zoom(1 if delta > 0 else -1)
                    return True   # dicekal — jangan scroll tabel
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------
    # APPLY — font + QSS + re-fit (lapis 2 & 3)
    # ------------------------------------------------------------
    def _apply(self) -> None:
        window = self._win_ref()
        if window is None:
            return  # window sudah di-destroy — zoom stale, no-op aman.
        px = px_for_pct(self._pct)
        set_current_font_px(px)
        # (a) font aplikasi — dasar fontMetrics pengukuran tinggi baris.
        #     px→pt: 96 DPI logical (1px = 0.75pt) — Qt logical pixel.
        f = QFont()
        f.setFamilies([p.strip().strip('"')
                       for p in UI_FONT_FAMILY.split(",")])
        f.setPointSizeF(px * 72.0 / 96.0)
        self._app.setFont(f)
        # (b) QSS — rendering seluruh widget (token font-size diskalakan).
        self._app.setStyleSheet(build_qss(px))
        # (c) buang cache fit semua tabel anak jendela + ukur ulang.
        for t in window.findChildren(QTableView):
            refresh = getattr(t, "zoom_refresh", None)
            if callable(refresh):
                refresh()
        # Umpan-balik level aktif (pola status-bar app, 2.5 dtk).
        sb = window.findChild(QStatusBar)
        if sb is not None:
            sb.showMessage(f"Zoom tampilan: {self._pct}%", 2500)
