"""test_v21310.py — regresi v2.13.10 (Gelombang 1 deep audit:
KEJUJURAN INTERAKSI INTI — 4 P1 + P2 terkait + V1 visual).

Sumber temuan: /home/z/my-project/audit-ui-waste.md seksi 3 (P1) +
V1 (geometri pop-up). Re-eksekusi WASTE-G1R (commit asli 7b09973 hilang
karena environment reset sebelum push — spesifikasi dari worklog
WASTE-G1 direplikasi setia).

Cakupan (5 klaster fix, 11 test):
[A1]×2  '✕ Hapus Filter' jujur — combo 'Kategori PERUBAHAN' ikut
        direset PRA-render (tooltip menjanjikan SEMUA; dulu combo
        tetap aktif → tabel diam-diah subset).
[A2]     Dataset baru me-reset combo kategori (asimetri vs HariView).
[B1]     ✓ banding konsisten pasca ganti/lepas funnel — _page_mask
        SELALU re-komputasi CHECK_COL dari ctx.followup_set()+__FPS
        (dulu: hanya df model yang dimutasi, sumber basi).
[B12]    Jalur mutasi ✓ dgn funnel aktif tanpa SettingWithCopyWarning.
[B2]     Semua file pembanding dihapus → baseline None DUA LAPIS
        (ctx + effective) + baseline_changed ter-emit.
[B5]×2   Baseline usang (bulan terhapus / Tipikal pasca set_history
        baru) jatuh ke fallback; dict suntetis tanpa 'path' dipercaya.
[D1]×2   Shortcut F1 'Bantuan' benar-benar terpasang (QTest keyClick
        F1 → dialog terbuka; QAction.shortcuts() == F1).
[V1]     CTA pop-up (☑ Masuk Follow Up + drill + pembuka kolom) di
        footer AKSI STICKY di luar QScrollArea — terlihat tanpa gulir.

Headless: QT_QPA_PLATFORM=offscreen sebelum PySide6 (konvensi suite).
"""
from __future__ import annotations

import os
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd

REPO = Path(__file__).resolve().parent.parent


def _qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def Qt_ItemDataRole():
    from PySide6.QtCore import Qt
    return Qt.ItemDataRole


# ============================================================
# Fixture
# ============================================================

def _df_ayam() -> pd.DataFrame:
    """Dataset bulan berjalan: AYAM@R1 2 baris anomali (Handling 100 /
    Cancel Nota 40 — keduanya melonjak vs bulan lalu) + 2 baris Normal
    (BEBEK + noise AYAM; pola test_v2123._df_bandung)."""
    def _row(jenis, ket, barang, resto, total, status, day=5):
        data = {str(d): 0.0 for d in range(1, 32)}
        data["5"] = float(day)
        return {
            "SOURCE DATA": "WASTE BAHAN DAN PACKAGING", "JENIS": jenis,
            "KETERANGAN": ket, "NAMA BARANG": barang, "NAMA RESTO": resto,
            "SATUAN": "PCS", "ANOMALY STATUS": status,
            **data, "TOTAL": float(total),
        }

    return pd.DataFrame([
        _row("WASTE", "Handling", "AYAM", "R1", 100.0, "Perlu Review", 100),
        _row("WASTE", "Cancel Nota", "AYAM", "R1", 40.0, "Prioritas Tinggi", 40),
        _row("WASTE", "Over Stock", "AYAM", "R1", 0.0, "Normal", 0),
        _row("WASTE", "Handling", "BEBEK", "R1", 0.0, "Normal", 0),
    ]).assign(**{
        "HARI TERSANGKA": [5, 5, 5, 5],
        "HARI MAX": [5, 5, 5, 5],
    })


def _wb_bulan_lalu(tmp_path: Path) -> Path:
    """Workbook bulan pembanding JULI: AYAM@R1 (Handling 80 + Cancel
    Nota 10) → bulan berjalan melonjak (Naik Sedang / Naik Tinggi)."""
    rows = []

    def _row(ket, day5):
        data = {str(d): 0.0 for d in range(1, 32)}
        data["5"] = float(day5)
        rows.append({
            "SOURCE DATA": "WASTE BAHAN DAN PACKAGING", "JENIS": "WASTE",
            "KETERANGAN": ket, "NAMA BARANG": "AYAM",
            "NAMA RESTO": "R1", "SATUAN": "PCS",
            **data, "TOTAL": float(sum(data.values())),
        })

    _row("Handling", 80)
    _row("Cancel Nota", 10)
    out = tmp_path / "REKAP MENTAH JULI 2026.xlsx"
    pd.DataFrame(rows).to_excel(out, sheet_name="REKAP MENTAH", index=False)
    return out


