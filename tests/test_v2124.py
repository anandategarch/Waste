"""test_v2124.py — regresi v2.12.4: sidebar & slicer dihapus + funnel di
SEMUA kolom + kalimat penjelas dihapus dari UI.

Permintaan user (3):
1. "tab filter di sebelah kiri semacam side bar hapus aja. hapus juga
   tombol filter di ui untuk undhide side bar" — sidebar filter kiri
   (app.py, v2.8.0) + aksi ☰ Filter DIHAPUS total; tabel memakai lebar
   penuh jendela. SlicerBar chip (v2.11.0) ikut dihapus (permintaan
   v2.12.3 "ganti slicer dgn filter header" — kini funnel satu-satunya).
2. "harusnya semua kolom punya filter" — SEMUA kolom tabel (Anomali,
   Hari, Follow Up, 6 halaman Banding Periode) ber-funnel:
   - Anomali/Hari: 5 kolom mapping = state GLOBAL ctx (antar-tab
     sinkron, KPI ikut); kolom LAIN = filter LOKAL tampilan (mask isin,
     memo per state — objek stabil → cache fit DataTable kena).
   - Follow Up/Banding: filter lokal (daftar ✓ / ekspor tak tersentuh).
   - Tombol '✕ Hapus Filter' (Anomali/Hari) = pengganti tombol sidebar:
     lepas SEMUA filter (global + lokal + skor) sekaligus.
3. Kalimat "💡 Bukti hari = ..." & sejenisnya DIHAPUS dari UI (semua
   tab); penjelasan istilah tetap di tooltip + Bantuan.

Infra test: conftest._dispose_orphan_widgets — widget sisa test
dihancurkan aman (close + deleteLater + processEvents) antar test;
diagnosa: cyclic gc menghapus widget yatim TEPIK saat Qt melukis tabel
test lain → heap rusak → Segfault (v2.12.3 lolos karena timing; bukan
perbaikan — kebetulan). Lihat docstring conftest.
"""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel

REPO = Path(__file__).resolve().parent.parent


def _qapp():
    app = QApplication.instance() or QApplication([])
    return app


# ============================================================
# Fixture
# ============================================================

def _df_bandung() -> pd.DataFrame:
    """4 baris: AYAM@R1 2 anomali (Handling/Cancel Nota) + 2 baris
    Normal (noise); TOTAL bervariasi utk funnel kolom numerik."""
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


def _ctx_dataset(df):
    from ui.state import AppContext
    ctx = AppContext({})
    ctx.set_dataset(df, {"key_akhir": 31})
    return ctx


# ============================================================
# [A] MainWindow — sidebar & tombol ☰ Filter dihapus
# ============================================================

class TestSidebarDihapus:
    def _win(self):
        _qapp()
        from ui.app import MainWindow
        return MainWindow()

    def test_tanpa_aksi_filter_dan_shortcut(self):
        win = self._win()
        try:
            from PySide6.QtGui import QAction
            texts = [a.text() for a in win.findChildren(QAction) if a.text()]
            assert not any("☰" in t for t in texts), (
                f"aksi ☰ Filter masih ada: {texts}")
            for attr in ("_act_filter", "_sidebar", "_split",
                         "_sidebar_sizes"):
                assert not hasattr(win, attr), f"{attr} masih ada"
        finally:
            win.close()

    def test_central_qtabwidget_lebar_penuh(self):
        from PySide6.QtWidgets import QSplitter, QTabWidget, QWidget
        win = self._win()
        try:
            win.resize(1280, 800)
            win.show()
            app = _qapp()
            app.processEvents()
            QWidget.grab(win)
            app.processEvents()
            assert isinstance(win.centralWidget(), QTabWidget)
            assert not win.findChildren(QSplitter), "splitter masih ada"
            # tabel makan lebar PENUH (dulu ±300px sidebar)
            assert win._tabs.width() >= win.width() - 12
        finally:
            win.close()

    def test_lima_tab_utuh(self):
        # v2.13.1: 5 → 6 tab (+ Scorecard Cabang setelah Hari Mencurigakan)
        win = self._win()
        try:
            labels = [win._tabs.tabText(i) for i in range(win._tabs.count())]
            assert labels == ["Anomali", "Follow Up", "Hari Mencurigakan",
                              "Scorecard Cabang", "Banding Periode",
                              "Pipeline"]
        finally:
            win.close()


