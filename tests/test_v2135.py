"""test_v2135.py — v2.13.5: klik-2× filter DIHAPUS + pop-up selalu bisa
dibuka + tab Hari Mencurigakan punya opsi follow-up.

Dua keluhan user (satu pesan):
1. "coba cek: klik 1x pop up kadang sering tidak muncul dan malah justru
   ke trigger yang klik 2x yaitu langsung filter. hilangkan yang klik 2x"
   → Akar terbukti: klik-2× baris → _on_double → set_filter(cabang+item)
   → render ulang → _popup.hide() di awal _refresh_table_impl = pop-up
   "menghilang". Ditambah: tutup pop-up (X) → klik baris SAMA →
   currentRowChanged TIDAK memicu (index tak berubah) → pop-up tak bisa
   dibuka lagi → user klik lagi (cepat) → Qt sintesis DblClick → filter.
   Fix: (a) _on_double dihapus dari AnomaliView & HariView; (b) sinyal
   row_clicked (relay QTableView.clicked + doubleClicked, KECUALI sel ✓)
   → pop-up detail selalu bisa dibuka ulang; (c) guard idempoten
   DetailDialog.show_record (record sama + tampak = tak dibangun ulang);
   (d) tekanan di sel ✓ = aksi centang murni (pop-up ditekan).
2. "hari mencurigakan juga beri opsi untuk follow up"
   → tab Hari Mencurigakan kini punya kolom ✓ + tombol ☑ Centang yang
   tampil + tombol follow-up di pop-up detail (pola AnomaliView; satu
   state ctx, sinkron antar tab).

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

def _anomali_df(n: int = 4) -> pd.DataFrame:
    data = {
        "NAMA RESTO": [f"RESTO {i}" for i in range(n)],
        "NAMA BARANG": [f"BARANG {i}" for i in range(n)],
        "JENIS": ["BAHAN"] * n,
        "KETERANGAN": ["alasan A"] * n,
        "SOURCE DATA": ["S1"] * n,
        "SATUAN": ["GR"] * n,
        "TOTAL": [float(1000 * (i + 1)) for i in range(n)],
        "ANOMALY SCORE": [9 - i for i in range(n)],
        "ANOMALY STATUS": ["Prioritas Tinggi", "Potensi Anomali",
                           "Perlu Review", "Perlu Review"][:n],
        "ANOMALY REASONS": ["S1 spike; S6 max/BOM"] * n,
    }
    return pd.DataFrame(data)


def _hari_df() -> pd.DataFrame:
    """3 outlet, 1 item — outlet A salah ketik hari 17 (pola _df_hari
    test_v290) + kolom bukti hari hasil Stage 15."""
    from waste_anomaly.day_focus import annotate_day_evidence
    rows = []
    for resto in ("A.OUTLET", "B.OUTLET", "C.OUTLET"):
        vals = {str(d): 5.0 if resto != "C.OUTLET" else 4.0
                for d in range(1, 31)}
        if resto == "A.OUTLET":
            vals["17"] = 70.0
        rows.append({
            "NAMA RESTO": resto, "NAMA BARANG": "ITEM UJI",
            "JENIS": "WASTE", "KETERANGAN": "Kualitas",
            "SOURCE DATA": "REKAP", "SATUAN": "GR",
            **vals,
            "TOTAL": float(sum(vals.values())),
            "ANOMALY STATUS": "Potensi Anomali",
            "ANOMALY SCORE": 9,
            # input stage-6/7 yang dibaca day_focus (pola _df_hari v290)
            "HARI MAX": 17.0 if resto == "A.OUTLET" else 1.0,
            "SCALE SIGNAL": "YES" if resto == "A.OUTLET" else "NO",
            "SINGLE DAY": "NO",
        })
    df = pd.DataFrame(rows)
    return annotate_day_evidence(df, 31, {"thresholds": {}})


def _make_view():
    _qapp()
    from ui.state import AppContext
    from ui.view_anomali import AnomaliView
    ctx = AppContext({})
    view = AnomaliView(ctx)
    ctx.set_dataset(_anomali_df(), {"key_akhir": 31})
    view._refresh_table()
    return view, ctx


def _make_hari_view(df=None):
    _qapp()
    from ui.state import AppContext
    from ui.view_hari import HariView
    ctx = AppContext({})
    view = HariView(ctx)
    ctx.set_dataset(df if df is not None else _hari_df(),
                    {"key_akhir": 31})
    view._refresh_table()
    return view, ctx


# ============================================================
# [A] KLIK-2× → FILTER DIHAPUS (permintaan user)
# ============================================================

class TestKlikGandaTakLagiFilter:

    def test_on_double_dihapus_kedua_view(self):
        """Handler + guard coalesce dihapus bersama perilakunya."""
        src_a = (UI / "view_anomali.py").read_text(encoding="utf-8")
        src_h = (UI / "view_hari.py").read_text(encoding="utf-8")
        for src in (src_a, src_h):
            assert "def _on_double" not in src
            # atribut instance (kode) — komentar sejarah tak dihitung
            assert "self._batch_filters" not in src
            assert "self._table.double_clicked.connect" not in src

    def test_emit_double_clicked_tanpa_efek_anomali(self):
        view, ctx = _make_view()
        rec = view._table.model().record(0)
        n = view._table.model().rowCount()
        view._table.double_clicked.emit(rec)
        _qapp().processEvents()
        assert not any(ctx.active_filters.values())
        assert view._table.model().rowCount() == n

    def test_emit_double_clicked_tanpa_efek_hari(self):
        view, ctx = _make_hari_view()
        rec = view._table.model().record(0)
        n = view._table.model().rowCount()
        view._table.double_clicked.emit(rec)
        _qapp().processEvents()
        assert not any(ctx.active_filters.values())
        assert view._table.model().rowCount() == n

    def test_sinyal_double_clicked_tetap_hidup_untuk_view_lain(self):
        """Infrastruktur double_clicked TIDAK dihancurkan — tab Scorecard
        & Banding Periode masih memakainya utk pop-up rincian (bukan
        filter)."""
        from ui.widgets import DataTable
        assert hasattr(DataTable, "double_clicked")
        src_s = (UI / "view_scorecard.py").read_text(encoding="utf-8")
        assert "double_clicked.connect" in src_s

    def test_dblclick_kini_juga_membuka_pop_up(self):
        """doubleClicked diteruskan ke row_clicked (tekan#2 DblClick tidak
        memancarkan clicked — tanpa relay ini klik-ulang-cepat baris sama
        tidak membuka apa-apa setelah filter dihapus)."""
        view, _ = _make_view()
        fired = []
        view._table.row_clicked.connect(
            lambda i: fired.append(i.row()))
        m = view._table.model()
        view._table.doubleClicked.emit(m.index(0, 2))
        _qapp().processEvents()
        assert fired == [0]
        # emit DblClick pada sel ✓ TIDAK diteruskan (aksi centang murni)
        fired.clear()
        view._table.doubleClicked.emit(m.index(0, 0))
        assert fired == []


# ============================================================
# [B] POP-UP SELALU BISA DIBUKA (row_clicked + idempoten)
# ============================================================

class TestPopupSelaluBisaDibuka:

    def test_row_clicked_dihubungkan_tiga_view(self):
        """Anomali / Hari / Follow Up: klik baris SAMA pun membuka pop-up
        (currentRowChanged diam saat index tak berubah)."""
        for fname in ("view_anomali.py", "view_hari.py",
                      "view_followup.py"):
            src = (UI / fname).read_text(encoding="utf-8")
            assert "row_clicked.connect" in src, fname

    def test_show_record_idempoten_record_sama(self):
        """Pop-up tampak + record sama → TIDAK dibangun ulang (klik
        tunggal memicu currentRowChanged + clicked; guard mencegah rebuild
        ganda ~70 widget)."""
        from PySide6.QtWidgets import QApplication
        view, _ = _make_view()
        QApplication.processEvents()
        rec = view._table.model().record(0)
        view._popup.show_record(rec)
        QApplication.processEvents()
        assert view._popup.isVisible()
        # hitung rebuild: patch panel.show_record
        calls = []
        orig = view._popup._panel.show_record
        view._popup._panel.show_record = \
            lambda r: (calls.append(1), orig(r))
        try:
            view._popup.show_record(rec)  # record sama + tampak
            assert calls == [], "rebuild harus dilewati (idempoten)"
            rec2 = view._table.model().record(1)
            view._popup.show_record(rec2)  # record beda → rebuild
            assert calls == [1]
        finally:
            view._popup._panel.show_record = orig

    def test_popup_tertutup_record_sama_tetap_dibangun_ulang(self):
        """Pop-up HIDDEN (ditutup X / refresh) + record sama → dibangun
        ulang & dimunculkan (guard hanya men-skip saat VISIBLE)."""
        from PySide6.QtWidgets import QApplication
        view, _ = _make_view()
        QApplication.processEvents()
        rec = view._table.model().record(0)
        view._popup.show_record(rec)
        view._popup.close()
        QApplication.processEvents()
        assert view._popup.isHidden()
        view._popup.show_record(rec)
        QApplication.processEvents()
        assert view._popup.isVisible()

    def test_sel_centang_tekan_murni_aksi_centang(self):
        """mousePressEvent di sel ✓: flag suppress_row_popup hidup selama
        super() — view memakainya supaya klik-✓ baris BARU pun tidak
        membuka pop-up (alur centang massal murni)."""
        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtWidgets import QApplication

        from waste_anomaly.followup import CHECK_COL
        view, _ = _make_view()
        QApplication.processEvents()
        m = view._table.model()
        assert m.dataframe.columns[0] == CHECK_COL
        view._popup.hide()
        QApplication.processEvents()
        # klik NYATA (tekan+lepas) pada sel ✓ baris 1 (current row = -1 →
        # currentRowChanged ikut memicu — harus ditekan flag)
        idx = m.index(1, 0)
        rect = view._table.visualRect(idx)
        pos, g = QPointF(rect.center()), QPointF(
            view._table.mapToGlobal(rect.center()))
        for typ, btns in [(QEvent.Type.MouseButtonPress,
                           Qt.MouseButton.LeftButton),
                          (QEvent.Type.MouseButtonRelease,
                           Qt.MouseButton.NoButton)]:
            QApplication.sendEvent(view._table.viewport(), QMouseEvent(
                typ, pos, g, Qt.MouseButton.LeftButton, btns,
                Qt.KeyboardModifier.NoModifier))
        QApplication.processEvents()
        assert view._table.selectionModel().currentIndex().row() == 1
        assert not view._popup.isVisible(), (
            "klik sel ✓ tidak boleh membuka pop-up (aksi centang murni)")

    def test_row_clicked_ditekan_untuk_sel_centang(self):
        """Relay row_clicked memfilter sel ✓ — kolom ✓ harus ADA di df
        (pola display AnomaliView) supaya guard mengenalinya."""
        from ui.widgets import DataTable
        from waste_anomaly.followup import CHECK_COL
        _qapp()
        t = DataTable()
        m = t.model()
        df = _anomali_df()
        df.insert(0, CHECK_COL, [False] * len(df))
        m.set_dataframe(df)
        fired = []
        t.row_clicked.connect(lambda i: fired.append(i.column()))
        m.set_check_column(CHECK_COL)
        t._on_clicked(m.index(0, 1))  # sel biasa → diteruskan
        assert fired == [1]
        t._on_clicked(m.index(0, 0))  # kolom 0 = ✓ → ditelan
        assert fired == [1]
        t._on_double(m.index(0, 0))  # DblClick di ✓ juga ditelan
        assert fired == [1]
        t._on_double(m.index(0, 2))  # DblClick sel biasa → diteruskan
        assert fired == [1, 2]


# ============================================================
# [C] HARI MENCURIGAKAN — OPsi FOLLOW UP (kolom ✓ + bulk)
# ============================================================

class TestHariFollowup:

    def test_kolom_centang_dan_fp_di_tabel(self):
        from waste_anomaly.followup import CHECK_COL, FP_COL
        view, _ = _make_hari_view()
        m = view._table.model()
        assert m.dataframe.columns[0] == CHECK_COL
        assert FP_COL in m.dataframe.columns
        assert view._table.model()._check_col == CHECK_COL

    def test_toggle_centang_hari_masuk_daftar(self):
        from waste_anomaly.followup import FP_COL
        view, ctx = _make_hari_view()
        m = view._table.model()
        fp = str(m.record(0)[FP_COL])
        view._on_check_toggled(0, True)
        assert fp in ctx.followup_set()
        view._on_check_toggled(0, False)
        assert fp not in ctx.followup_set()

    def test_fps_sesuai_fingerprint_sumber(self):
        """Sidik jari tabel hari == fingerprint_series(df anomali — baris
        yang sama terlacak lintas tab (Anomali/Hari/Follow Up satu state)."""
        from waste_anomaly.followup import FP_COL, fingerprint_series
        df = _hari_df()
        view, _ = _make_hari_view(df)
        m = view._table.model()
        src_fps = set(fingerprint_series(
            view._ctx.anomali_df()).astype(str))
        shown = set(m.dataframe[FP_COL].astype(str))
        assert shown and shown.issubset(src_fps)

    def test_tombol_centang_semua_yang_tampil(self):
        view, ctx = _make_hari_view()
        n = view._table.model().rowCount()
        view._on_check_all()
        _qapp().processEvents()
        assert len(ctx.followup_keys) == n
        view._on_check_all()  # idempoten
        assert len(ctx.followup_keys) == n
        ctx.clear_followup()

    def test_tombol_centang_semua_ada_di_bar_kontrol(self):
        view, _ = _make_hari_view()
        assert view._btn_fu_all.text().startswith("☑")

    def test_perubahan_eksternal_segar_in_place(self):
        """Toggle dari tab lain (tombol pop-up / ✓ Anomali) → kolom ✓
        tabel hari diperbarui TANPA reset model (objek df tetap)."""
        from waste_anomaly.followup import CHECK_COL, FP_COL
        view, ctx = _make_hari_view()
        m = view._table.model()
        df_obj = m.dataframe
        fp = str(m.record(0)[FP_COL])
        ctx.toggle_followup(fp, True)
        _qapp().processEvents()
        assert m.dataframe is df_obj, "model tidak boleh di-reset"
        assert bool(m.dataframe.iloc[0][CHECK_COL]) is True
        ctx.toggle_followup(fp, False)
        _qapp().processEvents()
        assert bool(m.dataframe.iloc[0][CHECK_COL]) is False

    def test_display_memo_objek_stabil(self):
        """Salinan display (✓/__FP) di-memo per objek df → cache fit tabel
        tetap kena antar-refresh; nilai ✓ disegarkan tiap pemakaian."""
        from waste_anomaly.followup import CHECK_COL, FP_COL
        view, ctx = _make_hari_view()
        df_show = view._ctx.anomali_df()
        d1 = view._display_df(df_show)
        d2 = view._display_df(df_show)
        assert d1 is d2
        fp = str(d1.iloc[0][FP_COL])
        ctx.toggle_followup(fp, True)
        d3 = view._display_df(df_show)
        assert d3 is d1, "objek memo dipakai ulang"
        assert bool(d3.iloc[0][CHECK_COL]) is True, (
            "nilai ✓ harus ikut state terbaru")
        ctx.clear_followup()

    def test_funnel_tak_menyaring_kolom_centang_dan_fp(self):
        view, _ = _make_hari_view()
        t = view._table
        from waste_anomaly.followup import CHECK_COL, FP_COL
        assert not t._hf_has(CHECK_COL)
        assert not t._hf_has(FP_COL)

    def test_dataset_baru_memo_dilepas(self):
        view, _ = _make_hari_view()
        df2 = _hari_df().copy()
        view._ctx.set_dataset(df2, {"key_akhir": 31})
        _qapp().processEvents()
        view._refresh_table()
        _qapp().processEvents()
        assert view._table.model().rowCount() > 0


# ============================================================
# [D] TOMBOL FOLLOW-UP DI POP-UP DETAIL (semua tab)
# ============================================================

class TestPopupTombolFollowup:

    def _popup(self):
        from ui.state import AppContext
        from ui.view_anomali import DetailDialog
        ctx = AppContext({})
        dlg = DetailDialog(ctx, None)
        return ctx, dlg

    def test_tombol_ada_dan_fp_sesuai(self):
        _ctx, dlg = self._popup()
        rec = _anomali_df().iloc[0]
        dlg.show_record(rec)
        assert dlg._panel._fu_btn is not None
        assert dlg._panel._cur_fp
        assert "Masuk Follow Up" in dlg._panel._fu_btn.text()

    def test_toggle_dari_pop_up_update_state_dan_teks(self):
        ctx, dlg = self._popup()
        rec = _anomali_df().iloc[0]
        dlg.show_record(rec)
        fp = dlg._panel._cur_fp
        dlg._panel._on_fu_toggle()
        _qapp().processEvents()
        assert fp in ctx.followup_set()
        assert "Sudah" in dlg._panel._fu_btn.text()
        # toggle eksternal → teks tombol ikut TANPA rebuild
        calls = []
        orig = dlg._panel.show_record
        dlg._panel.show_record = lambda r: (calls.append(1), orig(r))
        try:
            ctx.toggle_followup(fp, False)
            _qapp().processEvents()
            assert "Masuk" in dlg._panel._fu_btn.text()
            assert calls == [], "update teks harus in-place"
        finally:
            dlg._panel.show_record = orig

    def test_fallback_fp_tanpa_kolom_fp(self):
        """Record tanpa __FP (fixture) → sidik jari dihitung ulang dan
        SAMA dengan fingerprint_series baris itu (identitas lintas jalur)."""
        from waste_anomaly.followup import fingerprint_series
        _ctx, dlg = self._popup()
        df = _anomali_df()
        rec = df.iloc[2]
        assert "__FP" not in rec.index
        fp = dlg._panel._row_fingerprint(rec)
        assert fp == str(fingerprint_series(df).iloc[2])

    def test_clear_reset_ref_tombol(self):
        """clear() (dataset berubah) → ref tombol/fp di-reset — handler
        followup_changed tak menyentuh widget yang sudah dihapus."""
        ctx, dlg = self._popup()
        dlg.show_record(_anomali_df().iloc[0])
        assert dlg._panel._fu_btn is not None
        dlg._panel.clear()
        assert dlg._panel._fu_btn is None
        assert dlg._panel._cur_fp is None
        # broadcast setelah clear → tak boleh meledak
        ctx.toggle_followup("x" * 32, True)
        ctx.clear_followup()

    def test_record_sig_dari_fp(self):
        _ctx, dlg = self._popup()
        df = _anomali_df()
        rec = df.iloc[1]
        sig = dlg._record_sig(rec)
        assert sig[0] is None  # tanpa __FP → None (fallback identitas)
        assert sig[1] == "RESTO 1"


# ============================================================
# [E] TEKS UI — sumber follow-up menyebut Hari Mencurigakan
# ============================================================

class TestTeksSumberFollowup:

    def test_judul_followup_menyebut_hari(self):
        src = (UI / "view_followup.py").read_text(encoding="utf-8")
        assert "Hari Mencurigakan" in src
        # pesan arahan kosong juga mengarah ke tab Hari
        assert "atau Hari Mencurigakan" in src

    def test_bantuan_menyebut_hari_dan_larangan_klik_2x(self):
        src = (UI / "app.py").read_text(encoding="utf-8")
        assert "Hari Mencurigakan" in src
        # v2.13.12 (gel-3 D19) — pin DITULIS ULANG JUJUR: frasa lama
        # "TIDAK lagi memfilter" mengandung token versi implisit (kata
        # "lagi" = merujuk perubahan v2.13.5); pembersihan 10 token
        # versi dari Bantuan ikut menyingkatnya jadi "TIDAK memfilter".
        # MAKSUD test tak berubah: Bantuan harus menyatakan klik-2×
        # TIDAK memfilter (klik-2× filter dihapus — judul test ini).
        assert "TIDAK memfilter" in src

    def test_tooltip_layar_penuh_tak_menyebut_klik_2x_filter(self):
        """Tooltip ⛶ tidak lagi mengiklankan klik-2× (perilaku dihapus)."""
        src_h = (UI / "view_hari.py").read_text(encoding="utf-8")
        assert "klik 2× tetap" not in src_h


# ============================================================
# [F] DATA ASLI — jalur penuh (golden-safe, additive)
# ============================================================

class TestDataAsli:

    def test_pipeline_hari_view_dgn_kolom_centang(self):
        """Data asli 25.901 baris: tabel hari mencurigakan ber-✓, pop-up
        detail ber-tombol follow-up ber-sidik jari valid, klik-2× tanpa
        filter. (Golden tak tersentuh — hanya jalur UI.)"""
        from ui.state import AppContext
        from ui.view_hari import HariView
        from waste_anomaly.followup import CHECK_COL, fingerprint_series
        from waste_anomaly.pipeline import run_pipeline
        res = run_pipeline(str(REPO / "DATA_WASTE.xlsx"))
        assert res.get("success"), res.get("error")
        ctx = AppContext({})
        view = HariView(ctx)
        ctx.set_dataset(res["df"], res)
        view._refresh_table()
        _qapp().processEvents()
        m = view._table.model()
        assert m.rowCount() > 0
        assert m.dataframe.columns[0] == CHECK_COL
        # klik-2× emit → tanpa filter
        rec = m.record(0)
        view._table.double_clicked.emit(rec)
        _qapp().processEvents()
        assert not any(ctx.active_filters.values())
        # pop-up tombol follow-up: fp valid = anggota fingerprint dataset
        view._popup.show_record(m.record(1))
        fp = view._popup._panel._cur_fp
        assert fp in set(fingerprint_series(res["df"]).astype(str))
        # bulk → semua baris tampil masuk
        n = m.rowCount()
        view._on_check_all()
        _qapp().processEvents()
        assert len(ctx.followup_keys) == n
        ctx.clear_followup()
        view.close()

    def test_anomali_view_popup_fu_toggle_data_asli(self):
        from ui.state import AppContext
        from ui.view_anomali import AnomaliView
        from waste_anomaly.pipeline import run_pipeline
        res = run_pipeline(str(REPO / "DATA_WASTE.xlsx"))
        assert res.get("success")
        ctx = AppContext({})
        view = AnomaliView(ctx)
        ctx.set_dataset(res["df"], res)
        view._refresh_table()
        _qapp().processEvents()
        m = view._table.model()
        view._popup.show_record(m.record(0))
        fp = view._popup._panel._cur_fp
        view._popup._panel._on_fu_toggle()
        _qapp().processEvents()
        assert fp in ctx.followup_set()
        # baris tabel ikut tercentang in-place (tanpa reset)
        assert bool(m.dataframe.iloc[0]["✓"]) is True
        ctx.clear_followup()
        view.close()