def _ctx_dataset(df):
    from ui.state import AppContext
    ctx = AppContext({})
    ctx.set_dataset(df, {"key_akhir": 31})
    return ctx


def _view_anomali(tmp_path):
    """AnomaliView TAMPIL + dataset AYAM + baseline Juli termuat →
    combo 'Kategori PERUBAHAN' AKTIF (pattern test_v2102: set_history
    bulan riil → banding_baseline_effective bulan terbaru)."""
    from waste_anomaly.period_history import load_history_file
    from ui.view_anomali import AnomaliView
    app = _qapp()
    ctx = _ctx_dataset(_df_ayam())
    view = AnomaliView(ctx)
    view.show()
    m = load_history_file(_wb_bulan_lalu(tmp_path))
    ctx.set_history([m], None)
    app.processEvents()
    view.refresh()
    app.processEvents()
    return view, ctx, app


def _view_periode(tmp_path, monkeypatch):
    """PeriodeView + file pembanding termuat (worker SUNGGUHAN) +
    dataset AYAM + halaman FU ter-render (pola test_v2123._view)."""
    from waste_anomaly import period_history as ph
    from ui.view_periode import PeriodeView
    app = _qapp()
    store = tmp_path / "history_files.json"
    monkeypatch.setattr(ph, "history_store_path", lambda: store)
    wb = _wb_bulan_lalu(tmp_path)
    ph.save_history_entries([{"path": str(wb), "label": None}], store)
    ctx = _ctx_dataset(_df_ayam())
    view = PeriodeView(ctx)
    view._start_worker()
    t0 = time.perf_counter()
    while view._running and time.perf_counter() - t0 < 30:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()
    view._refresh_result()
    app.processEvents()
    return view, ctx, app


# ============================================================
# [A1] '✕ Hapus Filter' jujur — combo kategori ikut direset
# ============================================================

class TestA1HapusFilterJujur:
    def test_clear_dengan_funnel_dan_combo_semua_baris_kembali(self, tmp_path):
        """A1: funnel LOKAL + combo kategori aktif → tombol ✕ Hapus
        Filter → combo kembali 'Semua' (index 0) + SEMUA baris tampil.
        Dulu: _on_clear_filters tak menyentuh combo → _refresh_table_impl
        re-apply currentData() → tabel tetap terfilter kategori padahal
        tooltip menjanjikan 'Hapus SEMUA filter yang sedang aktif'.
        v2.19.0 — tampilan GRUP: 2 baris AYAM anomali → 1 grup (TOTAL=140);
        funnel TOTAL=[140] = 1 grup tampil; TOTAL=[100] = 0 grup."""
        view, ctx, app = _view_anomali(tmp_path)
        n_all = view._table.model().rowCount()
        assert n_all == 3, "fixture: 2 grup (AYAM + BEBEK) + 1 pemisah (Normal ikut, v2.19.8)"
        assert view._cb_change.isEnabled(), "baseline aktif → combo aktif"
        # combo kategori: 'Naik Tinggi' = grup AYAM (+56% vs 90 bulan lalu)
        idx = [i for i in range(view._cb_change.count())
               if view._cb_change.itemData(i) == "Naik Tinggi"][0]
        view._cb_change.setCurrentIndex(idx)   # view tampil → sinyal render
        app.processEvents()
        assert view._table.model().rowCount() == 1
        # funnel LOKAL TOTAL=100 → 0 grup (TOTAL grup=140, bukan 100)
        view._on_header_filter("TOTAL", "TOTAL", [100.0])
        app.processEvents()
        assert view._table.model().rowCount() == 0
        # CLEAR: janji tooltip diuji — SEMUA (funnel + combo)
        view._on_clear_filters()
        app.processEvents()
        assert view._cb_change.currentIndex() == 0, (
            "combo kategori harus kembali 'Semua' (tooltip menipu — audit A1)")
        assert view._cb_change.currentData() is None
        assert view._table.model().rowCount() == n_all, (
            "semua baris harus tampil kembali setelah Hapus SEMUA filter")

    def test_clear_cabang_tanpa_filter_global_tetap_reset_combo(self, tmp_path):
        """A1 (cabang kedua _on_clear_filters): tanpa filter global/skor
        → render LANGSUNG dari tombol (bukan lewat filters_changed) —
        combo kategori tetap harus direset PRA-render (blok sinyal mencegah
        render ganda; jalur had_global=False).
        v2.19.0 — tampilan GRUP: 1 grup AYAM (TOTAL=140) di dataset ini."""
        view, _, app = _view_anomali(tmp_path)
        idx = [i for i in range(view._cb_change.count())
               if view._cb_change.itemData(i) == "Naik Tinggi"][0]
        view._cb_change.setCurrentIndex(idx)
        app.processEvents()
        assert view._table.model().rowCount() == 1
        view._on_clear_filters()  # had_global False → _refresh_table langsung
        app.processEvents()
        assert view._cb_change.currentIndex() == 0
        assert view._table.model().rowCount() == 3  # 2 grup + pemisah (Normal ikut)


