"""test_v2139.py — v2.13.9: pop-up detail RINGKAS + guard tekan#1 replay.

Dua permintaan user (satu pesan):
1. "bisa gak data pada bagian pop up hanya tampilkan yang penting
   penting aja jangan semua ditampilkan aku jadi bingung"
   → DetailPanel didesain ulang: RINGKASAN (±7 angka kunci berlabel
   awam) + chip sinyal TERPICU saja + alasan + peta hari + tombol
   tindak lanjut; ±25 baris kolom lengkap kini di balik tombol
   "▸ Tampilkan semua kolom data" (default sembunyi, reset per baris).
2. "dan masih ada bug pada klik filter muncul pop up"
   → Akar terbukti empiris (tests/repro_filter_popup_2139.py): klik
     yang MENUTUP menu funnel di-replay Qt ke tabel sebagai tekan#1
     TUNGGAL; guard v2.12.5 hanya menelan klik-GANDA artefak → tekan#1
     lolos → currentRowChanged → pop-up terbuka tanpa niat.
     Fix: mousePressEvent DataTable menelan tekan kiri dalam jendela
     _HF_HIDE_GUARD_S (0,6 dtk) pasca menu funnel tertutup.

Headless: QT_QPA_PLATFORM=offscreen sebelum PySide6 (konvensi suite).
"""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
UI = REPO / "ui"


def _qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


# ============================================================
# FIXTURE
# ============================================================

_FRAG = "Lonjakan vs rata-rata harian | Puncak harian vs BOM | Menumpuk di hari terakhir"


def _full_df(n: int = 4) -> pd.DataFrame:
    """Fixture lengkap: kolom ringkasan + peer + pembanding + hari."""
    rows = []
    for i in range(n):
        vals = {str(d): 5.0 for d in range(1, 31)}
        vals["17"] = 8000.0
        rows.append({
            "NAMA RESTO": f"RESTO {i}", "NAMA BARANG": f"BARANG {i}",
            "JENIS": "WASTE", "KETERANGAN": "Kualitas Internal",
            "SOURCE DATA": "REKAP", "SATUAN": "GR",
            **vals,
            "TOTAL": 12470.0, "MAX": 8000.0, "HARI MAX": 17,
            "ANOMALY SCORE": 12, "ANOMALY STATUS": "Prioritas Tinggi",
            "ANOMALY REASONS": _FRAG,
            "% to BOM": 0.0134, "MAX SHARE": 0.64,
            "PEER COUNT": 9, "TOTAL / PEER MEDIAN": 2.44,
            "BULAN LALU": 9220.0, "PERUBAHAN %": 35.2,
            "RANGKING WASTE": "Top 2 TOTAL",
            "KATEGORI ANOMALI": "Lonjakan Ekstrem",
        })
    return pd.DataFrame(rows)


def _make_view(df: pd.DataFrame | None = None):
    _qapp()
    from ui.state import AppContext
    from ui.view_anomali import AnomaliView
    ctx = AppContext({})
    view = AnomaliView(ctx)
    ctx.set_dataset(df if df is not None else _full_df(), {"key_akhir": 31})
    view._refresh_table()
    return view, ctx


def _panel(rec: pd.Series):
    _qapp()
    from ui.state import AppContext
    from ui.view_anomali import DetailPanel
    panel = DetailPanel(AppContext({}))
    panel.show()
    panel.show_record(rec)
    return panel


def _labels(panel) -> list[str]:
    from PySide6.QtWidgets import QLabel
    return [l.text() for l in panel._content.findChildren(QLabel)]


