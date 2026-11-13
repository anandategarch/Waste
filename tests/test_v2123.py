"""test_v2123.py — regresi v2.12.3 (Opsi A + TOTAL BULAN LALU + tab Hari
+ filter header + redesain peta hari).

Cakupan (semua fitur sesi ini):
[A] Opsi A "1 item per resto" — peta ✓ banding HANYA baris anomali
    (ANOMALY STATUS ≠ Normal); baris tanpa anomali ditolak; lepas ✓
    membersihkan noise warisan v2.12.2; fallback tanpa kolom status.
[B] Follow Up TOTAL BULAN LALU — kolom BULAN LALU + PERUBAHAN % muncul
    bila baseline pembanding ada; alias judul 'TOTAL BULAN LALU';
    nilai join benar; tanpa baseline = tabel identik; history_ready
    menandai dirty.
[C] Tab Hari Mencurigakan — JENIS keluar dari narrow_hide; tombol ⤢
    (ciutkan KPI/judul/ctrl) & ⛶ (reparent + pulihkan index + guard).
[D] FilterHeader — funnel per kolom + menu (sort naik/turun, daftar
    nilai bercentang, cari, debounce live-apply); integrasi AnomaliView
    (ctx.set_filter → state global lintas-tab) + Follow Up (filter LOKAL:
    daftar & ekspor tak tersentuh).
[E] Peta hari pop-up — tanggal kecil + nilai TEBAL terpisah (dulu
    '13:1245' membingungkan — user kira '13' bagian nilai).
"""
from __future__ import annotations

import os
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd
import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QLabel, QApplication

REPO = Path(__file__).resolve().parent.parent


def _qapp():
    app = QApplication.instance() or QApplication([])
    return app


# ============================================================
# Fixture
# ============================================================

def _df_bandung() -> pd.DataFrame:
    """Dataset dgn kolom ANOMALY STATUS: item AYAM @R1 punya 2 baris
    anomali + 1 baris Normal (noise placeholder TOTAL=0); item BEBEK @R1
    HANYA baris Normal (→ ✓ harus ditolak)."""
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
        _row("WASTE", "Over Stock", "AYAM", "R1", 0.0, "Normal", 0),  # noise
        _row("WASTE", "Handling", "BEBEK", "R1", 0.0, "Normal", 0),   # noise
    ]).assign(**{
        "HARI TERSANGKA": [5, 5, 5, 5],
        "HARI MAX": [5, 5, 5, 5],
    })


def _ctx_dataset(df):
    from ui.state import AppContext
    ctx = AppContext({})
    ctx.set_dataset(df, {"key_akhir": 31})
    return ctx


def _baseline_dict() -> dict:
    return {
        "label": "Juli 2026",
        "key_akhir": 31,
        "agg_detail": pd.DataFrame({
            "NAMA RESTO": ["R1", "R1"],
            "NAMA BARANG": ["AYAM", "AYAM"],
            "JENIS": ["WASTE", "WASTE"],
            "KETERANGAN": ["Handling", "Cancel Nota"],
            "TOTAL": [80.0, 10.0],
        }),
    }


# ============================================================
# [A] Opsi A — ✓ banding hanya baris anomali
# ============================================================

class TestOpsiAPetaAnomali:
    def test_peta_fu_hanya_baris_anomali(self):
        _qapp()
        from waste_anomaly.followup import fingerprint_series
        df = _df_bandung()
        ctx = _ctx_dataset(df)
        from ui.view_periode import PeriodeView
        view = PeriodeView(ctx)
        maps = view._fu_maps()
        assert maps is not None
        item_map, _branch = maps
        fps = fingerprint_series(df).astype(str).tolist()
        fps_ayam = item_map.get(("WASTE", "R1", "AYAM"))
        # HANYA 2 baris anomali AYAM — baris Normal Over Stock TIDAK ikut.
        assert sorted(fps_ayam) == sorted(fps[:2])
        # Peta PENUH (utk lepas) memuat SEMUA 3 baris AYAM.
        assert sorted(view._fu_item_full[("WASTE", "R1", "AYAM")]) == \
            sorted(fps[:3])
        # BEBEK: tanpa anomali → peta centang KOSONG, peta penuh ada.
        assert view._fu_item.get(("WASTE", "R1", "BEBEK")) is None
        assert len(view._fu_item_full[("WASTE", "R1", "BEBEK")]) == 1

    def test_fallback_tanpa_kolom_status(self):
        """Fixture lama tanpa ANOMALY STATUS → perilaku v2.12.2 (semua
        baris) — 31 test v2.12.2 bergantung fallback ini."""
        _qapp()
        df = _df_bandung().drop(columns=["ANOMALY STATUS"])
        ctx = _ctx_dataset(df)
        from ui.view_periode import PeriodeView
        view = PeriodeView(ctx)
        item_map, _ = view._fu_maps()
        assert len(item_map[("WASTE", "R1", "AYAM")]) == 3


