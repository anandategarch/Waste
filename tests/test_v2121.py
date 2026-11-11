"""test_v2121.py — regresi v2.12.1 (PERF TOMBOL — "cek lagi yang bikin
lemot tombol tombol dan fix").

Empat akar lemot yang difix (semua terukur profil data asli 25.901 baris,
mesin user 2-4× lebih lambat dari sandbox):

1. _apply_filters: salinan df PENUH di depan mask (→ fast path tanpa
   filter = objek sama, 21 ms → 0 ms per klik "kembali/bersihkan").
2. PandasTableModel.text_at: snapshot numpy utk jalur pengukuran massal
   (data() Qt tetap iat/hidup — 42.927 panggilan sel = 1,7 dtk → ~0,27 dtk
   di render tab Follow Up 797×41).
3. AnomaliView._display_df: memo SATU SLOT → LRU-8 per objek df (toggle
   slicer bolak-balik = cache fit DataTable kena lagi; jalur balik
   baseline 348 ms → 33 ms).
4. suspicious_days vektor numpy (68 ms → 3 ms; ekuivalensi vs oracle
   loop lama dikunci test).
5. PipelineWorker menyumbang followup_fps + state.set_dataset memetikannya
   (fingerprint 25.901 baris keluar dari thread UI).
6. Tabel lebar (>24 kolom tampak) = wrap mati + elide (konvensi tabel
   raksasa) → lepas ✓ di tab Follow Up tak membayar pengukuran tinggi.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from PySide6.QtCore import Qt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from waste_anomaly.followup import (  # noqa: E402
    CHECK_COL,
    FP_COL,
    fingerprint_series,
    suspicious_days,
)


def _qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication(sys.argv)


def _df_synth(n: int = 60, seed: int = 7) -> pd.DataFrame:
    """Data acak + kasus tepi utk filter/oracle: NaN, 0, negatif, string."""
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({
        "NAMA RESTO": [f"R{i % 7}" for i in range(n)],
        "NAMA BARANG": [f"BRG{i % 13}" for i in range(n)],
        "JENIS": ["WASTE" if i % 3 else "SUSUT" for i in range(n)],
        "KETERANGAN": ["Cancel Nota" if i % 2 else "Alat/Mesin"
                       for i in range(n)],
        "ANOMALY STATUS": rng.choice(
            ["Normal", "Prioritas Tinggi", "Perlu Review"], n),
        "TOTAL": rng.normal(50, 10, n).round(1),
        "ANOMALY SCORE": rng.integers(0, 30, n),
        "HARI MAX": rng.integers(1, 32, n),
    })
    df.loc[rng.integers(0, n, 6), "ANOMALY STATUS"] = None
    df.loc[rng.integers(0, n, 4), "HARI MAX"] = pd.NA
    return df


# ============================================================
# 1. _apply_filters — fast path tanpa salinan
# ============================================================

class TestApplyFiltersNoCopy:
    def test_tanpa_filter_objek_sama(self):
        from ui.shared import _apply_filters
        df = _df_synth()
        out = _apply_filters(df, {"cabang": None, "item": None, "jenis": [],
                                  "keterangan": None, "status": None})
        assert out is df  # kontrak v2.12.1: pemanggil hanya membaca

    def test_list_kosong_semua_dimensi_objek_sama(self):
        from ui.shared import _apply_filters
        df = _df_synth()
        out = _apply_filters(
            df, {"jenis": [], "keterangan": [], "status": []})
        assert out is df

    def test_filter_kolom_tak_ada_objek_sama(self):
        # kunci valid tapi kolom target absen → tak ada mask → df apa adanya
        # (v2.13.8: rentang hari dihapus — kunci valid = jenis)
        from ui.shared import _apply_filters
        df = _df_synth().drop(columns=["JENIS"])
        out = _apply_filters(df, {"jenis": ["WASTE"]})
        assert out is df

    def test_dengan_filter_objek_baru_konten_benar(self):
        from ui.shared import _apply_filters
        df = _df_synth()
        out = _apply_filters(df, {"jenis": ["WASTE"]})
        assert out is not df
        assert (out["JENIS"] == "WASTE").all()
        assert len(out) == int((df["JENIS"] == "WASTE").sum())

    def test_tanpa_filter_tak_termutasi_konsumen(self):
        # konsumen baca-saja: mask/slice kolom menghasilkan objek baru —
        # df asli tak berubah (kontrak lama tetap).
        from ui.shared import _apply_filters
        df = _df_synth()
        out = _apply_filters(df, None)
        sub = out[out["JENIS"] == "WASTE"]
        assert len(sub) > 0
        assert len(df) == len(out) == 60


# ============================================================
# 2. PandasTableModel.text_at — snapshot bulk vs data() live
# ============================================================

class TestTextAtSnapshot:
    def _model(self, df=None):
        _qapp()
        from ui.models import PandasTableModel
        return PandasTableModel(df if df is not None else _df_synth())

    def test_text_at_sama_dengan_data_display(self):
        m = self._model()
        for r in range(min(9, len(m.dataframe))):
            for c in range(len(m.dataframe.columns)):
                via_data = str(m.data(m.index(r, c), Qt.DisplayRole) or "")
                via_bulk = m.text_at(r, c)
                assert via_bulk == via_data, (r, c)

    def test_text_at_kolom_centang_kosong(self):
        m = self._model()
        m.set_check_column("TOTAL")
        assert m.text_at(0, list(m.dataframe.columns).index("TOTAL")) == ""

    def test_data_hidup_setelah_mutasi_df_langsung(self):
        # REGRESI desain: snapshot TIDAK boleh membuat data() Qt buta
        # terhadap mutasi df langsung (data() = sumber kebenaran hidup).
        m = self._model()
        m.set_check_column("ANOMALY SCORE")
        col = list(m.dataframe.columns).index("ANOMALY SCORE")
        m.dataframe.iat[0, col] = True
        got = m.data(m.index(0, col), Qt.ItemDataRole.CheckStateRole)
        assert got == Qt.CheckState.Checked

    def test_text_at_segar_setelah_notify_column_changed(self):
        # jalur sinkron resmi: mutasi df → notify_column_changed →
        # snapshot ikut disegarkan (pengukuran berikutnya tak basi).
        m = self._model()
        m.set_check_column("ANOMALY SCORE")
        col = list(m.dataframe.columns).index("ANOMALY SCORE")
        m.dataframe["ANOMALY SCORE"] = [True] * len(m.dataframe)
        m.notify_column_changed("ANOMALY SCORE")
        assert m.text_at(0, col) == ""
        got = m.data(m.index(0, col), Qt.ItemDataRole.CheckStateRole)
        assert got == Qt.CheckState.Checked

    def test_set_data_flip_sinkron_snapshot(self):
        m = self._model()
        m.set_check_column("ANOMALY SCORE")
        col = list(m.dataframe.columns).index("ANOMALY SCORE")
        m.dataframe["ANOMALY SCORE"] = [False] * len(m.dataframe)
        m.notify_column_changed("ANOMALY SCORE")
        assert m.setData(m.index(0, col), Qt.CheckState.Checked,
                         Qt.ItemDataRole.CheckStateRole)
        # nilai mentah snapshot (via jalur bulk) sudah True
        assert m._arr[0, col] is True or bool(m._arr[0, col]) is True

    def test_snapshot_dibangun_ulang_setelah_sort(self):
        m = self._model()
        before = m.text_at(0, 0)
        m.sort(0, Qt.DescendingOrder)
        after = m.text_at(0, 0)
        # urutan berganti → sel (0,0) kini baris ter-sort-desc
        col_vals = [str(v) for v in m.dataframe.iloc[:, 0]]
        assert after == str(col_vals[0])
        assert (after != before) or col_vals[0] == before


# ============================================================
# 3. AnomaliView._display_df — LRU per objek df (anti-lemot inti)
# ============================================================

class TestDisplayLru:
    def _view(self):
        _qapp()
        from ui.state import AppContext
        from ui.view_anomali import AnomaliView
        ctx = AppContext({})
        return ctx, AnomaliView(ctx)

    def test_bolak_balik_antar_state_objek_display_sama(self):
        """Kontrak v2.12.1: state A → B → A mengembalikan objek display A
        yang PERSIS sama (kunci cache fit DataTable — model.dataframe =
        salinan ter-sort, kunci cache = objek display via _src_df)."""
        ctx, view = self._view()
        view.show()
        ctx.set_dataset(_df_synth(80), {"key_akhir": 31})
        view.refresh()
        _qapp().processEvents()
        disp_a1 = view._table._src_df  # objek display state A
        ctx.set_filter("jenis", ["WASTE"])
        view._refresh_table()
        _qapp().processEvents()
        assert view._table._src_df is not disp_a1
        ctx.set_filter("jenis", [])
        view._refresh_table()
        _qapp().processEvents()
        assert view._table._src_df is disp_a1  # ← inti LRU (cache fit kena)
        view.close()

    def test_nilai_centang_disegarkan_saat_objek_dipakai_ulang(self):
        # v2.19.0 — tampilan GRUP: kolom kunci = __FPS (tuple sidik jari
        # anggota grup), bukan __FP baris-tunggal. Centang semua grup =
        # masukkan SEMUA fp anggota semua grup (SATU broadcast).
        from ui.grouping import FPS_COL
        ctx, view = self._view()
        view.show()
        ctx.set_dataset(_df_synth(40), {"key_akhir": 31})
        view.refresh()
        _qapp().processEvents()
        m = view._table.model()
        disp = m.dataframe
        all_fps: list[str] = []
        for fps in disp[FPS_COL]:
            if isinstance(fps, tuple):
                all_fps.extend(str(f) for f in fps)
        ctx.add_followup_many(all_fps)
        _qapp().processEvents()
        assert m.dataframe is disp
        assert bool(disp[CHECK_COL].all())
        # keluarkan semua → ✓ False pada objek display YANG SAMA
        ctx.clear_followup()
        _qapp().processEvents()
        assert m.dataframe is disp
        assert not bool(disp[CHECK_COL].any())
        view.close()

    def test_data_ready_mengosongkan_cache_display(self):
        ctx, view = self._view()
        view.show()
        ctx.set_dataset(_df_synth(30), {"key_akhir": 31})
        view.refresh()
        _qapp().processEvents()
        old_disp = view._table._src_df
        ctx.set_dataset(_df_synth(30, seed=99), {"key_akhir": 31})
        _qapp().processEvents()
        # memo display dataset LAMA tak terpakai lagi (bersih — bukan
        # menumpuk); objek display baru ≠ lama; cache tak melebihi entri
        # state yang benar2 dipakai.
        assert view._table._src_df is not old_disp
        assert len(view._disp_cache) <= 2  # data_ready + filters_changed
        assert all(e[0]() is not None for e in view._disp_cache.values())
        assert all(e[1] is not old_disp
                   for e in view._disp_cache.values())  # identitas, bukan ==
        view.close()

    def test_fps_reindex_sama_dengan_md5_lokal(self):
        """Jalur cepat reindex dari memo penuh ≡ fingerprint md5 ulang."""
        ctx, view = self._view()
        df = _df_synth(50)
        ctx.set_dataset(df, {"key_akhir": 31,
                             "followup_fps": fingerprint_series(df)})
        subset = ctx.anomali_df()
        got = view._fps_for(subset)
        want = fingerprint_series(subset)
        assert list(got) == list(want)
        assert list(got.index) == list(subset.index)
        view.close()

    def test_fps_fallback_md5_bila_memo_tak_ada(self):
        ctx, view = self._view()
        ctx.set_dataset(_df_synth(30), {"key_akhir": 31})  # tanpa followup_fps
        subset = ctx.anomali_df()
        got = view._fps_for(subset)
        assert list(got) == list(fingerprint_series(subset))
        view.close()


# ============================================================
# 4. state.set_dataset — pickup followup_fps dari worker
# ============================================================

class TestFollowupFpsFromWorker:
    def test_set_dataset_menerima_fps_dari_summary(self):
        from ui.state import AppContext
        df = _df_synth(25)
        fps = fingerprint_series(df)
        ctx = AppContext({})
        ctx.set_dataset(df, {"key_akhir": 31, "followup_fps": fps})
        # memo = objek PERSIS dari worker (tanpa hitung ulang)
        assert ctx.fingerprints() is fps
        assert ctx._fp_version == ctx.data_version

    def test_tanpa_fps_bangun_malas_lalu_memo(self):
        from ui.state import AppContext
        df = _df_synth(25)
        ctx = AppContext({})
        ctx.set_dataset(df, {"key_akhir": 31})
        assert ctx._fp_series is None
        first = ctx.fingerprints()
        assert list(first) == list(fingerprint_series(df))
        assert ctx.fingerprints() is first  # memo stabil

    def test_fps_index_tak_cocok_diabaikan(self):
        from ui.state import AppContext
        df = _df_synth(25)
        fps_lain = fingerprint_series(_df_synth(10))
        ctx = AppContext({})
        ctx.set_dataset(df, {"key_akhir": 31, "followup_fps": fps_lain})
        assert ctx._fp_series is None  # index beda → tolak, bangun malas


# ============================================================
# 5. suspicious_days — ekuivalensi vektor vs oracle loop lama
# ============================================================

def _suspicious_days_oracle(df, fps):
    """Implementasi loop lama (pre-v2.12.1) — oracle ekuivalensi."""
    red, amber = {}, set()
    if len(df) == 0:
        return red, amber
    dcols = [c for c in (str(i) for i in range(1, 32)) if c in df.columns]
    if not dcols:
        return red, amber
    ters = pd.to_numeric(df["HARI TERSANGKA"], errors="coerce") \
        if "HARI TERSANGKA" in df.columns else None
    hmax = pd.to_numeric(df["HARI MAX"], errors="coerce") \
        if "HARI MAX" in df.columns else None
    avg = None
    for src in ("AVG AKTIF", "AVG"):
        if src in df.columns:
            avg = pd.to_numeric(df[src], errors="coerce")
            break
    vals = df[dcols].apply(pd.to_numeric, errors="coerce")
    for i in range(len(df)):
        fp = str(fps.iloc[i])
        rday = None
        for series in (ters, hmax):
            if series is None:
                continue
            try:
                v = series.iloc[i]
                if v == v and 1 <= float(v) <= 31:
                    rday = int(v)
                    break
            except (TypeError, ValueError):
                continue
        if rday is not None and str(rday) in dcols:
            red[fp] = rday
        base = None
        if avg is not None:
            b = avg.iloc[i]
            if b == b and b > 0:
                base = float(b)
        if base is not None:
            for c in dcols:
                v = vals.iloc[i][c]
                if v == v and v > 0 and float(v) >= 2.0 * base:
                    if int(c) != rday:
                        amber.add((fp, c))
    return red, amber


class TestSuspiciousDaysVektor:
    def _df_days(self, n=120, seed=3):
        rng = np.random.default_rng(seed)
        data = {"HARI TERSANGKA": rng.choice([pd.NA, 1, 7, 31, 0, 40, 2.0], n),
                "HARI MAX": rng.choice([pd.NA, 2, 9, 30, 31, 0], n),
                "AVG AKTIF": rng.choice([0.0, 1.0, 5.0, 12.5, pd.NA], n),
                "AVG": rng.choice([2.0, 8.0, pd.NA], n)}
        for d in range(1, 32):
            data[str(d)] = rng.choice([0, 1, 5, 11, 24, 30, -3, pd.NA], n)
        return pd.DataFrame(data)

    def test_ekuivalensi_oracle_data_acak(self):
        df = self._df_days()
        fps = fingerprint_series(df)
        assert suspicious_days(df, fps) == _suspicious_days_oracle(df, fps)

    def test_ekuivalensi_oracle_tanpa_tersangka(self):
        df = self._df_days(seed=11).drop(columns=["HARI TERSANGKA"])
        fps = fingerprint_series(df)
        assert suspicious_days(df, fps) == _suspicious_days_oracle(df, fps)

    def test_ekuivalensi_oracle_tanpa_avg_kolom(self):
        df = self._df_days(seed=5).drop(columns=["AVG AKTIF", "AVG"])
        fps = fingerprint_series(df)
        assert suspicious_days(df, fps) == _suspicious_days_oracle(df, fps)

    def test_ekuivalensi_oracle_sebagian_kolom_hari(self):
        df = self._df_days(seed=8).drop(columns=["31", "30"])
        fps = fingerprint_series(df)
        a = suspicious_days(df, fps)
        b = _suspicious_days_oracle(df, fps)
        assert a == b

    def test_tersangka_hari_tak_ada_di_kolom_tak_jadi_merah(self):
        # rday valid tapi kolom hari itu absen → TIDAK masuk red (tetap
        # mengecualikan hari itu dari amber — kontrak lama).
        df = pd.DataFrame({"HARI TERSANGKA": [31], "AVG": [1.0],
                           **{str(d): [0] for d in range(1, 31)}})
        fps = fingerprint_series(df)
        red, amber = suspicious_days(df, fps)
        assert red == {}
        assert amber == set()

    def test_input_list_fps_diterima(self):
        df = self._df_days(10)
        fps = fingerprint_series(df)
        a = suspicious_days(df, fps)
        b = suspicious_days(df, list(fps))
        assert a == b


# ============================================================
# 6. Tabel lebar — wrap mati + elide (konvensi tabel raksasa)
# ============================================================

class TestWideTableNoWrap:
    def _table(self):
        _qapp()
        from ui.widgets import DataTable
        return DataTable()

    def test_lebar_followup_wrap_mati(self):
        t = self._table()
        df = _df_synth(40)
        visible = [str(i) for i in range(1, 30)]  # 29 kolom tampak
        t.set_dataframe(df, visible_cols=visible)
        assert t._no_wrap is True
        assert t.wordWrap() is False
        assert t.textElideMode() == Qt.TextElideMode.ElideRight

    def test_sempit_anomali_wrap_nyala(self):
        t = self._table()
        df = _df_synth(40)
        t.set_dataframe(df, visible_cols=["NAMA RESTO", "NAMA BARANG",
                                          "TOTAL"])
        assert t._no_wrap is False
        assert t.wordWrap() is True

    def test_raksasa_baris_tetap_wrap_mati(self):
        t = self._table()
        df = _df_synth(3001)
        t.set_dataframe(df, visible_cols=["NAMA RESTO", "TOTAL"])
        assert t._no_wrap is True

    def test_refit_rows_noop_saat_wrap_mati(self):
        t = self._table()
        df = _df_synth(40)
        t.set_dataframe(df, visible_cols=[str(i) for i in range(1, 30)])
        h_before = [t.rowHeight(r) for r in range(10)]
        t._refit_rows()  # harus no-op (wrap mati — tak ada pengukuran)
        assert [t.rowHeight(r) for r in range(10)] == h_before


# ============================================================
# 7. Status bar — stylesheet hanya saat warna berganti
# ============================================================

class TestStatusColorCache:
    def test_setstylesheet_hanya_saat_warna_berubah(self):
        _qapp()
        from ui.app import MainWindow
        win = MainWindow()
        calls = []
        orig = win._lbl_status.setStyleSheet
        win._lbl_status.setStyleSheet = \
            lambda css: calls.append(css) or orig(css)
        try:
            win._on_status("memproses", "running")
            win._on_status("masih", "running")
            win._on_status("selesai", "done")
            win._on_status("oke", "done")
            win._on_status("lagi", "running")
        finally:
            win._lbl_status.setStyleSheet = orig
        # 3 perubahan warna (running→running→done→done→running) = 3 kali
        assert len(calls) == 3
        win.close()
