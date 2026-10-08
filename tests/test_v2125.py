"""test_v2125.py — regresi v2.12.5 (2 keluhan user pasca funnel header).

Keluhan (WhatsApp-style, bahasa user):
(1) "Nama header jadi terpotong ya semenjak ada icon filter"
(2) "waktu aku apply filter sepertinya ketrigger double klik sehingga
    pop up muncul atau drill down detail muncul"

Akar terukur (bukti piksel data asli 1366×700):
(1) Judul kolom dilukis QSS dgn font-weight 600 + font *{} 13px —
    ``self.fontMetrics()`` (weight 400, font default widget) mengukur
    8-12% lebih pendek → lantai header kurang; ekor judul masuk zona
    backing funnel v2.12.3-4 [right-32, right-12] → tampak terpotong.
    Fix: paintSection melukis judul di rect YANG DISEMPITKAN sebesar
    _HF_STRIP (22px) — teks ter-elide SEBELUM strip; strip dilukis
    manual (bg + ikon + border replica QSS); lantai diukur dgn font
    QSS asli (_header_font: family chain + 13px + DemiBold).
(2) Klik penutup menu funnel yang jatuh di tabel DI-REPLAY Qt sebagai
    tekan#1 pada baris; klik ke-2 user = tekan#2 → Qt menyintesis
    klik-ganda → doubleClicked → DetailDialog terbuka sendiri.
    Fix: mouseDoubleClickEvent menelan klik-ganda dalam <0.6 s setelah
    menu funnel tertutup (klik tunggal pilih-baris tetap hidup).
    v2.13.9 REVISI (laporan user: "masih ada bug pada klik filter muncul
    pop up"): tekan#1 replay TUNGGAL ternyata juga membuka pop-up di tab
    ber-sinyal currentRowChanged (Anomali/Hari/Follow Up) — kini tekan
    kiri dalam jendela guard juga DITELAN (mousePressEvent, lihat
    test_v2139.py); test "klik tunggal tetap memilih baris" lama
    ditulis ulang jujur di kelas TestGuardDClick.

Cakupan:
[A] anti-terpotong: font QSS, lantai jujur, piksel strip bersih,
    ikon funnel tetap dilukis, konstanta theme dipakai QSS.
[B] guard DClick: waktu tertutup tercatat; artefak ditelan; klik ganda
    sah tetap hidup (setelah selang / tabel tanpa menu); klik tunggal
    dalam guard ditelan (revisi v2.13.9) + kontrol klik sah.
[C] zona hit funnel baru ([w-24, w-2] — ikon di right-12).
"""
from __future__ import annotations

import os
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QFont, QFontMetrics, QMouseEvent
from PySide6.QtWidgets import QApplication, QWidget

REPO = Path(__file__).resolve().parent.parent


def _qapp():
    return QApplication.instance() or QApplication([])


def _df() -> pd.DataFrame:
    return pd.DataFrame({
        "KETERANGAN LAMANYA SEKALI": ["Kualitas Internal", "Over Stock",
                                      "Handling"],
        "JENIS": ["WASTE", "SUSUT", "TRIAL"],
        "TOTAL": [100.0, 7.0, 12.0],
    })


def _table(all_cols: bool = True):
    from ui.widgets import DataTable
    app = _qapp()
    host = QWidget()
    host.resize(700, 300)
    t = DataTable(host)
    t.setGeometry(10, 10, 680, 280)
    t.setup_header_filters({"JENIS": "jenis"}, lambda *a: None,
                           lambda c: None, all_cols=all_cols)
    t.set_dataframe(_df(), sort_desc="TOTAL")
    host.show()
    app.processEvents()
    return t, host


