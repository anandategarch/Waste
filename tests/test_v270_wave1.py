"""Test — regresi fix wave 1 v2.7.0 (app/state/workers/view_periode).

Mengunci perbaikan audit v2.6.x (FIX wave 1):
- V26-H3: ui.view_periode._RESULT_KEYS cocok dengan kunci asli hasil
  compare_periods ('branch'/'items') — dulu 'branch_summary'/'item_summary'
  → tab Cabang Mover & Item Mover Banding Periode selalu kosong.
- Regresi key_akhir PeriodWorker (vs v2.5.1): pipeline periode B harus
  menerima hari aktif terbesar workbook B (deteksi sheet mentah), bukan
  default 31 → sinyal S11 (LAST DAY SHARE) hidup untuk periode B.
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
import pytest

# Harus diset sebelum PySide6 di-import (dilakukan lazy di dalam test).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from waste_anomaly.period_compare import compare_periods
from waste_anomaly.pipeline import run_pipeline

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
# FIX 2 — PeriodWorker: pipeline B dengan key_akhir terdeteksi
# ============================================================

def _build_workbook_hari20(tmp_path: Path) -> Path:
    """Workbook periode B dari sample_workbook.xlsx, hari 21..31 dikosongkan
    (data berhenti di hari 20) + satu baris di-spike di hari 20 (S11)."""
    rekap = pd.read_excel(SAMPLE_WB, sheet_name="DATA_WASTE")
    day_cols = [c for c in rekap.columns
                if str(c).strip().isdigit() and 21 <= int(str(c)) <= 31]
    for c in day_cols:
        rekap[c] = 0.0
    # Spike hari ke-20 (hari aktif TERAKHIR) — S11 LAST DAY SHARE harus
    # punya nilai > 0 untuk baris ini saat pipeline B jalan dengan ka=20.
    rekap.loc[0, "20"] = 60.0
    all_days = [c for c in rekap.columns if str(c).strip().isdigit()]
    rekap["TOTAL"] = rekap[all_days].sum(axis=1)
    out = tmp_path / "wb_periode_b_hari20.xlsx"
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        rekap.to_excel(writer, sheet_name="DATA_WASTE", index=False)
        pd.read_excel(SAMPLE_WB, sheet_name="BOM").to_excel(
            writer, sheet_name="BOM", index=False)
        pd.read_excel(SAMPLE_WB, sheet_name="DATABASE_SATUAN").to_excel(
            writer, sheet_name="DATABASE_SATUAN", index=False)
    return out


class TestPeriodWorkerKeyAkhir:
    @pytest.fixture()
    def df_a(self) -> pd.DataFrame:
        """Periode A: pipeline sample penuh (31 hari)."""
        summary = run_pipeline(str(SAMPLE_WB), key_akhir=31)
        assert summary.get("success"), summary.get("error")
        return summary["df"]

    def test_pipeline_b_menerima_key_akhir_terdeteksi_bukan_31(
            self, df_a, tmp_path, monkeypatch):
        """Bukti regresi: pre-fix run_pipeline dipanggil key_akhir=None →
        di-resolve 31 → S11 periode B mati. Fix → deteksi mentah = 20."""
        _ensure_app()
        from ui import workers as ui_workers
        from ui.workers import PeriodWorker

        wb_b = _build_workbook_hari20(tmp_path)
        captured: dict = {}
        orig = ui_workers.run_pipeline

        def spy(*args, **kwargs):
            captured["key_akhir"] = kwargs.get("key_akhir")
            summary = orig(*args, **kwargs)
            captured["summary"] = summary
            return summary

        monkeypatch.setattr(ui_workers, "run_pipeline", spy)

        results: list[dict] = []
        failures: list[tuple[str, str]] = []
        worker = PeriodWorker(df_a, str(wb_b), 31)
        worker.done.connect(results.append)
        worker.failed.connect(lambda err, tb: failures.append((err, tb)))
        worker.run()  # sinkron — QThread.run() boleh dipanggil langsung

        assert not failures, f"worker gagal: {failures[0]}"
        assert results, "signal done tidak terpicu"
        # run_pipeline periode B menerima hari terdeteksi (20), bukan None/31
        assert captured["key_akhir"] == 20
        # summary pipeline B memakai ka yang sama (S11 vs hari 20, bukan 31)
        assert captured["summary"].get("key_akhir") == 20
        # hasil banding memakai ka_b konsisten
        assert results[0]["key_akhir_b"] == 20
        # S11 hidup: kolom LAST DAY SHARE ada & spike hari 20 terhitung
        df_b = captured["summary"].get("df")
        assert "LAST DAY SHARE" in df_b.columns
        assert float(df_b["LAST DAY SHARE"].max()) > 0

    def test_cancel_worker_banding(self, df_a, tmp_path, monkeypatch):
        """V26-L5: cancel() sebelum pipeline → failed 'dibatalkan pengguna',
        pipeline B TIDAK dijalankan."""
        _ensure_app()
        from ui import workers as ui_workers
        from ui.workers import PeriodWorker

        wb_b = _build_workbook_hari20(tmp_path)
        called: list[bool] = []
        monkeypatch.setattr(ui_workers, "run_pipeline",
                            lambda *a, **k: called.append(True) or {})

        failures: list[tuple[str, str]] = []
        results: list[dict] = []
        worker = PeriodWorker(df_a, str(wb_b), 31)
        worker.done.connect(results.append)
        worker.failed.connect(lambda err, tb: failures.append((err, tb)))
        worker.cancel()
        worker.run()
        assert not called, "pipeline B tidak boleh dijalankan setelah cancel"
        assert results == []
        assert failures and failures[0][0] == "Perbandingan dibatalkan pengguna"


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
        periode = win._views[6][1]  # ("Banding Periode", PeriodeView)
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
# FIX 4 (V26-H2) — sidebar sinkron setelah re-run
# ============================================================

class TestSidebarDesync:
    def test_widget_reset_setelah_set_dataset(self):
        """Re-run pipeline (set_dataset me-reset filter) → combo cabang
        '(Semua)', kotak cari kosong, chip default — widget tidak lagi
        menampilkan filter lama padahal state None."""
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
            # Simulasi user: pilih cabang + ketik pencarian
            win._cb_cabang.setCurrentText("R1")
            win._ent_search.setText("exp")
            win._apply_search_now()  # flush debounce 300ms
            assert win.ctx.active_filters.get("cabang") == "R1"
            assert win.ctx.search == "exp"
            # Re-run pipeline → dataset baru (filter direset oleh state)
            win.ctx.set_dataset(df.copy(), {"key_akhir": 31, "total_rows": 3})
            # Sidebar harus jujur kembali (V26-H2)
            assert win._cb_cabang.currentText() == "(Semua)"
            assert win._ent_search.text() == ""
            assert win._lbl_chips.text() == "Tidak ada filter aktif."
            assert win.ctx.active_filters.get("cabang") is None
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
        """filtered_df() dua kali → objek sama (memo); setter filter/
        search dan set_dataset meng-invalidasi (hasil dihitung ulang)."""
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

        ctx.set_search("zzz")  # tidak ada match → invalidasi + kosong
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
            df, ctx.active_filters, day_min=None, day_max=None,
            search=ctx.search).reset_index(drop=True)
        pd.testing.assert_frame_equal(got, want)


# ============================================================
# FIX 7 (V26-L6) — penanda hasil banding basi
# ============================================================

class TestStaleResultMarker:
    def test_data_baru_menandai_basi_dan_ganti_tab_tidak(self):
        """Re-run periode A setelah banding → status 'tidak lagi berlaku';
        sekadar ganti tab (on_shown, data sama) TIDAK boleh warning palsu."""
        _ensure_app()
        from ui.app import MainWindow

        df = pd.DataFrame({
            "NAMA RESTO": ["R1"], "NAMA BARANG": ["I1"], "JENIS": ["WASTE"],
            "TOTAL": [10.0], "ANOMALY STATUS": ["Normal"],
        })
        win = MainWindow()
        try:
            pv = win._views[6][1]  # PeriodeView
            summary = {"key_akhir": 31, "total_rows": 1}
            win.ctx.set_dataset(df, summary)
            # simulasi hasil banding selesai (state seperti _on_done)
            pv._has_result = True
            pv._result_version = win.ctx.data_version
            pv._lbl_status.setText("✓ Selesai — periode B: X (key_akhir 31).")
            # ganti tab → on_shown → data TIDAK berubah → tanpa warning palsu
            pv.on_shown()
            assert "tidak lagi berlaku" not in pv._lbl_status.text()
            # re-run pipeline → dataset baru → hasil di atas basi
            win.ctx.set_dataset(df.copy(), summary)
            assert "tidak lagi berlaku" in pv._lbl_status.text()
        finally:
            win.close()


# ============================================================
# FIX 6 (V26-L11) — _build_derived_sheets defensif
# ============================================================

class TestDerivedSheets:
    def test_anomali_prioritas_tanpa_anomaly_score(self):
        """ANOMALY STATUS ada tapi ANOMALY SCORE absen → tidak raise,
        sheet 'Anomali Prioritas' kosong (pre-fix: KeyError sort_values)."""
        from ui.state import _build_derived_sheets
        df = pd.DataFrame({
            "NAMA RESTO": ["A", "B"],
            "NAMA BARANG": ["I1", "I2"],
            "JENIS": ["WASTE", "SUSUT"],
            "ANOMALY STATUS": ["Prioritas Tinggi", "Normal"],
        })
        sheets = _build_derived_sheets(df)  # tidak boleh raise
        assert sheets["Anomali Prioritas"].empty

    def test_per_cabang_total_string_dijumlah_numerik(self):
        """TOTAL/MAX dtype object (string) → dijumlah NUMERIK (pre-fix:
        'sum' object menggabungkan teks '1020')."""
        from ui.state import _build_derived_sheets
        df = pd.DataFrame({
            "NAMA RESTO": ["A", "A", "B"],
            "NAMA BARANG": ["I1", "I1", "I2"],
            "JENIS": ["WASTE", "WASTE", "SUSUT"],
            "TOTAL": ["10", "20", "5"],
            "MAX": ["5", "3", "2"],
            "ANOMALY STATUS": ["Normal", "Normal", "Normal"],
        })
        sheets = _build_derived_sheets(df)
        pc = sheets["Per Cabang"].set_index("Cabang")
        assert pc.loc["A", "Total_Waste"] == 30.0  # 10+20, bukan "1020"
        assert pc.loc["A", "Max_Waste_Harian"] == 5.0
        ti = sheets["Top Items"].set_index("NAMA BARANG")
        assert ti.loc["I1", "Total_Waste"] == 30.0
        assert ti.loc["I2", "Total_Waste"] == 5.0
