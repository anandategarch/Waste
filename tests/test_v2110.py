"""test_v2110.py — regresi v2.11.0: SlicerBar + set_filters_multi +
combo sidebar sadar-multi + semantik list _apply_filters.

Slicer (tombol filter kilat multi-select ala Excel) di atas tabel tab
Anomali + Hari Mencurigakan — Banding Periode sengaja TIDAK ikut
(membandingkan file bulan, bukan baris data).

Kontrak yang dikunci:
- set_filters_multi: beberapa dimensi → SATU broadcast filters_changed
  (klik beruntun chip = satu render); kunci asing diabaikan; memo
  filtered_df ter-invalidasi.
- _apply_filters: nilai LIST semua dimensi = gabungan single; list
  keterangan ternormalisasi whitespace ≡ single ternormalisasi
  (kontrak v2.5.1 utuh); list kosong ≡ None (tanpa filter).
- SlicerBar: sembunyi sebelum ada data; dataset baru → repopulasi
  (JENIS hanya yang ada di data + urutan tetap, KETERANGAN
  ternormalisasi-unik, STATUS 4 + properti sev utk QSS); klik chip →
  pending → apply = list TERURUT + satu broadcast utk klik beruntun;
  uncheck semua → kanonik ([] jenis / None keterangan); sinkron dari
  state (sidebar str → chip aktif tunggal); reset_filters → semua chip
  lepas; tombol ✕ Bersihkan → tiga dimensi kosong sekaligus.
- MainWindow: combo sidebar keterangan/status menampilkan placeholder
  '▪ beberapa dipilih' saat nilai list (tidak berbohong '(Semua)');
  user memilih placeholder = no-op (bukan filter).
- FlowLayout: chip membungkus ke baris baru saat sempit (anti-terpotong).
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _qapp():
    """QApplication offscreen tunggal per proses (pola test_ui_structure)."""
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication(sys.argv)


def _df_slicer() -> pd.DataFrame:
    """Fixture sintetis 6 baris — variasi JENIS / KETERANGAN / STATUS.

    KETERANGAN sengaja memuat varian spasi ('Cancel  Nota ' vs
    'Cancel Nota') — norm_text menyatukan keduanya (kontrak v2.5.1).
    """
    return pd.DataFrame({
        "JENIS": ["WASTE", "WASTE", "SUSUT", "TRIAL", "WASTE", "SUSUT"],
        "KETERANGAN": ["Cancel Nota", "Cancel  Nota ", "Alat/Mesin",
                       "Over Stock", "Alat/Mesin", "Cancel Nota"],
        "ANOMALY STATUS": ["Prioritas Tinggi", "Potensi Anomali",
                           "Perlu Review", "Normal", "Normal",
                           "Prioritas Tinggi"],
        "TOTAL": [10.0, 20.0, 30.0, 40.0, 50.0, 60.0],
    })


# ============================================================
# set_filters_multi (state) — coalesce broadcast
# ============================================================

class TestV2110SetFiltersMulti:
    def _ctx(self):
        _qapp()
        from ui.state import AppContext
        return AppContext({})

    def test_dua_dimensi_satu_broadcast(self):
        ctx = self._ctx()
        ctx.set_dataset(_df_slicer(), {"key_akhir": 31})
        n = {"emit": 0}
        ctx.filters_changed.connect(
            lambda: n.__setitem__("emit", n["emit"] + 1))
        ctx.set_filters_multi(
            {"jenis": ["WASTE"], "keterangan": ["Cancel Nota"]})
        assert ctx.active_filters["jenis"] == ["WASTE"]
        assert ctx.active_filters["keterangan"] == ["Cancel Nota"]
        assert n["emit"] == 1  # SATU render — bukan satu per dimensi

    def test_kunci_asing_diabaikan(self):
        ctx = self._ctx()
        before = dict(ctx.active_filters)
        ctx.set_filters_multi({"dimensi_tak_dikenal": ["X"], "status": None})
        assert ctx.active_filters == before

    def test_memo_filtered_df_terinvalidasi(self):
        ctx = self._ctx()
        ctx.set_dataset(_df_slicer(), {"key_akhir": 31})
        assert len(ctx.filtered_df()) == 6
        ctx.set_filters_multi({"jenis": ["SUSUT"]})
        assert len(ctx.filtered_df()) == 2  # bukan salinan memo basi


# ============================================================
# _apply_filters — nilai LIST ≡ gabungan single (semantik v2.5.1)
# ============================================================

class TestV2110ApplyFiltersList:
    def test_status_list_gabungan_single(self):
        from ui.shared import _apply_filters
        df = _df_slicer()
        by_list = _apply_filters(
            df, {"status": ["Prioritas Tinggi", "Perlu Review"]})
        a = _apply_filters(df, {"status": "Prioritas Tinggi"})
        b = _apply_filters(df, {"status": "Perlu Review"})
        assert sorted(by_list.index) == sorted(a.index.append(b.index))
        assert len(by_list) == 3

    def test_keterangan_list_ternormalisasi(self):
        from ui.shared import _apply_filters
        df = _df_slicer()
        # 'Cancel  Nota ' di data → norm 'Cancel Nota' — list mengenali
        out = _apply_filters(df, {"keterangan": ["Cancel Nota"]})
        assert sorted(out.index) == [0, 1, 5]
        single = _apply_filters(df, {"keterangan": "Cancel Nota"})
        assert sorted(out.index) == sorted(single.index)

    def test_list_kosong_setara_tanpa_filter(self):
        from ui.shared import _apply_filters
        df = _df_slicer()
        a = _apply_filters(
            df, {"jenis": [], "keterangan": [], "status": []})
        b = _apply_filters(df, {})
        assert len(a) == len(b) == 6


# ============================================================
# SlicerBar — interaksi chip / sinkron / kanonisasi
# ============================================================

class TestV2110SlicerBar:
    def _bar(self):
        _qapp()
        from ui.state import AppContext
        from ui.widgets import SlicerBar
        ctx = AppContext({})
        return ctx, SlicerBar(ctx)

    def test_sebelum_data_bar_sembunyi(self):
        _ctx, bar = self._bar()
        assert bar.isHidden()  # tidak ada ruang kosong pra-pipeline

    def test_populasi_dataset_baru(self):
        ctx, bar = self._bar()
        ctx.set_dataset(_df_slicer(), {"key_akhir": 31})
        # JENIS: urutan tetap WASTE·SUSUT·TRIAL (bukan alfabetis)
        assert list(bar._chips["jenis"]) == ["WASTE", "SUSUT", "TRIAL"]
        # KETERANGAN ternormalisasi-unik (varian spasi menyatu)
        assert sorted(bar._chips["keterangan"]) == [
            "Alat/Mesin", "Cancel Nota", "Over Stock"]
        # STATUS: 4 nilai + properti severity utk QSS [sev=...]
        assert list(bar._chips["status"]) == [
            "Prioritas Tinggi", "Potensi Anomali", "Perlu Review", "Normal"]
        for val, btn in bar._chips["status"].items():
            assert btn.property("sev") == val
        assert not bar.isHidden()
        # dataset baru = filter direset → semua chip lepas
        assert not any(b.isChecked()
                       for chips in bar._chips.values() for b in chips.values())

    def test_klik_chip_multi_satu_broadcast(self):
        ctx, bar = self._bar()
        ctx.set_dataset(_df_slicer(), {"key_akhir": 31})
        n = {"emit": 0}
        ctx.filters_changed.connect(
            lambda: n.__setitem__("emit", n["emit"] + 1))
        bar.chip("jenis", "WASTE").click()
        bar.chip("jenis", "SUSUT").click()
        assert bar._pending["jenis"] == ["WASTE", "SUSUT"]
        bar._apply_pending()  # debounce berakhir
        # list TERURUT (tanda tangan LRU stabil terlepas urutan klik)
        assert ctx.active_filters["jenis"] == ["SUSUT", "WASTE"]
        assert n["emit"] == 1  # 2 klik beruntun = SATU broadcast
        assert len(ctx.filtered_df()) == 5  # WASTE+SUSUT

    def test_uncheck_semua_kanonik(self):
        ctx, bar = self._bar()
        ctx.set_dataset(_df_slicer(), {"key_akhir": 31})
        bar.chip("keterangan", "Cancel Nota").click()
        bar._apply_pending()
        assert ctx.active_filters["keterangan"] == ["Cancel Nota"]
        bar.chip("keterangan", "Cancel Nota").click()  # lepas
        bar._apply_pending()
        # kanonik reset_filters: keterangan kosong = None (bukan [])
        assert ctx.active_filters["keterangan"] is None
        # jenis kosong = [] (kanonik jenis memang list)
        bar.chip("jenis", "WASTE").click()
        bar._apply_pending()
        bar.chip("jenis", "WASTE").click()
        bar._apply_pending()
        assert ctx.active_filters["jenis"] == []

    def test_sinkron_dari_state_str(self):
        """Sidebar combo (single str) → chip aktif tunggal (dua arah)."""
        ctx, bar = self._bar()
        ctx.set_dataset(_df_slicer(), {"key_akhir": 31})
        ctx.set_filter("keterangan", "Over Stock")
        assert bar.chip("keterangan", "Over Stock").isChecked()
        assert not bar.chip("keterangan", "Cancel Nota").isChecked()
        # list multi → semua anggota aktif
        ctx.set_filter("status", ["Normal", "Perlu Review"])
        assert bar.chip("status", "Normal").isChecked()
        assert bar.chip("status", "Perlu Review").isChecked()
        assert not bar.chip("status", "Prioritas Tinggi").isChecked()

    def test_reset_filters_semua_chip_lepas(self):
        ctx, bar = self._bar()
        ctx.set_dataset(_df_slicer(), {"key_akhir": 31})
        ctx.set_filters_multi(
            {"jenis": ["WASTE"], "status": ["Normal"]})
        ctx.reset_filters()
        ctx.filters_changed.emit()
        assert not any(b.isChecked()
                       for chips in bar._chips.values() for b in chips.values())

    def test_tombol_bersihkan_tiga_dimensi(self):
        ctx, bar = self._bar()
        ctx.set_dataset(_df_slicer(), {"key_akhir": 31})
        ctx.set_filters_multi({
            "jenis": ["WASTE"], "keterangan": ["Cancel Nota"],
            "status": ["Normal"]})
        assert bar.chip("jenis", "WASTE").isChecked()
        bar._btn_clear.click()
        assert ctx.active_filters["jenis"] == []
        assert ctx.active_filters["keterangan"] is None
        assert ctx.active_filters["status"] is None
        assert not bar.chip("status", "Normal").isChecked()


# ============================================================
# MainWindow — combo sidebar sadar-multi (tanpa berbohong '(Semua)')
# ============================================================

class TestV2110SidebarComboMulti:
    def _win(self):
        _qapp()
        from ui.app import MainWindow
        return MainWindow()

    def test_placeholder_multi_lalu_single(self):
        win = self._win()
        try:
            # isi item combo dulu (normalnya oleh _on_data_ready dataset)
            win._fill_combo(win._cb_ket,
                            ["Alat/Mesin", "Cancel Nota", "Over Stock"])
            win.ctx.set_filter("keterangan", ["Cancel Nota", "Over Stock"])
            assert win._cb_ket.currentText() == "▪ beberapa dipilih"
            # kembali single → placeholder dibuang, nilai asli terpilih
            win.ctx.set_filter("keterangan", "Over Stock")
            assert win._cb_ket.currentText() == "Over Stock"
            assert win._cb_ket.findText("▪ beberapa dipilih") < 0
        finally:
            win.close()

    def test_placeholder_dipilih_user_noop(self):
        win = self._win()
        try:
            win.ctx.set_filter("keterangan", ["Cancel Nota"])
            idx = win._cb_ket.findText("▪ beberapa dipilih")
            assert idx >= 0
            win._cb_ket.setCurrentIndex(idx)  # seolah user memilihnya
            # placeholder BUKAN pilihan — state tak berubah
            assert win.ctx.active_filters["keterangan"] == ["Cancel Nota"]
        finally:
            win.close()


# ============================================================
# FlowLayout — chip membungkus saat sempit (anti-terpotong)
# ============================================================

class TestV2110FlowLayout:
    def test_wrap_ke_baris_baru(self):
        _qapp()
        from PySide6.QtCore import QPoint
        from PySide6.QtWidgets import QToolButton, QWidget
        from ui.widgets import FlowLayout
        host = QWidget()
        lay = FlowLayout(host, hspacing=6, vspacing=4)
        btns = []
        for i in range(12):
            b = QToolButton(host)
            b.setText(f"chip-panjang-{i:02d}")
            lay.addWidget(b)
            btns.append(b)
        host.resize(240, 200)
        lay.setGeometry(host.rect())
        ys = {b.geometry().y() for b in btns}
        xs_ok = all(b.geometry().x() >= 0 and
                    b.geometry().right() <= host.width()
                    for b in btns)
        assert len(ys) >= 2  # benar-benar membungkus ke ≥ 2 baris
        assert xs_ok         # tidak ada chip keluar batas lebar
        # heightForWidth konsisten dgn geometri nyata (ukur ulang test-only)
        assert lay.heightForWidth(240) >= max(
            b.geometry().bottom() for b in btns) + 1 - host.rect().y()