# ============================================================
# [B] SlicerBar dihapus total; hint 💡 dihapus dari semua view
# ============================================================

class TestSlicerDanHintDihapus:
    def test_kelas_slicerbar_tak_ada(self):
        import ui.widgets as W
        assert not hasattr(W, "SlicerBar"), (
            "kelas SlicerBar masih ada di widgets.py")
        assert not hasattr(W, "FlowLayout"), (
            "kelas FlowLayout masih ada (hanya dipakai SlicerBar)")

    def test_view_tanpa_slicer_dan_hint(self):
        from ui.state import AppContext
        from ui.view_anomali import AnomaliView
        from ui.view_hari import HariView
        from ui.view_followup import FollowUpView
        app = _qapp()
        ctx = AppContext({})
        av, hv, fv = AnomaliView(ctx), HariView(ctx), FollowUpView(ctx)
        for view, nm in ((av, "Anomali"), (hv, "Hari"), (fv, "FollowUp")):
            assert not hasattr(view, "_slicer"), f"{nm}: _slicer masih ada"
            hints = [l.text() for l in view.findChildren(QLabel)
                     if "💡" in l.text()]
            assert not hints, f"{nm}: hint 💡 masih ada: {hints}"

    def test_hint_dihapus_periode(self):
        from ui.state import AppContext
        from ui.view_periode import PeriodeView
        app = _qapp()
        pv = PeriodeView(AppContext({}))
        hints = [l.text() for l in pv.findChildren(QLabel)
                 if "💡" in l.text()]
        assert not hints, f"Periode: hint 💡 masih ada: {hints}"

    def test_hint_bukti_hari_dihapus_dari_view_hari(self):
        """Kalimat persis yang diminta user hilang: konstanta _HINT_BASE
        & atribut _hint tak ada lagi (statis maupun dinamis)."""
        import ui.view_hari as vh
        assert not hasattr(vh, "_HINT_BASE"), (
            "konstanta _HINT_BASE masih ada")
        from ui.state import AppContext
        app = _qapp()
        view = vh.HariView(AppContext({}))
        assert not hasattr(view, "_hint"), (
            "atribut _hint masih ada (hint belum dihapus)")


# ============================================================
# [C] Funnel SEMUA kolom — level widget (DataTable/FilterHeader)
# ============================================================

class TestFunnelSemuaKolomWidget:
    def _table(self):
        from ui.widgets import DataTable
        t = DataTable()
        t.set_dataframe(_df_bandung())
        return t

    def test_mode_all_cols_flag_dan_default(self):
        t = self._table()
        assert t._hf_all is False and t._hf_cols == {}
        t.setup_header_filters({"JENIS": "jenis"}, None, None,
                               all_cols=True, skip=("TOTAL",))
        assert t._hf_all is True
        assert t._hf_skip == {"TOTAL"}
        assert t._hf_has("JENIS")          # mapping menang
        assert t._hf_has("NAMA RESTO")     # all_cols: kolom lain
        assert not t._hf_has("TOTAL")      # di-skip

    def test_hit_funnel_kini_semua_kolom(self):
        """Klik area funnel kolom NON-mapping dikenali (v2.12.3: None)."""
        from PySide6.QtCore import QPointF
        t = self._table()
        t.setup_header_filters(None, lambda *a: None, lambda c: None,
                               all_cols=True)
        hdr = t.horizontalHeader()
        app = _qapp()
        app.processEvents()
        df_cols = list(t.model().dataframe.columns)
        logical = df_cols.index("TOTAL")  # kolom numerik non-mapping
        x0 = hdr.sectionViewportPosition(logical)
        w = hdr.sectionSize(logical)
        assert w >= 60, "kolom terlalu sempit utk area funnel"
        assert hdr._hit_funnel(QPointF(x0 + w - 22, hdr.height() / 2)) \
            == logical

    def test_kolom_check_tidak_ber_funnel(self):
        from waste_anomaly.followup import CHECK_COL
        from ui.widgets import DataTable
        t = DataTable()
        df = _df_bandung()
        df.insert(0, CHECK_COL, [True] * len(df))
        t.set_dataframe(df)
        t.setup_header_filters(None, lambda *a: None, lambda c: None,
                               all_cols=True, skip=(CHECK_COL,))
        assert not t._hf_has(CHECK_COL)

    def test_menu_funnel_kolom_numerik_bisa_dibuka(self):
        """Menu nilai kolom numerik (TOTAL) dibangun dari value_counts —
        nilai mentah round-trip (UserRole) utk isin."""
        t = self._table()
        t.setup_header_filters(None, lambda *a: None, lambda c: None,
                               all_cols=True)
        hdr = t.horizontalHeader()
        app = _qapp()
        df_cols = list(t.model().dataframe.columns)
        hdr._open_menu(df_cols.index("TOTAL"))
        app.processEvents()
        menu = hdr._menu
        assert menu is not None
        texts = [menu._lw.item(i).text() for i in range(menu._lw.count())]
        assert any("100" in x for x in texts), f"nilai TOTAL tak tampil: {texts}"
        # tombol sort tetap ada
        assert menu._lw.count() > 0