def _wb_pembanding(tmp_path: Path) -> Path:
    """Workbook bulan pembanding: AYAM@R1 WASTE (Handling+Cancel Nota)."""
    rows = []

    def _row(ket, day5, base):
        data = {str(d): float(base) for d in range(1, 32)}
        data["5"] = float(day5)
        rows.append({
            "SOURCE DATA": "WASTE BAHAN DAN PACKAGING", "JENIS": "WASTE",
            "KETERANGAN": ket, "NAMA BARANG": "AYAM",
            "NAMA RESTO": "R1", "SATUAN": "PCS",
            **data, "TOTAL": float(sum(data.values())),
        })

    _row("Handling", 80, 0.0)
    _row("Cancel Nota", 10, 0.0)
    out = tmp_path / "REKAP MENTAH JULI 2026.xlsx"
    pd.DataFrame(rows).to_excel(out, sheet_name="REKAP MENTAH", index=False)
    return out


class TestOpsiACentang:
    def _view(self, tmp_path, monkeypatch):
        """PeriodeView + file pembanding termuat (worker sungguhan) +
        dataset dgn ANOMALY STATUS + tabel items ter-render."""
        from waste_anomaly import period_history as ph
        from ui.view_periode import PeriodeView
        app = _qapp()
        store = tmp_path / "history_files.json"
        monkeypatch.setattr(ph, "history_store_path", lambda: store)
        wb = _wb_pembanding(tmp_path)
        ph.save_history_entries(
            [{"path": str(wb), "label": None}], store)
        ctx = _ctx_dataset(_df_bandung())
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

    def test_centang_hanya_tambah_anomali(self, tmp_path, monkeypatch):
        from waste_anomaly.followup import CHECK_COL, fingerprint_series
        view, ctx, app = self._view(tmp_path, monkeypatch)
        mi = view._tables["items"].model()
        df = _df_bandung()
        fps = fingerprint_series(df).astype(str).tolist()
        rows = {str(mi.record(r).get("NAMA BARANG")): r
                for r in range(mi.rowCount())}
        r_ayam = rows["AYAM"]
        assert mi.setData(mi.index(r_ayam, 0), True,
                          Qt.ItemDataRole.CheckStateRole)
        app.processEvents()
        # +2 baris ANOMALI saja — baris Normal (fps[2]) TIDAK masuk.
        assert set(ctx.followup_keys) == set(fps[:2])
        # ✓ frame banding membawa fps anomali (bukan penuh).
        rec = mi.record(r_ayam)
        assert sorted(rec.get("__FPS")) == sorted(fps[:2])

    def test_baris_tanpa_anomali_ditolak(self, tmp_path, monkeypatch):
        from waste_anomaly.followup import CHECK_COL
        view, ctx, app = self._view(tmp_path, monkeypatch)
        mi = view._tables["items"].model()
        rows = {str(mi.record(r).get("NAMA BARANG")): r
                for r in range(mi.rowCount())}
        r_bebek = rows["BEBEK"]
        assert mi.setData(mi.index(r_bebek, 0), True,
                          Qt.ItemDataRole.CheckStateRole)
        app.processEvents()
        # ditolak: centangan kembali False, state kosong.
        assert ctx.followup_keys == []
        assert not bool(mi.dataframe.iloc[r_bebek][CHECK_COL])

    def test_lepas_membersihkan_noise_warisan(self, tmp_path, monkeypatch):
        """fps noise v2.12.2 (baris Normal) yang masih tersimpan ikut
        dikeluarkan saat lepas ✓ (peta penuh)."""
        from waste_anomaly.followup import fingerprint_series
        view, ctx, app = self._view(tmp_path, monkeypatch)
        df = _df_bandung()
        fps = fingerprint_series(df).astype(str).tolist()
        # simulasikan warisan: anomali + noise AYAM + noise BEBEK tersimpan
        ctx.followup_keys = list(fps)
        app.processEvents()
        mi = view._tables["items"].model()
        rows = {str(mi.record(r).get("NAMA BARANG")): r
                for r in range(mi.rowCount())}
        r_ayam = rows["AYAM"]
        # BEBEK noise tidak punya pasangan anomali → uncheck AYAM harus
        # membersihkan SEMUA fps AYAM (anomali + noise).
        assert mi.setData(mi.index(r_ayam, 0), False,
                          Qt.ItemDataRole.CheckStateRole)
        app.processEvents()
        assert ctx.followup_keys == [fps[3]]  # hanya BEBEK tersisa