# ============================================================
# [A2] Dataset baru me-reset combo kategori
# ============================================================

class TestA2DatasetBaru:
    def test_dataset_baru_reset_kategori(self, tmp_path):
        """A2: combo kategori aktif saat dataset baru datang → refresh
        me-reset ke 'Semua'. Dulu: combo mewarisi kategori run lama →
        tabel diam-diah hanya menampilkan subset (HariView kembar-nya
        justru me-reset _cb_mode — asimetri).
        v2.19.0 — tampilan GRUP: 1 grup AYAM (TOTAL=140) di dataset ini."""
        view, ctx, app = _view_anomali(tmp_path)
        idx = [i for i in range(view._cb_change.count())
               if view._cb_change.itemData(i) == "Naik Tinggi"][0]
        view._cb_change.setCurrentIndex(idx)
        app.processEvents()
        assert view._cb_change.currentIndex() == idx
        # dataset baru (data_ready → refresh — view tampil)
        ctx.set_dataset(_df_ayam(), {"key_akhir": 31})
        app.processEvents()
        view.refresh()
        app.processEvents()
        assert view._cb_change.currentIndex() == 0, (
            "dataset baru harus me-reset combo kategori (audit A2)")
        assert view._table.model().rowCount() == 3, (
            "2 grup (AYAM + BEBEK) + pemisah tampil setelah reset combo (Normal ikut, v2.19.8)")


# ============================================================
# [B1+B12] ✓ banding konsisten pasca ganti/lepas funnel
# ============================================================