def _click_row(view, row: int) -> None:
    """Klik NYATA (QTest) pada baris tabel — jalur event penuh Qt."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    app = _qapp()
    m = view._table.model()
    rect = view._table.visualRect(m.index(row, 1))
    QTest.mouseClick(view._table.viewport(), Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier,
                     QPoint(rect.center().x(), rect.center().y()))
    app.processEvents()


# ============================================================
# [F] GUARD TEKAN#1 REPLAY — bug "klik filter muncul pop up"
# ============================================================

class TestGuardTekanTunggal:
    """tekan#1 replay pasca-tutup-menu DITELAN; klik sah tetap utuh."""

    def test_repro_utuh_popup_tidak_muncul(self):
        """Skenario repro: buka menu funnel → tutup (klik di luar) →
        tekan#1 replay jatuh di baris → pop-up TIDAK boleh terbuka +
        baris TIDAK terseleksi (dulu: keduanya terjadi — bug user)."""
        view, _ = _make_view()
        app = _qapp()
        view.resize(1200, 700)
        view.show()
        app.processEvents()
        hdr = view._table.horizontalHeader()
        logical = list(view._table.model().dataframe.columns).index("JENIS")
        hdr._open_menu(logical)
        assert hdr._menu is not None and hdr._menu.isVisible()
        hdr._menu.hide()  # klik-di-luar → aboutToHide → guard tercatat
        app.processEvents()
        # seleksi awal (fitur) lalu tutup pop-up → premis bersih
        view._table.setCurrentIndex(view._table.model().index(0, 1))
        app.processEvents()
        view._popup.hide()
        app.processEvents()
        assert not view._popup.isVisible()

        _click_row(view, 2)  # tekan#1 replay
        assert not view._popup.isVisible(), (
            "BUG: pop-up terbuka dari tekan#1 replay pasca menu filter")
        assert view._table.selectionModel().currentIndex().row() != 2, (
            "tekan#1 replay harus ditelan (baris tak terseleksi)")

    def test_klik_sah_setelah_guard_popup_terbuka(self):
        """Kontrol dua arah: jendela guard lewat → klik baris = fitur
        inti (pop-up terbuka — 'klik 1× selalu membuka pop-up' v2.13.5
        tetap utuh)."""
        from PySide6.QtTest import QTest
        view, _ = _make_view()
        app = _qapp()
        view._table.setCurrentIndex(view._table.model().index(0, 1))
        app.processEvents()
        view._popup.hide()
        app.processEvents()
        QTest.qWait(50)
        view._table._hf_hide = (view._table._hf_hide[0] - 10.0, None)
        _click_row(view, 1)
        assert view._popup.isVisible(), "klik normal harus membuka pop-up"
        assert "RESTO 1" in view._popup._panel._title.text()

    def test_guard_hanya_setelah_menu_riil(self):
        """Tabel tanpa riwayat menu (_hf_hide awal -1e9) → klik pertama
        langsung bekerja (guard tak aktif dari konstruksi)."""
        view, _ = _make_view()
        assert view._table._hf_hide[0] < 0
        _click_row(view, 1)
        assert view._popup.isVisible()

    def test_guard_tidak_mematikan_sel_centang(self):
        """Tekan sel ✓ (tanpa riwayat menu) tetap = perilaku v2.13.5:
        baris terseleksi, pop-up TIDAK terbuka (aksi centang murni).
        (Catatan: flip bool via delegate editorEvent hanya terpicu oleh
        event jendela asli — di lingkungan offscreen test suite selalu
        memverifikasi toggle secara programatik via _on_check_toggled,
        kontrak yang sama sejak test_v2135 [C]; guard baru TIDAK aktif
        tanpa riwayat menu funnel → jalur super() tak tersentuh.)"""
        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        from waste_anomaly.followup import CHECK_COL
        view, ctx = _make_view()
        app = _qapp()
        view._popup.hide()
        app.processEvents()
        m = view._table.model()
        assert m.dataframe.columns[0] == CHECK_COL
        # toggle programatik (kontrak suite) — jalur setData/model
        view._on_check_toggled(1, True)
        fp = str(m.record(1)["__FP"])
        assert fp in ctx.followup_set()
        # tekan mouse pada sel ✓ → seleksi hidup + pop-up ditekan
        idx = m.index(2, 0)
        rect = view._table.visualRect(idx)
        pos, g = QPointF(rect.center()), QPointF(
            view._table.mapToGlobal(rect.center()))
        for typ, btns in [(QEvent.Type.MouseButtonPress,
                           Qt.MouseButton.LeftButton),
                          (QEvent.Type.MouseButtonRelease,
                           Qt.MouseButton.NoButton)]:
            app.sendEvent(view._table.viewport(), QMouseEvent(
                typ, pos, g, Qt.MouseButton.LeftButton, btns,
                Qt.KeyboardModifier.NoModifier))
        app.processEvents()
        assert view._table.selectionModel().currentIndex().row() == 2
        assert not view._popup.isVisible(), (
            "klik sel ✓ tanpa riwayat menu tetap aksi murni (v2.13.5)")


# ============================================================
# [P] POP-UP RINGKAS — "hanya yang penting-penting aja"
# ============================================================