# ============================================================
# [B] Follow Up — TOTAL BULAN LALU
# ============================================================

class TestFollowUpBulanLalu:
    def _fu_view(self, baseline=None):
        from ui.view_followup import FollowUpView
        df = _df_bandung()
        ctx = _ctx_dataset(df)
        if baseline is not None:
            ctx.banding_baseline = baseline
        fv = FollowUpView(ctx)
        from waste_anomaly.followup import fingerprint_series
        fps = fingerprint_series(df).astype(str).tolist()
        ctx.add_followup_many(fps[:2])  # 2 baris anomali AYAM
        _qapp().processEvents()
        fv.show()
        fv.refresh()
        _qapp().processEvents()
        return fv, ctx

    def test_kolom_dan_alias_dengan_baseline(self):
        fv, _ = self._fu_view(_baseline_dict())
        m = fv._table.model()
        cols = list(m.dataframe.columns)
        assert "BULAN LALU" in cols and "PERUBAHAN %" in cols
        # alias judul: BULAN LALU → TOTAL BULAN LALU (kanonik tetap).
        idx = cols.index("BULAN LALU")
        assert str(m.headerData(idx, Qt.Orientation.Horizontal)) == \
            "TOTAL BULAN LALU"
        # urutan tampak: ✓ TOTAL BULAN LALU PERUBAHAN % AVG ...
        vis = [str(m.headerData(i, Qt.Orientation.Horizontal))
               for i in range(m.columnCount())
               if not fv._table.isColumnHidden(i)]
        assert vis[1:4] == ["TOTAL", "TOTAL BULAN LALU", "PERUBAHAN %"]

    def test_nilai_bulan_lalu_benar(self):
        fv, _ = self._fu_view(_baseline_dict())
        m = fv._table.model()
        dfv = m.dataframe
        # AYAM/Handling: sekarang 100 vs bulan lalu 80 → +25%.
        h = dfv[dfv["KETERANGAN"] == "Handling"]
        assert float(h["BULAN LALU"].iloc[0]) == 80.0
        assert abs(float(h["PERUBAHAN %"].iloc[0]) - 25.0) < 1e-9
        # AYAM/Cancel Nota: 40 vs 10 → +300%.
        c = dfv[dfv["KETERANGAN"] == "Cancel Nota"]
        assert float(c["BULAN LALU"].iloc[0]) == 10.0
        assert abs(float(c["PERUBAHAN %"].iloc[0]) - 300.0) < 1e-9

    def test_tanpa_baseline_tanpa_kolom(self):
        fv, _ = self._fu_view(None)
        assert "BULAN LALU" not in fv._table.model().dataframe.columns
        assert "TOTAL BULAN LALU" not in [
            str(fv._table.model().headerData(i, Qt.Orientation.Horizontal))
            for i in range(fv._table.model().columnCount())]

    def test_history_ready_menandai_dirty(self):
        fv, _ = self._fu_view(None)
        fv.hide()
        _qapp().processEvents()
        fv._dirty = False
        fv._ctx.history_ready.emit()
        assert fv._dirty  # view tersembunyi → render ditunda (pola H2)


