"""view_pipeline.py — view 'Pipeline': jalankan analisa + log + ringkasan
+ editor threshold config (gabungan tab Run + Ringkasan + Config lama).

Worker = QThread (ui tidak freeze); tombol dua-mode Mulai↔Batalkan (F9);
log selalu terlihat (popup log lama dihapus — tidak ada tombol ganda).
"""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
    QLabel,
)

from .shared import APP_DIR, fmt_id
from .state import AppContext
from .widgets import Card, WLabel
from .workers import PipelineWorker

_SUMMARY_LABELS = {
    "total_rows": "Total baris",
    "anomali_count": "Total anomali",
    "prioritas_count": "Prioritas tinggi",
    "potensi_count": "Potensi anomali",
    "review_count": "Perlu review",
    "normal_count": "Normal",
    "cabang_count": "Jumlah cabang",
    "item_count": "Jumlah item",
    "key_akhir": "Key akhir (hari)",
    "timestamp": "Waktu run",
}


class PipelineView(QWidget):
    """Kontrol pipeline: input, parameter, run/cancel, progress, log, ringkasan."""

    # MainWindow memantau ini (tombol export global perlu tahu status run)
    run_state_changed = Signal(bool)

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._worker: PipelineWorker | None = None
        self._running = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        # ===== Card 1: Input workbook =====
        c1 = Card(self)
        l1 = QVBoxLayout(c1)
        l1.setContentsMargins(12, 10, 12, 10)
        l1.setSpacing(6)
        t = WLabel("Input Workbook", c1)
        t.setObjectName("cardTitle")
        l1.addWidget(t)
        row = QWidget(c1)
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(8)
        self._ent_workbook = QLineEdit(row)
        self._ent_workbook.setPlaceholderText("Pilih file Excel rekap (mis. DATA_WASTE.xlsx)")
        self._ent_workbook.returnPressed.connect(self._on_run_button)
        rl.addWidget(self._ent_workbook, 1)
        b_browse = QPushButton("Browse…", row)
        b_browse.clicked.connect(self._browse)
        rl.addWidget(b_browse)
        b_sample = QPushButton("Pakai Sample", row)
        b_sample.setToolTip("Isi kolom dengan DATA_WASTE.xlsx dari folder repo")
        b_sample.clicked.connect(self._use_sample)
        rl.addWidget(b_sample)
        l1.addWidget(row)
        lay.addWidget(c1)

        # ===== Card 2: Parameter + Kontrol =====
        c2 = Card(self)
        l2 = QVBoxLayout(c2)
        l2.setContentsMargins(12, 10, 12, 10)
        l2.setSpacing(6)
        t2 = WLabel("Parameter & Kontrol", c2)
        t2.setObjectName("cardTitle")
        l2.addWidget(t2)
        prow = QWidget(c2)
        pl = QHBoxLayout(prow)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(10)
        pl.addWidget(WLabel("Key Akhir (1–31):", prow))
        try:
            ka_default = int(self._ctx.config.get("default_key_akhir", 31))
        except (TypeError, ValueError):
            ka_default = 31
        if not (1 <= ka_default <= 31):
            ka_default = 31
        self._spin_ka = QSpinBox(prow)
        self._spin_ka.setRange(1, 31)
        self._spin_ka.setValue(ka_default)
        pl.addWidget(self._spin_ka)
        hint = WLabel("(hanya hari 1..N dianalisa — 14 stage pipeline dijalankan in-memory)", prow)
        hint.setObjectName("hint")
        pl.addWidget(hint, 1)
        l2.addWidget(prow)

        self._btn_run = QPushButton("▶ Mulai Pipeline", c2)
        self._btn_run.setObjectName("accent")
        self._btn_run.clicked.connect(self._on_run_button)
        l2.addWidget(self._btn_run)
        self._progress = QProgressBar(c2)
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        l2.addWidget(self._progress)
        self._lbl_status = WLabel("Siap. Pilih workbook lalu klik Mulai Pipeline.", c2)
        self._lbl_status.setObjectName("hint")
        l2.addWidget(self._lbl_status)
        lay.addWidget(c2)

        # ===== Card 3: Ringkasan + Log (splitter vertikal) =====
        c3 = Card(self)
        l3 = QVBoxLayout(c3)
        l3.setContentsMargins(12, 10, 12, 10)
        l3.setSpacing(6)
        t3 = WLabel("Ringkasan Run & Log Proses", c3)
        t3.setObjectName("cardTitle")
        l3.addWidget(t3)
        self._summary = QTextBrowser(c3)
        self._summary.setOpenExternalLinks(False)
        self._summary.setMaximumHeight(150)
        self._summary.setPlaceholderText("Ringkasan run akan tampil di sini setelah pipeline selesai.")
        l3.addWidget(self._summary)
        self._log = QPlainTextEdit(c3)
        self._log.setObjectName("log")
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(2000)
        self._log.setPlaceholderText("Log proses (14 stage) tampil di sini saat pipeline berjalan…")
        l3.addWidget(self._log, 1)
        lay.addWidget(c3, 1)

        # ===== Card 4: Threshold & Konfigurasi =====
        c4 = Card(self)
        l4 = QVBoxLayout(c4)
        l4.setContentsMargins(12, 10, 12, 10)
        l4.setSpacing(6)
        t4 = WLabel("Threshold & Konfigurasi (config.json)", c4)
        t4.setObjectName("cardTitle")
        l4.addWidget(t4)
        h4 = WLabel("Edit nilai threshold lalu Simpan — berlaku mulai run BERIKUTNYA.", c4)
        h4.setObjectName("hint")
        l4.addWidget(h4)
        scroll = QScrollArea(c4)
        scroll.setWidgetResizable(True)
        inner = QWidget()
        form_host = QWidget(inner)
        fl = QFormLayout(form_host)
        fl.setContentsMargins(4, 4, 4, 4)
        fl.setSpacing(4)
        fl.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self._config_vars: dict[str, QLineEdit] = {}
        for key, val in sorted(self._ctx.config.get("thresholds", {}).items()):
            ent = QLineEdit(str(val))
            ent.setMaximumWidth(140)
            lbl = QLabel(f"{key}:", form_host)
            lbl.setToolTip(key)
            fl.addRow(lbl, ent)
            self._config_vars[key] = ent
        btns = QWidget(inner)
        bl = QHBoxLayout(btns)
        bl.setContentsMargins(4, 8, 4, 4)
        bl.setSpacing(8)
        b_save = QPushButton("Simpan config.json", btns)
        b_save.setObjectName("accent")
        b_save.clicked.connect(self._save_config)
        bl.addWidget(b_save)
        b_reset = QPushButton("Reset Default", btns)
        b_reset.clicked.connect(self._reset_config)
        bl.addWidget(b_reset)
        bl.addStretch(1)
        inner_lay = QVBoxLayout(inner)
        inner_lay.setContentsMargins(0, 0, 0, 0)
        inner_lay.addWidget(form_host)
        inner_lay.addWidget(btns)
        inner_lay.addStretch(1)
        scroll.setWidget(inner)
        l4.addWidget(scroll, 1)
        lay.addWidget(c4, 1)

        # Log line dari ctx → panel log (worker progress juga lewat sini)
        ctx.log_line.connect(self._append_log)
        # Set split: ringkasan/log card mendapat ruang lebih besar
        lay.setStretch(2, 3)
        lay.setStretch(3, 2)

    # ------------------------------------------------------------
    # INPUT
    # ------------------------------------------------------------
    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Pilih Workbook Excel", str(APP_DIR),
            "Excel files (*.xlsx *.xlsm *.xls);;All files (*.*)")
        if path:
            self._ent_workbook.setText(path)

    def _use_sample(self) -> None:
        sample = APP_DIR / "DATA_WASTE.xlsx"
        if sample.exists():
            self._ent_workbook.setText(str(sample))
        else:
            QMessageBox.information(
                self, "Sample", "DATA_WASTE.xlsx tidak ditemukan di folder aplikasi.")

    def current_workbook(self) -> str:
        return self._ent_workbook.text().strip()

    def set_workbook(self, path: str) -> None:
        self._ent_workbook.setText(path)

    # ------------------------------------------------------------
    # RUN / CANCEL
    # ------------------------------------------------------------
    def _on_run_button(self) -> None:
        if self._running:
            self._cancel()
        else:
            self._start()

    def _start(self) -> None:
        if self._running:
            return
        wb = self.current_workbook()
        if not wb or not Path(wb).exists():
            QMessageBox.critical(self, "Input Error",
                                 "Workbook belum dipilih atau tidak ditemukan.")
            return
        ka = self._spin_ka.value()
        self._running = True
        self.run_state_changed.emit(True)
        self._btn_run.setText("⏹ Batalkan Run")
        self._btn_run.setObjectName("danger")
        self._btn_run.style().unpolish(self._btn_run)
        self._btn_run.style().polish(self._btn_run)
        self._progress.setValue(0)
        self._ctx.set_status("Memulai pipeline…", "running")
        self._ctx.log("=== Mulai Pipeline ===")
        self._ctx.log(f"Workbook: {wb} • Key Akhir: {ka} (in-memory)")

        self._worker = PipelineWorker(wb, ka, self)
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _cancel(self) -> None:
        if not self._running or self._worker is None:
            return
        self._worker.cancel()
        self._btn_run.setEnabled(False)
        self._ctx.set_status("⏹ Membatalkan run… (berhenti di gate stage berikutnya)", "running")
        self._ctx.log("=== Permintaan batal diterima — pipeline berhenti di gate antar-stage ===")

    def _finish_run(self) -> None:
        self._running = False
        self.run_state_changed.emit(False)
        self._btn_run.setEnabled(True)
        self._btn_run.setText("▶ Mulai Pipeline")
        self._btn_run.setObjectName("accent")
        self._btn_run.style().unpolish(self._btn_run)
        self._btn_run.style().polish(self._btn_run)
        self._worker = None

    def _on_progress(self, msg: str, pct: float) -> None:
        self._ctx.log(msg)
        self._progress.setValue(int(pct))
        self._lbl_status.setText(msg)

    def _on_done(self, summary: dict) -> None:
        self._finish_run()
        if not summary.get("success"):
            self._on_failed(summary.get("error", "Unknown error"), "")
            return
        self._progress.setValue(100)
        df = summary.get("df")
        rows = summary.get("total_rows", 0)
        self._ctx.set_status(f"✓ Pipeline selesai — {fmt_id(rows)} baris", "done")
        self._ctx.log("=== Selesai ===")
        self._ctx.log(f"Total baris: {rows}")
        self._ctx.log(f"Anomali prioritas: {summary.get('prioritas_count', 0)}")
        cfg_err = summary.get("config_load_error")
        if cfg_err:
            self._ctx.log(f"⚠ Config load error: {cfg_err} — threshold memakai default")
        self._lbl_status.setText(
            f"✓ Selesai — {fmt_id(rows)} baris • {fmt_id(summary.get('prioritas_count', 0))} prioritas")
        # Ringkasan run
        self._render_summary(summary)
        if df is not None and not df.empty:
            self._ctx.set_dataset(df, summary)
            QMessageBox.information(
                self, "Pipeline Selesai",
                f"Pipeline selesai!\n\nTotal baris: {fmt_id(rows)}\n"
                f"Anomali prioritas: {fmt_id(summary.get('prioritas_count', 0))}\n"
                f"Potensi anomali: {fmt_id(summary.get('potensi_count', 0))}\n\n"
                "Buka tab 'Anomali' untuk mulai memburu anomali.")

    def _on_failed(self, err: str, tb: str) -> None:
        self._finish_run()
        cancelled = (err == "Run dibatalkan pengguna")
        if cancelled:
            self._ctx.set_status("⏹ Run dibatalkan pengguna", "error")
            self._ctx.log("=== Run dibatalkan — hasil tidak dirender ===")
            QMessageBox.information(self, "Run Dibatalkan",
                                    "Run dibatalkan — hasil tidak dirender.")
        else:
            self._ctx.set_status(f"ERROR: {err}", "error")
            self._ctx.log(f"!!! ERROR: {err}")
            if tb:
                self._ctx.log(tb)
            QMessageBox.critical(self, "Pipeline Error", err)

    def _render_summary(self, summary: dict) -> None:
        rows = ["<table cellspacing='6'>"]
        for key, label in _SUMMARY_LABELS.items():
            val = summary.get(key)
            if val is None:
                continue
            rows.append(f"<tr><td style='color:#64748b;'>{label}</td>"
                        f"<td style='font-weight:600;'>{val}</td></tr>")
        rows.append("</table>")
        self._summary.setHtml("".join(rows))

    def _append_log(self, line: str) -> None:
        self._log.appendPlainText(line)

    # ------------------------------------------------------------
    # CONFIG
    # ------------------------------------------------------------
    def _save_config(self) -> None:
        target = APP_DIR / "waste_anomaly" / "config.json"
        if not target.parent.exists():  # frozen exe: sidecar di samping exe
            target = APP_DIR / "config.json"
        try:
            for key, ent in self._config_vars.items():
                text = ent.text().strip()
                try:
                    val = float(text)
                    val = int(val) if val == int(val) else val
                except ValueError:
                    val = text
                self._ctx.config.setdefault("thresholds", {})[key] = val
            tmp_path = target.with_suffix(".json.tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self._ctx.config, f, ensure_ascii=False, indent=2)
            tmp_path.replace(target)  # F2: atomic save
            self._ctx.set_status(f"✓ config.json tersimpan: {target}", "done")
            self._ctx.log(f"=== Threshold disimpan → {target} (berlaku mulai run berikutnya) ===")
            QMessageBox.information(self, "Config", f"config.json tersimpan:\n{target}")
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Config Error", f"Gagal menyimpan config:\n{e}")

    def _reset_config(self) -> None:
        from waste_anomaly.utils import _DEFAULT_CONFIG
        defaults = _DEFAULT_CONFIG.get("thresholds", {})
        for key, ent in self._config_vars.items():
            if key in defaults:
                ent.setText(str(defaults[key]))
        self._ctx.set_status("Form threshold dikembalikan ke default (belum disimpan)", "running")