# ============================================================
# [D] AnomaliView — funnel global (mapping) vs LOKAL (kolom lain)
# ============================================================

class TestAnomaliFunnelLokal:
    def _view(self):
        from ui.view_anomali import AnomaliView
        app = _qapp()
        ctx = _ctx_dataset(_df_bandung())
        view = AnomaliView(ctx)
        view.show()
        view.refresh()
        app.processEvents()
        return view, ctx

    def test_semua_kolom_tampak_ber_funnel(self):
        view, _ = self._view()
        hdr = view._table.horizontalHeader()
        t = view._table
        m = t.model()
        app = _qapp()
        app.processEvents()
        vis = [str(m.headerData(c, Qt.Orientation.Horizontal))
               for c in range(m.columnCount())
               if not t.isColumnHidden(c) and str(
                   m.headerData(c, Qt.Orientation.Horizontal)) != "✓"]
        for name in vis:
            assert t._hf_has(name), (
                f"kolom tampak '{name}' tanpa funnel (harusnya semua)")
        # kolom ✓ TIDAK ber-funnel (identitas)
        assert not t._hf_has("✓")

    def test_funnel_kolom_numerik_lokal(self):
        """TOTAL (non-mapping) → mask isin lokal: tabel menyusut, state
        ctx TIDAK tersentuh (KPI/global tetap), daftar follow-up utuh."""
        view, ctx = self._view()
        app = _qapp()
        assert view._table.model().rowCount() == 2  # 2 anomali AYAM
        view._on_header_filter("TOTAL", "TOTAL", [100.0])
        app.processEvents()
        m = view._table.model()
        assert m.rowCount() == 1
        assert float(m.record(0)["TOTAL"]) == 100.0
        # state global tak tersentuh
        assert not any(ctx.active_filters.values()), (
            "filter lokal menulis ke state ctx (harusnya tampilan saja)")
        assert view._hf_state("TOTAL") == [100.0]
        # lepas (None) → kembali 2
        view._on_header_filter("TOTAL", "TOTAL", None)
        app.processEvents()
        assert view._table.model().rowCount() == 2

    def test_mask_memo_objek_stabil(self):
        """A→B→A: objek hasil mask A dipakai ulang (kunci cache fit)."""
        view, _ = self._view()
        app = _qapp()
        view._on_header_filter("TOTAL", "TOTAL", [100.0])
        app.processEvents()
        a1 = view._table._src_df
        view._on_header_filter("TOTAL", "TOTAL", [40.0])
        app.processEvents()
        b = view._table._src_df
        assert b is not a1
        view._on_header_filter("TOTAL", "TOTAL", [100.0])
        app.processEvents()
        a2 = view._table._src_df
        assert a2 is a1, "objek mask A harus dipakai ulang (LRU memo)"

    def test_centang_yang_tampil_hanya_yang_tampil(self):
        """Mask lokal ikut menyempitkan '☑ Centang yang tampil'."""
        from waste_anomaly.followup import fingerprint_series
        view, ctx = self._view()
        app = _qapp()
        df = ctx.anomali_df()
        fps = fingerprint_series(df).astype(str).tolist()
        view._on_header_filter("TOTAL", "TOTAL", [100.0])
        app.processEvents()
        view._on_check_all()
        app.processEvents()
        assert ctx.followup_keys == [f for f, t in
                                     zip(fps, df["TOTAL"].tolist()) if t == 100.0]

    def test_tombol_hapus_filter(self):
        """✕ Hapus Filter: lepas global + lokal + skor sekaligus."""
        view, ctx = self._view()
        app = _qapp()
        view._on_header_filter("TOTAL", "TOTAL", [100.0])   # lokal
        app.processEvents()
        ctx.set_filter("jenis", ["WASTE"])                    # global
        app.processEvents()
        view._spin_score.setValue(0)
        view._on_clear_filters()
        app.processEvents()
        assert not view._hfilters
        assert not any(ctx.active_filters.values())
        assert view._table.model().rowCount() == 2
        assert view._spin_score.value() == 0

    def test_dataset_baru_reset_filter_lokal(self):
        view, ctx = self._view()
        app = _qapp()
        view._on_header_filter("TOTAL", "TOTAL", [100.0])
        app.processEvents()
        assert view._hfilters
        ctx.set_dataset(_df_bandung(), {"key_akhir": 31})  # re-run
        app.processEvents()
        assert not view._hfilters, (
            "dataset baru harus mereset funnel lokal")