# ============================================================
# [C] Tab Hari — JENIS + ⤢/⛶
# ============================================================

def _hari_df_v2123() -> pd.DataFrame:
    df = _df_bandung().copy()
    df["HARI TERSANGKA"] = [5.0, 5.0, 5.0, 5.0]
    df["HARI MAX"] = [5, 5, 5, 5]
    df["BUKTI HARI"] = ["YES", "YES", "NO", "NO"]
    df["NILAI HARI TERSANGKA"] = [100.0, 40.0, 0.0, 0.0]
    df["TIPIKAL CABANG LAIN"] = [4.5, 4.5, 4.5, 4.5]
    df["RASIO VS CABANG LAIN"] = [100 / 4.5, 40 / 4.5, 0.0, 0.0]
    df["SHARE HARI TERSANGKA"] = [1.0, 1.0, 0.0, 0.0]
    df["ALASAN HARI"] = ["Hari 5: nilai 100", "", "", ""]
    df["ANOMALY SCORE"] = [10, 8, 0, 0]
    return df


def _hari_view():
    from ui.view_hari import HariView
    app = _qapp()
    ctx = _ctx_dataset(_hari_df_v2123())
    view = HariView(ctx)
    view._refresh_table()
    app.processEvents()
    return view, ctx


class TestHariJenisDanPerbesar:
    def test_jenis_tidak_lagi_narrow_hide(self):
        view, _ = _hari_view()
        assert "JENIS" not in view._table._narrow_hide
        assert "KETERANGAN" in view._table._narrow_hide  # sisanya tetap
        # JENIS ada di kolom tampak
        m = view._table.model()
        j = list(m.dataframe.columns).index("JENIS")
        assert not view._table.isColumnHidden(j)

    def test_expand_toggle(self):
        view, _ = _hari_view()
        assert not view._kpi_row.isHidden()
        view._on_expand()
        assert view._kpi_row.isHidden() and view._head_row.isHidden()
        assert view._ctrl.isHidden()
        assert "⤡" in view._btn_expand.text()
        view._on_expand()
        assert not view._kpi_row.isHidden()
        assert not view._head_row.isHidden() and not view._ctrl.isHidden()

    def test_fullscreen_reparent_dan_pulihkan(self):
        view, _ = _hari_view()
        app = _qapp()
        idx_asli = view._tcl.indexOf(view._table)
        view._on_fullscreen()
        app.processEvents()
        assert view._table.parent() is view._fs_dlg
        view._restore_table_from_fs()
        app.processEvents()
        assert view._tcl.indexOf(view._table) == idx_asli
        # idempoten: pemanggilan ganda tak mengacak
        view._restore_table_from_fs()
        assert view._tcl.indexOf(view._table) == idx_asli

    def test_fullscreen_guard_tabel_kosong(self):
        view, _ = _hari_view()
        view._table.set_dataframe(None)
        view._on_fullscreen()  # harus no-op (tidak crash)
        assert view._fs_dlg is None


# ============================================================
# [D] FilterHeader — funnel + menu + sort
# ============================================================