class TestB1B12CheckBanding:
    def test_check_konsisten_pasca_lepas_funnel(self, tmp_path, monkeypatch):
        """B1: centang ✓ banding → lepas centangan DARI STATE (toggle di
        tab lain) → ganti/lepas funnel → re-mask dari _page_src HARUS
        jujur. Dulu: handler hanya memutasi df model (salinan mask),
        sumber tak diupdate → ✓ tampil TERCENTANG padahal baris sudah
        dikeluarkan (kebalikan kebenaran — audit B1). Semua halaman FU
        dicek konsisten dgn state."""
        from waste_anomaly.followup import CHECK_COL, fingerprint_series
        from ui.view_periode import _FPS_COL
        view, ctx, app = self._view(tmp_path, monkeypatch)
        fps = fingerprint_series(_df_ayam()).astype(str).tolist()
        # 1) centang AYAM TANPA funnel → 2 baris anomali masuk
        mi = view._tables["items"].model()
        rows = {str(mi.record(r).get("NAMA BARANG")): r
                for r in range(mi.rowCount())}
        mi.setData(mi.index(rows["AYAM"], 0), True,
                   Qt_ItemDataRole().CheckStateRole)
        app.processEvents()
        assert set(ctx.followup_keys) == set(fps[:2])
        # 2) funnel aktif (AYAM tersembunyi) → lepas centangan via STATE
        view._on_page_filter("items", "NAMA BARANG", ["BEBEK"])
        app.processEvents()
        ctx.remove_followup_many(fps[:2])   # broadcast (jalur tab Anomali)
        app.processEvents()
        # 3) lepas funnel → re-mask dari sumber — harus jujur (kosong)
        view._on_page_filter("items", "NAMA BARANG", None)
        app.processEvents()
        mdf = view._tables["items"].model().dataframe
        r_ayam = [i for i in range(len(mdf))
                  if str(mdf.iloc[i].get("NAMA BARANG")) == "AYAM"][0]
        assert not bool(mdf.iloc[r_ayam][CHECK_COL]), (
            "✓ banding tampil TERCENTANG padahal baris sudah dikeluarkan "
            "(sumber _page_src basi — audit B1)")
        # 4) SEMUA halaman FU: ✓ == keanggotaan state sekarang
        fset = ctx.followup_set()
        assert not fset
        for page in ("branch", "items", "new_items"):
            m2 = view._tables[page].model().dataframe
            if m2 is None or not len(m2) or CHECK_COL not in m2.columns:
                continue
            for i in range(len(m2)):
                fs = m2.iloc[i].get(_FPS_COL) or []
                assert bool(m2.iloc[i][CHECK_COL]) == (
                    bool(fs) and all(f in fset for f in fs)), (
                    f"halaman {page} baris {i}: ✓ tak konsisten dgn state")

    def test_b12_tanpa_settingwithcopywarning(self, tmp_path, monkeypatch):
        """B12: centang ✓ di halaman dgn funnel AKTIF — jalur mutasi kolom
        model (salinan mask) + re-mask — tanpa SettingWithCopyWarning
        (dulu: df[m] slice ber-_is_copy → assignment kolom memicu warning
        pandas; rapuh menuju CoW)."""
        import warnings
        from waste_anomaly.followup import fingerprint_series
        view, ctx, app = self._view(tmp_path, monkeypatch)
        fps = fingerprint_series(_df_ayam()).astype(str).tolist()
        view._on_page_filter("items", "NAMA BARANG", ["AYAM"])
        app.processEvents()
        with warnings.catch_warnings():
            warnings.simplefilter("error", pd.errors.SettingWithCopyWarning)
            mi = view._tables["items"].model()
            rows = {str(mi.record(r).get("NAMA BARANG")): r
                    for r in range(mi.rowCount())}
            mi.setData(mi.index(rows["AYAM"], 0), True,
                       Qt_ItemDataRole().CheckStateRole)  # → _on_followup_changed
            app.processEvents()
            view._on_page_filter("items", "NAMA BARANG", None)  # re-mask
            app.processEvents()
        assert set(ctx.followup_keys) == set(fps[:2])

    def _view(self, tmp_path, monkeypatch):
        return _view_periode(tmp_path, monkeypatch)


# ============================================================
# [B2] Baseline hantu — hapus semua pembanding
# ============================================================

class TestB2BaselineHantu:
    def test_hapus_semua_pembanding_baseline_none_dua_lapis(self, tmp_path,
                                                            monkeypatch):
        """B2: semua file pembanding dihapus → tabel jujur 'Belum ada
        file pembanding' + baseline dibersihkan DUA LAPIS: (1)
        ctx.banding_baseline = None via _clear_tables (emit
        baseline_changed — view pemakai render ulang), (2) fallback
        banding_baseline_effective() juga None. Dulu: baseline bulan
        terhapus tetap hidup → tab Anomali menghitung BULAN LALU vs
        bulan yang sudah tak ada (angka vs hantu)."""
        view, ctx, app = _view_periode(tmp_path, monkeypatch)
        assert view._ctx.banding_baseline is not None, (
            "premis: render hasil memasang baseline")
        hits = []
        ctx.baseline_changed.connect(lambda: hits.append(1))
        # hapus semua file (pola _on_delete: entri + cache + _finalize)
        view._entries = []
        view._loaded.clear()
        view._last_results.clear()
        view._finalize()
        app.processEvents()
        view._refresh_result()
        app.processEvents()
        # lapis 1 — combo/baseline ctx dibersihkan + signal ter-emit
        assert ctx.banding_baseline is None, (
            "_clear_tables harus set_banding_baseline(None) — audit B2")
        assert hits, "baseline_changed harus ter-emit (view Anomali ikut refresh)"
        # lapis 2 — fallback juga kosong (bulan terhapus tak dipakai lagi)
        assert ctx.banding_baseline_effective() is None
        assert "Belum ada file pembanding" in view._lbl_compare.text()