def _klik_ganda(t, global_pos: QPoint) -> None:
    """Urutan terbukti memicu doubleClicked: tekan+lepas lalu DClick
    pada sel valid (Qt hanya memancarkan bila tekan#1 mengenai baris)."""
    app = _qapp()
    vp = t.viewport()
    lp = QPointF(vp.mapFromGlobal(global_pos))
    for tipe in (QEvent.Type.MouseButtonPress,
                 QEvent.Type.MouseButtonRelease,
                 QEvent.Type.MouseButtonDblClick,
                 QEvent.Type.MouseButtonRelease):
        QApplication.sendEvent(vp, QMouseEvent(
            tipe, lp, QPointF(global_pos), Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    app.processEvents()


def _sel_tabel(t) -> QPoint:
    vp = t.viewport()
    return vp.mapToGlobal(QPoint(30, t.rowHeight(0) // 2))


# ============================================================
# [A] judul kolom tak terpotong oleh funnel
# ============================================================

class TestHeaderAntiTerpotong:
    def test_header_font_mirip_qss(self):
        from ui.widgets import _header_font
        from ui.theme import UI_FONT_FAMILY, UI_FONT_PX
        f = _header_font()
        assert f.pixelSize() == UI_FONT_PX
        assert f.weight() == QFont.Weight.DemiBold
        fams = f.families()
        assert any("Segoe UI" in x for x in fams), fams
        # family chain dari konstanta theme (satu sumber kebenaran)
        assert "Segoe UI" in UI_FONT_FAMILY

    def test_theme_font_dipakai_qss(self):
        from ui.theme import QSS, UI_FONT_FAMILY, UI_FONT_PX, UI_HEADER_WEIGHT
        assert f"font-family: {UI_FONT_FAMILY}" in QSS
        assert f"font-size: {UI_FONT_PX}px" in QSS
        assert f"font-weight: {UI_HEADER_WEIGHT}" in QSS

    def test_lantai_header_diukur_font_qss(self):
        from ui.widgets import _header_font
        t, host = _table()
        hfm = QFontMetrics(_header_font())
        m = t.model()
        for c in range(m.columnCount()):
            if t.isColumnHidden(c):
                continue
            name = str(m.headerData(c, Qt.Orientation.Horizontal))
            adv = hfm.horizontalAdvance(name)
            assert t.columnWidth(c) >= adv + 26, (
                f"lantai judul '{name}' kurang: {t.columnWidth(c)}px < "
                f"{adv + 26}px (ukur dgn font QSS bold)")
        host.close()

    def test_piksel_strip_bersih_dari_teks(self):
        """Teks judul TIDAK boleh ada piksel gelap di zona strip
        [x0+w-24, x0+w) utk kolom ber-funnel — judul ter-elide sebelum
        funnel (v2.12.3-4: backing menutup [right-32, right-12])."""
        t, host = _table()
        hdr = t.horizontalHeader()
        m = t.model()
        img = hdr.grab().toImage()
        app = _qapp()
        app.processEvents()
        bad = []
        for c in range(m.columnCount()):
            if t.isColumnHidden(c):
                continue
            name = str(m.headerData(c, Qt.Orientation.Horizontal))
            if not t._hf_has(name):
                continue  # kolom tanpa funnel (✓ dst) — bukan sasaran
            x0 = hdr.sectionViewportPosition(c)
            w = hdr.sectionSize(c)
            dark = sum(1 for x in range(x0 + w - 24, x0 + w)
                       for y in range(hdr.height())
                       if (px := img.pixelColor(x, y))
                       and px.value() < 130)
            if dark:
                bad.append((name, dark))
        assert not bad, f"judul terpotong oleh funnel: {bad}"
        host.close()

    def test_ikon_funnel_tetap_dilukis_di_strip(self):
        from ui.theme import UI_FONT_FAMILY  # noqa: F401 — info provenance
        t, host = _table()
        hdr = t.horizontalHeader()
        m = t.model()
        c = 0  # kolom pertama ber-funnel (header panjang)
        x0 = hdr.sectionViewportPosition(c)
        w = hdr.sectionSize(c)
        img = hdr.grab().toImage()
        # fill idle funnel = #cbd5e1 (rgb 203,213,225)
        ada_ikon = any(
            abs((px := img.pixelColor(x, y)).red() - 203) < 15
            and abs(px.green() - 213) < 15 and abs(px.blue() - 225) < 15
            for x in range(x0 + w - 24, x0 + w)
            for y in range(hdr.height()))
        assert ada_ikon, "ikon funnel tak terlukis di strip kanan"
        host.close()

    def test_kolom_panpa_funnel_tak_berubah(self):
        """Kolom non-funnel = super() murni: tak ada strip/ikon."""
        t, host = _table(all_cols=False)  # hanya JENIS mapping
        hdr = t.horizontalHeader()
        m = t.model()
        c = 0  # KETERANGAN… — tanpa funnel (bukan mapping, all_cols off)
        x0 = hdr.sectionViewportPosition(c)
        w = hdr.sectionSize(c)
        img = hdr.grab().toImage()
        _ = (img, x0, w)  # grab supaya paint jalan; cek via _hf_has
        name = str(m.headerData(c, Qt.Orientation.Horizontal))
        assert not t._hf_has(name)
        host.close()


# ============================================================
# [B] guard klik-ganda pasca menu funnel tertutup
# ============================================================

class TestGuardDClick:
    def test_tutup_menu_mencatat_waktu(self):
        t, host = _table()
        hdr = t.horizontalHeader()
        app = _qapp()
        hdr._open_menu(0)
        app.processEvents()
        before = time.monotonic()
        hdr._menu.close()
        app.processEvents()
        ts, _rect = t._hf_hide
        assert before - 1.0 < ts <= time.monotonic() + 0.05, (
            f"waktu tutup tak tercatat: ts={ts}")
        host.close()

    def test_dclick_artefak_ditelan(self):
        """Pasca menu tertutup < 0.6 s — klik ganda pada baris TIDAK
        memicu double_clicked (dulu: DetailDialog muncul sendiri)."""
        t, host = _table()
        hdr = t.horizontalHeader()
        app = _qapp()
        fired = []
        t.double_clicked.connect(lambda rec: fired.append(rec))
        hdr._open_menu(0)
        app.processEvents()
        hdr._menu.close()
        app.processEvents()
        _klik_ganda(t, _sel_tabel(t))
        assert not fired, "klik-ganda artefak lolos ke double_clicked"
        host.close()

    def test_dclick_sah_setelah_guard_lewat(self):
        t, host = _table()
        fired = []
        t.double_clicked.connect(lambda rec: fired.append(rec))
        t._hf_hide = (time.monotonic() - 5.0, None)  # guard kedaluwarsa
        _klik_ganda(t, _sel_tabel(t))
        assert len(fired) == 1
        host.close()

    def test_tabel_tanpa_menu_tak_terpengaruh(self):
        """_hf_hide awal = -1e9 (tak pernah buka menu) → klik ganda
        normal langsung dari konstruksi."""
        t, host = _table()
        assert t._hf_hide[0] < 0
        fired = []
        t.double_clicked.connect(lambda rec: fired.append(rec))
        _klik_ganda(t, _sel_tabel(t))
        assert len(fired) == 1
        host.close()

    def test_klik_tunggal_dalam_guard_ditelan_v2139(self):
        """v2.13.9 REVISI desain (test v2.12.5 lama ditulis ulang jujur —
        alasan tercatat): dulu klik tunggal dalam jendela guard masih
        memilih baris ("pilih-baris tetap hidup"). Tekanan tunggal itu
        justru jalur bocornya tekan#1 REPLAY: klik yang menutup menu
        funnel di-replay Qt ke tabel → baris terseleksi → pop-up detail
        terbuka tanpa niat user — laporan user v2.13.8 "masih ada bug
        pada klik filter muncul pop up" (repro: tests/repro_filter_
        popup_2139.py [3]). Kini tekan kiri dalam jendela guard DITELAN
        TOTAL (tanpa seleksi); klik sah sesudah jendela utuh (lihat
        test_v2139.TestGuardTekanTunggal utk bukti dua arah)."""
        t, host = _table()
        hdr = t.horizontalHeader()
        app = _qapp()
        hdr._open_menu(0)
        app.processEvents()
        hdr._menu.close()
        app.processEvents()
        vp = t.viewport()
        y = t.rowHeight(0) + t.rowHeight(1) // 2  # baris ke-1 (indeks 1)
        gp = vp.mapToGlobal(QPoint(30, y))
        lp = QPointF(vp.mapFromGlobal(gp))
        for tipe in (QEvent.Type.MouseButtonPress,
                     QEvent.Type.MouseButtonRelease):
            QApplication.sendEvent(vp, QMouseEvent(
                tipe, lp, QPointF(gp), Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier))
        app.processEvents()
        assert t.currentIndex().row() != 1, (
            "tekan#1 replay pasca-tutup-menu harus ditelan (v2.13.9 — "
            "dulu baris terseleksi → pop-up terbuka tanpa niat user)")
        host.close()

    def test_klik_tunggal_sah_setelah_guard_lewat(self):
        """Kontrol sisi positif: jendela guard lewat → klik tunggal
        memilih baris & memicu sinyal klik normal (fitur inti utuh)."""
        t, host = _table()
        app = _qapp()
        t._hf_hide = (time.monotonic() - 5.0, None)  # guard kedaluwarsa
        vp = t.viewport()
        y = t.rowHeight(0) + t.rowHeight(1) // 2
        gp = vp.mapToGlobal(QPoint(30, y))
        lp = QPointF(vp.mapFromGlobal(gp))
        for tipe in (QEvent.Type.MouseButtonPress,
                     QEvent.Type.MouseButtonRelease):
            QApplication.sendEvent(vp, QMouseEvent(
                tipe, lp, QPointF(gp), Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier))
        app.processEvents()
        assert t.currentIndex().row() == 1, (
            "klik tunggal normal harus tetap memilih baris")
        host.close()


# ============================================================
# [C] zona hit funnel (ikon di right-12)
# ============================================================

class TestZonaHitFunnel:
    def test_zona_baru(self):
        t, host = _table()
        hdr = t.horizontalHeader()
        x0 = hdr.sectionViewportPosition(0)
        w = hdr.sectionSize(0)
        y = hdr.height() / 2
        assert hdr._hit_funnel(QPointF(x0 + w - 22, y)) == 0  # posisi lama
        assert hdr._hit_funnel(QPointF(x0 + w - 12, y)) == 0  # pusat ikon
        assert hdr._hit_funnel(QPointF(x0 + w - 24, y)) == 0  # tepi kiri
        assert hdr._hit_funnel(QPointF(x0 + w - 1, y)) is None  # tepi kanan
        assert hdr._hit_funnel(QPointF(x0 + w - 40, y)) is None  # area teks
        host.close()