# ============================================================
# [E] HariView — funnel lokal + KPI mengikuti tabel
# ============================================================

class TestHariFunnelLokal:
    def _view(self):
        from ui.view_hari import HariView
        app = _qapp()
        ctx = _ctx_dataset(_df_bandung())
        view = HariView(ctx)
        view.show()
        view.refresh()
        app.processEvents()
        return view, ctx

    def test_semua_kolom_tampak_ber_funnel(self):
        view, _ = self._view()
        t = view._table
        m = t.model()
        app = _qapp()
        # v2.13.5: kolom ✓ follow-up kini juga tampil di tabel Hari —
        # SENGAJA tanpa funnel (kolom aksi centang, pola AnomaliView:
        # skip=(CHECK_COL, FP_COL)).
        from waste_anomaly.followup import CHECK_COL
        vis = [str(m.headerData(c, Qt.Orientation.Horizontal))
               for c in range(m.columnCount())
               if not t.isColumnHidden(c)]
        assert CHECK_COL in vis, "kolom ✓ follow-up harus tampil (v2.13.5)"
        for name in vis:
            if name == CHECK_COL:
                assert not t._hf_has(name), (
                    "kolom ✓ = aksi centang, bukan filter")
                continue
            assert t._hf_has(name), f"kolom '{name}' tanpa funnel"
        assert not hasattr(view, "_hint")

    def test_funnel_lokal_rasio_kolom(self):
        view, ctx = self._view()
        app = _qapp()
        n0 = view._table.model().rowCount()
        view._on_header_filter("HARI TERSANGKA", "HARI TERSANGKA", [5])
        app.processEvents()
        assert view._hfilters == {"HARI TERSANGKA": [5]}
        # state global tak tersentuh
        assert not any(ctx.active_filters.values())
        # lepas
        view._on_header_filter("HARI TERSANGKA", "HARI TERSANGKA", None)
        app.processEvents()
        assert view._table.model().rowCount() == n0

    def test_kolom_mapping_tetap_global(self):
        """KETERANGAN (mapping) → ctx (sinkron dgn tab Anomali)."""
        view, ctx = self._view()
        app = _qapp()
        view._on_header_filter("KETERANGAN", "keterangan", ["Handling"])
        app.processEvents()
        assert ctx.active_filters["keterangan"] == ["Handling"]
        assert view._hfilters == {}, (
            "kolom mapping tidak boleh masuk filter lokal")


# ============================================================
# [F] Follow Up — funnel SEMUA kolom (termasuk hari 1-31)
# ============================================================