class TestFilterHeaderUnit:
    def _table(self):
        from ui.widgets import DataTable
        app = _qapp()
        t = DataTable()
        t.set_dataframe(pd.DataFrame({
            "JENIS": ["WASTE", "WASTE", "SUSUT", "TRIAL"],
            "TOTAL": [10.0, 20.0, 5.0, 1.0],
        }))
        t.resize(500, 200)
        t.show()
        app.processEvents()
        return t

    def test_setup_dan_kolom_kanonik(self):
        t = self._table()
        calls = []
        t.setup_header_filters(
            {"JENIS": "jenis"},
            lambda col, key, vals: calls.append((col, key, vals)),
            lambda col: None)
        hdr = t.horizontalHeader()
        assert "JENIS" in t._hf_cols
        assert hdr._col_name(0) == "JENIS"
        assert hdr._col_name(1) == "TOTAL"
        # kolom tanpa funnel: hit None
        from PySide6.QtCore import QPointF
        assert hdr._hit_funnel(QPointF(30, hdr.height() / 2)) is None

    def test_menu_apply_daftar_nilai(self):
        t = self._table()
        calls = []
        t.setup_header_filters(
            {"JENIS": "jenis"},
            lambda col, key, vals: calls.append((col, key, vals)),
            lambda col: None)
        hdr = t.horizontalHeader()
        app = _qapp()
        hdr._open_menu(0)
        app.processEvents()
        menu = hdr._menu
        # daftar nilai + jumlah baris
        texts = [menu._lw.item(i).text()
                 for i in range(menu._lw.count())]
        assert any("WASTE" in x and "(2)" in x for x in texts)
        assert any("SUSUT" in x and "(1)" in x for x in texts)
        # uncheck SUSUT → apply list = sisanya
        it = next(menu._lw.item(i) for i in range(menu._lw.count())
                  if "SUSUT" in menu._lw.item(i).text())
        it.setCheckState(Qt.CheckState.Unchecked)
        assert menu._timer.isActive()  # debounce
        menu._apply_now()
        assert calls[-1] == ("JENIS", "jenis", ["WASTE", "TRIAL"])
        # kembalikan semua → None (lepas)
        it.setCheckState(Qt.CheckState.Checked)
        menu._apply_now()
        assert calls[-1] == ("JENIS", "jenis", None)
        # state awal tercentang sesuai state_fn
        assert all(menu._checked.values())

    def test_menu_state_awal_dari_state_fn(self):
        t = self._table()
        state = {"JENIS": ["WASTE"]}
        t.setup_header_filters(
            {"JENIS": "jenis"}, lambda *a: None, lambda c: state.get(c))
        hdr = t.horizontalHeader()
        app = _qapp()
        hdr._open_menu(0)
        app.processEvents()
        menu = hdr._menu
        assert menu._checked == {"WASTE": True, "SUSUT": False,
                                 "TRIAL": False}

    def test_menu_pilih_semua(self):
        t = self._table()
        calls = []
        t.setup_header_filters(
            {"JENIS": "jenis"},
            lambda col, key, vals: calls.append((col, key, vals)),
            lambda col: None)
        hdr = t.horizontalHeader()
        app = _qapp()
        hdr._open_menu(0)
        app.processEvents()
        menu = hdr._menu
        it = next(menu._lw.item(i) for i in range(menu._lw.count())
                  if "SUSUT" in menu._lw.item(i).text())
        it.setCheckState(Qt.CheckState.Unchecked)
        menu._pick_all()
        assert calls[-1][2] is None
        assert all(menu._checked.values())

    def test_menu_tombol_sort(self):
        t = self._table()
        t.setup_header_filters({"JENIS": "jenis"}, lambda *a: None,
                               lambda c: None)
        hdr = t.horizontalHeader()
        app = _qapp()
        hdr._open_menu(0)
        app.processEvents()
        menu = hdr._menu
        menu._sort(Qt.SortOrder.DescendingOrder)
        app.processEvents()
        m = t.model()
        # desc: WASTE, WASTE, TRIAL, SUSUT (urutan teks menurun)
        assert str(m.record(0)["JENIS"]) == "WASTE"
        assert str(m.record(2)["JENIS"]) == "TRIAL"
        assert str(m.record(3)["JENIS"]) == "SUSUT"
        assert hdr.sortIndicatorSection() == 0

    def test_cari_nilai_memfilter_daftar(self):
        t = self._table()
        t.setup_header_filters({"JENIS": "jenis"}, lambda *a: None,
                               lambda c: None)
        hdr = t.horizontalHeader()
        app = _qapp()
        hdr._open_menu(0)
        app.processEvents()
        menu = hdr._menu
        menu._populate("sus")
        texts = [menu._lw.item(i).text()
                 for i in range(menu._lw.count())]
        assert len(texts) == 1 and "SUSUT" in texts[0]

    def test_tabel_tanpa_mapping_perilaku_biasa(self):
        """Default (tanpa setup) — funnel tak digambar, klik = sort."""
        from ui.widgets import FilterHeader
        t = self._table()
        hdr = t.horizontalHeader()
        assert isinstance(hdr, FilterHeader)
        assert t._hf_cols == {}
        from PySide6.QtCore import QPointF
        x0 = hdr.sectionViewportPosition(0)
        w = hdr.sectionSize(0)
        assert hdr._hit_funnel(QPointF(x0 + w - 22, hdr.height() / 2)) is None


