"""test_v21311.py — regresi v2.13.11 (Gelombang 2 deep audit:
KEJUJURAN ANGKA & FIRST-RUN).

Sumber temuan: /home/z/my-project/audit-ui-waste.md seksi 4 (P2) +
seksi 5 (P3 klaster B6/B7/B20/D23). Entry worklog WASTE-G2 (sesi asli,
commit 9913fd2 yang hilang pra-push) = SPESIFIKASI replikasi setia —
re-eksekusi WASTE-G2R.

Cakupan (9 klaster fix, 20 test):
[D4]×2   First-run: tab awal (Anomali) ter-render — label arah CTA ke
         Pipeline tampil SEKALI pasca-wiring (dulu currentChanged
         terpasang setelah addTab → tab 0 tak pernah on_shown → tabel
         kosong tanpa empty-state, terlihat hang) + empty-state SEMUA
         tab data mengarah ke Pipeline.
[D3]×2   Dua definisi anomali DILABELI: status bar "N baris • X
         berstatus non-Normal • Y prioritas+potensi • run HH:MM:SS"
         (angka prioritas+potensi ≡ semantik _build_summary) + label
         kartu Ringkasan Run "Total anomali (prioritas+potensi)".
[C1+C5]×2  (DIHAPUS v2.18.5 — KPI Scorecard: tab Scorecard Cabang
         & waste_anomaly/insights.py dibuang permintaan user.)
[C4]×2   (DIHAPUS v2.18.5 — label 💰 kartu Scorecard, idem.)
[C2]     Funnel lokal Follow Up direset saat dataset baru (pola
         Anomali/Hari; dulu menyangkut → tabel 0 baris senyap).
[B4]×2   Combo pembanding PRESERVE pilihan user by path (kunci identitas
         sama dgn _baseline_alive G1) pasca daftar file berubah; bulan
         terhapus → fallback default jujur.
[B3]×2   "N file pembanding gagal dimuat: <nama>" ≠ "belum ada file"
         (dulu instruksi salah arah saat semua file gagal dibaca).
[B6]     Baris status "⏳ belum dimuat" pasca-cancel (bukan "memuat…"
         selamanya).
[B7]     Label jumlah bulan dihitung ulang pasca-delete (dulu "✓ 2
         bulan aktif" basi menempel).
[B20]    Tambah file duplikat ditolak BERPESAN status.
[D2]×2   Export saat pipeline berjalan: question box "…hasil run
         SEBELUMNYA…" default No + "Export ditunda"; kontrak
         _pipeline_busy (worker banding sengaja tak dicek).
[D23]×2  Progress bar pasca-cancel/gagal reset 0 + label jujur.

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


def _wait_worker(view, app, timeout: float = 30.0) -> None:
    """Pompa event loop sampai worker banding selesai (pola v21310)."""
    t0 = time.perf_counter()
    while view._running and time.perf_counter() - t0 < timeout:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()


# ============================================================
# Fixture (pola test_v21310 — G1R)
# ============================================================

def _df_ayam() -> pd.DataFrame:
    """Dataset bulan berjalan: AYAM@R1 2 baris anomali + 2 Normal
    (prioritas 1 / perlu-review 1 / normal 2 — bahan D3 dua definisi)."""
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


def _wb_month(tmp_path: Path, month: str) -> Path:
    """Workbook pembanding 1 bulan (REKAP MENTAH; pola _wb_bulan_lalu
    v21310 — AYAM@R1 Handling day5=80, umum utk semua bulan)."""
    rows = []
    data = {str(d): 0.0 for d in range(1, 32)}
    data["5"] = 80.0
    rows.append({
        "SOURCE DATA": "WASTE BAHAN DAN PACKAGING", "JENIS": "WASTE",
        "KETERANGAN": "Handling", "NAMA BARANG": "AYAM",
        "NAMA RESTO": "R1", "SATUAN": "PCS",
        **data, "TOTAL": float(sum(data.values())),
    })
    out = tmp_path / f"REKAP MENTAH {month} 2026.xlsx"
    pd.DataFrame(rows).to_excel(out, sheet_name="REKAP MENTAH", index=False)
    return out


def _ctx_dataset(df, summary=None):
    from ui.state import AppContext
    ctx = AppContext({})
    ctx.set_dataset(df, summary if summary is not None
                    else {"key_akhir": 31})
    return ctx


def _view_periode_files(tmp_path, monkeypatch, months):
    """PeriodeView + N file pembanding termuat (worker SUNGGUHAN) +
    dataset AYAM (pola test_v2123/_view_periode v21310)."""
    from waste_anomaly import period_history as ph
    from ui.view_periode import PeriodeView
    app = _qapp()
    store = tmp_path / "history_files.json"
    monkeypatch.setattr(ph, "history_store_path", lambda: store)
    wbs = {}
    entries = []
    for m in months:
        wb = _wb_month(tmp_path, m)
        wbs[m] = wb
        entries.append({"path": str(wb), "label": None})
    ph.save_history_entries(entries, store)
    ctx = _ctx_dataset(_df_ayam())
    view = PeriodeView(ctx)
    view.show()
    _wait_worker(view, app)
    view._refresh_result()
    app.processEvents()
    return view, ctx, app, wbs


class TestD4FirstRun:
    def test_first_run_label_arah_terrender(self, tmp_path, monkeypatch):
        """D4: MainWindow baru (belum ada data) → label 'Belum ada data —
        buka tab Pipeline, pilih workbook, jalankan.' + tabel kosong.
        v2.17.0 rombak: tab 0 kini Pipeline (entry point), Anomali di tab 1
        — first-run TIDAK lagi mendarat di Anomali. Beralih ke tab Anomali
        → on_shown → refresh → empty-state ter-render (CTA arah Pipeline).
        Dulu: currentChanged terpasang SETELAH addTab → tab 0 tak pernah
        on_shown → tabel+label kosong tanpa CTA (terlihat hang; VLM QA
        konfirmasi layar first-run tanpa empty-state)."""
        import ui.app as ap
        monkeypatch.setattr(ap, "followup_path",
                            lambda: tmp_path / "followup.json")
        app = _qapp()
        win = ap.MainWindow()
        win.show()
        app.processEvents()
        # v2.17.0: first-run = Pipeline (tab 0); beralih ke Anomali (tab 1)
        # utk memicu on_shown → refresh → empty-state.
        win._tabs.setCurrentIndex(1)
        app.processEvents()
        anom = win._views[1][1]
        assert "Belum ada data" in anom._lbl_count.text(), (
            "label arah Anomali empty-state harus ter-render setelah tab "
            "dibuka (audit D4)")
        assert "Pipeline" in anom._lbl_count.text(), "CTA mengarah ke Pipeline"
        assert anom._table.model().rowCount() == 0
        assert anom._dirty is False, (
            "refresh harus sudah terjadi (bukan cuma dirty flag)")
        win.close()

    def test_empty_state_semua_tab_data_arah_pipeline(self, tmp_path,
                                                      monkeypatch):
        """D4 (verifikasi konsistensi): buka SEMUA tab data saat belum
        ada data → tiap tab punya pesan arah yang menyebut Pipeline
        (FollowUp/Hari/Scorecard/Periode — Pipeline sendiri = form,
        bukan view data)."""
        import ui.app as ap
        monkeypatch.setattr(ap, "followup_path",
                            lambda: tmp_path / "followup.json")
        app = _qapp()
        win = ap.MainWindow()
        win.show()
        app.processEvents()
        from PySide6.QtWidgets import QLabel
        names = [n for n, _ in win._views]
        for i in range(1, 5):  # Follow Up, Hari, Scorecard, Banding
            win._tabs.setCurrentIndex(i)
            app.processEvents()
            texts = [l.text() for l in win._views[i][1].findChildren(QLabel)]
            assert any("Pipeline" in t for t in texts), (
                f"tab '{names[i]}' tanpa CTA ke Pipeline saat data kosong")
        win.close()


# ============================================================
# [D3] Dua definisi anomali dilabeli
# ============================================================

class TestD3DuaDefinisi:
    def test_status_bar_dua_angka_dilabeli(self, tmp_path, monkeypatch):
        """D3: status bar kini DUA definisi BERLABEL — 'X berstatus
        non-Normal' + 'Y prioritas+potensi' — dan Y ≡ semantik
        _build_summary (anomali_count = prioritas+potensi; engine tak
        diubah). Dulu: '797 anomali' (non-Normal) vs kartu '399'
        (prioritas+potensi) tanpa pembeda."""
        import ui.app as ap
        from waste_anomaly.pipeline import _build_summary
        monkeypatch.setattr(ap, "followup_path",
                            lambda: tmp_path / "followup.json")
        app = _qapp()
        win = ap.MainWindow()
        win.show()
        app.processEvents()
        win.ctx.set_dataset(_df_ayam(), {"key_akhir": 31})
        app.processEvents()
        txt = win._lbl_perm.text()
        assert "4 baris" in txt
        assert "2 berstatus non-Normal" in txt, (
            "definisi 1 = semua baris non-Normal (Perlu Review + "
            "Prioritas Tinggi), harus dilabeli")
        assert "1 prioritas+potensi" in txt, (
            "definisi 2 = prioritas+potensi saja, harus dilabeli")
        assert "run " in txt
        # konsistensi dgn engine: anomali_count == prioritas+potensi
        sm = _build_summary(_df_ayam(), 31, [])
        assert sm["anomali_count"] == 1
        assert sm["anomali_count"] == sm["prioritas_count"] \
            + sm["potensi_count"]
        win.close()

    def test_ringkasan_run_label_anomali_prioritas_potensi(self):
        """D3: kartu 'Ringkasan Run' memberi label 'Total anomali
        (prioritas+potensi)' — bukan 'Total anomali' telanjang yang
        dibaca sama dgn hitungan non-Normal status bar."""
        from ui.view_pipeline import _SUMMARY_LABELS, PipelineView
        app = _qapp()
        assert _SUMMARY_LABELS["anomali_count"] == \
            "Total anomali (prioritas+potensi)"
        view = PipelineView(_ctx_dataset(_df_ayam()))
        view._render_summary({"anomali_count": 399,
                              "prioritas_count": 399})
        plain = view._summary.toPlainText()
        assert "Total anomali (prioritas+potensi)" in plain
        assert "399" in plain
        view.close()
        view.deleteLater()


# ============================================================
# [C1+C5] KPI Scorecard basi dibasmi
# ============================================================

class TestC2FunnelFollowUp:
    def test_dataset_baru_reset_funnel_followup(self):
        """C2: funnel lokal Follow Up (_hfilters) direset saat dataset
        baru — pola AnomaliView/HariView. Dulu view ini terlewat:
        nilai dataset lama menyangkut → apply_hfilter di atas data baru
        → tabel 0 baris SENYAP pasca ganti dataset."""
        from ui.view_followup import FollowUpView
        app = _qapp()
        ctx = _ctx_dataset(_df_ayam())
        view = FollowUpView(ctx)
        view.show()
        app.processEvents()
        view._on_header_filter("TOTAL", "TOTAL", [100.0])
        assert view._hfilters == {"TOTAL": [100.0]}, "premis: filter aktif"
        # dataset baru (data_ready → _on_data_ready)
        ctx.set_dataset(_df_ayam(), {"key_akhir": 31})
        app.processEvents()
        assert view._hfilters == {}, (
            "dataset baru harus me-reset funnel lokal Follow Up "
            "(audit C2 — tabel 0 baris senyap)")
        view.close()
        view.deleteLater()


# ============================================================
# [B4] Combo pembanding preserve pilihan user
# ============================================================

class TestB4PreserveCombo:
    def test_pilihan_user_preserve_pasca_daftar_berubah(self, tmp_path,
                                                         monkeypatch):
        """B4: user memilih Juli → file LAIN (Agustus) ditambah → combo
        diisi ulang TAPI pilihan Juli DIPERTAHANKAN (identitas path —
        kunci sama dgn _baseline_alive G1) + baseline tab Anomali ikut
        Juli. Dulu: rebuild selalu me-reset ke default Tipikal →
        baseline berganti senyap tiap daftar file berubah."""
        view, ctx, app, wbs = _view_periode_files(
            tmp_path, monkeypatch, ["JUNI", "JULI"])
        from ui.view_periode import _TYPICAL_KEY
        assert view._cb_b.currentData() == _TYPICAL_KEY, (
            "premis: 2 bulan → default Tipikal")
        # user memilih Juli (kronologis lama→baru: Juni sebelum Juli)
        idx = [i for i in range(view._cb_b.count())
               if isinstance(view._cb_b.itemData(i), dict)
               and view._cb_b.itemData(i).get("path") == str(wbs["JULI"])][0]
        view._cb_b.setCurrentIndex(idx)
        app.processEvents()
        assert ctx.banding_baseline.get("path") == str(wbs["JULI"]), (
            "premis: baseline mengikuti pilihan user")
        # file KETIGA ditambah (bulan lain) → daftar berubah
        wb_ags = _wb_month(tmp_path, "AGUSTUS")
        view._entries.append({"path": str(wb_ags), "label": None})
        view._start_worker()
        _wait_worker(view, app)
        view._refresh_result()
        app.processEvents()
        cur = view._cb_b.currentData()
        assert isinstance(cur, dict) and cur.get("path") == str(wbs["JULI"]), (
            "pilihan user harus DIPERTAHANKAN by path (audit B4) — "
            "bukan di-reset ke Tipikal")
        assert ctx.banding_baseline.get("path") == str(wbs["JULI"]), (
            "baseline tab Anomali konsisten dgn pilihan user (audit B4)")
        view.close()
        view.deleteLater()

    def test_bulan_terhapus_fallback_default(self, tmp_path, monkeypatch):
        """B4 (fallback): bulan yang DIPILIH user dihapus dari daftar →
        pilihan tak bisa dipulihkan → jatuh ke default jujur (Tipikal
        bila ada; bulan terbaru bila < 2 bulan)."""
        view, ctx, app, wbs = _view_periode_files(
            tmp_path, monkeypatch, ["JUNI", "JULI"])
        from ui.view_periode import _TYPICAL_KEY
        # user memilih Juni
        idx = [i for i in range(view._cb_b.count())
               if isinstance(view._cb_b.itemData(i), dict)
               and view._cb_b.itemData(i).get("path") == str(wbs["JUNI"])][0]
        view._cb_b.setCurrentIndex(idx)
        app.processEvents()
        assert ctx.banding_baseline.get("path") == str(wbs["JUNI"])
        # Juni dihapus (baris 0 di daftar file)
        view._tbl_files.selectRow(0)
        view._on_delete()
        app.processEvents()
        cur = view._cb_b.currentData()
        # 1 bulan tersisa → Tipikal tak tersedia → default = bulan TERBARU
        assert isinstance(cur, dict) and cur.get("path") == str(wbs["JULI"]), (
            "bulan terhapus → fallback bulan terbaru (Tipikal butuh ≥ 2 bulan)")
        assert cur != _TYPICAL_KEY
        assert ctx.banding_baseline.get("path") == str(wbs["JULI"])
        view.close()
        view.deleteLater()


# ============================================================
# [B3] Semua file gagal ≠ belum ada file
# ============================================================

class TestB3PesanGagal:
    def test_semua_file_gagal_instruksi_jujur(self, tmp_path, monkeypatch):
        """B3: file PEMBANDING ada tapi GAGAL dibaca → pesan 'N file
        pembanding gagal dimuat: <nama> — periksa kolom Status…', BUKAN
        'Belum ada file pembanding' (dulu instruksi salah arah: suruh
        menambah file padahal masalahnya gagal dibaca)."""
        from waste_anomaly import period_history as ph
        from ui.view_periode import PeriodeView
        app = _qapp()
        store = tmp_path / "history_files.json"
        monkeypatch.setattr(ph, "history_store_path", lambda: store)
        bad = tmp_path / "REKAP MENTAH JUNI 2026.xlsx"
        bad.write_bytes(b"ini bukan workbook excel - bytes sampah")
        ph.save_history_entries([{"path": str(bad), "label": None}], store)
        ctx = _ctx_dataset(_df_ayam())
        view = PeriodeView(ctx)
        view.show()
        _wait_worker(view, app)
        view._refresh_result()
        app.processEvents()
        txt = view._lbl_compare.text()
        assert "1 file pembanding gagal dimuat" in txt, (
            "semua file gagal → pesan gagal-dimuat (audit B3)")
        assert bad.name in txt, "nama file harus disebut (arah perbaikan)"
        assert "Status" in txt, "mengarah ke kolom Status / Muat Ulang"
        assert "Belum ada file pembanding" not in txt, (
            "pesan 'belum ada file' salah arah saat file ada tapi gagal")
        assert "1 file gagal" in view._lbl_status.text()
        view.close()
        view.deleteLater()

    def test_belum_ada_file_pesan_klasik(self, tmp_path, monkeypatch):
        """B3 (sisi lain): benar-benar belum ada file → pesan klasik
        'Belum ada file pembanding — tambahkan…' tetap dipakai."""
        from waste_anomaly import period_history as ph
        from ui.view_periode import PeriodeView
        app = _qapp()
        store = tmp_path / "history_files.json"
        monkeypatch.setattr(ph, "history_store_path", lambda: store)
        ph.save_history_entries([], store)
        ctx = _ctx_dataset(_df_ayam())
        view = PeriodeView(ctx)
        view.show()
        view._refresh_result()
        app.processEvents()
        txt = view._lbl_compare.text()
        assert "Belum ada file pembanding" in txt
        assert "gagal dimuat" not in txt
        view.close()
        view.deleteLater()


# ============================================================
# [B6] Baris status pasca-cancel
# ============================================================

class TestB6StatusPascaCancel:
    def test_cancel_baris_status_belum_dimuat(self, tmp_path, monkeypatch):
        """B6: cancel di tengah pemuatan → baris file kembali jujur
        '⏳ belum dimuat' (dulu '⏳ memuat…' menempel SELAMANYA karena
        _render_file_list tak pernah dipanggil di jalur cancel)."""
        view, ctx, app, _ = _view_periode_files(
            tmp_path, monkeypatch, ["JULI"])
        # simulasikan tengah pemuatan file berikutnya: hasil belum masuk
        view._last_results.clear()
        view._running = True
        view._render_file_list()
        assert view._tbl_files.item(0, 2).text() == "⏳ memuat…", (
            "premis: saat berjalan baris menampilkan 'memuat…'")
        view._on_failed("Pemuatan pembanding dibatalkan", "")
        app.processEvents()
        assert view._tbl_files.item(0, 2).text() == "⏳ belum dimuat", (
            "pasca-cancel baris harus jujur 'belum dimuat' (audit B6)")
        assert "dibatalkan" in view._lbl_status.text().lower()
        view.close()
        view.deleteLater()


# ============================================================
# [B7] Label jumlah bulan pasca-delete
# ============================================================

class TestB7LabelBulan:
    def test_label_bulan_dihitung_ulang_pasca_delete(self, tmp_path,
                                                      monkeypatch):
        """B7: '✓ 2 bulan pembanding aktif' → hapus satu file → label
        dihitung ulang '✓ 1 bulan…' (dulu label basi '2 bulan' menempel
        karena hanya _on_done yang meng-update)."""
        view, ctx, app, _ = _view_periode_files(
            tmp_path, monkeypatch, ["JUNI", "JULI"])
        assert "2 bulan pembanding aktif" in view._lbl_status.text(), (
            "premis: 2 bulan termuat")
        view._tbl_files.selectRow(0)  # Juni — entri pertama daftar
        view._on_delete()
        app.processEvents()
        assert view._lbl_status.text().startswith(
            "✓ 1 bulan pembanding aktif"), (
            "label jumlah bulan harus dihitung ulang pasca-delete "
            "(audit B7 — dulu basi '2 bulan')")
        assert len(view._entries) == 1
        view.close()
        view.deleteLater()


# ============================================================
# [B20] Duplikat ditolak berpesan
# ============================================================

class TestB20Duplikat:
    def test_tambah_duplikat_ditolak_berpesan(self, tmp_path, monkeypatch):
        """B20: menambah file yang SUDAH ada di daftar → ditolak dgn
        pesan status 'ℹ N file sudah ada di daftar pembanding — tidak
        ditambahkan dua kali: <nama>' (dulu ditolak SENYAP — user tak
        tahu kenapa file 'tidak masuk')."""
        from PySide6.QtWidgets import QFileDialog
        view, ctx, app, wbs = _view_periode_files(
            tmp_path, monkeypatch, ["JULI"])
        n_before = len(view._entries)
        monkeypatch.setattr(
            QFileDialog, "getOpenFileNames",
            lambda *a, **k: ([str(wbs["JULI"])], ""))
        view._on_add()
        app.processEvents()
        assert len(view._entries) == n_before, (
            "duplikat tidak boleh masuk dua kali")
        txt = view._lbl_status.text()
        assert "sudah ada di daftar pembanding" in txt, (
            "penolakan duplikat harus BERPESAN (audit B20)")
        assert "tidak ditambahkan dua kali" in txt
        assert wbs["JULI"].name in txt, "nama file disebut"
        assert not view._running, "tidak ada file baru → tanpa worker"
        view.close()
        view.deleteLater()


# ============================================================
# [D2] Export saat pipeline berjalan
# ============================================================

class TestD2ExportSaatRun:
    def _win(self, tmp_path, monkeypatch):
        import ui.app as ap
        monkeypatch.setattr(ap, "followup_path",
                            lambda: tmp_path / "followup.json")
        app = _qapp()
        win = ap.MainWindow()
        win.show()
        app.processEvents()
        win.ctx.set_dataset(_df_ayam(), {"key_akhir": 31})
        app.processEvents()
        return win, app

    def test_busy_question_default_no_export_ditunda(self, tmp_path,
                                                      monkeypatch):
        """D2: pipeline SEDANG berjalan + Export diklik → question box
        jujur '…data yang diekspor adalah hasil run SEBELUMNYA…
        Lanjutkan?' dgn tombol DEFAULT No (Enter salah = aman batal);
        jawab No → status 'Export ditunda' + TIDAK lanjut ke dialog
        file. Dulu: menyimpan data run lama tanpa keterangan."""
        from PySide6.QtWidgets import QMessageBox
        win, app = self._win(tmp_path, monkeypatch)
        pv = next(v for n, v in win._views if n == "Pipeline")
        pv._running = True  # run sedang berjalan
        captured = {}

        def fake_question(parent, title, text, buttons=None, default=None):
            captured["title"] = title
            captured["text"] = text
            captured["default"] = default
            return QMessageBox.StandardButton.No

        monkeypatch.setattr(QMessageBox, "question", fake_question)
        from PySide6.QtWidgets import QFileDialog

        def _no_file_dialog(*a, **k):
            raise AssertionError(
                "dialog file TIDAK boleh terbuka saat user menjawab No")

        monkeypatch.setattr(QFileDialog, "getSaveFileName", _no_file_dialog)
        win._export_excel()
        app.processEvents()
        assert captured, "question box harus muncul saat pipeline busy"
        assert "SEBELUMNYA" in captured["text"]
        assert "Lanjutkan?" in captured["text"]
        assert captured["default"] == QMessageBox.StandardButton.No, (
            "default harus No — Enter salah tidak mengekspor data lama")
        assert "Export ditunda" in win._lbl_status.text()
        assert win._export_worker is None, (
            "jawab No → tidak boleh ada export worker jalan")
        pv._running = False
        win.close()

    def test_pipeline_busy_kontrak_hanya_pipeline(self, tmp_path,
                                                   monkeypatch):
        """D2 (kontrak _pipeline_busy): HANYA run Pipeline yang mengganti
        ctx.df yang dihitung busy; HistoryWorker banding sengaja TIDAK
        dicek (export saat banding berjalan tetap sah — data df tak
        berubah)."""
        win, app = self._win(tmp_path, monkeypatch)
        pv = next(v for n, v in win._views if n == "Pipeline")
        bd = next(v for n, v in win._views if n == "Banding Periode")
        assert win._pipeline_busy() is False
        bd._running = True  # worker banding jalan → export tetap sah
        assert win._pipeline_busy() is False, (
            "worker banding tak mengganti ctx.df — bukan alasan tunda")
        pv._running = True
        assert win._pipeline_busy() is True
        pv._running = False
        bd._running = False
        win.close()


# ============================================================
# [D23] Progress pasca-cancel/gagal
# ============================================================

class TestD23ProgressPascaGagal:
    def _view(self):
        from ui.view_pipeline import PipelineView
        app = _qapp()
        view = PipelineView(_ctx_dataset(_df_ayam()))
        return view, app

    def test_on_failed_cancel_reset_progress_label(self, monkeypatch):
        """D23: cancel → progress bar kembali 0 + label status jujur
        '⏹ Dibatalkan — tidak ada hasil…' (dulu sisa % terakhir +
        pesan stage lama menempel selamanya)."""
        from PySide6.QtWidgets import QMessageBox
        monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
        view, app = self._view()
        view._progress.setValue(40)
        view._lbl_status.setText("⏳ Stage 05 — menghitung sinyal…")
        view._on_failed("Run dibatalkan pengguna", "")
        app.processEvents()
        assert view._progress.value() == 0, (
            "progress harus direset 0 pasca-cancel (audit D23)")
        assert "Dibatalkan" in view._lbl_status.text()
        assert "tidak ada hasil" in view._lbl_status.text()
        view.close()
        view.deleteLater()

    def test_on_failed_error_reset_progress_label(self, monkeypatch):
        """D23 (jalur gagal): error → progress 0 + label '⚠ Gagal: <err>'
        jujur (bukan sisa % + pesan stage terakhir)."""
        from PySide6.QtWidgets import QMessageBox
        monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: None)
        view, app = self._view()
        view._progress.setValue(67)
        view._lbl_status.setText("⏳ Stage 12 — quadrant…")
        view._on_failed("Workbook terkunci", "traceback-tidak-dipakai")
        app.processEvents()
        assert view._progress.value() == 0
        assert view._lbl_status.text().startswith("⚠ Gagal: Workbook terkunci")
        view.close()
        view.deleteLater()


# ============================================================
# CATATAN VERSI: pin 2.13.11 dilakukan di situs test LAMA (pola G1/G1R
# — test_v2136 ×6 baris + test_v2102:716 + test_v2139 + test_v270_wave4
# — test_v21310 tak memegang assert versi), TIDAK di file ini, supaya
# jumlah test baru tepat 20 (953 + 20 = 973 — kontrak worklog WASTE-G2).
# ============================================================