class TestFollowUpFunnelSemua:
    def _view(self):
        from ui.view_followup import FollowUpView
        from waste_anomaly.followup import fingerprint_series
        app = _qapp()
        df = _df_bandung()
        ctx = _ctx_dataset(df)
        fps = fingerprint_series(df).astype(str).tolist()
        ctx.add_followup_many(fps[:2])
        app.processEvents()
        fv = FollowUpView(ctx)
        fv.show()
        fv.refresh()
        app.processEvents()
        return fv, ctx, fps

    def test_kolom_hari_ber_funnel(self):
        fv, _, _ = self._view()
        t = fv._table
        assert t._hf_all is True
        assert t._hf_has("1") and t._hf_has("31"), (
            "kolom hari 1-31 harus punya funnel")

    def test_filter_kolom_hari_lokal(self):
        """Filter hari '5' (nilai > 0) → hanya tampilan; daftar utuh."""
        fv, ctx, fps = self._view()
        app = _qapp()
        fv._on_header_filter("5", "5", [100.0, 40.0])
        app.processEvents()
        m = fv._table.model()
        assert m.rowCount() == 2
        assert len(ctx.followup_keys) == 2  # daftar tak tersentuh
        assert len(fv._rows) == 2            # bahan ekspor tak tersentuh
        # lepas
        fv._on_header_filter("5", "5", None)
        app.processEvents()
        assert fv._table.model().rowCount() == 2


# ============================================================
# [G] PeriodeView — funnel lokal per halaman
# ============================================================

def _wb_bulan2124(tmp_path: Path, name: str = "REKAP MENTAH JULI 2026.xlsx") -> Path:
    """Workbook bulan sintetis (pola test_v2122._wb_bulan)."""
    rows = []

    def _row(jenis, ket, day24, base):
        data = {str(d): float(base) for d in range(1, 32)}
        data["24"] = float(day24)
        rows.append({
            "SOURCE DATA": "WASTE BAHAN dan PACKAGING", "JENIS": jenis,
            "KETERANGAN": ket, "NAMA BARANG": "MIE (V.20)",
            "NAMA RESTO": "1042.KWGGAL", "SATUAN": "PCS",
            **data, "TOTAL": float(sum(data.values())),
        })

    _row("WASTE", "Handling", 100, 2.0)
    _row("WASTE", "Cancel Nota", 94, 0.0)
    out = tmp_path / name
    pd.DataFrame(rows).to_excel(out, sheet_name="REKAP MENTAH", index=False)
    return out


def _df_a2124() -> pd.DataFrame:
    """Dataset bulan berjalan (A) — 2 baris WASTE (pola v2122)."""
    rows = []

    def _row(jenis, ket, day24, base):
        data = {str(d): float(base) for d in range(1, 32)}
        data["24"] = float(day24)
        rows.append({
            "SOURCE DATA": "WASTE BAHAN dan PACKAGING", "JENIS": jenis,
            "KETERANGAN": ket, "NAMA BARANG": "MIE (V.20)",
            "NAMA RESTO": "1042.KWGGAL", "SATUAN": "PCS",
            **data, "TOTAL": float(sum(data.values())),
        })

    _row("WASTE", "Handling", 150.0, 2.0)
    _row("WASTE", "Cancel Nota", 94.0, 0.0)
    return pd.DataFrame(rows)


def _armed_periode(tmp_path, monkeypatch):
    """View + dataset A + 1 file pembanding termuat + render hasil
    (pola _armed_view test_v2122 — worker riil + _refresh_result)."""
    import time
    from waste_anomaly import period_history as ph
    from ui.state import AppContext
    from ui.view_periode import PeriodeView
    app = _qapp()
    store = tmp_path / "history_files.json"
    monkeypatch.setattr(ph, "history_store_path", lambda: store)
    ph.save_history_entries(
        [{"path": str(_wb_bulan2124(tmp_path)), "label": None}], store)
    ctx = AppContext({})
    view = PeriodeView(ctx)
    t0 = time.perf_counter()
    while view._running and time.perf_counter() - t0 < 30.0:
        app.processEvents()
        time.sleep(0.01)
    ctx.set_dataset(_df_a2124(), {"key_akhir": 31})
    app.processEvents()
    view._refresh_result()
    app.processEvents()
    return view, ctx, app