# ============================================================
# [B5] Baseline usang → fallback (validasi umur _baseline_alive)
# ============================================================

class TestB5BaselineUsang:
    def _ctx(self):
        _qapp()
        from ui.state import AppContext
        return AppContext({})

    def test_bulan_usang_jatuh_fallback_bulan_baru(self):
        """B5/B2: baseline bulan yang path-nya tak ada lagi di daftar
        bulan OK (file dihapus / daftar berganti) → DIABAIKAN, jatuh ke
        fallback bulan TERBARU — bukan bulan hantu. Dict suntetis TANPA
        'path' (fixture test lama) tetap DIPERCAYA (kompatibilitas 31+
        test v2.12.3/v2.10.2 yang menyuntik baseline langsung)."""
        ctx = self._ctx()
        agg = pd.DataFrame({"NAMA RESTO": ["R"], "NAMA BARANG": ["I"],
                            "TOTAL": [1.0]})
        m_lama = {"label": "Juli 2026", "path": "/lama/juli.xlsx", "agg": agg}
        m_baru = {"label": "Agustus 2026", "path": "/baru/agustus.xlsx",
                  "agg": agg}
        ctx.set_history([m_baru], None)
        ctx.set_banding_baseline(m_lama)  # pilihan combo run lama (usang)
        eff = ctx.banding_baseline_effective()
        assert eff is not m_lama, "bulan usang tak boleh dipakai (hantu)"
        assert eff is m_baru, "fallback = bulan TERBARU"
        # fixture sintetis tanpa 'path' → dipercaya apa adanya
        synth = {"label": "Juli 2026", "agg_detail": agg}
        ctx.set_banding_baseline(synth)
        assert ctx.banding_baseline_effective() is synth

    def test_tipikal_usang_jatuh_fallback(self):
        """B5: objek Tipikal usang (set_history baru membuat objek Tipikal
        baru — mis. saat view banding tersembunyi hanya menandai dirty)
        → baseline lama mati (identitas objek), jatuh ke Tipikal SAAT
        INI. Validasi identitas: 'agg' = DataFrame — dict-equality penuh
        akan crash (bool(DataFrame) truth-ambiguous), identitas objek
        aman."""
        ctx = self._ctx()
        agg = pd.DataFrame({"NAMA RESTO": ["R"], "NAMA BARANG": ["I"],
                            "TOTAL": [1.0]})
        m = {"label": "Juli 2026", "path": "/juli.xlsx", "agg": agg}
        typ_lama = {"label": "Tipikal", "path": "(gabungan lama)",
                    "months_count": 2, "agg": agg}
        typ_baru = {"label": "Tipikal", "path": "(gabungan baru)",
                    "months_count": 2, "agg": agg}
        ctx.set_history([m], typ_lama)
        ctx.set_banding_baseline(typ_lama)  # combo dulu memilih Tipikal
        assert ctx.banding_baseline_effective() is typ_lama
        # file bertambah saat view tersembunyi → set_history BARU
        ctx.set_history([m], typ_baru)
        eff = ctx.banding_baseline_effective()
        assert eff is not typ_lama, "objek Tipikal usang tak boleh dipakai"
        assert eff is typ_baru, "fallback = Tipikal SAAT INI"


# ============================================================
# [D1] Shortcut F1 'Bantuan'
# ============================================================