class TestPopupRingkas:

    def test_ringkasan_tampil_dengan_label_awam(self):
        """Seksi 'Ringkasan' + label Bahasa awam + nilai terformat."""
        panel = _panel(_full_df().iloc[0])
        texts = _labels(panel)
        assert "Ringkasan" in texts
        # v2.13.15 (gel-6 A18 — ditulis ulang jujur): label "vs cabang
        # lain (median)" kini "vs median cabang lain (sebulan)" — pop-up
        # memuat dua median pembanding beda definisi (TOTAL sebulan vs
        # puncak per hari); label lama generik = ambigu.
        for lbl in ("Total waste sebulan:", "Puncak sehari:",
                    "vs penjualan (BOM):",
                    "vs median cabang lain (sebulan):",
                    "vs bulan lalu:", "Peringkat waste cabang:",
                    "Jenis & alasan catatan:"):
            assert lbl in texts, f"label ringkasan hilang: {lbl}"
        assert "12.470 GR" in texts
        assert "8.000 di tanggal 17" in texts
        assert "1,34%" in texts
        assert "2,4× (median sebulan 9 cabang)" in texts
        assert "+35,2% — bulan lalu 9.220" in texts
        assert "WASTE · Kualitas Internal" in texts

    def test_kolom_lengkap_tersembunyi_default(self):
        """Default: daftar ±25 kolom TERSEMBUNYI + tombol pembuka ada
        (memuat jumlah baris). Konten ringkas tetap semua terlihat."""
        panel = _panel(_full_df().iloc[0])
        assert panel._full_box is not None
        assert panel._full_box.isHidden(), (
            "daftar kolom lengkap harus sembunyi default (permintaan "
            "user: jangan semua ditampilkan)")
        assert panel._more_btn is not None
        assert panel._more_btn.text().startswith("▸ Tampilkan semua kolom data (")
        # seksi inti tetap hadir (tidak ikut disembunyikan)
        texts = _labels(panel)
        assert "Ringkasan" in texts
        assert any(t.startswith("Sinyal terpicu (3 dari 12)") for t in texts)
        assert "Alasan terdeteksi" in texts

    def test_toggle_buka_tutup_daftar_lengkap(self):
        """Klik tombol → daftar terlihat + teks tombol berubah; klik
        lagi → sembunyi kembali."""
        panel = _panel(_full_df().iloc[0])
        panel._toggle_full()
        assert panel._full_box.isVisible()
        assert panel._more_btn.text().startswith(
            "▾ Sembunyikan daftar kolom lengkap")
        # nilai pct lama tetap terformat benar saat dibuka
        texts = _labels(panel)
        assert "64,00%" in texts  # MAX SHARE 0.64
        panel._toggle_full()
        assert panel._full_box.isHidden()
        assert panel._more_btn.text().startswith("▸ Tampilkan semua kolom data")

    def test_baris_baru_mulai_tersembunyi_lagi(self):
        """Pilih baris lain setelah membuka daftar → daftar kembali
        sembunyi (keadaan default per baris — pop-up selalu ringkas)."""
        df = _full_df()
        panel = _panel(df.iloc[0])
        panel._toggle_full()
        assert panel._full_box.isVisible()
        panel.show_record(df.iloc[1])
        _qapp().processEvents()
        assert panel._full_box is not None
        assert panel._full_box.isHidden(), (
            "baris baru harus mulai dari daftar tersembunyi")

    def test_chip_hanya_sinyal_terpicu(self):
        """Chip MERAH (terpicu) saja — chip abu-abu 'tidak terpicu'
        tidak lagi dirender; jumlah ✓ == jumlah fragmen reasons."""
        panel = _panel(_full_df().iloc[0])
        texts = _labels(panel)
        chips = [t for t in texts if "✓" in t]
        n_frag = len([f for f in _FRAG.split(" | ") if f])
        assert len(chips) == n_frag == 3
        assert any("S1 ·" in t for t in chips)
        assert any("S6 ·" in t for t in chips)
        assert any("S11 ·" in t for t in chips)
        # chip tidak terpicu (abu-abu) TAK dirender: 12-3=9 label S*
        # lain tidak ada di daftar label
        s_labels = [t for t in texts if t.startswith("S") and " · " in t]
        assert len(s_labels) == 3

    def test_nol_sinyal_catatan_jujur(self):
        """Baris tanpa sinyal terpicu → catatan redup (bukan 12 chip
        abu-abu)."""
        df = _full_df()
        df.loc[0, "ANOMALY REASONS"] = ""
        panel = _panel(df.iloc[0])
        texts = _labels(panel)
        assert any(t.startswith("Sinyal terpicu (0 dari 12)") for t in texts)
        assert any("Tidak ada sinyal terpicu" in t for t in texts)
        assert not [t for t in texts if "✓" in t]

    def test_baris_tanpa_pembanding_tetap_ramping(self):
        """Fixture tanpa kolom peer/BOM/perubahan → baris ringkasan
        kosong DILEWATI (tidak ada baris '—' nyasar)."""
        rec = pd.Series({
            "NAMA RESTO": "R1", "NAMA BARANG": "B1", "JENIS": "WASTE",
            "KETERANGAN": "Kualitas", "SOURCE DATA": "REKAP",
            "SATUAN": "GR", "TOTAL": 100.0, "MAX": 50.0, "HARI MAX": 3,
            "ANOMALY SCORE": 5, "ANOMALY STATUS": "Perlu Review",
            "ANOMALY REASONS": "Terpusat di satu hari",
        })
        panel = _panel(rec)
        texts = _labels(panel)
        assert "Ringkasan" in texts
        assert "Total waste sebulan:" in texts
        assert "100 GR" in texts
        assert "50 di tanggal 3" in texts
        assert "vs penjualan (BOM):" not in texts
        assert "vs median cabang lain (sebulan):" not in texts
        assert "vs bulan lalu:" not in texts

    def test_peta_hari_dan_tindak_lanjut_tetap_ada(self):
        """Regression: peta hari 1-31, tombol follow-up + drill fokus
        tetap dirender (tidak ikut 'dirampingkan' hilang).

        v2.13.10 (gel-1 V1): pencarian tombol diperluas dari _content ke
        SELURUH panel — tombol tindak lanjut kini tinggal di footer AKSI
        STICKY di luar QScrollArea (di bawah konten gulir; audit V1:
        CTA dulunya di bawah lipatan scroll). Maksud test tak berubah:
        'tombol ter-render di panel pop-up' (peta hari tetap di konten
        gulir — scope findChildren-nya tetap _content)."""
        panel = _panel(_full_df().iloc[0])
        from PySide6.QtWidgets import QDoubleSpinBox, QPushButton
        # v2.16.0: peta hari kini EDITABLE — QDoubleSpinBox per hari (bukan
        # QLabel read-only). Sel ber-tooltip 'Hari N ...' = peta hari.
        day_cells = [s for s in panel._content.findChildren(QDoubleSpinBox)
                     if s.toolTip().startswith("Hari ")]
        assert len(day_cells) >= 30, "peta hari 1-31 harus utuh"
        red = [s for s in day_cells if "#dc2626" in (s.styleSheet() or "")]
        assert red, "hari tersangka harus disorot merah"
        btns = [b.text() for b in panel.findChildren(QPushButton)]
        assert any("Masuk Follow Up" in t for t in btns)
        assert any("Fokus cabang" in t for t in btns)
        assert any("Fokus item" in t for t in btns)

    def test_clear_reset_ref_kolom_lengkap(self):
        """clear() (dataset berubah) mereset ref _full_box/_more_btn —
        handler tak menyentuh widget mayat (pola _fu_btn v2.13.5)."""
        panel = _panel(_full_df().iloc[0])
        assert panel._full_box is not None
        panel.clear()
        assert panel._full_box is None
        assert panel._more_btn is None

    def test_data_riil_popup_dari_pipeline(self):
        """Data riil (sample_workbook): pop-up baris top terbangun;
        jumlah chip ✓ == jumlah fragmen (kontrak v2.7.0 utuh di desain
        ringkas); ringkasan ≥ 3 baris."""
        from waste_anomaly.pipeline import run_pipeline
        sample = REPO / "sample_workbook.xlsx"
        if not sample.exists():
            import pytest
            pytest.skip("sample_workbook.xlsx tidak ada")
        s = run_pipeline(str(sample), key_akhir=31)
        assert s.get("success")
        top = s["df"].sort_values("ANOMALY SCORE", ascending=False).iloc[0]
        panel = _panel(top)
        texts = _labels(panel)
        n_frag = len([f for f in str(
            top.get("ANOMALY REASONS") or "").split(" | ") if f])
        chips = [t for t in texts if "✓" in t]
        assert len(chips) == n_frag, (len(chips), n_frag)
        assert "Ringkasan" in texts
        assert any(t == "Total waste sebulan:" for t in texts)
        assert panel._full_box.isHidden()


# ============================================================
# [V] VERSI
# ============================================================

class TestVersi:
    def test_versi_semua_situs_2139(self):
        from waste_anomaly import __version__
        from waste_anomaly.utils import load_config
        from ui.shared import APP_VERSION
        cfg = load_config()
        assert APP_VERSION == __version__ == cfg.get("version") == "2.17.0"
