"""test_v2195.py — tab Update nilai (staging koreksi batch).

Permintaan user: "bisa gak misal update nilai nya ke file rekap mentah
dikumpulin dulu terus baru proses dari pada proses satu per satu? Jadi
tombol simpan koreksi hari ke file excel diganti aja Pindah ke tab Update
nilai. Di tab update nilai itu buat tampung sementara nilai nilai yang
aku simpan dan akan diproses nanti nya."

Cover:
  [A] AppContext staging API — add/remove/clear/mark/count + signals
      (update_staged hanya saat add; updates_changed saat any change).
  [B] BatchUpdateWorker — proses SEMUA staging ke file Excel (loop per
      entry, backup=False). Sukses → done; gagal (file terkunci) → failed
      + batch lanjut; idempoten (entry 'done' di-skip).
  [C] DetailPanel._on_stage_edits — tombol "Pindah ke tab Update nilai"
      menampung koreksi ke ctx.pending_updates (BUKAN tulis Excel).
  [D] UpdateView — tabel staging refresh + hapus/kosongkan.
  [E] MainWindow — 6 tab (Update nilai index 5) + ctx.update_staged →
      pindah tab otomatis.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd  # noqa: F401  (dipakai fixture)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

REPO = Path(__file__).resolve().parent.parent


def _qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication(sys.argv)


def _suppress_msgbox(monkeypatch):
    """Monkeypatch SEMUA static QMessageBox (information/warning/critical/
    question) + instance exec() utk return langsung (anti modal hang di
    offscreen). Static C++ bypass instance exec-patch — semua harus
    di-patch eksplisit."""
    from PySide6.QtWidgets import QMessageBox
    SB = QMessageBox.StandardButton
    monkeypatch.setattr(QMessageBox, "information",
                        lambda *a, **kw: SB.Ok)
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *a, **kw: SB.Ok)
    monkeypatch.setattr(QMessageBox, "critical",
                        lambda *a, **kw: SB.Ok)
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **kw: SB.Yes)
    # Instance dialog (confirm = QMessageBox(self); confirm.exec()).
    monkeypatch.setattr(QMessageBox, "exec", lambda *a, **kw: SB.Yes)


def _make_sheet(tmp_path, name="REKAP MENTAH_TEST.xlsx") -> Path:
    """Workbook rekap mini: header + 1 baris data hari 1-5."""
    import openpyxl
    p = tmp_path / name
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "REKAP MENTAH"
    ws.append(["SOURCE DATA", "JENIS", "KETERANGAN", "NAMA BARANG",
               "NAMA RESTO", "SATUAN", 1, 2, 3, 4, 5])
    ws.append(["WASTE BAHAN DAN PACKAGING", "WASTE", "Cancel Nota",
               "AYAM", "R1", "GR", 10, 0, 0, 0, 0])
    wb.save(p)
    return p


# ============================================================
# [A] AppContext staging API
# ============================================================

class TestStagingApi:
    def _ctx(self):
        from ui.state import AppContext
        return AppContext({})

    def test_add_update_menampung_dan_pancar_sinyal(self):
        """add_update → pending_updates bertambah + pancar update_staged
        (hanya saat add) + updates_changed (any change)."""
        from PySide6.QtCore import QObject
        ctx = self._ctx()
        staged_n = {"n": 0}
        changed_n = {"n": 0}
        ctx.update_staged.connect(lambda: staged_n.__setitem__("n", staged_n["n"] + 1))
        ctx.updates_changed.connect(lambda: changed_n.__setitem__("n", changed_n["n"] + 1))
        assert ctx.pending_count() == 0
        idx = ctx.add_update({
            "source": "/tmp/rekap.xlsx", "src_rows": [2],
            "day_edits": {"5": 55.0}, "day_orig": {"5": 100.0},
            "label": "WASTE · AYAM · R1", "jenis": "WASTE",
            "barang": "AYAM", "resto": "R1"})
        assert idx == 0
        assert ctx.pending_count() == 1
        assert ctx.pending_updates[0]["day_edits"] == {"5": 55.0}
        assert ctx.pending_updates[0]["status"] == "pending"  # default
        assert ctx.pending_updates[0]["added_at"]  # timestamp terisi
        assert staged_n["n"] == 1, "update_staged pancar 1× saat add"
        assert changed_n["n"] == 1, "updates_changed pancar saat add"

    def test_update_staged_hanya_saat_add_bukan_remove(self):
        """update_staged dipancar HANYA add_update — BUKAN remove/clear
        (MainWindow pindah tab hanya saat koreksi baru ditampung)."""
        ctx = self._ctx()
        staged_n = {"n": 0}
        ctx.update_staged.connect(lambda: staged_n.__setitem__("n", staged_n["n"] + 1))
        ctx.add_update({"source": "x", "src_rows": [2],
                        "day_edits": {"5": 55.0}, "day_orig": {"5": 100.0}})
        assert staged_n["n"] == 1
        ctx.remove_update(0)  # remove → update_staged TIDAK boleh pancar
        assert staged_n["n"] == 1, "remove tak pancar update_staged"
        ctx.add_update({"source": "y", "src_rows": [3],
                        "day_edits": {"6": 1.0}, "day_orig": {"6": 0.0}})
        assert staged_n["n"] == 2, "add kedua pancar update_staged"
        ctx.clear_updates()  # clear → update_staged TIDAK boleh pancar
        assert staged_n["n"] == 2, "clear tak pancar update_staged"

    def test_remove_update_dan_clear(self):
        ctx = self._ctx()
        ctx.add_update({"source": "a", "src_rows": [2],
                        "day_edits": {"5": 1.0}, "day_orig": {"5": 0.0}})
        ctx.add_update({"source": "b", "src_rows": [3],
                        "day_edits": {"6": 2.0}, "day_orig": {"6": 0.0}})
        assert ctx.pending_count() == 2
        assert ctx.remove_update(0) is True
        assert ctx.pending_count() == 1
        assert ctx.pending_updates[0]["source"] == "b"  # index geser
        assert ctx.remove_update(99) is False  # out-of-range False
        n = ctx.clear_updates()
        assert n == 1
        assert ctx.pending_count() == 0

    def test_mark_status_dan_clear_processed(self):
        """mark_update_status → status berubah; clear_processed_updates
        buang HANYA 'done' (failed/pending tetap utk retry)."""
        ctx = self._ctx()
        ctx.add_update({"source": "a", "src_rows": [2],
                        "day_edits": {"5": 1.0}, "day_orig": {"5": 0.0}})
        ctx.add_update({"source": "b", "src_rows": [3],
                        "day_edits": {"6": 2.0}, "day_orig": {"6": 0.0}})
        ctx.add_update({"source": "c", "src_rows": [4],
                        "day_edits": {"7": 3.0}, "day_orig": {"7": 0.0}})
        ctx.mark_update_status(0, "done")
        ctx.mark_update_status(1, "failed", error="Excel terkunci")
        # idx 2 masih pending
        assert ctx.pending_updates[0]["status"] == "done"
        assert ctx.pending_updates[1]["status"] == "failed"
        assert ctx.pending_updates[1]["error"] == "Excel terkunci"
        assert ctx.pending_updates[2]["status"] == "pending"
        assert ctx.pending_unprocessed_count() == 2  # pending 1 + failed 1
        removed = ctx.clear_processed_updates()
        assert removed == 1  # hanya 'done' dibuang
        assert ctx.pending_count() == 2
        assert ctx.pending_updates[0]["status"] == "failed"  # tetap
        assert ctx.pending_updates[1]["status"] == "pending"  # tetap


# ============================================================
# [B] BatchUpdateWorker
# ============================================================

class TestBatchUpdateWorker:
    def _entry(self, source, row, day_edits, day_orig):
        return {
            "source": str(source), "src_rows": [row],
            "day_edits": dict(day_edits), "day_orig": dict(day_orig),
            "label": "test", "jenis": "WASTE", "barang": "AYAM",
            "resto": "R1", "status": "pending",
        }

    def _run_worker(self, ctx, entries):
        """Jalankan BatchUpdateWorker sinkron (run() langsung — signal
        direct-call di thread sama). Progress → mark_update_status."""
        from ui.workers import BatchUpdateWorker
        w = BatchUpdateWorker(entries, parent=None)
        results = {"ok": [], "fail": [], "done": None}

        def on_progress(idx, ok, msg):
            ctx.mark_update_status(
                idx, "done" if ok else "failed",
                error=None if ok else msg)
            (results["ok"] if ok else results["fail"]).append(idx)

        def on_done(n_ok, n_fail):
            results["done"] = (n_ok, n_fail)

        w.progress.connect(on_progress)
        w.done.connect(on_done)
        w.run()  # sinkron — signal direct-call (same thread)
        return results

    def test_batch_sukses_semua_entry_ditulis(self, tmp_path):
        """2 entry (file sama, baris berbeda) → SEMUA ditulis ke Excel;
        done(n_ok=2, n_fail=0); entry ber-status 'done'."""
        import openpyxl
        from ui.state import AppContext
        p = _make_sheet(tmp_path)
        ctx = AppContext({})
        # Tambah baris ke-2 utk entry kedua (baris 2 & 3).
        wb = openpyxl.load_workbook(str(p))
        ws = wb["REKAP MENTAH"]
        ws.append(["WASTE BAHAN DAN PACKAGING", "SUSUT", "Internal",
                   "BEBEK", "R2", "GR", 0, 0, 0, 0, 0])
        wb.save(p)
        wb.close()
        e1 = self._entry(p, 2, {"3": 55.0}, {"3": 0.0})
        e2 = self._entry(p, 3, {"1": 99.0}, {"1": 0.0})
        ctx.pending_updates = [e1, e2]
        res = self._run_worker(ctx, ctx.pending_updates)
        assert res["done"] == (2, 0)
        assert ctx.pending_updates[0]["status"] == "done"
        assert ctx.pending_updates[1]["status"] == "done"
        # Verifikasi nilai tertulis ke file Excel.
        wb = openpyxl.load_workbook(str(p), read_only=True, data_only=True)
        ws = wb["REKAP MENTAH"]
        rows = list(ws.iter_rows(min_row=2, max_row=3, values_only=True))
        wb.close()
        assert rows[0][8] == 55  # baris 2 hari 3 (index 8)
        assert rows[1][6] == 99  # baris 3 hari 1 (index 6)

    def test_batch_gagal_satu_lanjut_berikutnya(self, tmp_path, monkeypatch):
        """1 entry gagal (file terkunci — write_day_edits raise) + 1 entry
        sukses → batch TIDAK berhenti; done(n_ok=1, n_fail=1); failed tetap
        di staging utk retry."""
        import waste_anomaly.source_writer as sw
        from ui.state import AppContext
        p = _make_sheet(tmp_path)
        ctx = AppContext({})
        e1 = self._entry(p, 2, {"3": 55.0}, {"3": 0.0})
        e2 = self._entry(p, 2, {"4": 66.0}, {"4": 0.0})
        ctx.pending_updates = [e1, e2]
        real_write = sw.write_day_edits
        calls = {"n": 0}

        def flaky_write(source, row, day_edits, **kw):
            calls["n"] += 1
            if calls["n"] == 1:  # entry pertama gagal
                raise sw.SourceWriteError("Access denied (Excel terbuka)")
            return real_write(source, row, day_edits, **kw)

        monkeypatch.setattr(sw, "write_day_edits", flaky_write)
        # Worker lazy-import write_day_edits di run() — patch sw module.
        res = self._run_worker(ctx, ctx.pending_updates)
        assert res["done"] == (1, 1)
        assert ctx.pending_updates[0]["status"] == "failed"
        assert "Excel terbuka" in ctx.pending_updates[0]["error"]
        assert ctx.pending_updates[1]["status"] == "done"

    def test_batch_idempoten_skip_entry_done(self, tmp_path, monkeypatch):
        """Entry ber-status 'done' di-skip (write_day_edits TIDAK dipanggil
        ulang) — klik Proses ulang tak tulis ulang yg sukses."""
        import waste_anomaly.source_writer as sw
        from ui.state import AppContext
        p = _make_sheet(tmp_path)
        ctx = AppContext({})
        e_done = self._entry(p, 2, {"3": 55.0}, {"3": 0.0})
        e_done["status"] = "done"  # sudah sukses sebelumnya
        e_pending = self._entry(p, 2, {"4": 66.0}, {"4": 0.0})
        ctx.pending_updates = [e_done, e_pending]
        calls = {"n": 0}
        real_write = sw.write_day_edits

        def counting_write(source, row, day_edits, **kw):
            calls["n"] += 1
            return real_write(source, row, day_edits, **kw)

        monkeypatch.setattr(sw, "write_day_edits", counting_write)
        res = self._run_worker(ctx, ctx.pending_updates)
        assert res["done"] == (1, 0)  # hanya 1 diproses (pending)
        assert calls["n"] == 1, "entry 'done' tak boleh ditulis ulang"

    def test_batch_cancel_antar_entry(self, tmp_path, monkeypatch):
        """cancel() menghentikan batch ANTAR-entry (entry saat ini
        selesai, entry berikutnya di-skip)."""
        import waste_anomaly.source_writer as sw
        from ui.state import AppContext
        from ui.workers import BatchUpdateWorker
        p = _make_sheet(tmp_path)
        ctx = AppContext({})
        entries = [self._entry(p, 2, {str(d): float(d)}, {str(d): 0.0})
                   for d in range(1, 6)]  # 5 entry
        ctx.pending_updates = entries
        w = BatchUpdateWorker(entries, parent=None)
        results = {"done": None}

        def on_progress(idx, ok, msg):
            ctx.mark_update_status(idx, "done" if ok else "failed")
            if idx == 1:  # setelah entry ke-2 selesai → cancel
                w.cancel()

        def on_done(n_ok, n_fail):
            results["done"] = (n_ok, n_fail)

        w.progress.connect(on_progress)
        w.done.connect(on_done)
        w.run()
        ok, _fail = results["done"]
        # Entry 0 & 1 diproses; 2,3,4 di-skip (cancel setelah idx 1).
        assert ok == 2
        assert entries[0]["status"] == "done"
        assert entries[1]["status"] == "done"
        assert entries[2]["status"] == "pending"  # tak tersentuh


# ============================================================
# [C] DetailPanel._on_stage_edits
# ============================================================

class TestDetailPanelStage:
    def test_stage_edits_tampung_ke_pending(self, tmp_path, monkeypatch):
        """Klik 'Pindah ke tab Update nilai' → koreksi ditampung ke
        ctx.pending_updates (BELUM tulis Excel); entry berisi source,
        src_rows, day_edits, day_orig, label dari record."""
        _qapp()
        from PySide6.QtWidgets import QMessageBox
        from ui.state import AppContext
        from ui.view_anomali import DetailPanel
        src_path = str(tmp_path / "REKAP MENTAH_TEGAR.xlsx")
        ctx = AppContext({})
        ctx.summary = {"workbook_path": src_path}
        rec = pd.Series({
            "NAMA RESTO": "R1", "NAMA BARANG": "AYAM", "JENIS": "WASTE",
            "__SRC_ROW": 5, "ANOMALY STATUS": "Normal", "ANOMALY SCORE": 0,
        })
        panel = DetailPanel(ctx)
        panel.show_record(rec)
        # Inject day_edits + day_orig (spinbox mock) — simulate user ubah hari 5.
        class FakeSP:
            def __init__(self, v): self._v = v
            def value(self): return self._v
            def setEnabled(self, b): pass
        panel._day_orig = {"5": 100.0}
        panel._day_edits = {"5": FakeSP(55.0)}
        # Auto-confirm semua dialog (information/warning/critical/question/exec).
        _suppress_msgbox(monkeypatch)
        panel._on_stage_edits()
        # Koreksi ditampung ke staging.
        assert ctx.pending_count() == 1
        e = ctx.pending_updates[0]
        assert e["source"] == src_path
        assert e["src_rows"] == [5]
        assert e["day_edits"] == {"5": 55.0}
        assert e["day_orig"] == {"5": 100.0}
        assert e["jenis"] == "WASTE"
        assert e["barang"] == "AYAM"
        assert e["resto"] == "R1"
        assert e["status"] == "pending"
        panel.deleteLater()

    def test_stage_edits_folder_temp_ditolak(self, tmp_path, monkeypatch):
        """File folder-temp (SEMENTERA) → stage ditolak dgn pesan; staging
        tetap kosong (anti simpan ke file temp)."""
        _qapp()
        from PySide6.QtWidgets import QMessageBox
        from ui.state import AppContext
        from ui.view_anomali import DetailPanel, _FOLDER_TEMP_PREFIX
        ctx = AppContext({})
        ctx.summary = {"workbook_path": f"/tmp/{_FOLDER_TEMP_PREFIX}xyz.xlsx"}
        rec = pd.Series({"NAMA RESTO": "R1", "NAMA BARANG": "Y",
                         "__SRC_ROW": 5, "ANOMALY STATUS": "Normal",
                         "ANOMALY SCORE": 0})
        panel = DetailPanel(ctx)
        panel.show_record(rec)
        # Tombol harus DISABLED (folder temp) — klik tak picu staging.
        assert panel._save_btn.isEnabled() is False
        # Auto-confirm info dialog (folder-temp guard pakai static information).
        _suppress_msgbox(monkeypatch)
        panel._on_stage_edits()
        assert ctx.pending_count() == 0  # tak ada yg ditampung
        panel.deleteLater()


# ============================================================
# [D] UpdateView
# ============================================================

class TestUpdateView:
    def test_refresh_menampilkan_baris_staging(self):
        """ctx.add_update → UpdateView.refresh menampilkan baris dgn
        kolom file/item/resto/hari/status."""
        _qapp()
        from ui.state import AppContext
        from ui.view_update import UpdateView
        ctx = AppContext({})
        view = UpdateView(ctx)
        try:
            assert view._table.rowCount() == 0
            ctx.add_update({
                "source": "/tmp/REKAP MENTAH_TEGAR.xlsx", "src_rows": [5],
                "day_edits": {"5": 55.0}, "day_orig": {"5": 100.0},
                "jenis": "WASTE", "barang": "AYAM", "resto": "R1",
            })
            # updates_changed memicu refresh (connected di __init__).
            _qapp().processEvents()
            assert view._table.rowCount() == 1
            # Kolom File = nama file saja.
            assert view._table.item(0, 1).text() == "REKAP MENTAH_TEGAR.xlsx"
            # Kolom Item = "WASTE · AYAM".
            assert "AYAM" in view._table.item(0, 2).text()
            # Kolom Status = "⏳ Pending".
            assert "Pending" in view._table.item(0, 6).text()
        finally:
            view.deleteLater()

    def test_info_label_dan_enabled_state(self):
        """Info label: total/pending/done/failed; tombol Proses disabled
        saat tidak ada pending."""
        _qapp()
        from ui.state import AppContext
        from ui.view_update import UpdateView
        ctx = AppContext({})
        view = UpdateView(ctx)
        try:
            # Kosong → Proses disabled.
            assert view._btn_process.isEnabled() is False
            ctx.add_update({"source": "/tmp/a.xlsx", "src_rows": [2],
                            "day_edits": {"5": 1.0}, "day_orig": {"5": 0.0}})
            _qapp().processEvents()
            assert view._btn_process.isEnabled() is True  # ada pending
            # Tandai done → Proses disabled lagi (tak ada pending/failed).
            ctx.mark_update_status(0, "done")
            _qapp().processEvents()
            assert view._btn_process.isEnabled() is False
        finally:
            view.deleteLater()


# ============================================================
# [E] MainWindow integration
# ============================================================

class TestMainWindowUpdateTab:
    def test_tab_update_nilai_ada_index_5(self):
        """MainWindow punya 6 tab; tab 'Update nilai' di index 5;
        _update_view adalah UpdateView."""
        _qapp()
        from ui.app import MainWindow
        from ui.view_update import UpdateView
        win = MainWindow()
        try:
            assert win._tabs.count() == 6
            assert win._tabs.tabText(5).split(" (")[0] == "Update nilai"
            assert isinstance(win._update_view, UpdateView)
        finally:
            win.close()
            win.deleteLater()

    def test_update_staged_pindah_tab_otomatis(self):
        """ctx.update_staged (koreksi ditampung) → MainWindow pindah tab
        ke 'Update nilai' (index 5)."""
        _qapp()
        from ui.app import MainWindow
        win = MainWindow()
        try:
            assert win._tabs.currentIndex() == 0  # Pipeline (first-run)
            win.ctx.add_update({
                "source": "/tmp/x.xlsx", "src_rows": [2],
                "day_edits": {"5": 1.0}, "day_orig": {"5": 0.0}})
            _qapp().processEvents()
            assert win._tabs.currentIndex() == 5, (
                "update_staged harus pindah ke tab Update nilai (idx 5)")
        finally:
            win.close()
            win.deleteLater()