class TestD1ShortcutF1:
    def test_f1_membuka_dialog_bantuan(self):
        """D1: QTest keyClick F1 pada jendela utama → dialog Bantuan
        TERBUKA. Dulu: F1 didokumentasikan (README + banner .bat +
        Bantuan sendiri) tapi setShortcut tidak pernah terpasang —
        keyClick F1 tak membuka apa pun. Dialog modal ditangkap lewat
        QTimer.singleShot(0) → activeModalWidget() lalu di-accept
        (exec() modal akan memblokir test bila dibiarkan)."""
        from PySide6.QtCore import Qt, QTimer
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from ui.app import MainWindow
        app = _qapp()
        win = MainWindow()
        win.show()
        app.processEvents()
        seen = []

        def _snap_close():
            dlg = QApplication.activeModalWidget()
            if dlg is not None:
                seen.append(dlg.windowTitle())
                dlg.accept()

        QTimer.singleShot(0, _snap_close)
        QTest.keyClick(win, Qt.Key.Key_F1)
        app.processEvents()
        assert seen and "Bantuan" in seen[0], (
            "F1 harus membuka dialog Bantuan (audit D1: shortcut mati)")

    def test_shortcut_action_bantuan_f1(self):
        """D1: QAction '❓ Bantuan' memasang shortcut persis F1
        (QKeySequence.StandardKey.HelpContents — nested enum dgn 's')."""
        from PySide6.QtGui import QAction, QKeySequence
        from ui.app import MainWindow
        app = _qapp()
        win = MainWindow()
        acts = [a for a in win.findChildren(QAction)
                if "Bantuan" in a.text()]
        assert acts, "QAction Bantuan tak ditemukan di toolbar"
        for a in acts:
            sc = a.shortcuts()
            assert len(sc) == 1, "tepat satu shortcut (F1)"
            assert sc[0].matches(QKeySequence("F1")) == \
                QKeySequence.SequenceMatch.ExactMatch


# ============================================================
# [V1] CTA pop-up footer sticky
# ============================================================

class TestV1FooterSticky:
    def test_cta_footer_sticky(self):
        """V1: tombol aksi pop-up (☑ Masuk Follow Up + drill fokus +
        pembuka kolom lengkap) BUKAN anak konten gulir — footer AKSI
        STICKY di luar QScrollArea; geometri dalam batas dialog dan
        terlihat TANPA menggulir (audit V1: dulu y≈623-698 vs viewport
        578px — CTA di bawah lipatan)."""
        from PySide6.QtCore import QPoint
        from PySide6.QtWidgets import QPushButton
        from ui.state import AppContext
        from ui.view_anomali import DetailDialog
        app = _qapp()
        dlg = DetailDialog(AppContext({}))
        dlg.show()
        app.processEvents()
        rec = _df_ayam().iloc[0]
        dlg._panel.show_record(rec)
        app.processEvents()
        panel = dlg._panel
        # 1) footer DI LUAR area gulir (bukan anak konten/scroll)
        assert panel._actions.parentWidget() is panel
        assert panel._fu_btn is not None
        assert panel._fu_btn.parentWidget() is panel._actions, (
            "tombol follow-up harus anak footer sticky, bukan konten gulir")
        assert panel._more_btn is not None
        assert panel._more_btn.parentWidget() is panel._actions
        assert panel._fu_btn.parentWidget() is not panel._content
        # kolom lengkap TETAP di konten gulir (digulir saat dibuka)
        assert panel._full_box.parentWidget() is panel._content
        # 2) footer lengkap: judul seksi + follow-up + drill + pembuka
        texts = [b.text() for b in panel._actions.findChildren(QPushButton)]
        assert any("Masuk Follow Up" in t for t in texts)
        assert any("Fokus cabang" in t for t in texts)
        assert any("Fokus item" in t for t in texts)
        assert any("Tampilkan semua kolom data" in t for t in texts)
        labels = [l.text() for l in panel._actions.findChildren(
            __import__("PySide6.QtWidgets",
                       fromlist=["QLabel"]).QLabel)]
        assert any("Tindak lanjut & drill-down" in t for t in labels)
        # 3) geometri: CTA dalam batas dialog + TERLIHAT tanpa gulir
        fu = panel._fu_btn
        assert not fu.visibleRegion().isEmpty(), (
            "CTA harus terlihat tanpa menggulir (below-fold — audit V1)")
        pos = fu.mapTo(dlg, QPoint(0, 0))
        assert 0 <= pos.y() and pos.y() + fu.height() <= dlg.height(), (
            "CTA harus berada dalam batas dialog")


# ============================================================
# CATATAN VERSI: pin 2.13.10 dilakukan di 5 situs test LAMA (pola G1 —
# test_v2136 ×6 baris + test_v2102:716 + test_v2139:378 +
# test_v270_wave4:259), TIDAK di file ini, supaya jumlah test baru
# tepat 11 (942 + 11 = 953 — kontrak worklog WASTE-G1).
# ============================================================