class TestPeriodeFunnelHalaman:
    def test_semua_halaman_ber_funnel(self, tmp_path, monkeypatch):
        view, _, _ = _armed_periode(tmp_path, monkeypatch)
        for key, table in view._tables.items():
            assert table._hf_all is True, f"halaman {key} tanpa all_cols"

    def test_bahan_halaman_disimpan(self, tmp_path, monkeypatch):
        view, _, _ = _armed_periode(tmp_path, monkeypatch)
        for key in view._tables:
            assert key in view._page_src, (
                f"bahan halaman {key} tak tersimpan")
            assert view._page_src[key] is not None

    def test_filter_lokal_halaman_items(self, tmp_path, monkeypatch):
        view, _, app = _armed_periode(tmp_path, monkeypatch)
        t = view._tables["items"]
        m = t.model()
        df = m.dataframe
        assert df is not None and len(df) > 0
        # kolom JENIS: filter satu nilai → baris menyusut + konten murni
        uniq = [v for v in df["JENIS"].dropna().unique()]
        assert len(uniq) >= 1
        n0 = m.rowCount()
        if len(uniq) >= 2:
            view._on_page_filter("items", "JENIS", [str(uniq[0])])
            app.processEvents()
            m2 = view._tables["items"].model()
            assert m2.rowCount() < n0, "mask funnel halaman tak bekerja"
            assert all(str(r["JENIS"]) == str(uniq[0])
                       for r in (m2.record(i) for i in range(m2.rowCount())))
            assert view._pf_state("items", "JENIS") == [str(uniq[0])]
            # lepas → pulih utuh
            view._on_page_filter("items", "JENIS", None)
            app.processEvents()
            assert view._tables["items"].model().rowCount() == n0
        else:
            # satu nilai: state tetap tercatat + tabel tetap tampil
            view._on_page_filter("items", "JENIS", [str(uniq[0])])
            app.processEvents()
            assert view._pf_state("items", "JENIS") == [str(uniq[0])]
            view._on_page_filter("items", "JENIS", None)

    def test_state_funnel_halaman(self, tmp_path, monkeypatch):
        view, _, _ = _armed_periode(tmp_path, monkeypatch)
        assert view._pf_state("summary", "Metrik") is None
        view._on_page_filter("summary", "Metrik", ["x"])
        assert view._pf_state("summary", "Metrik") == ["x"]
        view._on_page_filter("summary", "Metrik", None)
        assert view._pf_state("summary", "Metrik") is None


# ============================================================
# [H] Kebersihan UI — tidak ada kalimat penjelas statis di semua view
# ============================================================

class TestUiBersihTanpaKalimatPenjelas:
    def _all_views(self):
        from ui.state import AppContext
        from ui.view_anomali import AnomaliView
        from ui.view_hari import HariView
        from ui.view_followup import FollowUpView
        from ui.view_periode import PeriodeView
        ctx = _ctx_dataset(_df_bandung())
        return [AnomaliView(ctx), HariView(ctx), FollowUpView(ctx),
                PeriodeView(ctx)]

    def test_tidak_ada_label_bulb(self):
        app = _qapp()
        for view in self._all_views():
            bulbs = [l.text() for l in view.findChildren(QLabel)
                     if "💡" in l.text()]
            assert not bulbs, (
                f"{type(view).__name__}: kalimat 💡 masih ada: {bulbs}")

    def test_popup_fullscreen_tanpa_hint(self):
        """Dialog layar penuh Anomali/Hari: hint dihapus, tombol kembali
        + judul (Esc = kembali) tetap ada."""
        from ui.state import AppContext
        from ui.view_anomali import AnomaliView
        app = _qapp()
        ctx = _ctx_dataset(_df_bandung())
        view = AnomaliView(ctx)
        view.show()
        view.refresh()
        app.processEvents()
        view._on_fullscreen()
        app.processEvents()
        dlg = view._fs_dlg
        assert dlg is not None
        bulbs = [l.text() for l in dlg.findChildren(QLabel)
                 if "💡" in l.text()]
        assert not bulbs, f"hint dialog layar penuh masih ada: {bulbs}"
        assert "Esc" in dlg.windowTitle(), (
            "judul dialog harus menyebut Esc (info kembali tetap ada)")
        btns = [b.text() for b in dlg.findChildren(
            __import__("PySide6.QtWidgets", fromlist=["QPushButton"])
            .QPushButton)]
        assert any("Kembali" in t for t in btns), (
            "tombol kembali hilang dari dialog layar penuh")
