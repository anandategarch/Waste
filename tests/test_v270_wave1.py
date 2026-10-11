"""Test — regresi fix wave 1 v2.7.0 (app/state/workers/view_periode).

Mengunci perbaikan audit v2.6.x (FIX wave 1):
- V26-H3: ui.view_periode._RESULT_KEYS cocok dengan kunci asli hasil
  compare_periods ('branch'/'items') — dulu 'branch_summary'/'item_summary'
  → tab Cabang Mover & Item Mover Banding Periode selalu kosong.
- Regresi key_akhir pembanding (vs v2.5.1): hari aktif terbesar workbook
  pembanding dideteksi dari sheet mentah, bukan default 31 (v2.10.0:
  PeriodWorker → HistoryWorker; kontrak penerus di test_v2100.py).
- V26-H1: closeEvent meng-guard SEMUA worker (pipeline/export/banding
  periode) — jawab 'tidak' → close di-ignore; jawab 'ya' → cancel+wait.
- V26-H2: sidebar sinkron kembali setelah re-run (combo/search/chip
  kembali ke default saat ctx.set_dataset me-reset filter).
- V26-L11: _build_derived_sheets defensif — ANOMALY STATUS ada tapi
  ANOMALY SCORE absen → tidak raise; TOTAL/MAX string dijumlah numerik.
- Perf (audit Task ID 1): filtered_df() di-memo — cache hit + invalidasi.

Headless: QT_QPA_PLATFORM=offscreen diset SEBELUM import PySide6.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd

# Harus diset sebelum PySide6 di-import (dilakukan lazy di dalam test).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from waste_anomaly.period_compare import compare_periods

REPO = Path(__file__).resolve().parent.parent
SAMPLE_WB = REPO / "sample_workbook.xlsx"


def _ensure_app():
    """QApplication offscreen (sekali per proses — dipakai test UI)."""
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication(sys.argv)


def make_detail(rows: list[dict]) -> pd.DataFrame:
    """Frame Detail minimal: kolom kunci + TOTAL + ANOMALY STATUS."""
    base = {
        "NAMA RESTO": "1001.A",
        "NAMA BARANG": "ITEM X",
        "JENIS": "WASTE",
        "TOTAL": 0.0,
        "ANOMALY STATUS": "Normal",
    }
    return pd.DataFrame([{**base, **r} for r in rows])


# ============================================================
# FIX 1 (V26-H3) — kontrak _RESULT_KEYS vs compare_periods
# ============================================================

class TestResultKeys:
    def test_semua_kunci_ada_di_hasil_compare(self):
        """Setiap nilai _RESULT_KEYS harus jadi kunci dict hasil
        compare_periods — tab Banding Periode tidak lagi kosong."""
        from ui.view_periode import _RESULT_KEYS
        a = make_detail([{"NAMA RESTO": "R1", "NAMA BARANG": "I1", "TOTAL": 100.0}])
        b = make_detail([{"NAMA RESTO": "R1", "NAMA BARANG": "I1", "TOTAL": 150.0}])
        res = compare_periods(a, b)
        for tab_key, res_key in _RESULT_KEYS.items():
            assert res_key in res, (
                f"tab '{tab_key}' memakai kunci '{res_key}' yang tidak "
                f"ada di hasil compare_periods — tab selalu kosong (V26-H3)")
            assert isinstance(res[res_key], pd.DataFrame)

    def test_tab_mover_terisi_bukan_kosong(self):
        """Mover perubahan nyata → 'branch'/'items' tidak kosong."""
        from ui.view_periode import _RESULT_KEYS
        a = make_detail([
            {"NAMA RESTO": "R1", "NAMA BARANG": "I1", "TOTAL": 100.0},
            {"NAMA RESTO": "R2", "NAMA BARANG": "I1", "TOTAL": 100.0},
        ])
        b = make_detail([
            {"NAMA RESTO": "R1", "NAMA BARANG": "I1", "TOTAL": 60.0},
            {"NAMA RESTO": "R2", "NAMA BARANG": "I1", "TOTAL": 190.0},
        ])
        res = compare_periods(a, b)
        assert not res[_RESULT_KEYS["branch"]].empty
        assert not res[_RESULT_KEYS["items"]].empty


# ============================================================
# FIX 2 — PeriodWorker: pipeline B key_akhir terdeteksi (v2.7.0)
# ------------------------------------------------------------
# v2.10.0: PeriodWorker DIGANTI HistoryWorker (banding kini
# multi-file, jalur ringan kuantiti tanpa BOM — kontrak penerus
# deteksi key_akhir + cancel ada di test_v2100.py). Kelas & helper
# lama dihapus jujur bersama subjeknya (pola v2.8.1).
# ============================================================


# ============================================================
# FIX 3 (V26-H1) — closeEvent meng-guard semua worker
# ============================================================

class _StubWorker:
    """Stub worker: cancel + wait tercatat (tanpa QThread sungguhan)."""

    def __init__(self) -> None:
        self.cancelled = False
        self.wait_ms = 0

    def cancel(self) -> None:
        self.cancelled = True

    def wait(self, ms: int) -> bool:
        self.wait_ms = ms
        return True


class TestCloseEvent:
    def test_guard_periode_worker_batal_dan_setuju(self, monkeypatch):
        """Periode view _running → dialog; 'Tidak' → ignore; 'Ya' →
        cancel + wait(5000) tanpa exception."""
        _ensure_app()
        from PySide6.QtGui import QCloseEvent
        from PySide6.QtWidgets import QMessageBox
        from ui.app import MainWindow

        win = MainWindow()
        # v2.8.0: lookup berdasar NAMA (bukan indeks) — urutan view berubah
        # saat tab Uang/Peer/Kualitas Data dihapus (8 → 5).
        periode = next(v for _n, v in win._views if _n == "Banding Periode")
        stub = _StubWorker()
        periode._running = True
        periode._worker = stub  # type: ignore[assignment]
        try:
            # Jawab TIDAK → close di-ignore (jendela tetap)
            monkeypatch.setattr(
                QMessageBox, "question",
                staticmethod(lambda *a, **k: QMessageBox.StandardButton.No))
            ev = QCloseEvent()
            win.closeEvent(ev)
            assert not ev.isAccepted(), "jawab 'Tidak' → event harus di-ignore"
            assert not stub.cancelled

            # Jawab YA → worker dibatalkan + ditunggu, event diterima
            monkeypatch.setattr(
                QMessageBox, "question",
                staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
            ev2 = QCloseEvent()
            win.closeEvent(ev2)
            assert ev2.isAccepted()
            assert stub.cancelled, "worker banding periode harus di-cancel"
            assert stub.wait_ms == 5000
        finally:
            periode._running = False
            periode._worker = None
            win.close()

    def test_tanpa_proses_berjalan_langsung_tutup(self):
        """Tidak ada worker hidup → tidak ada dialog, event diterima."""
        _ensure_app()
        from PySide6.QtGui import QCloseEvent
        from ui.app import MainWindow

        win = MainWindow()
        ev = QCloseEvent()
        win.closeEvent(ev)
        assert ev.isAccepted()


# ============================================================
# FIX 4 (V26-H2) — state filter direset oleh set_dataset
# (v2.12.4: sidebar dihapus — kontrak turun ke level state: tanpa
# widget yang bisa berbohong, reset TETAP harus jujur utk funnel)
# ============================================================

class TestSidebarDesync:
    def test_widget_reset_setelah_set_dataset(self):
        """Re-run pipeline (set_dataset me-reset filter) → state filter
        kembali kosong (V26-H2 — dulu combo/search sidebar menampilkan
        filter lama padahal state None; kini funnel header membaca state
        langsung, kontraknya: set_dataset = reset total)."""
        _ensure_app()
        from ui.app import MainWindow

        df = pd.DataFrame({
            "NAMA RESTO": ["R1", "R1", "R2"],
            "NAMA BARANG": ["I1", "I2", "I1"],
            "JENIS": ["WASTE", "WASTE", "SUSUT"],
            "KETERANGAN": ["Expired", "Cancel Nota", "Expired"],
            "TOTAL": [10.0, 20.0, 30.0],
            "ANOMALY STATUS": ["Normal", "Prioritas Tinggi", "Normal"],
        })
        win = MainWindow()
        try:
            win.ctx.set_dataset(df.copy(), {"key_akhir": 31, "total_rows": 3})
            # Simulasi funnel kolom NAMA RESTO (drill-down path)
            win.ctx.set_filter("cabang", "R1")
            assert win.ctx.active_filters.get("cabang") == "R1"
            # Re-run pipeline → dataset baru (filter direset oleh state)
            win.ctx.set_dataset(df.copy(), {"key_akhir": 31, "total_rows": 3})
            # State harus jujur kembali kosong (V26-H2)
            assert win.ctx.active_filters.get("cabang") is None
            assert not any(win.ctx.active_filters.values()), (
                "set_dataset harus me-reset SEMUA filter (funnel tidak "
                "menampilkan filter basi)")
        finally:
            win.close()


# ============================================================
# FIX 5 (perf) — memo filtered_df
# ============================================================

class TestFilteredDfCache:
    def _make_ctx(self):
        from ui.state import AppContext
        return AppContext({"default_key_akhir": 31})

    def test_cache_hit_dan_invalidasi(self):
        """filtered_df() dua kali → objek sama (memo); setter filter dan
        set_dataset meng-invalidasi (hasil dihitung ulang)."""
        ctx = self._make_ctx()
        df = pd.DataFrame({
            "NAMA RESTO": ["R1", "R1", "R2", "R2"],
            "NAMA BARANG": ["I1", "I1", "I2", "I2"],
            "JENIS": ["WASTE"] * 4,
            "TOTAL": [1.0, 2.0, 3.0, 4.0],
        })
        ctx.set_dataset(df, {"key_akhir": 31, "total_rows": 4})

        ctx.set_filter("cabang", "R1")
        f1 = ctx.filtered_df()
        f2 = ctx.filtered_df()
        assert f1 is f2, "memo: panggilan kedua harus cache hit (objek sama)"
        assert len(f1) == 2  # perilaku filter tak berubah

        ctx.set_filter("cabang", "R2")
        f3 = ctx.filtered_df()
        assert f3 is not f1, "set_filter harus meng-invalidasi memo"
        assert len(f3) == 2
        assert set(f3["NAMA RESTO"]) == {"R2"}

        ctx.set_filter("item", "I9")  # tak ada match → invalidasi + kosong
        f4 = ctx.filtered_df()
        assert f4 is not f3
        assert f4.empty

        ctx.set_dataset(df, {"key_akhir": 31, "total_rows": 4})
        f5 = ctx.filtered_df()
        assert f5 is not f4, "set_dataset harus meng-invalidasi memo"
        assert len(f5) == 4  # filter sudah direset

    def test_perilaku_identik_dengan_filter_murni(self):
        """Hasil memo == _apply_filters langsung (perilaku dijaga)."""
        from ui.shared import _apply_filters
        ctx = self._make_ctx()
        df = pd.DataFrame({
            "NAMA RESTO": ["R1", "R2"],
            "HARI MAX": [5, 20],
            "TOTAL": [10.0, 20.0],
        })
        ctx.set_dataset(df, {"key_akhir": 31, "total_rows": 2})
        ctx.set_filter("cabang", "R1")
        got = ctx.filtered_df().reset_index(drop=True)
        want = _apply_filters(
            df, ctx.active_filters).reset_index(drop=True)
        pd.testing.assert_frame_equal(got, want)


# ============================================================
# FIX 7 (V26-L6) — hasil banding basi → v2.10.0: selalu segar otomatis
# ============================================================

class TestStaleResultMarker:
    def test_data_baru_hasil_banding_auto_segar(self):
        """v2.10.0 mengganti penanda 'hasil basi' (V26-L6): tabel banding
        kini SELALU dihitung ulang dari dataset terkini saat view dibuka /
        data_ready (render ~100 ms — tak ada lagi hasil lama yang menetap).
        Kontrak penerus: dataset baru → _dirty; on_shown → render ulang;
        TIDAK ada pesan basi (karena tidak mungkin basi)."""
        _ensure_app()
        from ui.app import MainWindow

        df = pd.DataFrame({
            "NAMA RESTO": ["R1"], "NAMA BARANG": ["I1"], "JENIS": ["WASTE"],
            "TOTAL": [10.0], "ANOMALY STATUS": ["Normal"],
        })
        win = MainWindow()
        try:
            pv = next(v for _n, v in win._views if _n == "Banding Periode")
            summary = {"key_akhir": 31, "total_rows": 1}
            win.ctx.set_dataset(df, summary)
            pv._has_result = True
            # v2.13.15 (gel-6 B13 — baris dihapus jujur): penugasan
            # pv._result_version pernah ada di sini untuk meniru state
            # sesuai-lama; field itu dead state (ditulis, tak pernah
            # dibaca) dan dihapus dari view_periode — penanda stale
            # tinggal _dirty + data_version (kontrak v2.10.0 utuh).
            pv._lbl_status.setText("✓ 2 bulan pembanding aktif.")
            # ganti tab → data sama → tanpa warning palsu
            pv.on_shown()
            assert "tidak lagi berlaku" not in pv._lbl_status.text()
            # re-run pipeline → dataset baru → ditandai dirty (bukan basi)
            win.ctx.set_dataset(df.copy(), summary)
            assert pv._dirty
            pv._refresh_result()
            # hasil banding otomatis mengikuti dataset baru — kontrak baru:
            assert "tidak lagi berlaku" not in pv._lbl_status.text()
        finally:
            win.close()