class TestFilterHeaderAnomaliView:
    def _view(self):
        from ui.view_anomali import AnomaliView
        app = _qapp()
        ctx = _ctx_dataset(_df_bandung())
        view = AnomaliView(ctx)
        view.show()
        view.refresh()
        app.processEvents()
        return view, ctx

    def test_wiring_ctx_dan_render_ulang(self):
        # v2.21.0 — tampilan GRUP per (KETERANGAN×NAMA BARANG×NAMA RESTO):
        # fixture _df_bandung 4 baris (2 AYAM anomali + 1 AYAM Normal +
        # 1 BEBEK Normal) → 4 grup keterangan + 3 pemisah. Funnel wiring
        # tetap utuh: klik funnel → state ctx berubah → render ulang.
        # Uncheck SATU nilai tunggal di kolom = vals=[] = filter kosong
        # (kontrak _apply_filters: list kosong = tak ada filter → semua
        # baris tampil); test fokus verifikasi WIRING (state ctx ter-set
        # + render terjadi), bukan filter semantik (fixture terlalu kecil
        # utk pengujian baris-berkurang).
        view, ctx = self._view()
        hdr = view._table.horizontalHeader()
        app = _qapp()
        assert view._table.model().rowCount() == 7  # 4 grup keterangan + 3 pemisah (Normal ikut, v2.19.8)
        df_cols = list(view._table.model().dataframe.columns)
        logical = df_cols.index("NAMA BARANG")
        hdr._open_menu(logical)
        app.processEvents()
        menu = hdr._menu
        # Teks item = "AYAM   (1)" (label + jumlah baris); UserRole = nilai
        # mentah "AYAM" (pola test_v21312 round-trip).
        it = next(menu._lw.item(i) for i in range(menu._lw.count())
                  if menu._lw.item(i).data(Qt.ItemDataRole.UserRole) == "AYAM")
        it.setCheckState(Qt.CheckState.Unchecked)
        menu._apply_now()
        app.processEvents()
        # WIRING: state ctx ter-set lewat funnel (key "item" di HF_COLS).
        # v2.19.8 — Normal ikut: funnel punya AYAM + BEBEK; uncheck AYAM
        # → vals=['BEBEK'] (BEBEK masih tercentang) → filter item=['BEBEK'].
        assert ctx.active_filters["item"] == ["BEBEK"]
        # render ulang terjadi (filter ['BEBEK'] → hanya BEBEK grup tampil).
        assert view._table.model().rowCount() == 1
        # funnel aktif via _hf_state — ['BEBEK'] dikembalikan apa adanya
        # (semantik _hf_state: list non-kosong = filter aktif).
        assert view._hf_state("NAMA BARANG") == ["BEBEK"]

    def test_state_dari_drilldown_string(self):
        """set_filter string (drill-down) → _hf_state menormalkan list."""
        view, ctx = self._view()
        ctx.set_filter("cabang", "R1")
        assert view._hf_state("NAMA RESTO") == ["R1"]

    def test_klik_funnel_tidak_memicu_sort(self):
        view, _ = self._view()
        hdr = view._table.horizontalHeader()
        app = _qapp()
        df_cols = list(view._table.model().dataframe.columns)
        logical = df_cols.index("JENIS")
        before = hdr.sortIndicatorSection()
        x0 = hdr.sectionViewportPosition(logical)
        w = hdr.sectionSize(logical)
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtCore import QEvent, QPoint
        ev = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(x0 + w - 22, hdr.height() / 2),
            hdr.mapToGlobal(QPoint(int(x0 + w - 22), hdr.height() // 2)),
            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier)
        hdr.mousePressEvent(ev)
        app.processEvents()
        assert hdr.sortIndicatorSection() == before  # sort tak terpicu


class TestFilterHeaderFollowUpLokal:
    def _view(self):
        from ui.view_followup import FollowUpView
        app = _qapp()
        df = _df_bandung()
        ctx = _ctx_dataset(df)
        from waste_anomaly.followup import fingerprint_series
        fps = fingerprint_series(df).astype(str).tolist()
        ctx.add_followup_many(fps[:2])
        app.processEvents()
        fv = FollowUpView(ctx)
        fv.show()
        fv.refresh()
        app.processEvents()
        return fv, ctx, fps

    def test_filter_lokal_menaring_tampilan_saja(self):
        fv, ctx, fps = self._view()
        app = _qapp()
        # hanya 2 baris anomali AYAM (Handling + Cancel Nota)
        assert fv._table.model().rowCount() == 2
        fv._on_header_filter("KETERANGAN", "KETERANGAN", ["Handling"])
        app.processEvents()
        m = fv._table.model()
        assert m.rowCount() == 1
        assert str(m.record(0)["KETERANGAN"]) == "Handling"
        # daftar follow-up & ekspor TIDAK tersentuh
        assert len(ctx.followup_keys) == 2
        assert len(fv._rows) == 2
        # state funnel lokal
        assert fv._hfilters.get("KETERANGAN") == ["Handling"]

    def test_filter_lokal_lepas(self):
        fv, _ctx, _fps = self._view()
        app = _qapp()
        fv._on_header_filter("KETERANGAN", "KETERANGAN", ["Handling"])
        fv._on_header_filter("KETERANGAN", "KETERANGAN", None)
        app.processEvents()
        assert fv._table.model().rowCount() == 2
        assert "KETERANGAN" not in fv._hfilters

    def test_refresh_mempertahankan_filter_lokal(self):
        fv, _ctx, _fps = self._view()
        app = _qapp()
        fv._on_header_filter("KETERANGAN", "KETERANGAN", ["Handling"])
        app.processEvents()
        fv.refresh()  # mis. ✓ berubah di tempat lain
        app.processEvents()
        assert fv._table.model().rowCount() == 1


# ============================================================
# [E] Peta hari — tanggal & nilai terpisah
# ============================================================

class TestPetaHariRedesain:
    def _cells(self):
        from ui.view_anomali import DetailPanel
        app = _qapp()
        ctx = _ctx_dataset(_df_bandung())
        panel = DetailPanel(ctx)
        rec = _df_bandung().iloc[0].copy()
        host = panel._day_map(rec)
        app.processEvents()
        # host + panel di-PEGANG (tanpa ini label anak ikut terhapus saat
        # C++ host dihancurkan — RuntimeError 'already deleted').
        self._keepalive = (panel, host)
        return [l for l in host.findChildren(QLabel)]

    def test_format_baru_tanggal_kecil_nilai_tebal(self):
        cells = self._cells()
        assert len(cells) == 31
        # tidak ada lagi format 'N:nilai' satu baris (rich text memuat ':'
        # di atribut style — cek POLA 'angka:' di AWAL teks, bukannya ':').
        for c in cells:
            assert not c.text().startswith(tuple(f"{d}:" for d in range(1, 32))), \
                c.text()
            assert "<span" in c.text()  # format baru: tanggal = span kecil
        # hari 5 berisi tanggal kecil + nilai TEBAL
        d5 = next(c for c in cells if c.toolTip().startswith("Hari 5:"))
        assert "5</span>" in d5.text()
        assert "<b>100</b>" in d5.text()
        # hari kosong: tanggal redup saja
        d1 = next(c for c in cells if c.toolTip().startswith("Hari 1:"))
        assert "1</span>" in d1.text() and "<b>" not in d1.text()
        # hari tersangka (HARI TERSANGKA=5) disorot merah
        assert "#dc2626" in (d5.styleSheet() or "")
